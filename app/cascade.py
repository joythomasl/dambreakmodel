from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .hydrology import combine_hydrographs, hydrograph_volume_m3


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def route_hydrograph(points: list[dict], travel_hours: float, attenuation: float) -> dict:
    if travel_hours <= 0:
        raise ValueError("travel_hours must be positive")
    if not 0 < attenuation <= 1:
        raise ValueError("attenuation must be in (0, 1]")
    routed = [{
        "time": (_time(point["time"]) + timedelta(hours=travel_hours)).isoformat(),
        "flow_cumecs": round(float(point["flow_cumecs"]) * attenuation, 3),
    } for point in points]
    incoming = hydrograph_volume_m3(points)
    outgoing = hydrograph_volume_m3(routed)
    return {
        "points": routed,
        "travel_hours": travel_hours,
        "attenuation": attenuation,
        "incoming_volume_m3": round(incoming, 1),
        "outgoing_volume_m3": round(outgoing, 1),
        "temporary_storage_and_floodplain_loss_m3": round(incoming - outgoing, 1),
    }


def _level_from_storage(storage_mcm: float, dead_level_m: float, frl_m: float, capacity_mcm: float) -> float:
    fraction = min(1.2, max(0.0, storage_mcm / capacity_mcm))
    return round(dead_level_m + fraction * (frl_m - dead_level_m), 3)


def reservoir_response(
    inflow: list[dict], *, initial_storage_mcm: float, capacity_mcm: float,
    spill_threshold_mcm: float, base_release_cumecs: float, max_release_cumecs: float,
    dead_level_m: float, frl_m: float, conditional_failure: bool,
    failure_trigger_fraction: float, breach_release_fraction: float,
) -> dict:
    if not inflow:
        raise ValueError("Reservoir inflow is empty")
    if not 0 < initial_storage_mcm <= capacity_mcm:
        raise ValueError("Initial storage must be positive and not exceed capacity")
    if not 0 < spill_threshold_mcm <= capacity_mcm:
        raise ValueError("Spill threshold must be positive and not exceed capacity")
    if not 0 < failure_trigger_fraction <= 1:
        raise ValueError("Failure trigger fraction must be in (0, 1]")
    if not 0 < breach_release_fraction < 1:
        raise ValueError("Breach release fraction must be in (0, 1)")

    storage = initial_storage_mcm
    initial_volume = storage * 1_000_000.0
    outflow: list[dict] = []
    levels: list[dict] = []
    failure_time: str | None = None
    breach_schedule = [0.08, 0.24, 0.32, 0.21, 0.10, 0.05]
    breach_volume_m3 = 0.0
    breach_index = -1
    total_inflow = 0.0
    total_outflow = 0.0

    for point in inflow:
        current_time = point["time"]
        q_in = max(0.0, float(point["flow_cumecs"]))
        inflow_volume = q_in * 3600.0
        total_inflow += inflow_volume
        storage += inflow_volume / 1_000_000.0

        available_m3 = storage * 1_000_000.0
        controlled_q = min(max_release_cumecs, max(0.0, base_release_cumecs))
        controlled_volume = min(available_m3, controlled_q * 3600.0)
        storage -= controlled_volume / 1_000_000.0

        spill_volume = 0.0
        if storage > spill_threshold_mcm:
            excess_m3 = (storage - spill_threshold_mcm) * 1_000_000.0
            spill_volume = min(excess_m3, max_release_cumecs * 3600.0)
            storage -= spill_volume / 1_000_000.0

        if conditional_failure and failure_time is None and storage / capacity_mcm >= failure_trigger_fraction:
            failure_time = current_time
            breach_volume_m3 = storage * 1_000_000.0 * breach_release_fraction
            breach_index = 0

        breach_step_volume = 0.0
        if breach_index >= 0 and breach_index < len(breach_schedule):
            breach_step_volume = min(storage * 1_000_000.0, breach_volume_m3 * breach_schedule[breach_index])
            storage -= breach_step_volume / 1_000_000.0
            breach_index += 1

        step_outflow = controlled_volume + spill_volume + breach_step_volume
        total_outflow += step_outflow
        outflow.append({"time": current_time, "flow_cumecs": round(step_outflow / 3600.0, 3)})
        levels.append({
            "time": current_time,
            "storage_mcm": round(storage, 5),
            "level_m": _level_from_storage(storage, dead_level_m, frl_m, capacity_mcm),
            "inflow_cumecs": round(q_in, 3),
            "outflow_cumecs": round(step_outflow / 3600.0, 3),
        })

    final_volume = storage * 1_000_000.0
    balance_error = initial_volume + total_inflow - total_outflow - final_volume
    return {
        "outflow": outflow,
        "levels": levels,
        "failure_triggered": failure_time is not None,
        "failure_time": failure_time,
        "maximum_level_m": max(point["level_m"] for point in levels),
        "peak_inflow_cumecs": max(point["inflow_cumecs"] for point in levels),
        "peak_outflow_cumecs": max(point["outflow_cumecs"] for point in levels),
        "initial_storage_mcm": initial_storage_mcm,
        "final_storage_mcm": round(storage, 5),
        "inflow_volume_m3": round(total_inflow, 1),
        "outflow_volume_m3": round(total_outflow, 1),
        "mass_balance_error_m3": round(balance_error, 6),
    }


def first_arrival(points: list[dict]) -> str | None:
    if not points:
        return None
    peak = max(float(point["flow_cumecs"]) for point in points)
    if peak <= 0:
        return None
    threshold = peak * 0.05
    return next((point["time"] for point in points if float(point["flow_cumecs"]) >= threshold), points[0]["time"])


