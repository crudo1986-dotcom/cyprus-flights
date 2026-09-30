import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries(
  key TEXT PRIMARY KEY, last_checked REAL DEFAULT 0, best_pp REAL, fail_count INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS prices(
  ts REAL, key TEXT, offer_id TEXT, total REAL, per_person REAL, seats INTEGER, summary TEXT);
CREATE TABLE IF NOT EXISTS calls(day TEXT, n INTEGER, PRIMARY KEY(day));
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS alerted(key TEXT, sig TEXT, PRIMARY KEY(key, sig));
"""


class DB:
    def __init__(self, path):
        self.c = sqlite3.connect(path)
        self.c.executescript(SCHEMA)

    def today(self):
        return time.strftime("%Y-%m-%d")

    def calls_today(self):
        r = self.c.execute("SELECT n FROM calls WHERE day=?", (self.today(),)).fetchone()
        return r[0] if r else 0

    def count_call(self):
        self.c.execute("INSERT INTO calls VALUES(?,1) ON CONFLICT(day) DO UPDATE SET n=n+1",
                       (self.today(),))
        self.c.commit()

    def get(self, k):
        r = self.c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    def put(self, k, v):
        self.c.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, v))
        self.c.commit()

    def query_state(self, key):
        r = self.c.execute("SELECT last_checked,best_pp,fail_count FROM queries WHERE key=?",
                           (key,)).fetchone()
        return r or (0.0, None, 0)

    def save_query(self, key, best_pp, fail):
        self.c.execute(
            "INSERT INTO queries(key,last_checked,best_pp,fail_count) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET last_checked=excluded.last_checked,"
            "best_pp=excluded.best_pp,fail_count=excluded.fail_count",
            (key, time.time(), best_pp, fail))
        self.c.commit()

    def add_price(self, key, o):
        self.c.execute("INSERT INTO prices VALUES(?,?,?,?,?,?,?)",
                       (time.time(), key, o["id"], o["total"], o["per_person"],
                        o["seats"], o["summary"]))
        self.c.commit()

    def was_alerted(self, key, sig):
        return self.c.execute("SELECT 1 FROM alerted WHERE key=? AND sig=?", (key, sig)).fetchone() is not None

    def mark_alerted(self, key, sig):
        self.c.execute("INSERT OR IGNORE INTO alerted VALUES(?,?)", (key, sig))
        self.c.commit()
