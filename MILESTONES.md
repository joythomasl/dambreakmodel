# Prototype milestones

This file is the implementation contract for the SIH prototype. A milestone is complete only after its validation commands pass.

## M1 - Online Indian site catalogue and application shell

- Tehri -> Koteshwar -> Devprayag -> Rishikesh verified topology loads.
- Every observation includes source URL, observation time, retrieval time and quality state.
- API server and dashboard start without third-party packages.

Validation: `.\test.bat` (`test_catalog_state`)

## M2 - Live observations, hydrology and scenarios

- IMD, NASA IMERG metadata, CWC/RSMS, DAHITI, MOSDAC, Sentinel and OSM adapters report configured, healthy, stale or unavailable without inventing values.
- Rainfall-runoff returns low, central and high hydrographs only from accepted timestamped observations.
- Dam breach, sudden release, natural-lake burst and blockage failure inputs are accepted.
- Scenario manifests are deterministic for the same inputs.

Validation: `.\test.bat` (`test_hydrology_cascade`, `test_scenario_integration`)

## M3 - Cascade core

- An upstream hydrograph reaches Koteshwar before Devprayag and Rishikesh.
- No-secondary-failure and conditional-secondary-breach branches are separate.
- Reservoir accounting and routed-volume accounting are reported.

Validation: `.\test.bat` (`test_hydrology_cascade`)

## M4 - Damage, exports and adapters

- Assets are counted once per branch and receive low/central/high direct-loss estimates.
- KML, zipped Shapefile, GeoJSON, GeoTIFF, JSON manifest and PDF report open successfully.
- DualSPHysics and D-Flow FM adapters create input packages and truthfully report unavailable binaries.

Validation: `.\test.bat` (`test_damage_avulsion`, `test_exports`, `test_ingestion_adapters`)

## M5 - Dashboard and end-to-end verification

- The dashboard refreshes online sources, blocks analysis when required inputs are missing/stale, and shows observations, hydrograph, cascade timeline, branch comparison, damage and exports.
- HTML/JavaScript element contracts, backend tests and HTTP smoke test pass.

Validation: `.\test.bat` plus local requests to `/api/health`, `/api/catalog`, `/api/state`, `/api/sources` and `/`.

## M6 - Account-free self-contained demonstration

- A fixed, explicitly synthetic Indian dam-chain fixture runs without accounts or internet.
- Offline and live modes are separate; demo inputs never enter the live observation cache or bypass its freshness gate.
- The dashboard compares cascade branches, shows illustrative damage and avulsion screening, and labels every result as synthetic.
- KML, zipped Shapefile, GeoJSON and PDF exports retain the synthetic label.
- The upstream event-wave arrival is distinguished from background rainfall flow.

Validation: `.\test.bat` (`test_offline_demo`) plus local GET `/api/demo`, POST `/api/demo/scenarios` and `/?demo=1&autorun=1`.

## M7 - Executed local inundation and 3-D playback

- A cached public elevation sample near Rishikesh is reproducible with source attribution.
- Each cascade branch drives an executed, mass-conserving local 2-D flood calculation and depth frames.
- The dashboard plays those frames on a rotatable WebGL terrain mesh, with a clear distinction between 2-D physics and 3-D visualization.
- Point-asset cost screening samples the grid, and GIS polygons/GeoTIFF come from simulated wet cells rather than the earlier placeholder extent.
- SPH and Delft3D remain truthful external-solver adapters, not claimed runs.

Validation: `.\test.bat` (`test_inundation`), JavaScript syntax checks, live HTTP demo smoke test, GIS file parsing and browser screenshot review.

## M8 - Readable 3-D model inspection

- The terrain is continuous and hill-shaded, with source-derived elevation contours and a side skirt for relief.
- Water colour follows simulated depth classes, and the maximum wet outline is optional.
- Camera presets, orbit/zoom, vertical exaggeration and coordinate/depth probe help inspect the same saved frames without changing physics.
- The UI states the model-cell limit and the difference between 3-D display and 2-D computation.

Validation: `.\test.bat` (`test_frontend_contract`), `node --check app/static/simulation3d.js` and headless browser screenshot review.