def _incremental_signal(actual: list[dict], baseline: list[dict]) -> list[dict]:
    """Keep only the additional flow caused by the upstream event."""
    baseline_by_time = {point["time"]: float(point["flow_cumecs"]) for point in baseline}
    return [{"time": point["time"], "flow_cumecs": max(0.0, round(float(point["flow_cumecs"]) - baseline_by_time.get(point["time"], 0.0), 3))} for point in actual]


def hazard_from_hydrograph(points: list[dict], branch: str, event_arrival_time: str | None = None) -> dict:
    peak = max(float(point["flow_cumecs"]) for point in points)
    depth = min(9.0, 0.35 + peak / 1800.0)
    speed = min(7.0, 0.45 + peak / 2600.0)
    duration = sum(1 for point in points if float(point["flow_cumecs"]) >= peak * 0.20)
    scale = min(0.055, 0.012 + depth * 0.0048)
    center_lon, center_lat = 78.278, 30.092
    polygon = [[
        [center_lon - scale * 1.2, center_lat + scale * 0.55],
        [center_lon + scale * 0.8, center_lat + scale * 0.7],
        [center_lon + scale * 1.25, center_lat - scale * 0.45],
        [center_lon - scale * 0.65, center_lat - scale * 0.8],
        [center_lon - scale * 1.2, center_lat + scale * 0.55],
    ]]
    return {
        "branch": branch,
        "arrival_time": event_arrival_time,
        "peak_flow_cumecs": round(peak, 3),
        "maximum_depth_m": round(depth, 3),
        "maximum_speed_mps": round(speed, 3),
        "duration_hours": duration,
        "extent": {"type": "Feature", "properties": {"branch": branch, "maximum_depth_m": round(depth, 3)}, "geometry": {"type": "Polygon", "coordinates": polygon}},
        "method_status": "screening relationship pending calibrated D-Flow FM output",
    }


def run_cascade(source_hydrograph: list[dict], local_inflow: list[dict], routing: dict[str, dict], reservoir: dict) -> dict:
    to_koteshwar = route_hydrograph(source_hydrograph, **routing["tehri_koteshwar"])
    combined_koteshwar_inflow = combine_hydrographs(to_koteshwar["points"], local_inflow)

    common = dict(
        initial_storage_mcm=float(reservoir["initial_storage_mcm"]), capacity_mcm=float(reservoir["capacity_mcm"]),
        spill_threshold_mcm=float(reservoir["spill_threshold_mcm"]), base_release_cumecs=float(reservoir["base_release_cumecs"]),
        max_release_cumecs=float(reservoir["max_release_cumecs"]), dead_level_m=float(reservoir["dead_level_m"]),
        frl_m=float(reservoir["frl_m"]), failure_trigger_fraction=float(reservoir["failure_trigger_fraction"]),
        breach_release_fraction=float(reservoir["breach_release_fraction"]),
    )
    branches: dict[str, Any] = {}
    for branch_name, failure in (("no_secondary_failure", False), ("conditional_secondary_failure", True)):
        response = reservoir_response(combined_koteshwar_inflow, conditional_failure=failure, **common)
        local_by_time = {point["time"]: float(point["flow_cumecs"]) for point in local_inflow}
        baseline_inflow = [{"time": point["time"], "flow_cumecs": local_by_time.get(point["time"], 0.0)} for point in combined_koteshwar_inflow]
        baseline_response = reservoir_response(baseline_inflow, conditional_failure=failure, **common)
        to_devprayag = route_hydrograph(response["outflow"], **routing["koteshwar_devprayag"])
        to_rishikesh = route_hydrograph(to_devprayag["points"], **routing["devprayag_rishikesh"])
        baseline_devprayag = route_hydrograph(baseline_response["outflow"], **routing["koteshwar_devprayag"])
        baseline_rishikesh = route_hydrograph(baseline_devprayag["points"], **routing["devprayag_rishikesh"])
        devprayag_signal = _incremental_signal(to_devprayag["points"], baseline_devprayag["points"])
        rishikesh_signal = _incremental_signal(to_rishikesh["points"], baseline_rishikesh["points"])
        event_arrival = first_arrival(rishikesh_signal)
        hazard = hazard_from_hydrograph(to_rishikesh["points"], branch_name, event_arrival)
        branches[branch_name] = {
            "koteshwar": response,
            "devprayag_hydrograph": to_devprayag,
            "rishikesh_hydrograph": to_rishikesh,
            "event_signal": {"devprayag": devprayag_signal, "rishikesh": rishikesh_signal,
                             "basis": "actual flow minus local-rainfall-only baseline"},
            "rishikesh_hazard": hazard,
            "timeline": [
                {"node":"Tehri Dam","event":"Source wave begins","time":source_hydrograph[0]["time"]},
                {"node":"Koteshwar Dam","event":"Incoming source wave first arrival","time":first_arrival(to_koteshwar["points"])},
                {"node":"Koteshwar Dam","event":"Conditional breach" if response["failure_triggered"] else "No secondary breach","time":response["failure_time"]},
                {"node":"Devprayag","event":"Additional event-wave arrival","time":first_arrival(devprayag_signal)},
                {"node":"Rishikesh","event":"Additional event-wave arrival","time":event_arrival},
            ],
        }

    return {
        "source_to_koteshwar": to_koteshwar,
        "branches": branches,
        "comparison": {
            "additional_peak_flow_cumecs": round(branches["conditional_secondary_failure"]["rishikesh_hazard"]["peak_flow_cumecs"] - branches["no_secondary_failure"]["rishikesh_hazard"]["peak_flow_cumecs"], 3),
            "additional_depth_m": round(branches["conditional_secondary_failure"]["rishikesh_hazard"]["maximum_depth_m"] - branches["no_secondary_failure"]["rishikesh_hazard"]["maximum_depth_m"], 3),
        },
    }
