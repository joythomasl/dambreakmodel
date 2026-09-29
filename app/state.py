from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .connectors import data_age_hours, iso_now


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "runtime" / "state"


def _path(name: str) -> Path:
    return STATE_DIR / f"{name}.json"


def load_state(name: str, default: Any) -> Any:
    path = _path(name)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(name: str, value: Any) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _path(name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def append_unique(name: str, records: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    current = load_state(name, [])
    indexed = {tuple(row.get(field) for field in key_fields): row for row in current}
    for record in records:
        indexed[tuple(record.get(field) for field in key_fields)] = record
    merged = sorted(indexed.values(), key=lambda row: str(row.get("time") or row.get("observed_at") or ""))
    save_state(name, merged)
    return merged


def observation_gate(site: dict, observations: list[dict], rainfall: list[dict], assets: list[dict]) -> dict:
    max_obs_age = float(next(item["maximum_age_hours"] for item in site["required_live_inputs"] if item["id"] == "reservoir_state"))
    max_rain_age = float(next(item["maximum_age_hours"] for item in site["required_live_inputs"] if item["id"] == "rainfall"))

    def is_current(timestamp: str | None, maximum_age: float) -> bool:
        age = data_age_hours(timestamp)
        # A small future tolerance allows for clock skew but rejects incorrectly
        # dated records.  An age of exactly zero is valid.
        return age is not None and -1.0 <= age <= maximum_age

    # The scenario engine needs storage, not only a displayed water level.  Do
    # not let the quality gate pass with data the model cannot actually use.
    reservoir = [row for row in observations if row.get("variable") == "reservoir_storage" and row.get("site_id") in {"tehri", "koteshwar"}]
    reservoir_sites = {
        row.get("site_id") for row in reservoir
        if is_current(row.get("observed_at") or row.get("time"), max_obs_age)
    }
    recent_rain = [
        row for row in rainfall
        if is_current(row.get("time") or row.get("observed_at"), max_rain_age)
    ]
    checks = {
        "reservoir_state": {"ready": reservoir_sites == {"tehri", "koteshwar"}, "sites": sorted(reservoir_sites), "required": ["tehri", "koteshwar"], "max_age_hours": max_obs_age},
        "rainfall": {"ready": len(recent_rain) >= 3, "records": len(recent_rain), "minimum_records": 3, "max_age_hours": max_rain_age},
        "exposure": {"ready": len(assets) > 0, "records": len(assets)},
    }
    return {
        "ready": all(item["ready"] for item in checks.values()),
        "checked_at": iso_now(),
        "checks": checks,
        "message": "Ready for a timestamped scenario run." if all(item["ready"] for item in checks.values()) else "Required live inputs are missing or stale; simulation is blocked.",
    }
