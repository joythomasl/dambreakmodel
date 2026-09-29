from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .catalog import load_site, public_catalog, validate_catalog
from .connectors import connector_statuses, iso_now
from .exports import create_exports
from .ingestion import IngestionError, parse_standard_timeseries, save_upload
from .scenario import ScenarioBlocked, list_scenarios, load_demo, load_scenario, run_demo_scenario, run_online_scenario
from .state import append_unique, load_state, observation_gate, save_state


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
RUNTIME = ROOT / "runtime"


def _source_payload(site: dict, refresh: bool) -> dict:
    """Refresh online sources and ingest only canonical, model-ready records."""
    sources = connector_statuses(site, refresh=refresh)
    ingested = {"observations": 0, "rainfall": 0}
    if refresh:
        for source in sources:
            data = source.get("data")
            records = data.get("records", []) if isinstance(data, dict) else []
            if source.get("source_id") == "reservoir_feed":
                accepted = []
                for row in records:
                    if row.get("site_id") not in {"tehri", "koteshwar"} or row.get("variable") != "reservoir_storage":
                        continue
                    accepted.append({**row, "observed_at": row["time"]})
                if accepted:
                    append_unique("observations", accepted, ("site_id", "time", "variable", "source"))
                    ingested["observations"] += len(accepted)
            elif source.get("source_id") == "rainfall_feed":
                accepted = [
                    row for row in records
                    if row.get("variable") in {"rainfall", "precipitation"}
                    and str(row.get("unit", "")).lower() == "mm"
                ]
                if accepted:
                    append_unique("rainfall", accepted, ("site_id", "time", "variable", "source"))
                    ingested["rainfall"] += len(accepted)
    observations = load_state("observations", [])
    rainfall = load_state("rainfall", [])
    assets = load_state("assets", [])
    return {
        "sources": sources,
        "auto_ingested": ingested,
        "gate": observation_gate(site, observations, rainfall, assets),
    }


def _asset_records(payload: object) -> list[dict]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
        rows = []
        for index, feature in enumerate(payload.get("features", [])):
            properties = dict(feature.get("properties", {}))
            geometry = feature.get("geometry", {})
            if geometry.get("type") == "Point":
                properties["lon"], properties["lat"] = geometry["coordinates"][:2]
            properties.setdefault("id", feature.get("id", f"feature-{index}"))
            rows.append(properties)
    else:
        raise IngestionError("Assets must be a JSON list or GeoJSON FeatureCollection")
    required = {"id", "name", "type", "quantity", "unit", "unit_cost_inr", "cost_source", "source_url"}
    for index, row in enumerate(rows, start=1):
        missing = required - set(row)
        if missing:
            raise IngestionError(f"Asset {index} is missing: {', '.join(sorted(missing))}")
        row["quantity"] = float(row["quantity"])
        row["unit_cost_inr"] = float(row["unit_cost_inr"])
        if row["unit_cost_inr"] <= 0:
            raise IngestionError(f"Asset {index} has no positive, traceable unit cost")
        has_location = row.get("lat") is not None and row.get("lon") is not None
        if not has_location and row.get("hazard_factor") is None:
            raise IngestionError(f"Asset {index} needs lat/lon or an explicit hazard_factor for an aggregated exposure unit")
        if has_location:
            row["lat"], row["lon"] = float(row["lat"]), float(row["lon"])
        row.setdefault("confidence", "user verified")
        if row.get("hazard_factor") is not None:
            row["hazard_factor"] = float(row["hazard_factor"])
        row.setdefault("people", 0)
    return rows


