# Canonical input schemas

Use current, attributable values. The repository intentionally contains no fake operational observations.

## Reservoir and rainfall CSV

Required header:

```text
site_id,time,variable,value,unit,source,source_url,quality
```

- Reservoir rows: `site_id` is `tehri` or `koteshwar`; `variable` is `reservoir_storage`; canonical import `unit` is `MCM` (10⁶ m³). The dashboard converts large values to `BCM` for CWC-style display (`1 BCM = 1,000 MCM`).
- Rainfall rows: `variable` is `rainfall` or `precipitation`; `unit` is hourly accumulated `mm`.
- `time` must be ISO 8601 and include a timezone, for example `2026-09-29T10:00:00+05:30`.

## Exposure JSON/GeoJSON

Every asset needs:

```text
id, name, type, quantity, unit, unit_cost_inr, cost_source, source_url
```

It also needs either `lat` and `lon`, or an explicit `hazard_factor` for an aggregated exposure unit. Supported damage-curve types are `residential`, `critical_facility`, `bridge`, `road`, `cropland`, and `other`. Optional fields include `people` and `confidence`.

## Avulsion candidate GeoJSON

Use a FeatureCollection of LineString features. Required properties are:

```text
name, current_channel_elevation_m, candidate_elevation_m,
slope_current, slope_candidate, distance_to_channel_m,
evidence_source, source_url
```

Derive both elevations and slopes from the same hydrologically conditioned DEM and vertical datum. Keep the source URL and processing method with each candidate.
