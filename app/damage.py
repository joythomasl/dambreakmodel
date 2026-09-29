from __future__ import annotations

import math
from typing import Any


CURVES = {
    "residential": [(0.0, 0.0), (0.3, 0.05), (0.8, 0.18), (1.5, 0.38), (2.5, 0.60), (4.0, 0.82), (6.0, 0.95)],
    "critical_facility": [(0.0, 0.0), (0.3, 0.08), (0.8, 0.24), (1.5, 0.48), (2.5, 0.72), (4.0, 0.90)],
    "bridge": [(0.0, 0.0), (0.5, 0.03), (1.5, 0.12), (3.0, 0.35), (5.0, 0.65), (7.0, 0.88)],
    "road": [(0.0, 0.0), (0.3, 0.04), (0.8, 0.14), (1.5, 0.30), (3.0, 0.55), (5.0, 0.78)],
    "cropland": [(0.0, 0.0), (0.2, 0.12), (0.5, 0.35), (1.0, 0.62), (2.0, 0.85)],
    "other": [(0.0, 0.0), (0.5, 0.10), (1.5, 0.35), (3.0, 0.60), (5.0, 0.85)],
}


def point_in_polygon(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Return whether a point is inside a simple lon/lat polygon ring."""
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous
        x2, y2 = current
        crosses = (y1 > lat) != (y2 > lat)
        if crosses:
            boundary_x = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < boundary_x:
                inside = not inside
        previous = current
    return inside


def interpolate_damage_fraction(asset_type: str, depth_m: float) -> float:
    curve = CURVES.get(asset_type, CURVES["other"])
    if depth_m <= curve[0][0]:
        return curve[0][1]
    for (d0, f0), (d1, f1) in zip(curve, curve[1:]):
        if d0 <= depth_m <= d1:
            ratio = (depth_m - d0) / (d1 - d0)
            return f0 + ratio * (f1 - f0)
    return curve[-1][1]


def analyze_damage(assets: list[dict], hazard: dict, price_year: int = 2025) -> dict[str, Any]:
    seen: set[str] = set()
    items = []
    people_exposed = 0
    central_total = 0.0
    base_depth = float(hazard["maximum_depth_m"])
    speed = float(hazard["maximum_speed_mps"])
    duration = float(hazard["duration_hours"])
    ring = hazard.get("extent", {}).get("geometry", {}).get("coordinates", [[]])[0]

    for index, asset in enumerate(assets):
        asset_id = str(asset.get("id") or f"asset-{index}")
        if asset_id in seen:
            continue
        seen.add(asset_id)
        asset_type = str(asset.get("type", "other"))
        has_location = asset.get("lat") is not None and asset.get("lon") is not None
        if has_location and ring and not point_in_polygon(float(asset["lon"]), float(asset["lat"]), ring):
            continue
        if not has_location and asset.get("hazard_factor") is None:
            # Never silently treat a non-spatial inventory as inundated.
            continue
        spatial_factor = float(asset.get("hazard_factor", 1.0))
        depth = max(0.0, base_depth * spatial_factor)
        fraction = interpolate_damage_fraction(asset_type, depth)
        if speed > 2.0:
            fraction += min(0.12, (speed - 2.0) * 0.025)
        if duration > 6:
            fraction += min(0.08, (duration - 6) * 0.01)
        fraction = min(1.0, fraction)
        quantity = float(asset.get("quantity", 1.0))
        unit_cost = float(asset.get("unit_cost_inr", 0.0))
        replacement_value = quantity * unit_cost
        central = replacement_value * fraction
        central_total += central
        if depth >= 0.3:
            people_exposed += int(asset.get("people", 0))
        items.append({
            "asset_id": asset_id, "name": asset.get("name", asset_id), "type": asset_type,
            "quantity": quantity, "unit": asset.get("unit", "asset"), "depth_m": round(depth, 3),
            "speed_mps": speed, "damage_fraction": round(fraction, 4), "unit_cost_inr": unit_cost,
            "replacement_value_inr": round(replacement_value, 2), "loss_low_inr": round(central * 0.70, 2),
            "loss_central_inr": round(central, 2), "loss_high_inr": round(central * 1.35, 2),
            "cost_source": asset.get("cost_source", "missing - requires local rate"),
            "confidence": asset.get("confidence", "unverified exposure"),
            "exposure_basis": "point-in-polygon" if has_location else "explicit aggregated hazard factor",
        })

    return {
        "branch": hazard["branch"], "price_year": price_year, "currency": "INR",
        "people_potentially_exposed": people_exposed, "unique_assets_assessed": len(items),
        "totals": {"low_inr": round(central_total * 0.70, 2), "central_inr": round(central_total, 2), "high_inr": round(central_total * 1.35, 2)},
        "items": items,
        "method": "Depth-damage screening with speed/duration modifiers. Rates must be locally verified before decision use.",
        "limitations": ["Exposure does not equal verified loss.", "People exposed are not casualty predictions.", "Indirect losses are excluded."],
    }


def analyze_grid_damage(assets: list[dict], simulation: dict, price_year: int = 2025) -> dict[str, Any]:
    """Sample simulated maximum depth at point assets; no polygon/global-depth shortcut."""
    terrain = simulation["terrain"]
    width, height = simulation["width"], simulation["height"]
    depths = simulation["maximum_depth_m"]
    items: list[dict] = []
    seen: set[str] = set()
    central_total = 0.0
    people = 0
    for index, asset in enumerate(assets):
        asset_id = str(asset.get("id") or f"asset-{index}")
        if asset_id in seen or asset.get("lon") is None or asset.get("lat") is None:
            continue
        seen.add(asset_id)
        col = math.floor((float(asset["lon"]) - terrain["west"]) / terrain["lon_step"])
        row = math.floor((terrain["north"] - float(asset["lat"])) / terrain["lat_step"])
        if not (0 <= row < height and 0 <= col < width):
            continue
        depth = float(depths[row * width + col])
        if depth < 0.1:
            continue
        fraction = interpolate_damage_fraction(str(asset.get("type", "other")), depth)
        value = float(asset.get("quantity", 1.0)) * float(asset.get("unit_cost_inr", 0.0))
        loss = value * fraction
        central_total += loss
        people += int(asset.get("people", 0))
        items.append({
            "asset_id": asset_id, "name": asset.get("name", asset_id), "type": asset.get("type", "other"),
            "row": row, "col": col, "depth_m": round(depth, 3), "damage_fraction": round(fraction, 4),
            "quantity": float(asset.get("quantity", 1.0)), "unit": asset.get("unit", "asset"),
            "unit_cost_inr": float(asset.get("unit_cost_inr", 0.0)), "replacement_value_inr": round(value, 2),
            "loss_low_inr": round(loss * 0.7, 2), "loss_central_inr": round(loss, 2),
            "loss_high_inr": round(loss * 1.35, 2), "cost_source": asset.get("cost_source"),
            "confidence": asset.get("confidence", "unverified"),
            "exposure_basis": "point sampled from 2-D maximum-depth grid",
        })
    return {
        "currency": "INR", "price_year": price_year, "items": items,
        "unique_assets_assessed": len(items), "people_potentially_exposed": people,
        "totals": {"low_inr": round(central_total * 0.7, 2), "central_inr": round(central_total, 2),
                   "high_inr": round(central_total * 1.35, 2)},
        "method": "Point assets sampled at maximum simulated depth; illustrative depth-damage curves. No speed, duration, indirect loss, or surveyed footprint correction.",
        "limitations": ["A point is not a building footprint.", "Terrain and boundary conditions are uncalibrated.",
                        "Synthetic demo asset positions and costs are invented.", "People exposed are not casualty predictions."],
    }
