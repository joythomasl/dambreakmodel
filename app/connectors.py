from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "runtime" / "cache"


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def data_age_hours(observed_at: str | None) -> float | None:
    observed = parse_iso(observed_at)
    if observed is None:
        return None
    return round((utc_now() - observed.astimezone(timezone.utc)).total_seconds() / 3600.0, 2)


def http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None, timeout: int = 25) -> Any:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"Accept": "application/json", "User-Agent": "SIH-Flood-Prototype/0.1"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


@dataclass
class SourceResult:
    source_id: str
    name: str
    status: str
    retrieved_at: str
    source_url: str
    observed_at: str | None = None
    age_hours: float | None = None
    quality: str = "unverified"
    message: str = ""
    data: Any = None
    from_cache: bool = False
    credential_required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class CacheStore:
    def __init__(self, directory: Path = CACHE_DIR):
        self.directory = directory

    def write(self, result: SourceResult) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{result.source_id}.json").write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def read(self, source_id: str) -> SourceResult | None:
        path = self.directory / f"{source_id}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["from_cache"] = True
        payload["age_hours"] = data_age_hours(payload.get("observed_at"))
        return SourceResult(**payload)


class OnlineConnector:
    source_id = "base"
    name = "Base connector"
    source_url = ""
    max_age_hours = 24.0

    def __init__(self, cache: CacheStore | None = None):
        self.cache = cache or CacheStore()

    def fetch(self, site: dict) -> SourceResult:
        raise NotImplementedError

    def refresh(self, site: dict) -> SourceResult:
        try:
            result = self.fetch(site)
            result.age_hours = data_age_hours(result.observed_at)
            if result.age_hours is not None and result.age_hours > self.max_age_hours and result.status == "ok":
                result.status = "stale"
                result.message = f"Observation is {result.age_hours:.1f} hours old; limit is {self.max_age_hours:.1f}."
            if result.status in {"ok", "metadata_only", "stale"}:
                self.cache.write(result)
            return result
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
            cached = self.cache.read(self.source_id)
            if cached:
                cached.status = "cached"
                cached.message = f"Live refresh failed ({exc}); showing last successful response."
                return cached
            return SourceResult(
                self.source_id, self.name, "unavailable", iso_now(), self.source_url,
                message=f"Live refresh failed: {exc}", quality="no data"
            )


class IMDConnector(OnlineConnector):
    source_id = "imd"
    name = "India Meteorological Department"
    source_url = "https://api.imd.gov.in/public/api_reference.html"
    max_age_hours = float(os.getenv("MAX_OBSERVATION_AGE_HOURS", "12"))

    @staticmethod
    def _rows(payload: Any) -> list[dict]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "Data", "result", "results"):
                if isinstance(payload.get(key), list):
                    return payload[key]
            return [payload]
        return []

    def fetch(self, site: dict) -> SourceResult:
        headers = {}
        if os.getenv("IMD_API_KEY"):
            headers["Authorization"] = f"Bearer {os.environ['IMD_API_KEY']}"
        state_id = os.getenv("IMD_UTTARAKHAND_STATE_ID", "31")
        aws_url = f"https://api.imd.gov.in/api/v1/aws_data?sid={urllib.parse.quote(state_id)}"
        qpf_url = "https://api.imd.gov.in/api/v1/basinqpf"
        aws_rows = self._rows(http_json(aws_url, headers=headers))
        qpf_rows = self._rows(http_json(qpf_url, headers=headers))
        bounds = site["area_of_interest"]
        nearby = []
        observed_times = []
        for row in aws_rows:
            try:
                lat = float(row.get("Latitude", row.get("latitude")))
                lon = float(row.get("Longitude", row.get("longitude")))
            except (TypeError, ValueError):
                continue
            if bounds["south"] <= lat <= bounds["north"] and bounds["west"] <= lon <= bounds["east"]:
                nearby.append(row)
                date = row.get("DATE") or row.get("Date")
                time = row.get("TIME") or row.get("Time") or "00:00:00"
                if date:
                    observed_times.append(f"{date}T{time}+00:00")
        basin_rows = [row for row in qpf_rows if any(token in str(row).upper() for token in ("GANGA", "BHAGIRATHI", "UTTARAKHAND"))]
        observed_at = max(observed_times) if observed_times else None
        return SourceResult(
            self.source_id, self.name, "ok" if nearby or basin_rows else "insufficient",
            iso_now(), aws_url, observed_at, quality="official, unreviewed",
            message=f"{len(nearby)} AWS/ARG records in the configured area; {len(basin_rows)} relevant basin-QPF rows.",
            data={"stations": nearby, "basin_qpf": basin_rows, "raw_station_count": len(aws_rows)}
        )


