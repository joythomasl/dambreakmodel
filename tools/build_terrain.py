"""Cache a small Rishikesh terrain grid from public Mapzen/AWS Terrarium tiles.

This is a reproducible data-preparation utility, not part of the server runtime.
It requires Pillow only when rebuilding the checked-in JSON grid.
"""

from __future__ import annotations

import json
import math
import struct
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "app" / "data" / "rishikesh_terrain.json"
ZOOM = 12
WIDTH, HEIGHT = 72, 48
CELL_M = 50.0
LON, LAT = 78.278, 30.092
BASE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium"


def _decode_png_rgb(data: bytes) -> tuple[int, int, list[bytes]]:
    """Decode the 8-bit RGB PNG used by Terrarium without runtime packages."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Terrain tile is not a PNG")
    offset, compressed = 8, bytearray()
    width = height = 0
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
            if bit_depth != 8 or color_type != 2:
                raise ValueError(f"Expected 8-bit RGB PNG, got depth={bit_depth}, type={color_type}")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(bytes(compressed))
    stride, bpp = width * 3, 3
    rows, previous, position = [], bytearray(stride), 0

    def paeth(a: int, b: int, c: int) -> int:
        estimate = a + b - c
        pa, pb, pc = abs(estimate - a), abs(estimate - b), abs(estimate - c)
        return a if pa <= pb and pa <= pc else b if pb <= pc else c

    for _ in range(height):
        filter_type = raw[position]
        position += 1
        source = raw[position:position + stride]
        position += stride
        row = bytearray(stride)
        for index, value in enumerate(source):
            left = row[index - bpp] if index >= bpp else 0
            above = previous[index]
            upper_left = previous[index - bpp] if index >= bpp else 0
            if filter_type == 0:
                restored = value
            elif filter_type == 1:
                restored = value + left
            elif filter_type == 2:
                restored = value + above
            elif filter_type == 3:
                restored = value + ((left + above) // 2)
            elif filter_type == 4:
                restored = value + paeth(left, above, upper_left)
            else:
                raise ValueError(f"Unsupported PNG filter {filter_type}")
            row[index] = restored & 255
        rows.append(bytes(row))
        previous = row
    return width, height, rows


def _world_pixel(lon: float, lat: float) -> tuple[float, float]:
    scale = 256 * 2**ZOOM
    x = (lon + 180.0) / 360.0 * scale
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * scale
    return x, y


def main() -> None:
    cache: dict[tuple[int, int], tuple[int, int, list[bytes]]] = {}
    lon_step = CELL_M / (111_320.0 * math.cos(math.radians(LAT)))
    lat_step = CELL_M / 111_320.0
    west = LON - WIDTH * lon_step / 2
    north = LAT + HEIGHT * lat_step / 2
    rows: list[list[float]] = []
    urls: set[str] = set()
    for row in range(HEIGHT):
        heights: list[float] = []
        for col in range(WIDTH):
            lon = west + (col + 0.5) * lon_step
            lat = north - (row + 0.5) * lat_step
            px, py = _world_pixel(lon, lat)
            tx, ty = int(px // 256), int(py // 256)
            if (tx, ty) not in cache:
                url = f"{BASE}/{ZOOM}/{tx}/{ty}.png"
                request = urllib.request.Request(url, headers={"User-Agent": "JalDrishti-SIH-terrain-prep/1.0"})
                cache[(tx, ty)] = _decode_png_rgb(urllib.request.urlopen(request, timeout=30).read())
                urls.add(url)
            _, _, tile_rows = cache[(tx, ty)]
            pixel_x, pixel_y = int(px) % 256, int(py) % 256
            base = pixel_x * 3
            red, green, blue = tile_rows[pixel_y][base:base + 3]
            heights.append(round(red * 256 + green + blue / 256 - 32768, 2))
        rows.append(heights)
    result = {
        "id": "rishikesh-mapzen-z12-72x48-v2",
        "label": "Real public elevation sample; hydrology and water boundary are not surveyed",
        "source": "Mapzen Terrain Tiles / AWS Open Data; underlying DEM sources vary by tile",
        "source_registry": "https://registry.opendata.aws/terrain-tiles/",
        "format_documentation": "https://github.com/tilezen/joerd/blob/master/docs/formats.md",
        "tiles": sorted(urls),
        "limitations": "Approximately 50 m model cells sampled from z12 tiles; not river bathymetry, embankment survey, levee inventory or calibrated hydraulic mesh.",
        "coordinate_system": "EPSG:4326",
        "west": west, "north": north, "lon_step": lon_step, "lat_step": lat_step,
        "width": WIDTH, "height": HEIGHT, "cell_size_m": CELL_M,
        "elevation_m": rows,
    }
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}: {WIDTH}x{HEIGHT}; elevation {min(map(min, rows))}..{max(map(max, rows))} m; {len(urls)} tiles")


if __name__ == "__main__":
    main()
