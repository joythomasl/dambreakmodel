"""Small, mass-conserving 2-D local-inertial flood simulation.

This executes a depth-averaged numerical model; it is NOT D-Flow FM, SPH, a
surveyed river mesh, or a validated operational inundation forecast. The
upstream inflow is spread over an assumed north-edge inlet and the open domain
edges use a critical-flow approximation. Those boundary assumptions are
deliberately exposed in the result.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from pathlib import Path


TERRAIN_PATH = Path(__file__).resolve().parent / "data" / "rishikesh_terrain.json"
STRUCTURES_PATH = Path(__file__).resolve().parent / "data" / "rishikesh_structures.json"
G = 9.81


def load_terrain() -> dict:
    terrain = json.loads(TERRAIN_PATH.read_text(encoding="utf-8"))
    width, height = terrain["width"], terrain["height"]
    if width < 3 or height < 3 or len(terrain["elevation_m"]) != height:
        raise ValueError("Terrain dimensions are invalid")
    if any(len(row) != width for row in terrain["elevation_m"]):
        raise ValueError("Terrain row width is inconsistent")
    if terrain["cell_size_m"] <= 0:
        raise ValueError("Terrain cell size must be positive")
    return terrain


def load_structures() -> dict:
    """Load cached, attributed OSM footprints; an absent cache is explicit."""
    if not STRUCTURES_PATH.exists():
        return {
            "id": "structures-not-cached", "label": "No cached mapped structures",
            "source": "OpenStreetMap contributors", "source_url": "https://www.openstreetmap.org/copyright",
            "height_note": "No footprints loaded.", "structures": [],
        }
    data = json.loads(STRUCTURES_PATH.read_text(encoding="utf-8"))
    required = {"id", "source", "source_url", "height_note", "structures"}
    if not required.issubset(data):
        raise ValueError("Structure cache metadata is incomplete")
    return data


def _interpolator(points: list[dict]):
    if not points:
        raise ValueError("Hydrograph is empty")
    series = sorted((datetime.fromisoformat(p["time"].replace("Z", "+00:00")).timestamp(),
                     max(0.0, float(p["flow_cumecs"]))) for p in points)

    def at(instant: float) -> float:
        if instant <= series[0][0]:
            return series[0][1]
        for (t0, q0), (t1, q1) in zip(series, series[1:]):
            if instant <= t1:
                return q0 + (q1 - q0) * (instant - t0) / max(t1 - t0, 1e-9)
        return series[-1][1]

    return at


def _condition_channel(terrain: dict, coordinates: list[list[float]], width_m: float = 200.0,
                       longitudinal_fall_m: float = 4.0) -> tuple[dict, dict]:
    """Burn a smooth, explicitly assumed river corridor into a coarse DEM.

    Public global DEMs commonly contain noisy or discontinuous elevations over
    water. The supplied line must be a mapped upstream-to-downstream centreline.
    This is terrain conditioning for routing, not surveyed bathymetry.
    """
    width, height = int(terrain["width"]), int(terrain["height"])
    west, north = float(terrain["west"]), float(terrain["north"])
    lon_step, lat_step = float(terrain["lon_step"]), float(terrain["lat_step"])
    cell = float(terrain["cell_size_m"])
    grid_points = [((lon - west) / lon_step, (north - lat) / lat_step)
                   for lon, lat in coordinates]
    path: list[tuple[int, int]] = []
    for (c0, r0), (c1, r1) in zip(grid_points, grid_points[1:]):
        steps = max(1, int(math.ceil(max(abs(c1 - c0), abs(r1 - r0)) * 4)))
        for step in range(steps + 1):
            fraction = step / steps
            col = round(c0 + (c1 - c0) * fraction)
            row = round(r0 + (r1 - r0) * fraction)
            if 0 <= col < width and 0 <= row < height and (row, col) not in path:
                path.append((row, col))
    if len(path) < 2:
        return terrain, {"applied": False, "reason": "Centreline does not cross the model domain."}

    elevations = [[float(value) for value in row] for row in terrain["elevation_m"]]
    head_samples = [elevations[row][col] for row, col in path[:max(3, min(10, len(path)))]]
    upstream_level = statistics.median(head_samples)
    radius = max(1, round(width_m / cell / 2))
    targets: dict[tuple[int, int], float] = {}
    for index, (row, col) in enumerate(path):
        progress = index / max(1, len(path) - 1)
        centre = upstream_level - longitudinal_fall_m * progress
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                distance = math.hypot(dr, dc)
                rr, cc = row + dr, col + dc
                if distance <= radius and 0 <= rr < height and 0 <= cc < width:
                    target = centre + 0.45 * distance
                    key = (rr, cc)
                    targets[key] = min(targets.get(key, target), target)
    for (row, col), target in targets.items():
        elevations[row][col] = target

    conditioned = {**terrain, "elevation_m": elevations}
    entry_col = path[0][1]
    inlet_columns = [col for col in range(max(0, entry_col - radius), min(width, entry_col + radius + 1))]
    return conditioned, {
        "applied": True,
        "method": "OSM centreline-conditioned trapezoidal corridor",
        "survey_status": "assumed channel geometry; not surveyed bathymetry",
        "width_m": width_m,
        "longitudinal_fall_m": longitudinal_fall_m,
        "conditioned_cells": len(targets),
        "path_cells": len(path),
        "inlet_columns": inlet_columns,
    }


def simulate_inundation(
    hydrograph: list[dict], *, start_time: str, terrain: dict | None = None,
    duration_s: int = 2400, frame_interval_s: int = 300, manning_n: float = 0.035,
    open_boundaries: tuple[str, ...] | list[str] = ("west", "east", "south"),
    channel_coordinates: list[list[float]] | None = None,
) -> dict:
    """Route a supplied boundary hydrograph over terrain and return depth frames.

    Face discharge is updated using a local-inertial approximation to the
    depth-averaged shallow-water equations, with Manning friction. Every face
    flux is limited by water available in its donor cell, so water cannot be
    created by wet/dry transitions. Source and boundary volumes are reported.
    """
    terrain = terrain or load_terrain()
    channel = {"applied": False, "reason": "No mapped centreline supplied."}
    if channel_coordinates:
        terrain, channel = _condition_channel(terrain, channel_coordinates)
    width, height = int(terrain["width"]), int(terrain["height"])
    cell = float(terrain["cell_size_m"])
    area = cell * cell
    if not (60 <= duration_s <= 7200 and 30 <= frame_interval_s <= duration_s):
        raise ValueError("Duration or frame interval is outside the supported range")
    if not 0.01 <= manning_n <= 0.2:
        raise ValueError("Manning n must be between 0.01 and 0.2")
    allowed_boundaries = {"west", "east", "south"}
    open_boundaries = tuple(open_boundaries)
    if not open_boundaries or not set(open_boundaries).issubset(allowed_boundaries):
        raise ValueError("Open boundaries must contain west, east and/or south")
    bed = [float(value) for row in terrain["elevation_m"] for value in row]
    size = width * height
    h = [0.0] * size
    qx = [0.0] * (height * (width - 1))
    qy = [0.0] * ((height - 1) * width)
    maximum = [0.0] * size
    arrival = [None] * size
    start_seconds = datetime.fromisoformat(start_time.replace("Z", "+00:00")).timestamp()
    inflow_at = _interpolator(hydrograph)
    inlet = channel.get("inlet_columns") or sorted(range(width // 2, width), key=lambda col: bed[col])[:4]
    frames: list[dict] = [{"time_s": 0, "depth_m": [0.0] * size}]
    next_frame = frame_interval_s
    t = 0.0
    total_in = total_out = 0.0
    steps = 0
    while t < duration_s - 1e-9:
        max_h = max(h)
        dt_cfl = 0.4 * cell / math.sqrt(2 * G * max(max_h, 0.05))
        dt = min(10.0, dt_cfl, duration_s - t, next_frame - t)
        if dt <= 0:
            break
        steps += 1
        # Update interior x-faces. qx is discharge per metre of face width.
        for row in range(height):
            base = row * width
            face_base = row * (width - 1)
            for col in range(width - 1):
                left, right = base + col, base + col + 1
                eta_l, eta_r = bed[left] + h[left], bed[right] + h[right]
                wet_depth = max(0.0, max(eta_l, eta_r) - max(bed[left], bed[right]))
                face = face_base + col
                if wet_depth < 1e-5:
                    qx[face] = 0.0
                    continue
                old = qx[face]
                friction = 1.0 + G * manning_n**2 * dt * abs(old) / max(wet_depth, 0.01)**(7.0 / 3.0)
                qx[face] = (old - G * wet_depth * dt * (eta_r - eta_l) / cell) / friction
        # Update interior y-faces; rows increase southward.
        for row in range(height - 1):
            base = row * width
            for col in range(width):
                north, south = base + col, base + col + width
                eta_n, eta_s = bed[north] + h[north], bed[south] + h[south]
                wet_depth = max(0.0, max(eta_n, eta_s) - max(bed[north], bed[south]))
                face = base + col
                if wet_depth < 1e-5:
                    qy[face] = 0.0
                    continue
                old = qy[face]
                friction = 1.0 + G * manning_n**2 * dt * abs(old) / max(wet_depth, 0.01)**(7.0 / 3.0)
                qy[face] = (old - G * wet_depth * dt * (eta_s - eta_n) / cell) / friction
        # A critical-flow approximation lets water leave the west/east/south
        # domain edges. The north edge is closed except for the assumed inlet.
        boundary = [0.0] * size
        outgoing = [0.0] * size
        for row in range(height):
            for col in range(width):
                idx = row * width + col
                if h[idx] <= 0:
                    continue
                edges = (int(col == 0 and "west" in open_boundaries) +
                         int(col == width - 1 and "east" in open_boundaries) +
                         int(row == height - 1 and "south" in open_boundaries))
                boundary[idx] = edges * h[idx] * math.sqrt(G * h[idx]) * cell * dt
                outgoing[idx] += boundary[idx]
        for row in range(height):
            for col in range(width - 1):
                face = row * (width - 1) + col
                flux = qx[face] * cell * dt
                donor = row * width + (col if flux >= 0 else col + 1)
                outgoing[donor] += abs(flux)
        for row in range(height - 1):
            for col in range(width):
                face = row * width + col
                flux = qy[face] * cell * dt
                donor = row * width + (col if flux >= 0 else col + width)
                outgoing[donor] += abs(flux)
        supply = [min(1.0, h[idx] * area / volume) if volume > 0 else 1.0
                  for idx, volume in enumerate(outgoing)]
        delta = [0.0] * size
        for row in range(height):
            for col in range(width - 1):
                face = row * (width - 1) + col
                left = row * width + col
                right = left + 1
                volume = qx[face] * cell * dt * supply[left if qx[face] >= 0 else right]
                qx[face] = volume / (cell * dt)
                delta[left] -= volume
                delta[right] += volume
        for row in range(height - 1):
            for col in range(width):
                face = row * width + col
                north = row * width + col
                south = north + width
                volume = qy[face] * cell * dt * supply[north if qy[face] >= 0 else south]
                qy[face] = volume / (cell * dt)
                delta[north] -= volume
                delta[south] += volume
        for idx, volume in enumerate(boundary):
            leaving = volume * supply[idx]
            delta[idx] -= leaving
            total_out += leaving
        supplied = inflow_at(start_seconds + t + dt / 2) * dt
        total_in += supplied
        for col in inlet:
            delta[col] += supplied / len(inlet)
        for idx in range(size):
            h[idx] = max(0.0, h[idx] + delta[idx] / area)
            if h[idx] > maximum[idx]:
                maximum[idx] = h[idx]
            if h[idx] >= 0.1 and arrival[idx] is None:
                arrival[idx] = round(t + dt, 1)
        t += dt
        if t >= next_frame - 1e-8:
            frames.append({"time_s": round(t), "depth_m": [round(v, 3) for v in h]})
            next_frame += frame_interval_s
    stored = sum(h) * area
    mass_error = total_in - total_out - stored
    downstream_cells = list(range((height - 1) * width, height * width))
    downstream_arrivals = [arrival[index] for index in downstream_cells if arrival[index] is not None]
    return {
        "engine": "executed_2d_local_inertial_shallow_water",
        "solver_family": "depth-averaged local-inertial approximation, not D-Flow FM or SPH",
        "terrain": {key: value for key, value in terrain.items() if key != "elevation_m"},
        "elevation_m": bed,
        "width": width, "height": height, "cell_size_m": cell,
        "inlet_cells": inlet, "inlet_boundary": "north", "open_boundaries": list(open_boundaries),
        "channel_conditioning": channel,
        "start_time": start_time, "duration_s": duration_s, "frame_interval_s": frame_interval_s,
        "manning_n_assumed": manning_n, "time_steps": steps,
        "frames": frames, "maximum_depth_m": [round(v, 3) for v in maximum],
        "arrival_s": arrival,
        "volume": {"inflow_m3": round(total_in, 2), "outflow_m3": round(total_out, 2),
                   "stored_m3": round(stored, 2), "mass_balance_error_m3": round(mass_error, 4)},
        "wet_cell_count": sum(v >= 0.1 for v in maximum),
        "peak_depth_m": round(max(maximum), 3),
        "downstream_reached": bool(downstream_arrivals),
        "downstream_arrival_s": min(downstream_arrivals) if downstream_arrivals else None,
        "downstream_wet_cells": sum(maximum[index] >= 0.1 for index in downstream_cells),
        "warning": "Uncalibrated, coarse-grid local flood simulation. No surveyed bathymetry/structures; boundary placement and Manning n are assumptions. Do not use for warnings or damage estimates without validation.",
    }