class NASAIMERGConnector(OnlineConnector):
    source_id = "nasa_imerg"
    name = "NASA GPM IMERG Early"
    source_url = "https://cmr.earthdata.nasa.gov/search/granules.json"
    max_age_hours = 12.0

    def fetch(self, site: dict) -> SourceResult:
        end = utc_now()
        start = end - timedelta(hours=36)
        bounds = site["area_of_interest"]
        params = {
            "short_name": "GPM_3IMERGHHE",
            "version": "07",
            "temporal": f"{start.isoformat().replace('+00:00','Z')},{end.isoformat().replace('+00:00','Z')}",
            "bounding_box": f"{bounds['west']},{bounds['south']},{bounds['east']},{bounds['north']}",
            "sort_key[]": "-start_date",
            "page_size": "12",
        }
        url = self.source_url + "?" + urllib.parse.urlencode(params, doseq=True)
        payload = http_json(url)
        entries = payload.get("feed", {}).get("entry", [])
        observed_at = entries[0].get("time_start") if entries else None
        products = []
        for entry in entries:
            links = [link.get("href") for link in entry.get("links", []) if link.get("href")]
            products.append({"id": entry.get("id"), "title": entry.get("title"), "time_start": entry.get("time_start"), "links": links})
        message = "Granule metadata found. Earthdata authentication and HDF5/OPeNDAP extraction are required for rainfall values."
        return SourceResult(
            self.source_id, self.name, "metadata_only" if products else "insufficient", iso_now(), url,
            observed_at, quality="official NASA metadata", message=message, data={"granules": products},
            credential_required=True
        )


class CopernicusSTACConnector(OnlineConnector):
    source_id = "copernicus_stac"
    name = "Copernicus Sentinel STAC"
    source_url = "https://stac.dataspace.copernicus.eu/v1/search"
    max_age_hours = 168.0

    def fetch(self, site: dict) -> SourceResult:
        end = utc_now()
        start = end - timedelta(days=15)
        bounds = site["area_of_interest"]
        body = {
            "collections": ["sentinel-1-grd", "sentinel-2-l2a"],
            "bbox": [bounds["west"], bounds["south"], bounds["east"], bounds["north"]],
            "datetime": f"{start.isoformat().replace('+00:00','Z')}/{end.isoformat().replace('+00:00','Z')}",
            "limit": 20,
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        }
        payload = http_json(self.source_url, method="POST", body=body)
        features = payload.get("features", [])
        observed_at = features[0].get("properties", {}).get("datetime") if features else None
        items = [{
            "id": item.get("id"), "collection": item.get("collection"),
            "datetime": item.get("properties", {}).get("datetime"),
            "cloud_cover": item.get("properties", {}).get("eo:cloud_cover"),
            "self": next((link.get("href") for link in item.get("links", []) if link.get("rel") == "self"), None)
        } for item in features]
        return SourceResult(
            self.source_id, self.name, "metadata_only" if items else "insufficient", iso_now(), self.source_url,
            observed_at, quality="official catalogue metadata",
            message=f"Found {len(items)} recent Sentinel items. Water classification must be run before using them as an observation.",
            data={"items": items}
        )


