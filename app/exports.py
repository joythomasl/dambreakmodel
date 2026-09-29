from __future__ import annotations

import json
import math
import struct
import zipfile
from datetime import date
from pathlib import Path
from typing import Iterable

from .scenario import SCENARIO_DIR


WGS84_PRJ = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'


def _indian_integer(value: float) -> str:
    number = str(abs(int(round(value))))
    if len(number) <= 3:
        grouped = number
    else:
        tail, head = number[-3:], number[:-3]
        pairs = []
        while head:
            pairs.append(head[-2:])
            head = head[:-2]
        grouped = ",".join(reversed(pairs)) + "," + tail
    return ("-" if value < 0 else "") + grouped


def _format_inr(value: float) -> str:
    absolute = abs(value)
    exact = _indian_integer(value)
    if absolute >= 10_000_000:
        return f"INR {value / 10_000_000:.2f} crore ({exact})"
    if absolute >= 100_000:
        return f"INR {value / 100_000:.2f} lakh ({exact})"
    return f"INR {exact}"


def _format_volume(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.3f} MCM"
    return f"{_indian_integer(value)} m³"


def _features(result: dict) -> list[dict]:
    if result.get("spatial_simulation"):
        features = []
        for branch, simulation in result["spatial_simulation"].items():
            terrain = simulation["terrain"]
            west, north = terrain["west"], terrain["north"]
            lon_step, lat_step = terrain["lon_step"], terrain["lat_step"]
            for index, depth in enumerate(simulation["maximum_depth_m"]):
                if depth < 0.1:
                    continue
                row, col = divmod(index, simulation["width"])
                x0, x1 = west + col * lon_step, west + (col + 1) * lon_step
                y0, y1 = north - row * lat_step, north - (row + 1) * lat_step
                properties = {
                    "branch": branch, "cell_row": row, "cell_col": col,
                    "maximum_depth_m": depth, "depth_unit": "m", "cell_size_m": simulation["cell_size_m"],
                    "data_mode": result.get("mode", "live_inputs"),
                    "model_status": "executed, uncalibrated 2-D local-inertial model; not D-Flow FM or SPH",
                    "terrain_source": terrain["source"],
                }
                if result.get("mode") == "offline_demo":
                    properties["warning"] = "SYNTHETIC DEMO HYDROGRAPH - NOT A REAL FLOOD MAP"
                features.append({
                    "type": "Feature", "properties": properties,
                    "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]},
                })
        return features
    features = []
    for branch in result["cascade"]["branches"].values():
        feature = json.loads(json.dumps(branch["rishikesh_hazard"]["extent"]))
        feature["properties"]["data_mode"] = result.get("mode", "live_inputs")
        feature["properties"]["model_status"] = "screening, not calibrated hydraulic output"
        if result.get("mode") == "offline_demo":
            feature["properties"]["warning"] = "SYNTHETIC DEMO - NOT A REAL FLOOD MAP"
        features.append(feature)
    return features


def write_geojson(path: Path, result: dict) -> None:
    path.write_text(json.dumps({"type":"FeatureCollection", "features":_features(result)}, indent=2), encoding="utf-8")


def write_kml(path: Path, result: dict) -> None:
    placemarks = []
    for feature in _features(result):
        props = feature["properties"]
        coords = " ".join(f"{lon},{lat},0" for lon, lat in feature["geometry"]["coordinates"][0])
        placemarks.append(
            f"<Placemark><name>{'SYNTHETIC DEMO - ' if result.get('mode') == 'offline_demo' else ''}{props['branch']}</name>"
            f"<description>Maximum screening depth: {props['maximum_depth_m']} m. {props.get('warning', 'Screening, not an official warning.')}</description>"
            f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        )
    content = '<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>' + "".join(placemarks) + "</Document></kml>"
    path.write_text(content, encoding="utf-8")


def _shape_header(file_length_words: int, bbox: tuple[float, float, float, float]) -> bytes:
    return (
        struct.pack(">7i", 9994, 0, 0, 0, 0, 0, file_length_words)
        + struct.pack("<2i", 1000, 5)
        + struct.pack("<8d", bbox[0], bbox[1], bbox[2], bbox[3], 0.0, 0.0, 0.0, 0.0)
    )


