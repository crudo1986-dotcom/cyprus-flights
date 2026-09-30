import datetime as dt
import json
import logging
import time
import urllib.request

from .db import DB
from .providers import ProviderError, make

log = logging.getLogger("flightwatch")


def build_queries(cfg, today=None):
    today = today or dt.date.today()
    start = dt.date.fromisoformat(cfg.depart_from) if cfg.depart_from else today + dt.timedelta(days=7)
    end = dt.date.fromisoformat(cfg.depart_to) if cfg.depart_to else start + dt.timedelta(days=60)
    start = max(start, today)
    qs = []
    d = start
    while d <= end:
        for o in cfg.origins:
            for dest in cfg.destinations:
                for n in (cfg.stay_nights or [None]):
                    q = {"origin": o, "dest": dest, "date": d.isoformat(),
                         "return": (d + dt.timedelta(days=n)).isoformat() if n else None}
                    q["key"] = "|".join(str(q[k] or "") for k in ("origin", "dest", "date", "return"))
                    qs.append(q)
        d += dt.timedelta(days=1)
    return qs


def recheck_seconds(cfg, q, today=None):
    days = (dt.date.fromisoformat(q["date"]) - (today or dt.date.today())).days
    h = cfg.recheck_hours_near if days <= 7 else cfg.recheck_hours_mid if days <= 30 else cfg.recheck_hours_far
    return h * 3600


class Engine:
    def __init__(self, cfg, provider=None, db=None):
        self.cfg = cfg
        self.db = db or DB(cfg.db_path)
        self.provider = provider or make(cfg, self.db)

    def next_due(self, now=None):
        """Most overdue query, or (None, seconds_until_next_due)."""
        now = now or time.time()
        best, best_over, soonest = None, 0, float("inf")
        for q in build_queries(self.cfg):
            last, _, fails = self.db.query_state(q["key"])
            due_at = last + recheck_seconds(self.cfg, q) * (2 ** min(fails, 4))  # backoff on failures
            over = now - due_at
            if over >= 0 and (best is None or over > best_over):
                best, best_over = q, over
            soonest = min(soonest, due_at - now)
        return best, max(soonest, 0)

    def check(self, q):
        """One API call. Returns list of alerts raised."""
        _, best_pp, fails = self.db.query_state(q["key"])
        self.db.count_call()
        try:
            offers = self.provider.search(q)
        except ProviderError as e:
            self.db.save_query(q["key"], best_pp, fails + 1)
            log.warning("search failed %s: %s", q["key"], e)
            if e.fatal:
                raise
            return []
        cap, legs = self.cfg.max_per_person_per_direction, 2 if q["return"] else 1
        if cap:  # per person, per direction, strictly under the cap
            offers = [o for o in offers if o["per_person"] / legs < cap]
        offers.sort(key=lambda o: o["per_person"])
        for o in offers:
            self.db.add_price(q["key"], o)
        alerts = []
        if offers:
            top = offers[0]
            cheap = bool(cap) or (self.cfg.max_price_per_person
                                  and top["per_person"] <= self.cfg.max_price_per_person)
            drop = best_pp is not None and top["per_person"] <= best_pp * (1 - self.cfg.min_drop_pct / 100)
            sig = f'{top["id"]}:{top["total"]}'
            if (cheap or drop) and not self.db.was_alerted(q["key"], sig):
                self.db.mark_alerted(q["key"], sig)
                alerts.append(self.alert(q, top, best_pp))
            best_pp = top["per_person"] if best_pp is None else min(best_pp, top["per_person"])
        self.db.save_query(q["key"], best_pp, 0)
        return alerts

    def alert(self, q, o, prev):
        a = {"when": dt.datetime.now().isoformat(timespec="seconds"), "route": f'{q["origin"]}->{q["dest"]}',
             "date": q["date"], "return": q["return"], "seats_together": self.cfg.passengers,
             "per_person": o["per_person"],
             "per_person_per_direction": round(o["per_person"] / (2 if q["return"] else 1), 2), "total": o["total"], "currency": self.cfg.currency,
             "previous_best_pp": prev, "flight": o["summary"]}
        log.info("DEAL %s %s: %s %s pp (total %s for %d) %s", a["route"], a["date"], a["per_person"],
                 a["currency"], a["total"], a["seats_together"], a["flight"])
        with open(self.cfg.alerts_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
        if self.cfg.webhook_url:
            try:
                req = urllib.request.Request(self.cfg.webhook_url, json.dumps(a, ensure_ascii=False).encode(),
                                             {"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10).read()
            except Exception as e:  # notification must never kill the loop
                log.warning("webhook failed: %s", e)
        return a

    def run_once(self):
        """Do at most one due check within budget. Returns seconds to sleep."""
        if self.db.calls_today() >= self.cfg.daily_call_budget:
            tomorrow = dt.datetime.combine(dt.date.today() + dt.timedelta(days=1), dt.time(0, 1))
            log.info("daily budget %d reached, sleeping until tomorrow", self.cfg.daily_call_budget)
            return (tomorrow - dt.datetime.now()).total_seconds()
        q, wait = self.next_due()
        if q is None:
            return min(max(wait, 30), 3600)
        self.check(q)
        return 1.0  # gentle pacing between calls

    def run_forever(self):
        log.info("watching %s -> %s, %d seats together, budget %d calls/day",
                 self.cfg.origins, self.cfg.destinations, self.cfg.passengers, self.cfg.daily_call_budget)
        while True:
            try:
                time.sleep(self.run_once())
            except ProviderError as e:
                log.error("fatal provider error (%s); sleeping 1h instead of burning quota", e)
                time.sleep(3600)
            except KeyboardInterrupt:
                return
