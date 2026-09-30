"""Flight offer providers. Each returns a list of normalized offers:
{id, total, per_person, seats, summary}  -- only offers that fit ALL passengers.

Key trick: we ask the API for `adults=N`. The airline only returns offers where N
seats are bookable together on the same flights & fare, so we never have to
search per-seat or split the group.
"""
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

HOSTS = {"test": "https://test.api.amadeus.com", "production": "https://api.amadeus.com"}


class ProviderError(Exception):
    def __init__(self, msg, fatal=False):
        super().__init__(msg)
        self.fatal = fatal  # fatal = don't burn more calls (auth/quota errors)


def normalize(offer, passengers, currency=None):
    """Return normalized offer, or None if it can't seat the whole group."""
    seats = offer.get("numberOfBookableSeats")
    tp = offer.get("travelerPricing") or []
    if seats is not None and seats < passengers:
        return None
    if tp and len(tp) != passengers:
        return None
    total = float(offer["price"]["grandTotal"])
    legs = []
    for it in offer.get("itineraries", []):
        segs = it["segments"]
        legs.append(f'{segs[0]["departure"]["iataCode"]} {segs[0]["departure"]["at"][:16]}'
                    f'->{segs[-1]["arrival"]["iataCode"]} {segs[-1]["arrival"]["at"][:16]}'
                    f' ({len(segs) - 1} stops, {"+".join(s["carrierCode"] + s["number"] for s in segs)})')
    return {"id": str(offer["id"]), "total": total, "per_person": round(total / passengers, 2),
            "seats": seats if seats is not None else passengers, "summary": " | ".join(legs)}


class Amadeus:
    def __init__(self, cfg, db):
        self.cfg, self.db = cfg, db
        self.host = HOSTS[cfg.amadeus_env]
        import os
        self.key, self.secret = os.environ.get("AMADEUS_API_KEY"), os.environ.get("AMADEUS_API_SECRET")
        if not (self.key and self.secret):
            raise ProviderError("set AMADEUS_API_KEY and AMADEUS_API_SECRET", fatal=True)

    def _http(self, req):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "replace")
            fatal = e.code in (401, 403, 429)
            raise ProviderError(f"HTTP {e.code}: {body}", fatal=fatal)
        except (urllib.error.URLError, TimeoutError) as e:
            raise ProviderError(f"network: {e}")

    def _token(self):
        """OAuth token is reused until shortly before it expires (never re-fetched needlessly)."""
        tok, exp = self.db.get("token"), float(self.db.get("token_exp") or 0)
        if tok and time.time() < exp - 60:
            return tok
        data = urllib.parse.urlencode({"grant_type": "client_credentials",
                                       "client_id": self.key, "client_secret": self.secret}).encode()
        j = self._http(urllib.request.Request(self.host + "/v1/security/oauth2/token", data=data))
        self.db.put("token", j["access_token"])
        self.db.put("token_exp", str(time.time() + int(j.get("expires_in", 1799))))
        return j["access_token"]

    def search(self, q):
        p = {"originLocationCode": q["origin"], "destinationLocationCode": q["dest"],
             "departureDate": q["date"], "adults": self.cfg.passengers,
             "currencyCode": self.cfg.currency, "max": self.cfg.max_offers_per_call,
             "nonStop": str(self.cfg.non_stop).lower()}
        if q.get("return"):
            p["returnDate"] = q["return"]
        req = urllib.request.Request(self.host + "/v2/shopping/flight-offers?" + urllib.parse.urlencode(p),
                                     headers={"Authorization": "Bearer " + self._token()})
        data = self._http(req).get("data", [])
        offers = [normalize(o, self.cfg.passengers) for o in data]
        return [o for o in offers if o]


class Mock:
    """Offline provider for demos/tests. Randomly returns prices; sometimes fewer than N seats."""
    def __init__(self, cfg, db):
        self.cfg = cfg

    def search(self, q):
        rnd = random.Random(f'{q["origin"]}{q["dest"]}{q["date"]}{q.get("return")}{int(time.time() // 3600)}')
        out = []
        for i in range(3):
            seats = rnd.choice([2, 3, 4, 5, 9])
            base = rnd.uniform(90, 260) * (2 if q.get("return") else 1)
            raw = {"id": f'{q["date"]}-{i}', "numberOfBookableSeats": seats,
                   "price": {"grandTotal": f"{base * self.cfg.passengers:.2f}"},
                   "travelerPricing": [{}] * self.cfg.passengers,
                   "itineraries": [{"segments": [{"departure": {"iataCode": q["origin"], "at": q["date"] + "T08:00"},
                                                  "arrival": {"iataCode": q["dest"], "at": q["date"] + "T10:10"},
                                                  "carrierCode": "XX", "number": str(100 + i)}]}]}
            o = normalize(raw, self.cfg.passengers)
            if o:
                out.append(o)
        return out


def make(cfg, db):
    return {"amadeus": Amadeus, "mock": Mock}[cfg.provider](cfg, db)