## M9 - Higher-resolution real terrain and mapped structures

- The local model and viewer use a 72 × 48 public elevation grid at approximately 50 m spacing over the same Rishikesh domain.
- The offline scene includes a complete bounded snapshot of 107 OpenStreetMap building footprints with ODbL attribution.
- Mapped height/levels and display-only estimated heights are counted and labelled separately.
- Default 18× relief, terrain grid lines and the mapped-structure toggle keep landform and structures legible.
- Buildings are presentation context only and are not claimed as surveyed geometry or hydraulic obstructions.

Validation: `.\test.bat` (`test_inundation`, `test_frontend_contract`), API result inspection and headless Chrome render review.

## M10 - Presentation-ready guided demonstration

- Five deterministic stories cover dam breach, monsoon-amplified breach, lake outburst, blockage failure and emergency release inputs.
- Event-specific labels explain what width, depth/head and formation/ramp time mean for the selected incident.
- A decision snapshot reports the conditional cascade state, Rishikesh arrival, relative peak-flow increase, maximum grid depth, affected synthetic assets and direct-loss screening.
- A five-stage ribbon makes the Tehri -> Koteshwar -> Devprayag -> Rishikesh sequence immediately visible.
- The rotatable 3-D flood model and vertical cascade propagation view sit side by side on presentation screens and use the same branch selection.
- The cascade view animates the routed wave, labels node arrival times and compares peak-flow amplification between contained and secondary-breach pathways.
- Peak-frame, 3-D jump and damage-jump controls support a reliable SIH presentation flow.

Validation: `.\test.bat` (`test_frontend_contract`, `test_offline_demo`) plus refreshed Edge accessibility-tree and screenshot review of `/?demo=1&autorun=1`.

## M11 - Satellite terrain and reservoir-corridor context

- The local hydraulic scene preserves executed water-depth playback while adding a cached Sentinel-2 texture, OSM roads and place/road labels.
- A selectable 96 × 96 regional terrain begins at Tehri Reservoir and shows Koteshwar, Devprayag and Rishikesh with public elevation, imagery, roads, named waterways and places.
- Cascade playback advances between the four verified regional nodes using the active branch timing; the connecting line is visibly described as schematic rather than a continuous hydraulic result.
- Satellite, terrain and OSM attribution and licence notes are present in the interface and source metadata.
- Satellite imagery, roads, labels and mapped structures can be independently hidden without changing model results.

Validation: `.\test.bat` (`test_inundation`, `test_frontend_contract`), local scenario API inspection, JavaScript parsing and browser review of both terrain domains.

## M12 - Full-corridor local water routing

- A cached OSM Ganges centreline conditions discontinuous elevations over the river in the coarse public DEM.
- The cropped local domain uses a north inlet and south downstream outlet so water is not lost through the eastern side before traversing the model.
- Results expose downstream arrival time and wet outlet-cell count, while retaining the volume-balance accounting and the warning that the corridor is not surveyed bathymetry.
- The 3-D water surface uses smoothed corner depths and playback remains on the final outlet frame.

Validation: `.\test.bat` (`test_mapped_channel_routes_water_to_downstream_boundary`), default conditional-branch run inspection and JavaScript parsing.

## M13 - SI and Indian reporting-unit audit

- Rainfall, discharge, depth, elevation, distance, area, volume and elapsed-time labels use explicit SI symbols.
- Reservoir storage displays follow the CWC-style BCM scale for Tehri while preserving MCM as the canonical import unit and for smaller storage.
- Timestamps are explicitly rendered in IST, and costs use Indian digit grouping with lakh/crore summaries plus exact-value tooltips.
- The rainfall/discharge chart has labelled dual axes and independently rounded scale ceilings.
- GeoJSON/Shapefile attributes declare units, and the maximum-depth GeoTIFF stores Float32 metre values with a unit description instead of an implicit integer scale.

Validation: `.\test.bat` (`test_exports`, `test_frontend_contract`) plus JavaScript parsing and a local scenario export inspection.

Stop-and-fix rule: if a validation fails, repair it before marking that milestone complete.
