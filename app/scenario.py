from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .cascade import run_cascade
from .avulsion import assess_avulsion
from .catalog import load_site
from .connectors import data_age_hours
from .damage import analyze_damage, analyze_grid_damage
from .hydrology import create_event_hydrograph, rainfall_runoff
from .inundation import load_structures, load_terrain, simulate_inundation
from .model_adapters import DFlowFMAdapter, DualSPHysicsAdapter
from .state import load_state, observation_gate, save_state


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = ROOT / "runtime" / "scenarios"
DEMO_PATH = ROOT / "app" / "data" / "offline_demo.json"
LOCAL_CONTEXT_PATH = ROOT / "app" / "data" / "rishikesh_context.json"
REGIONAL_TERRAIN_PATH = ROOT / "app" / "data" / "tehri_rishikesh_terrain.json"
REGIONAL_CONTEXT_PATH = ROOT / "app" / "data" / "tehri_rishikesh_context.json"


DEFAULT_CONFIG = {
    "event_type": "dam_breach",
    "event_time": None,
    "breach_width_m": 60.0,
    "breach_depth_m": 30.0,
    "formation_hours": 1.5,
    "release_peak_cumecs": None,
    "rainfall_multiplier": 1.0,
    "hydrology": {"catchment_area_km2": 4180.0, "runoff_coefficient": 0.42, "baseflow_cumecs": 80.0, "lag_hours": 2, "calibration_status": "user supplied; requires local calibration"},
    "routing": {
        "tehri_koteshwar": {"travel_hours": 1.5, "attenuation": 0.94},
        "koteshwar_devprayag": {"travel_hours": 3.0, "attenuation": 0.90},
        "devprayag_rishikesh": {"travel_hours": 4.5, "attenuation": 0.86}
    },
    "koteshwar": {"capacity_mcm": 35.0, "spill_threshold_mcm": 33.0, "base_release_cumecs": 120.0, "max_release_cumecs": 700.0, "dead_level_m": 580.0, "frl_m": 612.5, "failure_trigger_fraction": 0.96, "breach_release_fraction": 0.35},
    "spatial_model": {"duration_s": 2400, "frame_interval_s": 300, "manning_n": 0.035,
                      "open_boundaries": ["south"], "condition_mapped_channel": True},
    "price_year": 2025,
}


class ScenarioBlocked(ValueError):
    def __init__(self, gate: dict):
        super().__init__(gate["message"])
        self.gate = gate


def _merged_config(overrides: dict | None) -> dict:
    result = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key].update(value)
        else:
            result[key] = value
    return result


def _latest_storage(observations: list[dict], site_id: str) -> dict:
    rows = [row for row in observations if row.get("site_id") == site_id and row.get("variable") == "reservoir_storage"]
    if not rows:
        raise ValueError(f"No reservoir_storage observation for {site_id}")
    return max(rows, key=lambda row: row.get("observed_at") or row.get("time") or "")


def _rain_points(records: list[dict]) -> list[dict]:
    points = []
    for row in records:
        if row.get("variable", "rainfall") not in {"rainfall", "precipitation"}:
            continue
        unit = str(row.get("unit", "mm")).lower()
        value = float(row.get("value", row.get("mm", 0)))
        if unit in {"mm/hr", "mm/h"}:
            value = value
        elif unit != "mm":
            raise ValueError(f"Unsupported rainfall unit: {unit}")
        points.append({"time": row.get("time") or row.get("observed_at"), "mm": value})
    return sorted(points, key=lambda point: point["time"])


def scenario_id(manifest: dict) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def load_demo() -> dict:
    """Load a fixed, explicitly synthetic fixture; never mix it into live state."""
    data = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    if data.get("mode") != "offline_demo" or "SYNTHETIC" not in data.get("label", ""):
        raise ValueError("Demonstration fixture must identify itself as synthetic")
    return data


