"""Cache OpenStreetMap structure footprints inside the Rishikesh terrain grid.

The checked-in result lets the demonstration run offline. Footprints and tags
are community-mapped OSM data (ODbL); absent heights are explicitly estimated
for display and never represented as surveyed geometry.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "app" / "data" / "rishikesh_terrain.json"
OUTPUT = ROOT / "app" / "data" / "rishikesh_structures.json"
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
MAP_ENDPOINT = "https://api.openstreetmap.org/api/0.6/map"


def _number(value: object) -> float | None:
    try:
        text = str(value).lower().replace("metres", "").replace("meters", "").replace("m", "").strip()
        return float(text.split(";")[0])
    except (TypeError, ValueError):
        return None


def _height(tags: dict) -> tuple[float, str]:
    mapped = _number(tags.get("height"))
    if mapped and 1.5 <= mapped <= 150:
        return mapped, "osm_height"
    levels = _number(tags.get("building:levels"))
    if levels and 1 <= levels <= 40:
        return levels * 3.0, "osm_levels_x_3m"
    kind = tags.get("building", "yes")
    return (4.0 if kind in {"hut", "shed", "garage", "roof"} else 7.5), "estimated_from_type"


def _area_m2(ring: list[list[float]], latitude: float) -> float:
    sx = 111_320.0 * math.cos(math.radians(latitude))
    sy = 111_320.0
    return abs(sum((a[0] * sx) * (b[1] * sy) - (b[0] * sx) * (a[1] * sy)
                   for a, b in zip(ring, ring[1:] + ring[:1]))) / 2


def main() -> None:
    terrain = json.loads(TERRAIN.read_text(encoding="utf-8"))
    west = terrain["west"]
    east = west + terrain["width"] * terrain["lon_step"]
    north = terrain["north"]
    south = north - terrain["height"] * terrain["lat_step"]
    elements_by_id = {}
    endpoint_used = None
    map_error = None
    try:
        map_url = f"{MAP_ENDPOINT}?bbox={west},{south},{east},{north}"
        request = urllib.request.Request(map_url, headers={"User-Agent": "JalDrishti-SIH-structure-cache/1.0 (educational prototype)"})
        with urllib.request.urlopen(request, timeout=120) as response:
            root = ET.fromstring(response.read())
        nodes = {node.attrib["id"]: {"lat": float(node.attrib["lat"]), "lon": float(node.attrib["lon"])}
                 for node in root.findall("node")}
        for way in root.findall("way"):
            tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
            if "building" not in tags:
                continue
            geometry = [nodes[ref.attrib["ref"]] for ref in way.findall("nd") if ref.attrib["ref"] in nodes]
            if len(geometry) >= 4:
                elements_by_id[int(way.attrib["id"])] = {"id": int(way.attrib["id"]), "tags": tags, "geometry": geometry}
        endpoint_used = MAP_ENDPOINT
    except Exception as exc:
        map_error = str(exc)

    failed_tiles = []
    rows, columns = 3, 4
    for row in range(rows if not elements_by_id else 0):
        tile_south = south + (north - south) * row / rows
        tile_north = south + (north - south) * (row + 1) / rows
        for col in range(columns):
            tile_west = west + (east - west) * col / columns
            tile_east = west + (east - west) * (col + 1) / columns
            query = f"""[out:json][timeout:60];
              way[building]({tile_south},{tile_west},{tile_north},{tile_east});
              out tags geom;
            """
            last_error = None
            for endpoint in ENDPOINTS:
                try:
                    request = urllib.request.Request(
                        endpoint,
                        data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
                        headers={"User-Agent": "JalDrishti-SIH-structure-cache/1.0 (educational prototype)"},
                    )
                    with urllib.request.urlopen(request, timeout=90) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    endpoint_used = endpoint
                    for element in payload.get("elements", []):
                        elements_by_id[element["id"]] = element
                    break
                except Exception as exc:
                    last_error = exc
            else:
                failed_tiles.append({"row": row, "col": col, "error": str(last_error)})
    elements = list(elements_by_id.values())
    structures = []
    for element in elements:
        geometry = element.get("geometry") or []
        ring = [[float(node["lon"]), float(node["lat"])] for node in geometry]
        if len(ring) < 4:
            continue
        if ring[0] == ring[-1]:
            ring.pop()
        area = _area_m2(ring, (south + north) / 2)
        if not 8 <= area <= 80_000:
            continue
        tags = element.get("tags") or {}
        height, basis = _height(tags)
        structures.append({
            "id": f"osm-way-{element['id']}",
            "osm_type": "way", "osm_id": element["id"],
            "name": tags.get("name") or tags.get("name:en"),
            "building": tags.get("building", "yes"),
            "height_m": round(height, 2), "height_basis": basis,
            "area_m2": round(area, 1), "coordinates": ring,
        })
    structures.sort(key=lambda item: (item["height_basis"] != "estimated_from_type", item["area_m2"]), reverse=True)
    total_retained = len(structures)
    structures = structures[:1000]
    if not structures:
        raise RuntimeError("No OSM building footprints were downloaded")
    result = {
        "id": "rishikesh-osm-buildings-v1",
        "label": "OpenStreetMap building footprints in the local Rishikesh terrain domain",
        "source": "OpenStreetMap contributors",
        "source_url": "https://www.openstreetmap.org/copyright",
        "download_endpoint": endpoint_used,
        "license": "Open Database License (ODbL); attribution required",
        "bounds": {"west": west, "south": south, "east": east, "north": north},
        "downloaded_feature_count": len(elements),
        "valid_feature_count": total_retained,
        "retained_feature_count": len(structures),
        "selection_note": "At most 1000 footprints are retained, prioritising mapped heights then larger area, to keep browser playback responsive.",
        "map_download_error": map_error,
        "tile_grid": {"rows": rows, "columns": columns, "used_as_fallback": bool(map_error), "failed_tiles": failed_tiles},
        "height_note": "OSM height/levels are used when present. Missing heights are estimated only for display and are not surveyed.",
        "structures": structures,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    mapped = sum(s["height_basis"] != "estimated_from_type" for s in structures)
    print(f"Wrote {OUTPUT}: {len(structures)} footprints; {mapped} mapped/level-derived heights")


if __name__ == "__main__":
    main()
