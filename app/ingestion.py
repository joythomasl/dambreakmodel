from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT / "runtime" / "uploads"
ALLOWED = {".csv", ".json", ".geojson", ".nc", ".netcdf", ".tif", ".tiff", ".gpkg", ".zip", ".kml"}


class IngestionError(ValueError):
    pass


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def _csv_records(data: bytes) -> list[dict[str, str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionError("CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise IngestionError("CSV has no header row")
    records = list(reader)
    if not records:
        raise IngestionError("CSV contains no data rows")
    return records


def validate_upload(filename: str, data: bytes) -> dict[str, Any]:
    ext = _extension(filename)
    if ext not in ALLOWED:
        raise IngestionError(f"Unsupported format {ext or '(none)'}. Allowed: {', '.join(sorted(ALLOWED))}")
    if not data:
        raise IngestionError("File is empty")

    details: dict[str, Any] = {"format": ext, "size_bytes": len(data)}
    if ext == ".csv":
        records = _csv_records(data)
        details.update({"rows": len(records), "columns": list(records[0])})
    elif ext in {".json", ".geojson"}:
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IngestionError(f"Invalid JSON: {exc}") from exc
        if ext == ".geojson" and (not isinstance(payload, dict) or payload.get("type") != "FeatureCollection"):
            raise IngestionError("GeoJSON must be a FeatureCollection")
        details["root_type"] = payload.get("type", type(payload).__name__) if isinstance(payload, dict) else type(payload).__name__
    elif ext in {".nc", ".netcdf"}:
        if not (data.startswith(b"CDF") or data.startswith(b"\x89HDF\r\n\x1a\n")):
            raise IngestionError("NetCDF must have a classic CDF or NetCDF4/HDF5 signature")
    elif ext in {".tif", ".tiff"}:
        if data[:4] not in {b"II*\x00", b"MM\x00*"}:
            raise IngestionError("GeoTIFF/TIFF signature is invalid")
        details["crs_check"] = "CRS tags require GDAL/rasterio or manual metadata verification"
    elif ext == ".gpkg":
        if not data.startswith(b"SQLite format 3\x00"):
            raise IngestionError("GeoPackage is not a valid SQLite container")
    elif ext == ".zip":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = {Path(name).suffix.lower() for name in archive.namelist()}
        except zipfile.BadZipFile as exc:
            raise IngestionError("ZIP file is invalid") from exc
        missing = {".shp", ".shx", ".dbf", ".prj"} - names
        if missing:
            raise IngestionError(f"Zipped Shapefile is missing: {', '.join(sorted(missing))}")
        details["components"] = sorted(names)
    elif ext == ".kml":
        text = data[:10000].decode("utf-8", errors="ignore")
        if not re.search(r"<kml(?:\s|>)", text, re.IGNORECASE):
            raise IngestionError("KML root element was not found")

    details["sha256"] = hashlib.sha256(data).hexdigest()
    details["valid"] = True
    return details


def save_upload(filename: str, data: bytes) -> dict[str, Any]:
    validation = validate_upload(filename, data)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
    digest = validation["sha256"][:12]
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{digest}_{safe_name}"
    destination.write_bytes(data)
    return {**validation, "stored_path": str(destination.relative_to(ROOT)).replace("\\", "/")}


def parse_standard_timeseries(data: bytes) -> list[dict]:
    records = _csv_records(data)
    required = {"site_id", "time", "variable", "value", "unit", "source", "source_url", "quality"}
    missing = required - set(records[0])
    if missing:
        raise IngestionError(f"Time-series CSV is missing columns: {', '.join(sorted(missing))}")
    parsed = []
    for row_number, row in enumerate(records, start=2):
        try:
            value = float(row["value"])
        except ValueError as exc:
            raise IngestionError(f"Row {row_number}: value is not numeric") from exc
        if "T" not in row["time"]:
            raise IngestionError(f"Row {row_number}: time must be ISO 8601 with timezone")
        parsed.append({**row, "value": value})
    return parsed