def _load_json_context(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _run_scenario(
    site: dict, observations: list[dict], rainfall: list[dict], assets: list[dict],
    avulsion_candidates: list[dict], gate: dict, overrides: dict | None, mode: str,
    demo_id: str | None = None,
) -> dict[str, Any]:
    config = _merged_config(overrides)
    tehri_storage = _latest_storage(observations, "tehri")
    koteshwar_storage = _latest_storage(observations, "koteshwar")
    rain = _rain_points(rainfall)
    event_time = config["event_time"] or rain[-1]["time"]
    hydrology = rainfall_runoff(rain, multiplier=float(config["rainfall_multiplier"]), **{
        key: config["hydrology"][key] for key in ("catchment_area_km2", "runoff_coefficient", "baseflow_cumecs", "lag_hours")
    })
    source_event = create_event_hydrograph(
        event_time, config["event_type"], float(tehri_storage["value"]),
        float(config["breach_width_m"]), float(config["breach_depth_m"]), float(config["formation_hours"]),
        config.get("release_peak_cumecs")
    )
    local_inflow = [{"time": point["time"], "flow_cumecs": round(point["flow_cumecs"] * 0.08, 3)} for point in hydrology["central"]]
    reservoir = {**config["koteshwar"], "initial_storage_mcm": float(koteshwar_storage["value"])}
    cascade = run_cascade(source_event["points"], local_inflow, config["routing"], reservoir)

    terrain = load_terrain()
    structures = load_structures()
    local_context = _load_json_context(LOCAL_CONTEXT_PATH)
    regional_terrain = _load_json_context(REGIONAL_TERRAIN_PATH)
    regional_context = _load_json_context(REGIONAL_CONTEXT_PATH)
    mapped_channel = []
    if config["spatial_model"].get("condition_mapped_channel"):
        candidates = [item for item in regional_context.get("waterways", [])
                      if str(item.get("name", "")).lower() in {"ganges", "ganga"}]
        if candidates:
            mapped_channel = candidates[0].get("coordinates", [])
    spatial_simulation = {}
    spatial_damage = {}
    damage = {}
    avulsion = {}
    for branch, branch_result in cascade["branches"].items():
        hydrograph = branch_result["rishikesh_hydrograph"]["points"]
        spatial_simulation[branch] = simulate_inundation(
            hydrograph,
            start_time=branch_result["rishikesh_hazard"]["arrival_time"] or hydrograph[0]["time"],
            terrain=terrain,
            duration_s=int(config["spatial_model"]["duration_s"]),
            frame_interval_s=int(config["spatial_model"]["frame_interval_s"]),
            manning_n=float(config["spatial_model"]["manning_n"]),
            open_boundaries=config["spatial_model"].get("open_boundaries", ["west", "east", "south"]),
            channel_coordinates=mapped_channel,
        )
        spatial_damage[branch] = analyze_grid_damage(assets, spatial_simulation[branch], int(config["price_year"]))
        damage[branch] = analyze_damage(assets, branch_result["rishikesh_hazard"], int(config["price_year"]))
        avulsion[branch] = assess_avulsion(avulsion_candidates, branch_result["rishikesh_hazard"])
    cascade["comparison"]["additional_damage_central_inr"] = round(
        damage["conditional_secondary_failure"]["totals"]["central_inr"] - damage["no_secondary_failure"]["totals"]["central_inr"], 2
    )

    unit_system = {
        "standard": "SI", "locale": "en-IN", "time_zone": "Asia/Kolkata (IST, UTC+05:30)",
        "rainfall": "mm per observation interval", "discharge": "m³/s",
        "reservoir_storage_internal": "MCM (10⁶ m³)", "reservoir_storage_display": "BCM or MCM",
        "water_depth": "m", "elevation": "m AMSL", "distance": "m or km",
        "area": "m² or km²", "volume": "m³", "elapsed_time": "s internally; min or h in display",
        "currency": "INR with Indian digit grouping; lakh/crore display",
    }

    input_manifest = {
        # Exclude the wall-clock gate check time so identical inputs and
        # assumptions produce the same reproducible scenario ID.
        "site_id": site["basin"]["id"], "config": config, "mode": mode, "demo_fixture_id": demo_id,
        "unit_system": "SI_en-IN_v1",
        "terrain_id": terrain["id"], "spatial_engine": "local_inertial_v1",
        "gate": {"ready": gate["ready"], "checks": gate["checks"]},
        "observation_ids": [{"site_id": row.get("site_id"), "time": row.get("observed_at") or row.get("time"), "value": row.get("value"), "source": row.get("source")} for row in observations],
        "rainfall_ids": [{"time": row.get("time"), "value": row.get("value"), "source": row.get("source")} for row in rainfall],
        "asset_ids": [row.get("id") for row in assets],
        "avulsion_candidate_ids": [row.get("id") for row in avulsion_candidates],
    }
    run_id = scenario_id(input_manifest)
    run_dir = SCENARIO_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sph = DualSPHysicsAdapter().prepare(run_dir / "models" / "sph", config)
    dflow = DFlowFMAdapter().prepare(run_dir / "models" / "dflowfm", source_event["points"])
    result = {
        "id": run_id, "status": "completed_synthetic_screening" if mode == "offline_demo" else "completed_screening",
        "mode": mode, "site": site["basin"], "config": config, "unit_system": unit_system,
        "input_gate": gate, "hydrology": hydrology, "source_event": source_event, "cascade": cascade,
        "damage": damage, "spatial_simulation": spatial_simulation,
        "spatial_context": {
            "structures": structures,
            "local_map": local_context,
            "regional_terrain": regional_terrain,
            "regional_map": regional_context,
        }, "spatial_damage": spatial_damage,
        "avulsion": avulsion, "model_status": {
            "sph": {**sph, "run_status":"not run unless configured with reviewed case and solver binary"},
            "dflowfm": {**dflow, "run_status":"not run unless configured with reviewed mesh/model and solver binary"},
            "cascade_engine":"screening routing; replace with calibrated D-Flow FM outputs for operational predictions",
            "spatial_engine":"executed 2-D local-inertial shallow-water approximation on public sampled terrain; not D-Flow FM or SPH",
        },
        "manifest": input_manifest,
        "warnings": (["SYNTHETIC DEMONSTRATION: water, rainfall, assets, rates and avulsion values are invented; no event is observed or predicted."] if mode == "offline_demo" else []) + [
            "Conditional failure is a what-if branch, not a prediction that Koteshwar will fail.",
            "Hydraulic depths and extents are screening outputs until a calibrated D-Flow FM model is run.",
            "The executed 2-D local flood simulation uses coarse sampled elevation, an assumed inlet and open boundaries; it is uncalibrated and not a forecast.",
            "SPH and D-Flow FM adapters generated inputs but external solver runs are not claimed."
        ]
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result_path = run_dir / "result.json"
    display_path = result_path.relative_to(ROOT) if result_path.is_relative_to(ROOT) else result_path
    save_state("last_scenario", {"id": run_id, "path": str(display_path).replace("\\", "/")})
    return result


def run_online_scenario(overrides: dict | None = None) -> dict[str, Any]:
    site = load_site()
    observations = load_state("observations", [])
    rainfall = load_state("rainfall", [])
    assets = load_state("assets", [])
    avulsion_candidates = load_state("avulsion_candidates", [])
    gate = observation_gate(site, observations, rainfall, assets)
    if not gate["ready"]:
        raise ScenarioBlocked(gate)

    max_obs_age = float(next(item["maximum_age_hours"] for item in site["required_live_inputs"] if item["id"] == "reservoir_state"))
    max_rain_age = float(next(item["maximum_age_hours"] for item in site["required_live_inputs"] if item["id"] == "rainfall"))

    def current(rows: list[dict], maximum_age: float) -> list[dict]:
        selected = []
        for row in rows:
            age = data_age_hours(row.get("observed_at") or row.get("time"))
            if age is not None and -1.0 <= age <= maximum_age:
                selected.append(row)
        return selected

    return _run_scenario(
        site, current(observations, max_obs_age), current(rainfall, max_rain_age),
        assets, avulsion_candidates, gate, overrides, "live_inputs",
    )


def run_demo_scenario(overrides: dict | None = None) -> dict[str, Any]:
    demo = load_demo()
    site = load_site()
    gate = {
        "ready": True,
        "mode": "offline_demo",
        "message": "Synthetic fixture ready; values are not current observations.",
        "checks": {
            "reservoir_state": {"ready": True, "sites": ["tehri", "koteshwar"], "required": ["tehri", "koteshwar"], "synthetic": True},
            "rainfall": {"ready": True, "records": len(demo["rainfall"]), "minimum_records": 3, "synthetic": True},
            "exposure": {"ready": True, "records": len(demo["assets"]), "synthetic": True},
        },
    }
    return _run_scenario(
        site, demo["observations"], demo["rainfall"], demo["assets"],
        demo["avulsion_candidates"], gate, overrides, "offline_demo", demo["id"],
    )


def load_scenario(run_id: str) -> dict:
    path = SCENARIO_DIR / run_id / "result.json"
    if not path.exists():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_scenarios() -> list[dict]:
    if not SCENARIO_DIR.exists():
        return []
    results = []
    for path in SCENARIO_DIR.glob("*/result.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        results.append({"id":data["id"], "status":data["status"], "event_type":data["config"]["event_type"], "site":data["site"]["name"]})
    return sorted(results, key=lambda item: item["id"])