def _polygon_content(coords: list[list[float]]) -> bytes:
    xs, ys = [p[0] for p in coords], [p[1] for p in coords]
    return (
        struct.pack("<i", 5)
        + struct.pack("<4d", min(xs), min(ys), max(xs), max(ys))
        + struct.pack("<2i", 1, len(coords))
        + struct.pack("<i", 0)
        + b"".join(struct.pack("<2d", x, y) for x, y in coords)
    )


def _write_dbf(path: Path, rows: list[dict]) -> None:
    fields = [("NAME", "C", 32, 0), ("DEPTH_M", "N", 12, 3), ("PEAK_CMS", "N", 14, 2),
              ("D_UNIT", "C", 4, 0), ("Q_UNIT", "C", 8, 0), ("DATA_MODE", "C", 20, 0)]
    header_length = 32 + 32 * len(fields) + 1
    record_length = 1 + sum(field[2] for field in fields)
    today = date.today()
    header = struct.pack("<BBBBIHH20x", 3, today.year - 1900, today.month, today.day, len(rows), header_length, record_length)
    descriptors = b""
    for name, field_type, length, decimals in fields:
        name_bytes = name.encode("ascii")[:11].ljust(11, b"\x00")
        descriptors += name_bytes + field_type.encode("ascii") + b"\x00" * 4 + bytes([length, decimals]) + b"\x00" * 14
    records = b""
    for row in rows:
        values = [
            str(row["name"])[:32].ljust(32),
            f"{row['depth']:12.3f}",
            f"{row['peak']:14.2f}",
            "m".ljust(4),
            "m3/s".ljust(8),
            str(row["mode"])[:20].ljust(20),
        ]
        records += b" " + "".join(values).encode("ascii", errors="replace")
    path.write_bytes(header + descriptors + b"\r" + records + b"\x1a")