class DAHITIConnector(OnlineConnector):
    source_id = "dahiti"
    name = "DAHITI API v2"
    source_url = "https://dahiti.dgfi.tum.de/api/v2/list-targets/"
    max_age_hours = 720.0

    def fetch(self, site: dict) -> SourceResult:
        api_key = os.getenv("DAHITI_API_KEY")
        if not api_key:
            return SourceResult(self.source_id, self.name, "needs_credentials", iso_now(), self.source_url,
                                message="Set DAHITI_API_KEY to search and download water-level targets.",
                                quality="no data", credential_required=True)
        bounds = site["area_of_interest"]
        payload = http_json(self.source_url, method="POST", body={"api_key": api_key, "format": "json", **{
            "min_lon": bounds["west"], "max_lon": bounds["east"],
            "min_lat": bounds["south"], "max_lat": bounds["north"]
        }})
        target_id = os.getenv("DAHITI_TEHRI_ID")
        if target_id:
            water_url = "https://dahiti.dgfi.tum.de/api/v2/download-water-level/"
            water = http_json(water_url, method="POST", body={"api_key": api_key, "dahiti_id": target_id, "format": "json"})
            rows = water.get("data", [])
            observed_at = rows[-1].get("date") if rows else None
            return SourceResult(self.source_id, self.name, "ok" if rows else "insufficient", iso_now(), water_url,
                                observed_at, quality="satellite altimetry",
                                message=f"Downloaded {len(rows)} water-level points for DAHITI target {target_id}.", data=water)
        return SourceResult(self.source_id, self.name, "metadata_only", iso_now(), self.source_url,
                            quality="official catalogue metadata", message="Targets found; set DAHITI_TEHRI_ID after verifying the correct water body.", data=payload)