def _avulsion_records(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise IngestionError("Avulsion candidates must be a GeoJSON FeatureCollection")
    required = {
        "name", "current_channel_elevation_m", "candidate_elevation_m",
        "slope_current", "slope_candidate", "distance_to_channel_m",
        "evidence_source", "source_url",
    }
    rows = []
    for index, feature in enumerate(payload.get("features", []), start=1):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "LineString":
            raise IngestionError(f"Avulsion feature {index} must use LineString geometry")
        properties = dict(feature.get("properties") or {})
        missing = required - set(properties)
        if missing:
            raise IngestionError(f"Avulsion feature {index} is missing: {', '.join(sorted(missing))}")
        for key in ("current_channel_elevation_m", "candidate_elevation_m", "slope_current", "slope_candidate", "distance_to_channel_m"):
            properties[key] = float(properties[key])
        properties["id"] = str(feature.get("id") or properties.get("id") or f"candidate-{index}")
        properties["geometry"] = geometry
        rows.append(properties)
    if not rows:
        raise IngestionError("Avulsion GeoJSON contains no candidate paths")
    return rows


class Handler(SimpleHTTPRequestHandler):
    server_version = "SIHFlood/0.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, payload: object, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 25_000_000:
            raise ValueError("Request is too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _file(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_file() or not (resolved.is_relative_to(ROOT.resolve())):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = resolved.read_bytes()
        mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{resolved.name}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        site = load_site()
        if path == "/api/health":
            self._json({"status":"ok", "version":"0.1.0", "time":iso_now(), "catalog_errors":validate_catalog(site)})
        elif path == "/api/catalog":
            self._json(public_catalog(site))
        elif path == "/api/demo":
            demo = load_demo()
            self._json({
                "mode": "offline_demo", "id": demo["id"], "label": demo["label"],
                "description": demo["description"], "fixed_time_basis": demo["fixed_time_basis"],
                "observations": demo["observations"], "rainfall": demo["rainfall"],
                "assets": demo["assets"],
                "gate": {"ready": True, "mode": "offline_demo", "message": "Synthetic fixture ready; values are not current observations.",
                         "checks": {"reservoir_state": {"ready": True, "sites": ["tehri", "koteshwar"], "required": ["tehri", "koteshwar"], "synthetic": True},
                                    "rainfall": {"ready": True, "records": len(demo["rainfall"]), "minimum_records": 3, "synthetic": True},
                                    "exposure": {"ready": True, "records": len(demo["assets"]), "synthetic": True}}},
                "sources": [{"source_id": "offline_demo", "name": "Bundled synthetic fixture", "status": "demo",
                             "message": "Invented hydrology, assets and cost rates. Real Indian site names and chain; no external request.",
                             "observed_at": None}],
            })
        elif path == "/api/sources":
            self._json(_source_payload(site, refresh=query.get("refresh") == ["1"]))
        elif path == "/api/state":
            observations = load_state("observations", [])
            rainfall = load_state("rainfall", [])
            assets = load_state("assets", [])
            self._json({"observations":observations, "rainfall":rainfall, "assets":assets, "gate":observation_gate(site, observations, rainfall, assets)})
        elif path == "/api/scenarios":
            self._json({"scenarios":list_scenarios()})
        elif path.startswith("/api/scenarios/"):
            run_id = path.split("/")[3]
            try:
                self._json(load_scenario(run_id))
            except FileNotFoundError:
                self._json({"error":"Scenario not found"}, 404)
        elif path.startswith("/files/"):
            self._file(ROOT / path.removeprefix("/files/"))
        elif path in {"/", "/index.html"}:
            self._serve_static(STATIC / "index.html")
        elif path.startswith("/static/"):
            self._serve_static(STATIC / path.removeprefix("/static/"))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _serve_static(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_file() or not resolved.is_relative_to(STATIC.resolve()):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(resolved.name)[0] or "application/octet-stream") + ("; charset=utf-8" if resolved.suffix in {".html", ".css", ".js"} else ""))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
            if self.path == "/api/import/timeseries":
                data = base64.b64decode(payload["content_base64"])
                saved = save_upload(payload["filename"], data)
                rows = parse_standard_timeseries(data)
                kind = payload.get("kind")
                if kind not in {"observations", "rainfall"}:
                    raise IngestionError("kind must be observations or rainfall")
                if kind == "rainfall" and any(row["variable"] not in {"rainfall", "precipitation"} for row in rows):
                    raise IngestionError("Rainfall import may only contain rainfall or precipitation variables")
                merged = append_unique(kind, rows, ("site_id", "time", "variable", "source"))
                self._json({"imported":len(rows), "total":len(merged), "file":saved}, 201)
            elif self.path == "/api/import/assets":
                data = base64.b64decode(payload["content_base64"])
                saved = save_upload(payload["filename"], data)
                records = _asset_records(json.loads(data.decode("utf-8")))
                merged = append_unique("assets", records, ("id",))
                self._json({"imported":len(records), "total":len(merged), "file":saved}, 201)
            elif self.path == "/api/import/avulsion":
                data = base64.b64decode(payload["content_base64"])
                saved = save_upload(payload["filename"], data)
                records = _avulsion_records(json.loads(data.decode("utf-8")))
                merged = append_unique("avulsion_candidates", records, ("id",))
                self._json({"imported":len(records), "total":len(merged), "file":saved}, 201)
            elif self.path in {"/api/scenarios", "/api/demo/scenarios"}:
                result = run_demo_scenario(payload) if self.path == "/api/demo/scenarios" else run_online_scenario(payload)
                exports = create_exports(result)
                result["exports"] = {name:f"/files/{path}" for name, path in exports.items()}
                result_path = ROOT / "runtime" / "scenarios" / result["id"] / "result.json"
                result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
                self._json(result, 201)
            elif self.path == "/api/state/clear":
                # Intentionally scoped: only clears imported runtime state, never source files.
                for name in ("observations", "rainfall", "assets", "avulsion_candidates"):
                    save_state(name, [])
                self._json({"status":"cleared"})
            else:
                self._json({"error":"Not found"}, 404)
        except ScenarioBlocked as exc:
            self._json({"error":"scenario_blocked", "gate":exc.gate}, 409)
        except (ValueError, KeyError, IngestionError, json.JSONDecodeError) as exc:
            self._json({"error":str(exc)}, 400)
        except Exception as exc:
            self._json({"error":f"Internal error: {exc}"}, 500)


def serve(host: str | None = None, port: int | None = None) -> None:
    # Bind all local interfaces by default so IDE/Codex web-preview proxies can
    # reach the development server. Do not expose this prototype directly to
    # the public internet; put authentication and TLS in front of deployments.
    selected_host = host or os.getenv("APP_HOST", "0.0.0.0")
    selected_port = port or int(os.getenv("APP_PORT", "8000"))
    server = ThreadingHTTPServer((selected_host, selected_port), Handler)
    print(f"SIH Flood prototype running at http://{selected_host}:{selected_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
