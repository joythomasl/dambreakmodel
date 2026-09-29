from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SITE_PATH = ROOT / "app" / "data" / "site_tehri.json"


def load_site() -> dict[str, Any]:
    with SITE_PATH.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def validate_catalog(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {"basin", "nodes", "edges", "required_live_inputs", "observations", "rainfall", "assets"}
    missing = required - set(data)
    if missing:
        errors.append(f"Missing top-level keys: {', '.join(sorted(missing))}")

    node_ids = {node.get("id") for node in data.get("nodes", [])}
    for edge in data.get("edges", []):
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            errors.append(f"Invalid edge {edge!r}: endpoint is not in node catalogue")
        if edge.get("travel_hours") is not None and float(edge["travel_hours"]) <= 0:
            errors.append(f"Invalid edge {edge!r}: travel_hours must be positive when supplied")
        if edge.get("attenuation") is not None:
            attenuation = float(edge["attenuation"])
            if not 0 < attenuation <= 1:
                errors.append(f"Invalid edge {edge!r}: attenuation must be in (0, 1]")

    for observation in data.get("observations", []):
        for key in ("site_id", "variable", "value", "unit", "observed_at", "source", "quality", "crs"):
            if key not in observation:
                errors.append(f"Observation missing {key}: {observation!r}")
        if observation.get("site_id") not in node_ids:
            errors.append(f"Observation has unknown site: {observation.get('site_id')}")

    asset_ids = [asset.get("id") for asset in data.get("assets", [])]
    if len(asset_ids) != len(set(asset_ids)):
        errors.append("Asset IDs must be unique")
    return errors


def public_catalog(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "basin": data["basin"],
        "nodes": data["nodes"],
        "edges": data["edges"],
        "observations": data["observations"],
        "rainfall": data["rainfall"],
        "rainfall_metadata": data.get("rainfall_metadata", {"status":"waiting_for_online_data"}),
        "assets": data["assets"],
        "required_live_inputs": data["required_live_inputs"],
        "avulsion_paths": data.get("avulsion_paths", []),
        "warnings": [
            "Decision-support prototype: not an official warning service.",
            "No missing live observation is replaced with a synthetic value.",
            "Breach geometry and failure timing are user-defined what-if assumptions, not observed predictions.",
            "The Tehri-Koteshwar connection is real; flood outputs require calibrated hydraulic models before operational use."
        ]
    }
