# HYDRA – Hydrological Disaster Risk Analysis

**Website:** <https://joythomasl.github.io/dambreakmodel/>

A software-only decision-support prototype for the Smart India Hackathon dam/lake-break problem. It now has a zero-licence-cost **self-contained demonstration mode** and a separate live-input mode. The configured Indian demonstration chain is:

`Tehri Dam -> Koteshwar Dam -> Devprayag -> Rishikesh`

The application monitors timestamped source availability, estimates rainfall-runoff, creates dam-breach/lake-burst/blockage scenarios, evaluates a conditional downstream cascade, **executes a local 2-D flood simulation**, shows its time-changing water depth on a rotatable 3-D terrain mesh, samples depth at assets for direct-cost screening, screens imported avulsion candidates, and exports KML, Shapefile, GeoJSON, GeoTIFF, simulation frames and PDF.

> This is not an official warning service. The demonstration uses **invented water, rain, asset and cost values** with real Indian site names/topology and sampled public elevation near Rishikesh. The executable local model is a coarse, uncalibrated depth-averaged approximation, **not SPH or Delft3D output**. Its 3-D display visualizes a 2-D calculation; it is not a 3-D CFD model. Operational predictions require calibrated models, surveyed structures/bathymetry and authorised current observations.

## Run the demonstration without accounts or internet

1. Start the app with `.\start.bat` in PowerShell.
2. Open <http://127.0.0.1:8000/?demo=1> or click **Launch demonstration** on the landing page.
3. Choose one of the five **Demo story** presets, then click **Run cascade + 2-D simulation**. For a one-click recorded preview, open <http://127.0.0.1:8000/?demo=1&autorun=1>.
4. Present the decision snapshot, then compare the rotatable 3-D flood model with the time-labelled cascade propagation view beside it. Both views follow the same contained/secondary-breach branch selector. Play, scrub or jump to the peak frame.
5. Use **Review damage** to show grid-sampled illustrative losses, then download KML, zipped SHP, GeoTIFF, simulation JSON and PDF.

The bundled hydrology fixture lives in `app/data/offline_demo.json` and uses fixed 2026-09-29 timestamps so runs are reproducible. Its water and exposure inputs are synthetic and are **not** inserted into live observation state. The dashboard, scenario result, GIS attributes, export filenames and PDF all identify the synthetic mode. The schematic cascade drawing is not geographic; the KML/Shapefile polygons and GeoTIFF now come from wet cells and maximum depths in the executed local model, but are **not validated real flood maps**. No credential, hosted service, paid API or cloud account is needed to replay the cached demonstration. "Zero-licence-cost" does not mean zero computing, storage or internet cost.

## What the executable simulation actually is

