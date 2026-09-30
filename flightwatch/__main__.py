import argparse
import logging
import sqlite3

from . import config
from .engine import Engine, build_queries


def main():
    ap = argparse.ArgumentParser(prog="flightwatch")
    ap.add_argument("-c", "--config", default="config.json")
    ap.add_argument("cmd", choices=["run", "once", "best", "plan"], nargs="?", default="run")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = config.load(a.config)
    if a.cmd == "plan":
        qs = build_queries(cfg)
        print(f"{len(qs)} distinct searches per full sweep; budget {cfg.daily_call_budget}/day")
        return
    eng = Engine(cfg)
    if a.cmd == "run":
        eng.run_forever()
    elif a.cmd == "once":
        eng.run_once()
    else:
        rows = sqlite3.connect(cfg.db_path).execute(
            "SELECT key,best_pp FROM queries WHERE best_pp IS NOT NULL ORDER BY best_pp LIMIT 15").fetchall()
        for k, p in rows:
            print(f"{p:>9.2f} {cfg.currency}/person  {k}")


main()
