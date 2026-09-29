"""Build cached satellite, road, label and reservoir-corridor context.

The hydraulic grid remains the local Rishikesh model.  The wider terrain is a
presentation/context view from Tehri Reservoir to Rishikesh and is never
reported as a continuous hydraulic solve.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.build_terrain import _decode_png_rgb


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"
STATIC_DATA = ROOT / "app" / "static" / "data"
LOCAL_TERRAIN = DATA / "rishikesh_terrain.json"
SITE = DATA / "site_tehri.json"
LOCAL_CONTEXT = DATA / "rishikesh_context.json"
REGIONAL_TERRAIN = DATA / "tehri_rishikesh_terrain.json"
REGIONAL_CONTEXT = DATA / "tehri_rishikesh_context.json"
MAP_ENDPOINT = "https://api.openstreetmap.org/api/0.6/map"
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium"
SATELLITE_WMS = "https://tiles.maps.eox.at/map"
SATELLITE_ATTRIBUTION = "Sentinel-2 cloudless 2024 by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2024)"
SATELLITE_LICENSE = "CC BY-NC-SA 4.0; non-commercial use and attribution required"
REGIONAL_BOUNDS = {"west": 78.23, "south": 30.05, "east": 78.63, "north": 30.43}


def _request(url: str, *, data: bytes | None = None, timeout: int = 120) -> bytes:
    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "HYDRA-SIH-geocontext/1.0 (educational prototype)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _bounds(terrain: dict) -> dict[str, float]:
    return {
        "west": terrain["west"],
        "north": terrain["north"],
        "east": terrain["west"] + terrain["width"] * terrain["lon_step"],
        "south": terrain["north"] - terrain["height"] * terrain["lat_step"],
    }


def _satellite(bounds: dict[str, float], filename: str, width: int, height: int) -> dict:
    query = urllib.parse.urlencode({
        "service": "WMS", "request": "GetMap", "version": "1.1.1",
        "layers": "s2cloudless-2024", "styles": "", "format": "image/jpeg",
        "srs": "EPSG:4326",
        "bbox": f"{bounds['west']},{bounds['south']},{bounds['east']},{bounds['north']}",
        "width": str(width), "height": str(height),
    })
    data = _request(f"{SATELLITE_WMS}?{query}")
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("Satellite WMS did not return JPEG imagery")
    STATIC_DATA.mkdir(parents=True, exist_ok=True)
    (STATIC_DATA / filename).write_bytes(data)
    return {
        "url": f"/static/data/{filename}", "width": width, "height": height,
        "bounds": bounds, "source": "EOxCloudless Sentinel-2 cloudless 2024",
        "source_url": "https://s2maps.eu/", "attribution": SATELLITE_ATTRIBUTION,
        "license": SATELLITE_LICENSE,
        "purpose": "visual terrain texture only; not used as a hydraulic input",
    }


def _simplify(points: list[list[float]], tolerance: float = 0.00008) -> list[list[float]]:
    if len(points) <= 2:
        return points
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    denominator = dx * dx + dy * dy
    best_distance, best_index = 0.0, 0
    for index, point in enumerate(points[1:-1], start=1):
        if denominator == 0:
            distance = math.hypot(point[0] - start[0], point[1] - start[1])
        else:
            ratio = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denominator))
            projected = [start[0] + ratio * dx, start[1] + ratio * dy]
            distance = math.hypot(point[0] - projected[0], point[1] - projected[1])
        if distance > best_distance:
            best_distance, best_index = distance, index
    if best_distance <= tolerance:
        return [start, end]
    return _simplify(points[:best_index + 1], tolerance)[:-1] + _simplify(points[best_index:], tolerance)


def _local_osm(bounds: dict[str, float]) -> tuple[list[dict], list[dict]]:
    url = f"{MAP_ENDPOINT}?bbox={bounds['west']},{bounds['south']},{bounds['east']},{bounds['north']}"
    root = ET.fromstring(_request(url))
    node_elements = {node.attrib["id"]: node for node in root.findall("node")}
    nodes = {node_id: [float(node.attrib["lon"]), float(node.attrib["lat"])] for node_id, node in node_elements.items()}
    roads = []
    labels = []
    label_seen = set()
    for node in node_elements.values():
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in node.findall("tag")}
        name = tags.get("name:en") or tags.get("name")
        if not name or not ({"place", "amenity", "railway", "tourism"} & tags.keys()):
            continue
        key = name.casefold()
        if key in label_seen:
            continue
        label_seen.add(key)
        labels.append({"name": name, "kind": tags.get("place") or tags.get("amenity") or tags.get("railway") or tags.get("tourism") or "place", "lon": float(node.attrib["lon"]), "lat": float(node.attrib["lat"])})
    accepted = {"motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "service", "track"}
    for way in root.findall("way"):
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
        highway = tags.get("highway")
        if highway not in accepted:
            continue
        coordinates = [nodes[ref.attrib["ref"]] for ref in way.findall("nd") if ref.attrib["ref"] in nodes]
        if len(coordinates) < 2:
            continue
        coordinates = _simplify(coordinates)
        roads.append({"id": f"osm-way-{way.attrib['id']}", "name": tags.get("name:en") or tags.get("name") or tags.get("ref"), "kind": highway, "coordinates": coordinates})
    named_roads = [road for road in roads if road.get("name") and road["kind"] in {"trunk", "primary", "secondary", "tertiary"}]
    for road in named_roads:
        midpoint = road["coordinates"][len(road["coordinates"]) // 2]
        key = road["name"].casefold()
        if key not in label_seen:
            label_seen.add(key)
            labels.append({"name": road["name"], "kind": "road", "lon": midpoint[0], "lat": midpoint[1]})
    return roads[:900], labels[:80]


def _regional_osm(bounds: dict[str, float]) -> tuple[list[dict], list[dict], list[dict], str]:
    bbox = f"{bounds['south']},{bounds['west']},{bounds['north']},{bounds['east']}"
    query = f'''[out:json][timeout:150];(
      way[highway~"trunk|primary|secondary"]({bbox});
      way[waterway=river][name]({bbox});
      node[place~"city|town|village"]({bbox});
    );out tags geom;'''
    payload = None
    endpoint_used = ""
    last_error = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            payload = json.loads(_request(endpoint, data=urllib.parse.urlencode({"data": query}).encode("utf-8"), timeout=180).decode("utf-8"))
            endpoint_used = endpoint
            break
        except Exception as exc:
            last_error = exc
    if payload is None:
        raise RuntimeError(f"Regional OSM download failed: {last_error}")
    roads, waterways, places = [], [], []
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        if element.get("type") == "node" and tags.get("place"):
            places.append({"name": tags.get("name:en") or tags.get("name") or "Mapped place", "kind": tags["place"], "lon": element["lon"], "lat": element["lat"]})
            continue
        coordinates = [[float(point["lon"]), float(point["lat"])] for point in element.get("geometry", [])]
        if len(coordinates) < 2:
            continue
        item = {"id": f"osm-way-{element['id']}", "name": tags.get("name:en") or tags.get("name") or tags.get("ref"), "coordinates": _simplify(coordinates, 0.0003)}
        if tags.get("highway"):
            item["kind"] = tags["highway"]
            roads.append(item)
        elif tags.get("waterway"):
            item["kind"] = tags["waterway"]
            waterways.append(item)
    return roads, waterways, places, endpoint_used


def _world_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    scale = 256 * 2**zoom
    x = (lon + 180.0) / 360.0 * scale
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * scale
    return x, y


def _regional_elevation(bounds: dict[str, float], width: int = 96, height: int = 96, zoom: int = 10) -> dict:
    cache = {}
    urls = set()
    elevations = []
    for row in range(height):
        lat = bounds["north"] - (row + 0.5) / height * (bounds["north"] - bounds["south"])
        for col in range(width):
            lon = bounds["west"] + (col + 0.5) / width * (bounds["east"] - bounds["west"])
            px, py = _world_pixel(lon, lat, zoom)
            tx, ty = int(px // 256), int(py // 256)
            if (tx, ty) not in cache:
                url = f"{TERRARIUM}/{zoom}/{tx}/{ty}.png"
                cache[(tx, ty)] = _decode_png_rgb(_request(url, timeout=60))
                urls.add(url)
            _, _, tile_rows = cache[(tx, ty)]
            pixel_x, pixel_y = int(px) % 256, int(py) % 256
            base = pixel_x * 3
            red, green, blue = tile_rows[pixel_y][base:base + 3]
            elevations.append(round(red * 256 + green + blue / 256 - 32768, 1))
    center_lat = (bounds["north"] + bounds["south"]) / 2
    cell_x = (bounds["east"] - bounds["west"]) * 111_320 * math.cos(math.radians(center_lat)) / width
    cell_y = (bounds["north"] - bounds["south"]) * 111_320 / height
    return {
        "id": "tehri-rishikesh-mapzen-regional-v1", "label": "Regional context terrain; not a hydraulic mesh",
        "source": "Mapzen Terrain Tiles / AWS Open Data; underlying DEM sources vary by tile",
        "source_registry": "https://registry.opendata.aws/terrain-tiles/", "tiles": sorted(urls),
        "coordinate_system": "EPSG:4326", "bounds": bounds, "west": bounds["west"], "north": bounds["north"],
        "lon_step": (bounds["east"] - bounds["west"]) / width, "lat_step": (bounds["north"] - bounds["south"]) / height,
        "width": width, "height": height, "cell_size_m": round((cell_x + cell_y) / 2, 1), "elevation_m": elevations,
        "limitations": "Regional display sampled at approximately 400 m. It is visual context from Tehri Reservoir to Rishikesh, not the executed inundation grid.",
    }


def main() -> None:
    local_terrain = json.loads(LOCAL_TERRAIN.read_text(encoding="utf-8"))
    site = json.loads(SITE.read_text(encoding="utf-8"))
    local_bounds = _bounds(local_terrain)
    local_roads, local_labels = _local_osm(local_bounds)
    local = {
        "id": "rishikesh-satellite-osm-context-v1", "bounds": local_bounds,
        "satellite": _satellite(local_bounds, "rishikesh_sentinel2_2024.jpg", 1280, 900),
        "roads": local_roads, "labels": local_labels,
        "roads_source": "OpenStreetMap contributors", "roads_source_url": "https://www.openstreetmap.org/copyright",
        "roads_license": "Open Database License (ODbL); attribution required",
    }
    LOCAL_CONTEXT.write_text(json.dumps(local, indent=2, ensure_ascii=False), encoding="utf-8")

    regional_terrain = _regional_elevation(REGIONAL_BOUNDS)
    regional_terrain["satellite"] = _satellite(REGIONAL_BOUNDS, "tehri_rishikesh_sentinel2_2024.jpg", 1600, 1300)
    REGIONAL_TERRAIN.write_text(json.dumps(regional_terrain, indent=2, ensure_ascii=False), encoding="utf-8")
    roads, waterways, places, endpoint = _regional_osm(REGIONAL_BOUNDS)
    regional = {
        "id": "tehri-rishikesh-osm-context-v1", "bounds": REGIONAL_BOUNDS,
        "roads": roads, "waterways": waterways, "places": places,
        "cascade_nodes": site["nodes"], "download_endpoint": endpoint,
        "source": "OpenStreetMap contributors", "source_url": "https://www.openstreetmap.org/copyright",
        "license": "Open Database License (ODbL); attribution required",
        "limitations": "Roads, rivers and place names are community mapped. The straight node-to-node cascade overlay is schematic and does not replace a hydraulic river centreline.",
    }
    REGIONAL_CONTEXT.write_text(json.dumps(regional, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Local context: {len(local_roads)} roads, {len(local_labels)} labels")
    print(f"Regional context: {len(roads)} roads, {len(waterways)} rivers, {len(places)} places")
    print(f"Regional terrain: {regional_terrain['width']}x{regional_terrain['height']}; {min(regional_terrain['elevation_m'])}..{max(regional_terrain['elevation_m'])} m")


if __name__ == "__main__":
    main()