- `app/inundation.py` advances water depth and face discharge with a mass-conserving 2-D local-inertial, depth-averaged shallow-water approximation and an assumed Manning roughness. It reports source volume, open-boundary outflow, stored water and water-balance error.
- The local domain is a 72 × 48 grid of approximately 50 m cells near Rishikesh. The cached elevations in `app/data/rishikesh_terrain.json` are direct samples from the [public Mapzen Terrain Tiles on AWS](https://registry.opendata.aws/terrain-tiles/) using the standard-library-only `tools/build_terrain.py`; see [format notes](https://github.com/tilezen/joerd/blob/master/docs/formats.md) and [data-rights/attribution guidance](https://www.mapzen.com/rights/). Rebuilding the grid needs internet, but running the app does not.
- `app/data/rishikesh_structures.json` contains 107 real mapped building footprints downloaded for the identical bounds from [OpenStreetMap](https://www.openstreetmap.org/copyright) using `tools/build_structures.py`. Two include mapped height/level information; the remaining heights are explicitly labelled display estimates. They improve spatial context but are **not** surveyed structures, cost inventory, or hydraulic flow obstructions.
- The incoming hydrograph is produced by the existing Tehri–Koteshwar cascade screening. At Rishikesh it is injected through an **assumed** northern inlet. The cached OSM Ganges centreline conditions a 200 m routing corridor through noisy over-water DEM cells, and the south edge is the downstream outlet. The default conditional run now reaches that outlet during the saved playback. This is not surveyed bathymetry and the terrain still omits gates, levees and bridges; those choices can materially change results.
- The WebGL panel plays actual model depth frames above a continuously shaded terrain mesh and mapped building extrusions. The local view now drapes a cached 2024 Sentinel-2 cloudless mosaic over the Rishikesh grid and adds cached OpenStreetMap roads and labels. A separate regional view starts at Tehri Reservoir and follows the labelled cascade through Koteshwar, Devprayag and Rishikesh over a 96 × 96 public elevation grid, river/road context and satellite texture. Drag to orbit, scroll to zoom, hover for cell elevation/depth/coordinates, or use top/oblique camera presets. The regional orange route is a node-to-node cascade aid, not a continuous hydraulic solve. These refinements add **no** hydraulic resolution: this is 3-D visualization of 2-D equations, not a physically three-dimensional SPH simulation.
- Satellite textures are cached from [Sentinel-2 cloudless 2024 by EOX](https://s2maps.com/) for the non-commercial prototype under CC BY-NC-SA 4.0 and are display context only. Terrain comes from [Mapzen/AWS Open Data](https://registry.opendata.aws/terrain-tiles/); roads, rivers, places and structures come from [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) under ODbL. `tools/build_geocontext.py` rebuilds these caches when network access is available.
- Grid-sampled damage uses only illustrative point assets and depth-damage curves; reported INR values are not loss forecasts. The older network-stage screening values remain separate in the JSON for comparison. GIS exports now use the executed grid.

The app and local demonstration use Python's standard library with no third-party runtime package. DualSPHysics and Delft3D are not bundled or executed; the integration adapters produce input packages and report their true status. Running those open-source solvers later may require substantial CPU/GPU resources and site-specific terrain and calibration data.

## GitHub Pages deployment

Every push to `main` runs `.github/workflows/pages.yml`. It builds a GitHub Pages site containing the dashboard, 3-D terrain viewer, five reproducible demonstration scenarios and their KML, zipped Shapefile, GeoTIFF, JSON and PDF downloads. GitHub Pages cannot run the Python backend, so live feeds, uploads and arbitrary parameter combinations remain available through the local application; the hosted site truthfully limits simulation runs to the five packaged presets.

## Units and Indian display convention

The calculation engine uses SI units. The interface follows Indian public-sector reporting conventions and `en-IN` digit grouping:

| Quantity | Display/export unit |
|---|---|
| Rainfall | millimetres (`mm`) per stated observation interval |
| River/reservoir discharge | cubic metres per second (`m³/s`) |
| Large-reservoir storage | billion cubic metres (`BCM`); canonical imported storage remains `MCM` |
| Smaller storage and event volumes | million cubic metres (`MCM`, 10⁶ m³) or cubic metres (`m³`) |
| Flood depth and dimensions | metres (`m`) |
| Terrain elevation | metres above mean sea level (`m AMSL`) where the source supports it |
| Distance and area | `m`, `km`, `m²`, `km²` or `ha` as appropriate |
| Time | Indian Standard Time (`IST`) for timestamps; `s`, `min` and `h` for elapsed time |
| Cost | Indian rupees (`₹`/`INR`) with lakh/crore summaries and exact Indian-grouped values |

`1 BCM = 1,000 MCM = 10⁹ m³`. The maximum-depth GeoTIFF stores Float32 values directly in metres; its image description declares the unit and EPSG:4326 horizontal CRS. Shapefile fields use `DEPTH_M` and `PEAK_CMS`, with `D_UNIT` and `Q_UNIT` fields declaring `m` and `m3/s`.

## Live-data mode integrity

- Missing observations are never replaced with synthetic values.
- Every accepted observation needs a source, source URL, observation time, unit and quality label.
- Tehri and Koteshwar storage, recent upstream rainfall, and costed exposure must pass a freshness/readiness gate before a scenario can run.
- A failed source may show a clearly labelled last-known-good cache, but stale values do not silently become current values.
- Breach dimensions and conditional secondary failure remain visible *what-if assumptions*, not observations.

## Run it

From this folder, run:

```powershell
Copy-Item .env.example .env
.\start.bat
```

Open <http://127.0.0.1:8000>. `start.bat` uses the locally verified portable runtime when present, or an installed Python 3.11+ runtime. No third-party Python or JavaScript packages are required.

The development server binds to `0.0.0.0` so local IDE/Codex web-preview proxies can reach port `8000`. It has no production authentication layer and must not be exposed directly to the public internet.

Run the automated checks with:

```powershell
.\test.bat
```

## Configure live feeds

Copy `.env.example` to `.env`. The dashboard can check these online sources:

| Source | Prototype use | Configuration |
|---|---|---|
| Approved CWC/operator gateway | Tehri and Koteshwar storage | `CWC_FEED_URL`, optional bearer token |
| IMD AWS/ARG and basin QPF | Official rainfall check | `IMD_API_KEY` when required |
| Approved rainfall gateway | Automatically ingested hourly rainfall | `RAINFALL_FEED_URL`, optional bearer token |
| NASA IMERG Early | Recent granule discovery/failover metadata | Earthdata credentials for value extraction |
| ISRO MOSDAC | Satellite rainfall workflow | MOSDAC account and dataset ID |
| Copernicus Sentinel-1/2 | Recent scene discovery | Public STAC metadata; authenticated download may be needed |
| DAHITI | Satellite-altimetry water levels | API key and verified target ID |
| OpenStreetMap Overpass | Exposure discovery | Public endpoint, subject to completeness/rate limits |

The approved gateway endpoints must use HTTPS and return either a JSON list or `{"records": [...]}`. Each record uses this schema:

```json
{
  "site_id": "tehri",
  "time": "ISO-8601 timestamp with timezone",
  "variable": "reservoir_storage",
  "value": "numeric value",
  "unit": "MCM",
  "source": "publishing organisation and dataset",
  "source_url": "https://...",
  "quality": "publisher quality flag"
}
```

The reservoir feed accepts `reservoir_storage` for the `tehri` and `koteshwar` site IDs. The rainfall feed accepts `rainfall` or `precipitation` in hourly accumulated `mm`. Clicking **Refresh sources** validates and ingests canonical records.

The prototype does not scrape an undocumented government endpoint. If an authorised CWC/NWIC/WIMS feed is available, place a small controlled gateway in front of it and configure its HTTPS URL above. This is safer and reproducible for a recorded demonstration.

## File imports

Imports exist for official files downloaded shortly before recording. See [sample input schemas](sample_inputs/README.md).

- Reservoir and rainfall: UTF-8 CSV.
- Exposure/cost: JSON list or point GeoJSON.
- Avulsion: LineString GeoJSON with DEM-derived metrics.
- The validation library also recognises GeoTIFF, NetCDF, GeoPackage, KML and zipped Shapefile containers for future pipeline extensions.

Imports are content-checked, hashed and stored under ignored `runtime/` storage. A file being valid does not mean it is automatically model-ready; only the documented canonical schemas enter calculations.

## What the models do

1. **Rainfall-runoff:** a visible four-hour unit-hydrograph screening estimate with low/central/high bands. It must be locally calibrated before forecasting.
2. **Source event:** a parameterised dam breach, sudden release, lake burst or blockage-failure release hydrograph.
3. **Cascade:** routes the wave to Koteshwar, calculates reservoir storage/outflow with a mass balance, and compares two branches: no secondary failure and conditional secondary failure.
4. **Local inundation:** executes the 2-D local-inertial approximation on cached terrain for each cascade branch, saving nine depth frames and the maximum-depth grid. The mapped Ganges centreline is used for explicitly labelled DEM conditioning so the wave can be routed to the downstream boundary instead of escaping through the side of the cropped domain. The separate network-stage peak/depth/speed figures remain simplified screening relationships.
5. **3-D playback:** renders that terrain grid and simulated water surface in WebGL, with branch switching, orbit, zoom, play and scrub controls. The domain selector switches between the hydraulic Rishikesh impact grid and the larger Tehri Reservoir-to-Rishikesh cascade context.
6. **SPH and Delft3D:** adapters generate a DualSPHysics case manifest and D-Flow FM boundary/template package. They do not falsely claim that external solvers ran.
7. **Damage/cost:** samples model depth at point assets and applies illustrative depth-damage curves, reporting low/central/high direct losses. The legacy network-screening damage is retained separately in JSON; the dashboard uses grid-sampled values.
8. **Avulsion:** ranks imported DEM-derived alternative paths using relative elevation, slope, proximity and scenario depth. It reports susceptibility, not probability. It is not yet coupled to 2-D morphology.

## Exports and traceability

Every successful run gets a deterministic ID and a folder under `runtime/scenarios/<id>/`. It includes:

- flood extent GeoJSON and KML;
- zipped polygon Shapefile (`.shp`, `.shx`, `.dbf`, `.prj`);
- maximum-depth GeoTIFF derived from the executed 2-D grid;
- time-varying simulation frames and terrain metadata in JSON;
- scenario PDF report;
- input manifest and model adapter packages.

The interface keeps observations, assumptions, screening outputs and external-solver status separate.

## Optional live-data demo sequence

1. Configure the authorised live gateway URLs/keys or download the latest official files.
2. Start the app and record the source panel before refreshing.
3. Click **Refresh sources** and show timestamps, status colours and any credential limitations.
4. Import current reservoir/rainfall files only if the authorised feeds are unavailable.
5. Import exposure with traceable unit rates; optionally import DEM-derived avulsion candidates.
6. Show the quality gate turning ready.
7. Select an event, keep the breach inputs visible, and run the cascade screening.
8. Compare no-secondary-failure with conditional-secondary-failure arrival, peak, depth and cost.
9. Show the cascade timeline, damage table, avulsion result and solver-status caveats.
10. Download KML, Shapefile and PDF, then open the KML/Shapefile in QGIS or Google Earth for the recording.

Record the live refresh and scenario run close together so rainfall remains inside the 12-hour gate. Do not edit timestamps to make old data look current.

## Important limitations

- Public satellite products are generally near-real-time, not instantaneous ground truth.
- IMD/CWC/MOSDAC/DAHITI access can require credentials or approval.
- Satellite water surface/altimetry does not directly equal reservoir storage without a level-area-volume relationship.
- OSM exposure completeness and local unit-cost rates must be reviewed.
- The GeoTIFF and cell polygons reflect the executed local model, but its coarse terrain, unmeasured bathymetry and assumed boundaries make them unsuitable for real inundation decisions.
- This release does **not** run DualSPHysics or Delft3D, solve full 3-D fluid mechanics, model structural failure mechanics, calibrate roughness/breach parameters, or predict casualties/indirect economic losses. Those are remaining project stages.
- Flood warnings, evacuations and structural-safety decisions require competent authorities and calibrated/validated engineering models.
