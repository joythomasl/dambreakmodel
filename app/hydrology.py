from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable


@dataclass(frozen=True)
class HydroPoint:
    time: str
    flow_cumecs: float


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def hydrograph_volume_m3(points: Iterable[dict], step_seconds: int = 3600) -> float:
    return sum(max(0.0, float(point["flow_cumecs"])) * step_seconds for point in points)


def rainfall_runoff(
    rainfall: list[dict],
    catchment_area_km2: float,
    runoff_coefficient: float,
    baseflow_cumecs: float,
    lag_hours: int,
    multiplier: float = 1.0,
) -> dict:
    if not rainfall:
        raise ValueError("At least one rainfall observation is required")
    if catchment_area_km2 <= 0:
        raise ValueError("catchment_area_km2 must be positive")
    if not 0 <= runoff_coefficient <= 1:
        raise ValueError("runoff_coefficient must be between 0 and 1")
    if multiplier <= 0:
        raise ValueError("rainfall multiplier must be positive")

    times = [_parse_time(row["time"]) for row in rainfall]
    if times != sorted(times):
        raise ValueError("rainfall timestamps must be sorted")

    # A transparent four-hour unit hydrograph. The weights sum to one, so the
    # generated runoff volume is conserved before baseflow is added.
    weights = (0.12, 0.28, 0.38, 0.22)
    output_length = len(rainfall) + lag_hours + len(weights) - 1
    runoff_flow = [0.0] * output_length
    area_m2 = catchment_area_km2 * 1_000_000.0
    rain_total_mm = 0.0

    for index, row in enumerate(rainfall):
        rain_mm = max(0.0, float(row["mm"])) * multiplier
        rain_total_mm += rain_mm
        event_volume_m3 = rain_mm / 1000.0 * area_m2 * runoff_coefficient
        for weight_index, weight in enumerate(weights):
            runoff_flow[index + lag_hours + weight_index] += event_volume_m3 * weight / 3600.0

    start = times[0]
    central = [
        {"time": (start + timedelta(hours=i)).isoformat(), "flow_cumecs": round(baseflow_cumecs + flow, 3)}
        for i, flow in enumerate(runoff_flow)
    ]

    def scaled(factor: float) -> list[dict]:
        return [
            {"time": point["time"], "flow_cumecs": round(baseflow_cumecs + (point["flow_cumecs"] - baseflow_cumecs) * factor, 3)}
            for point in central
        ]

    generated_runoff_m3 = rain_total_mm / 1000.0 * area_m2 * runoff_coefficient
    peak = max(central, key=lambda point: point["flow_cumecs"])
    return {
        "method": "four-hour synthetic unit hydrograph",
        "assumption": "Prototype rainfall-runoff estimate; not calibrated for operational forecasting.",
        "rainfall_total_mm": round(rain_total_mm, 2),
        "generated_runoff_m3": round(generated_runoff_m3, 1),
        "peak_flow_cumecs": peak["flow_cumecs"],
        "time_to_peak": peak["time"],
        "low": scaled(0.70),
        "central": central,
        "high": scaled(1.30),
    }


def combine_hydrographs(*hydrographs: list[dict]) -> list[dict]:
    if not hydrographs:
        return []
    combined: dict[str, float] = {}
    for hydrograph in hydrographs:
        for point in hydrograph:
            combined[point["time"]] = combined.get(point["time"], 0.0) + float(point["flow_cumecs"])
    return [{"time": time, "flow_cumecs": round(combined[time], 3)} for time in sorted(combined)]


def create_event_hydrograph(
    start_time: str,
    event_type: str,
    storage_mcm: float,
    breach_width_m: float,
    breach_depth_m: float,
    formation_hours: float,
    release_peak_cumecs: float | None = None,
) -> dict:
    if event_type not in {"dam_breach", "sudden_release", "lake_burst", "blockage_failure"}:
        raise ValueError(f"Unsupported event type: {event_type}")
    if storage_mcm <= 0 or breach_width_m <= 0 or breach_depth_m <= 0 or formation_hours <= 0:
        raise ValueError("Storage and breach dimensions must be positive")

    severity = min(1.0, breach_width_m * breach_depth_m / 1800.0)
    fractions = {
        "dam_breach": 0.06 + 0.16 * severity,
        "sudden_release": 0.015 + 0.02 * severity,
        "lake_burst": 0.10 + 0.24 * severity,
        "blockage_failure": 0.12 + 0.28 * severity,
    }
    released_volume_m3 = storage_mcm * 1_000_000.0 * fractions[event_type]
    pulse = (0.04, 0.18, 0.34, 0.24, 0.13, 0.07)
    default_peak = released_volume_m3 * max(pulse) / 3600.0
    peak = float(release_peak_cumecs) if event_type == "sudden_release" and release_peak_cumecs else default_peak
    scale = peak / default_peak if default_peak else 1.0
    start = _parse_time(start_time)
    points = [
        {"time": (start + timedelta(hours=i)).isoformat(), "flow_cumecs": round(released_volume_m3 * weight / 3600.0 * scale, 3)}
        for i, weight in enumerate(pulse)
    ]
    return {
        "event_type": event_type,
        "method": "synthetic parameterized release hydrograph",
        "released_volume_m3": round(hydrograph_volume_m3(points), 1),
        "peak_flow_cumecs": max(point["flow_cumecs"] for point in points),
        "formation_hours": formation_hours,
        "points": points,
        "status": "synthetic scenario; not a solver output",
    }