class OverpassConnector(OnlineConnector):
    source_id = "osm"
    name = "OpenStreetMap Overpass"
    source_url = os.getenv("OVERPASS_ENDPOINT", "https://overpass-api.de/api/interpreter")
    max_age_hours = 720.0

    def fetch(self, site: dict) -> SourceResult:
        bounds = site["area_of_interest"]
        south, west, north, east = bounds["south"], bounds["west"], bounds["north"], bounds["east"]
        query = f"""[out:json][timeout:45];(
          nwr[building]({south},{west},{north},{east});
          nwr[highway~\"primary|secondary|trunk\"]({south},{west},{north},{east});
          nwr[amenity~\"hospital|school|fire_station\"]({south},{west},{north},{east});
          nwr[bridge=yes]({south},{west},{north},{east});
        );out center tags;"""
        encoded = urllib.parse.urlencode({"data": query}).encode("utf-8")
        request = urllib.request.Request(self.source_url, data=encoded, headers={"User-Agent": "SIH-Flood-Prototype/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        elements = payload.get("elements", [])
        return SourceResult(self.source_id, self.name, "ok" if elements else "insufficient", iso_now(), self.source_url,
                            iso_now(), quality="community map; completeness varies",
                            message=f"Retrieved {len(elements)} mapped features; geometry and local completeness require review.",
                            data={"elements": elements})


class CredentialWorkflowConnector(OnlineConnector):
    def __init__(self, source_id: str, name: str, source_url: str, env_keys: tuple[str, ...], message: str):
        super().__init__()
        self.source_id, self.name, self.source_url = source_id, name, source_url
        self.env_keys, self.workflow_message = env_keys, message

    def fetch(self, site: dict) -> SourceResult:
        # An empty key list means that no supported machine connection is
        # configured.  all([]) is True in Python, which previously displayed a
        # misleading green status for the manual CWC bulletin workflow.
        configured = bool(self.env_keys) and all(os.getenv(key) for key in self.env_keys)
        return SourceResult(
            self.source_id, self.name, "configured" if configured else "needs_credentials", iso_now(), self.source_url,
            quality="no observation downloaded", message=self.workflow_message,
            credential_required=not configured,
            data={"required_environment": list(self.env_keys), "configured": configured}
        )


class StandardJSONFeedConnector(OnlineConnector):
    """Read a user-authorised live feed with the prototype's canonical schema.

    This deliberately does not guess private/undocumented CWC or operator API
    formats.  An approved gateway may expose either a JSON list or
    ``{"records": [...]}``; every record remains attributable to that URL.
    """

    def __init__(self, source_id: str, name: str, url_env: str, token_env: str = ""):
        super().__init__()
        self.source_id = source_id
        self.name = name
        self.url_env = url_env
        self.token_env = token_env
        self.source_url = os.getenv(url_env, "")

    def fetch(self, site: dict) -> SourceResult:
        url = os.getenv(self.url_env)
        if not url:
            return SourceResult(
                self.source_id, self.name, "needs_configuration", iso_now(), "",
                quality="no data",
                message=f"Set {self.url_env} to an approved HTTPS endpoint using the canonical JSON schema.",
                data={"required_environment": [self.url_env]},
            )
        if not url.lower().startswith("https://"):
            raise ValueError(f"{self.url_env} must use HTTPS")
        headers = {}
        token = os.getenv(self.token_env) if self.token_env else None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = http_json(url, headers=headers)
        records = payload.get("records") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("Live feed must return a JSON list or an object containing records[]")
        required = {"site_id", "time", "variable", "value", "unit", "source", "source_url", "quality"}
        accepted = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict) or not required.issubset(record):
                missing = required - set(record) if isinstance(record, dict) else required
                raise ValueError(f"Feed record {index} is missing: {', '.join(sorted(missing))}")
            if parse_iso(str(record["time"])) is None:
                raise ValueError(f"Feed record {index} has an invalid ISO timestamp")
            accepted.append({**record, "value": float(record["value"]), "retrieved_at": iso_now()})
        observed_at = max((str(row["time"]) for row in accepted), default=None)
        return SourceResult(
            self.source_id, self.name, "ok" if accepted else "insufficient", iso_now(), url,
            observed_at, quality="publisher supplied; schema validated",
            message=f"Accepted {len(accepted)} timestamped records from the configured live gateway.",
            data={"records": accepted},
        )


def connectors() -> list[OnlineConnector]:
    return [
        StandardJSONFeedConnector("reservoir_feed", "Approved CWC/operator reservoir feed", "CWC_FEED_URL", "CWC_FEED_API_KEY"),
        StandardJSONFeedConnector("rainfall_feed", "Approved rainfall gateway", "RAINFALL_FEED_URL", "RAINFALL_FEED_API_KEY"),
        IMDConnector(),
        NASAIMERGConnector(),
        CopernicusSTACConnector(),
        DAHITIConnector(),
        OverpassConnector(),
        CredentialWorkflowConnector(
            "cwc_rsms", "CWC Reservoir Storage Monitoring", "https://rsms.cwc.gov.in/",
            tuple(), "CWC exposes official reservoir bulletins but no stable unrestricted machine API was verified. Use the bulletin importer or an approved NWIC/WIMS feed."
        ),
        CredentialWorkflowConnector(
            "mosdac", "ISRO MOSDAC Download API", "https://mosdac.gov.in/downloadapi-manual",
            ("MOSDAC_USERNAME", "MOSDAC_PASSWORD", "MOSDAC_DATASET_ID"),
            "MOSDAC download requires an approved account and dataset ID; configure them before running the official mdapi workflow."
        ),
    ]


def connector_statuses(site: dict, refresh: bool = False) -> list[dict]:
    results = []
    for connector in connectors():
        if refresh:
            result = connector.refresh(site)
        else:
            result = connector.cache.read(connector.source_id)
            if result is None:
                result = SourceResult(connector.source_id, connector.name, "not_checked", iso_now(), connector.source_url,
                                      quality="no data", message="Refresh this source to test live availability.")
        results.append(result.to_dict())
    return results


def normalize_timeseries(records: list[dict], source: str, variable: str, unit: str, source_url: str) -> list[dict]:
    normalized = []
    for record in records:
        if "time" not in record or "value" not in record:
            raise ValueError("Every imported record needs time and value")
        if parse_iso(str(record["time"])) is None:
            raise ValueError(f"Invalid ISO timestamp: {record['time']}")
        normalized.append({
            "site_id": record.get("site_id", "unassigned"), "variable": variable,
            "value": float(record["value"]), "unit": unit, "observed_at": record["time"],
            "retrieved_at": iso_now(), "source": source, "source_url": source_url,
            "quality": record.get("quality", "unverified import"), "crs": record.get("crs", "EPSG:4326"),
        })
    return normalized
