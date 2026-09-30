import os
import tempfile
import unittest

from flightwatch.config import Config
from flightwatch.db import DB
from flightwatch.engine import Engine, build_queries
from flightwatch.providers import normalize


def raw(seats, total, n=4):
    return {"id": "1", "numberOfBookableSeats": seats, "price": {"grandTotal": str(total)},
            "travelerPricing": [{}] * n, "itineraries": []}


class Fake:
    def __init__(self, price):
        self.price, self.calls = price, 0

    def search(self, q):
        self.calls += 1
        return [normalize(raw(4, self.price), 4)]


class T(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.cfg = Config(db_path=os.path.join(d, "t.db"), alerts_log=os.path.join(d, "a.jsonl"),
                          provider="mock", depart_from="2099-01-01", depart_to="2099-01-03",
                          daily_call_budget=2, max_price_per_person=0, max_per_person_per_direction=0)

    def test_requires_all_seats(self):
        self.assertIsNone(normalize(raw(3, 400), 4))
        self.assertIsNone(normalize(raw(9, 400, n=2), 4))
        self.assertEqual(normalize(raw(4, 400), 4)["per_person"], 100.0)

    def test_budget_and_dedupe_and_drop_alert(self):
        f = Fake(400)
        e = Engine(self.cfg, provider=f, db=DB(self.cfg.db_path))
        q = build_queries(self.cfg)[0]
        self.assertEqual(e.check(q), [])          # first sight: no alert (no baseline)
        f.price = 300
        self.assertEqual(len(e.check(q)), 1)      # >5% drop -> alert
        self.assertEqual(e.check(q), [])          # same offer again -> deduped
        e.run_once()
        self.assertTrue(e.db.calls_today() >= 3)
        before = f.calls
        e.run_once()                              # over budget -> no call
        self.assertEqual(f.calls, before)

    def test_cap_per_person_per_direction(self):
        self.cfg.max_per_person_per_direction = 100
        f = Fake(440)  # 110 pp one-way -> filtered out
        e = Engine(self.cfg, provider=f, db=DB(self.cfg.db_path))
        q = build_queries(self.cfg)[0]
        self.assertEqual(e.check(q), [])
        f.price = 396  # 99 pp -> shown
        self.assertEqual(len(e.check(q)), 1)
        rt = dict(q, **{"return": "2099-01-08"})
        f.price = 780  # 195 pp round trip = 97.5 per direction -> shown
        self.assertEqual(len(e.check(rt)), 1)
        f.price = 800  # 200 pp round trip = 100 per direction -> not strictly below
        self.assertEqual(e.check(dict(rt, key="k2")), [])

    def test_recheck_interval_saves_calls(self):
        f = Fake(400)
        self.cfg.daily_call_budget = 100
        e = Engine(self.cfg, provider=f, db=DB(self.cfg.db_path))
        for _ in range(20):
            q, _ = e.next_due()
            if q:
                e.check(q)
        self.assertEqual(f.calls, 6)            # 2 destinations x 3 days, each searched once until due again


if __name__ == "__main__":
    unittest.main()
