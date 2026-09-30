import json
from dataclasses import dataclass, field, fields


@dataclass
class Config:
    origins: list = field(default_factory=lambda: ["TLV", "HFA"])  # Tel Aviv, Haifa
    destinations: list = field(default_factory=lambda: ["LCA"])  # Larnaca
    passengers: int = 4                      # ALL must be on the same flight/offer
    depart_from: str = ""                    # YYYY-MM-DD (empty = today + 7)
    depart_to: str = ""                      # YYYY-MM-DD (empty = from + 60 days)
    stay_nights: list = field(default_factory=list)  # [] = one-way, [3, 7] = round trip
    currency: str = "USD"
    non_stop: bool = False
    max_per_person_per_direction: float = 100.0  # HARD filter: only show offers strictly below this (0 = off)
    max_price_per_person: float = 0.0        # extra alert threshold on total pp, 0 = off
    min_drop_pct: float = 5.0                # alert if cheaper than best known by this %
    daily_call_budget: int = 200             # hard cap on API calls per day
    max_offers_per_call: int = 5             # small responses = fewer wasted bytes
    recheck_hours_far: float = 24.0          # departure > 30 days away
    recheck_hours_mid: float = 12.0          # 8-30 days
    recheck_hours_near: float = 4.0          # <= 7 days
    provider: str = "amadeus"                # "amadeus" | "mock"
    amadeus_env: str = "test"                # "test" | "production"
    webhook_url: str = ""                    # optional: POST JSON alert (ntfy, Slack, etc.)
    db_path: str = "flightwatch.db"
    alerts_log: str = "alerts.jsonl"


def load(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    known = {f.name for f in fields(Config)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
    cfg = Config(**raw)
    if cfg.passengers < 1 or cfg.passengers > 9:
        raise ValueError("passengers must be 1..9")
    return cfg