def write_shapefile_zip(path: Path, result: dict) -> None:
    base = path.parent / "flood_extent"
    features = _features(result)
    contents = [_polygon_content(feature["geometry"]["coordinates"][0]) for feature in features]
    all_points = [point for feature in features for point in feature["geometry"]["coordinates"][0]]
    bbox = (min(p[0] for p in all_points), min(p[1] for p in all_points), max(p[0] for p in all_points), max(p[1] for p in all_points))
    shp_records = []
    shx_records = []
    offset_words = 50
    for index, content in enumerate(contents, start=1):
        length_words = len(content) // 2
        shp_records.append(struct.pack(">2i", index, length_words) + content)
        shx_records.append(struct.pack(">2i", offset_words, length_words))
        offset_words += 4 + length_words
    shp = _shape_header(50 + sum(len(record) for record in shp_records) // 2, bbox) + b"".join(shp_records)
    shx = _shape_header(50 + len(shx_records) * 4, bbox) + b"".join(shx_records)
    base.with_suffix(".shp").write_bytes(shp)
    base.with_suffix(".shx").write_bytes(shx)
    rows = []
    for feature in features:
        branch = feature["properties"]["branch"]
        hazard = result["cascade"]["branches"][branch]["rishikesh_hazard"]
        rows.append({"name":branch, "depth":feature["properties"]["maximum_depth_m"], "peak":hazard["peak_flow_cumecs"], "mode":result.get("mode", "live_inputs")})
    _write_dbf(base.with_suffix(".dbf"), rows)
    base.with_suffix(".prj").write_text(WGS84_PRJ, encoding="ascii")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for suffix in (".shp", ".shx", ".dbf", ".prj"):
            component = base.with_suffix(suffix)
            archive.write(component, component.name)
            component.unlink()


def write_geotiff(path: Path, result: dict, width: int = 64, height: int = 64) -> None:
    if result.get("spatial_simulation"):
        simulation = result["spatial_simulation"]["conditional_secondary_failure"]
        width, height = simulation["width"], simulation["height"]
        pixels = [float(value) for value in simulation["maximum_depth_m"]]
        terrain = simulation["terrain"]
        scale_x, scale_y = terrain["lon_step"], terrain["lat_step"]
        origin_x, origin_y = terrain["west"], terrain["north"]
    else:
        depth = result["cascade"]["branches"]["conditional_secondary_failure"]["rishikesh_hazard"]["maximum_depth_m"]
        pixels = []
        for y in range(height):
            for x in range(width):
                dx, dy = (x - width / 2) / (width / 2), (y - height / 2) / (height / 2)
                value = max(0.0, depth * (1.0 - math.sqrt(dx * dx + dy * dy)))
                pixels.append(float(value))
        scale_x, scale_y = 0.0015, 0.0015
        origin_x, origin_y = 78.22, 30.14
    # Float32 pixels are metres. Earlier builds stored implicit centimetres in
    # UInt16; explicit SI-valued pixels remove that undocumented scale factor.
    raster = struct.pack("<" + "f" * len(pixels), *pixels)

    entries = []
    extras = bytearray()
    entry_count = 15
    base_extra_offset = 8 + 2 + entry_count * 12 + 4

    def add(tag: int, typ: int, count: int, raw: bytes):
        if len(raw) <= 4:
            value = raw.ljust(4, b"\x00")
        else:
            while len(extras) % 2:
                extras.extend(b"\x00")
            offset = base_extra_offset + len(extras)
            value = struct.pack("<I", offset)
            extras.extend(raw)
        entries.append((tag, typ, count, value))

    add(256, 4, 1, struct.pack("<I", width))
    add(257, 4, 1, struct.pack("<I", height))
    description = b"Maximum flood depth; unit=metre (m); horizontal CRS=EPSG:4326\x00"
    add(258, 3, 1, struct.pack("<H", 32))
    add(270, 2, len(description), description)
    add(259, 3, 1, struct.pack("<H", 1))
    add(262, 3, 1, struct.pack("<H", 1))
    strip_offset_placeholder = len(entries)
    add(273, 4, 1, struct.pack("<I", 0))
    add(277, 3, 1, struct.pack("<H", 1))
    add(278, 4, 1, struct.pack("<I", height))
    add(279, 4, 1, struct.pack("<I", len(raster)))
    add(284, 3, 1, struct.pack("<H", 1))
    add(339, 3, 1, struct.pack("<H", 3))
    add(33550, 12, 3, struct.pack("<3d", scale_x, scale_y, 0.0))
    add(33922, 12, 6, struct.pack("<6d", 0.0, 0.0, 0.0, origin_x, origin_y, 0.0))
    geokeys = (1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 1, 2048, 0, 1, 4326)
    add(34735, 3, len(geokeys), struct.pack("<" + "H" * len(geokeys), *geokeys))

    raster_offset = base_extra_offset + len(extras)
    tag, typ, count, _ = entries[strip_offset_placeholder]
    entries[strip_offset_placeholder] = (tag, typ, count, struct.pack("<I", raster_offset))
    ifd = struct.pack("<H", len(entries)) + b"".join(struct.pack("<HHI", tag, typ, count) + value for tag, typ, count, value in sorted(entries)) + struct.pack("<I", 0)
    path.write_bytes(b"II" + struct.pack("<HI", 42, 8) + ifd + extras + raster)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1", errors="replace").decode("latin-1")


def write_pdf(path: Path, result: dict) -> None:
    lines = [
        "SIH Flood Scenario Report",
        f"Data mode: {result.get('mode', 'live_inputs')}",
        f"Site: {result['site']['name']}",
        f"Scenario ID: {result['id']}",
        f"Event type: {result['config']['event_type']}",
        "Units: SI; Indian number grouping; times in IST unless an offset is printed",
        "STATUS: DECISION-SUPPORT SCREENING - NOT AN OFFICIAL WARNING",
        "",
        "Cascade comparison",
    ]
    if result.get("mode") == "offline_demo":
        lines.insert(1, "SYNTHETIC DEMONSTRATION - NOT OBSERVED OR PREDICTED FLOOD DATA")
        lines.insert(2, "Water, rainfall, assets and INR unit rates are invented for software testing.")
    for name, branch in result["cascade"]["branches"].items():
        hazard = branch["rishikesh_hazard"]
        damage = result["damage"][name]
        lines.extend([
            f"{name}: arrival {hazard['arrival_time']}",
            f"  peak discharge {hazard['peak_flow_cumecs']} m³/s; depth {hazard['maximum_depth_m']} m; speed {hazard['maximum_speed_mps']} m/s",
            f"  people potentially exposed {_indian_integer(damage['people_potentially_exposed'])}; central direct loss {_format_inr(damage['totals']['central_inr'])}",
        ])
    if result.get("spatial_simulation"):
        lines.extend(["", "Executed local 2-D simulation (NOT Delft3D or SPH)"])
        for name, simulation in result["spatial_simulation"].items():
            assessed = result["spatial_damage"][name]
            lines.extend([
                f"{name}: {simulation['wet_cell_count']} wet cells; peak grid depth {simulation['peak_depth_m']} m",
                f"  inflow {_format_volume(simulation['volume']['inflow_m3'])}; outflow {_format_volume(simulation['volume']['outflow_m3'])}; stored {_format_volume(simulation['volume']['stored_m3'])}",
                f"  water-balance error {simulation['volume']['mass_balance_error_m3']:.3f} m³",
                f"  grid-sampled illustrative direct loss {_format_inr(assessed['totals']['central_inr'])}; {_indian_integer(assessed['unique_assets_assessed'])} wet point assets",
            ])
        cell_size = result["spatial_simulation"]["conditional_secondary_failure"]["cell_size_m"]
        structure_context = result.get("spatial_context", {}).get("structures", {})
        structure_count = len(structure_context.get("structures", []))
        lines.extend(["Grid source: Mapzen Terrain Tiles public elevation sample; no river bathymetry or surveyed hydraulic structures.",
                      f"Display context: {structure_count} OpenStreetMap building footprints; absent heights are estimated and buildings do not obstruct model flow.",
                      f"Assumed north inlet, south outlet and Manning friction; approximately {cell_size:g} m x {cell_size:g} m cells.",
                      "Mapped Ganges centreline conditions the DEM; it is not surveyed bathymetry or a validated forecast."])
    lines.extend(["", "Model status", "SPH and D-Flow FM input adapters were prepared; external solver runs are not claimed.",
                  "GIS extents/depth TIFF use the uncalibrated local 2-D run when present.",
                  "The network-stage depth/damage remain separate screening estimates.", "", "Key assumptions"])
    lines.extend([f"- {warning}" for warning in result["warnings"]])
    lines.extend(["", "Data gate"])
    for key, value in result["input_gate"]["checks"].items():
        lines.append(f"- {key}: {'ready' if value['ready'] else 'not ready'}")
    lines.extend(["", "Provenance is preserved in the accompanying manifest.json and result.json."])

    pages = [lines[i:i + 42] for i in range(0, len(lines), 42)]
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + i * 2} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page_index, page_lines in enumerate(pages):
        page_obj = 4 + page_index * 2
        content_obj = page_obj + 1
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>".encode())
        commands = ["BT", "/F1 10 Tf", "48 744 Td", "14 TL"]
        for line in page_lines:
            commands.append(f"({_pdf_escape(str(line))}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(output)


def create_exports(result: dict) -> dict[str, str]:
    directory = SCENARIO_DIR / result["id"] / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    prefix = "synthetic_demo_" if result.get("mode") == "offline_demo" else ""
    paths = {
        "geojson": directory / f"{prefix}flood_extent.geojson",
        "kml": directory / f"{prefix}flood_extent.kml",
        "shapefile": directory / f"{prefix}flood_extent_shapefile.zip",
        "geotiff": directory / f"{prefix}maximum_depth.tif",
        "simulation_json": directory / f"{prefix}simulation_frames.json",
        "pdf": directory / f"{prefix}scenario_report.pdf",
        "manifest": directory / "manifest.json",
    }
    write_geojson(paths["geojson"], result)
    write_kml(paths["kml"], result)
    write_shapefile_zip(paths["shapefile"], result)
    write_geotiff(paths["geotiff"], result)
    paths["simulation_json"].write_text(json.dumps({
        "mode": result.get("mode", "live_inputs"), "scenario_id": result["id"],
        "unit_system": result.get("unit_system", {"standard": "SI", "locale": "en-IN"}),
        "spatial_simulation": result.get("spatial_simulation", {}),
        "spatial_damage": result.get("spatial_damage", {}),
    }, indent=2), encoding="utf-8")
    write_pdf(paths["pdf"], result)
    paths["manifest"].write_text(json.dumps(result["manifest"], indent=2), encoding="utf-8")
    return {name:str(path.relative_to(SCENARIO_DIR.parent.parent)).replace("\\", "/") for name, path in paths.items()}
