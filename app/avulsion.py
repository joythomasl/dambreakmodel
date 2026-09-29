from __future__ import annotations

from typing import Any


def assess_avulsion(candidates: list[dict], hazard: dict) -> dict[str, Any]:
    """Screen user-derived alternative flow paths without inventing terrain data.

    Candidate metrics should be measured from a common DEM/vertical datum.  The
    result is a relative susceptibility indicator, not a river-course forecast.
    """
    if not candidates:
        return {
            "status": "not_assessed",
            "reason": "No DEM-derived candidate paths were imported.",
            "candidates": [],
            "method": "relative elevation, slope, proximity and scenario depth screening",
        }
    depth = float(hazard["maximum_depth_m"])
    results = []
    for candidate in candidates:
        current_elevation = float(candidate["current_channel_elevation_m"])
        candidate_elevation = float(candidate["candidate_elevation_m"])
        current_slope = max(0.00001, float(candidate["slope_current"]))
        candidate_slope = max(0.0, float(candidate["slope_candidate"]))
        distance = max(0.0, float(candidate["distance_to_channel_m"]))
        relief_advantage = max(0.0, current_elevation - candidate_elevation)
        slope_advantage = max(0.0, (candidate_slope - current_slope) / current_slope)
        relief_score = min(1.0, relief_advantage / 5.0)
        slope_score = min(1.0, slope_advantage / 1.5)
        proximity_score = max(0.0, 1.0 - distance / 1000.0)
        overtopping_score = min(1.0, depth / max(0.25, relief_advantage + 0.25))
        score = 100.0 * (0.32 * relief_score + 0.28 * slope_score + 0.18 * proximity_score + 0.22 * overtopping_score)
        category = "high" if score >= 67 else "moderate" if score >= 34 else "low"
        results.append({
            "id": candidate.get("id"),
            "name": candidate["name"],
            "score": round(score, 1),
            "category": category,
            "relief_advantage_m": round(relief_advantage, 3),
            "slope_ratio": round(candidate_slope / current_slope, 3),
            "distance_to_channel_m": distance,
            "evidence_source": candidate["evidence_source"],
            "source_url": candidate["source_url"],
            "geometry": candidate.get("geometry"),
        })
    results.sort(key=lambda item: item["score"], reverse=True)
    return {
        "status": "screened",
        "candidates": results,
        "highest_category": results[0]["category"],
        "method": "relative elevation, slope, proximity and scenario depth screening",
        "warning": "Susceptibility is not a probability. Confirm with multi-date imagery, sediment evidence and a calibrated 2-D model.",
    }
