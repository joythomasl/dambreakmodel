# Build progress

## Status

- [x] M1 Online Indian site catalogue and application shell
- [x] M2 Live observations, hydrology and scenarios
- [x] M3 Cascade core
- [x] M4 Damage, avulsion, exports and model adapters
- [x] M5 Dashboard and end-to-end verification
- [x] M6 Account-free self-contained demonstration
- [x] M7 Executed local inundation and 3-D playback
- [x] M8 Readable 3-D model inspection
- [x] M9 Higher-resolution real terrain and mapped structures
- [x] M10 Presentation-ready guided demonstration
- [x] M11 Satellite terrain and reservoir-corridor context
- [x] M12 Full-corridor local water routing
- [x] M13 SI and Indian reporting-unit audit

## Decisions

- The prototype uses a real Indian connected system: Tehri Dam -> Koteshwar Dam -> Devprayag -> Rishikesh.
- THDC establishes that Koteshwar is about 22 km downstream of Tehri and regulates releases toward Devprayag and Rishikesh.
- Live-mode observations and exposure data must come from timestamped online sources or explicit user uploads. Live analysis never replaces missing observations with synthetic values. A separate self-contained demonstration uses a fixed, prominently labelled synthetic fixture.
- A last-known-good cache is retained only for resilience and always exposes its observation/retrieval age. Stale data block a recording-quality run.
- The runtime is dependency-free Python plus HTML/CSS/JavaScript because the workspace runtime has no FastAPI, GIS or frontend packages. This keeps the online prototype reproducible while preserving clean API/module boundaries.
- SPH and Delft3D are integration adapters in this environment; no external solver run is claimed.
- The local engine executes a coarse 2-D depth-averaged approximation on cached public terrain. WebGL displays its water frames in 3-D; this is not a 3-D CFD/SPH solve. Its inlet, open edges and roughness are assumed and uncalibrated.

## Verification log

- Python 3.13.15 compile check: passed.
- Automated suite: 24 tests passed, including SI/Indian unit scaling, full-corridor outlet arrival, volume conservation, real terrain/structure bounds, cached satellite/road/river context, grid damage, cell-based GIS export and 3-D control wiring.
- HTTP smoke test: health, catalogue, state, source list and dashboard returned successfully.
- Real online connector check: NASA IMERG Early and Copernicus STAC returned current catalogue metadata.
- Export writers: GeoJSON, KML, zipped Shapefile, GeoTIFF and PDF signatures/components verified.
- Browser shell: dashboard document loaded in headless Edge; HTML/JavaScript element contracts are covered by tests.
- Offline HTTP smoke test: `/api/demo` and `/api/demo/scenarios` completed locally without credentials or internet; `/?demo=1&autorun=1` rendered the scenario and downloads.
- Offline scenario: both secondary-failure branches, cascade arrival, reservoir accounting, illustrative direct-loss comparison and avulsion screening rendered. These values are synthetic screening outputs, not operational flood forecasts.
- Executed 2-D demo at 50 m: 1,277 numerical steps, nine saved frames, 29 wet cells in the conditional branch and zero rounded volume-balance error in the default fixture. The numbers depend on synthetic boundary flow and uncalibrated terrain assumptions.
- 3-D browser review: terrain mesh and animated water rendered in headless Edge; a half-cell geometry defect found in the first image was repaired and rechecked.
- Refined 3-D browser review: continuous hill-shaded mesh, contours, relief sidewalls, depth-coloured water and clearly labelled controls rendered in headless Edge. Visual geometry was changed only; the hydraulic solver and depth frames were not modified.
- GIS review: GeoJSON features, KML placemarks and Shapefile records derive from the simulated wet cells; GeoTIFF now uses the 72 x 48 georeferenced maximum-depth grid.
- Real-context review: cached terrain ranges from 187 to 535 m in this model window; the complete bounded OSM snapshot contains 107 footprints, two with mapped/level-derived heights and 105 with explicitly estimated display heights.
- Guided-demonstration review: five event presets, event-specific parameter labels, a five-stage cascade ribbon, decision metrics, 3-D/damage jump controls and peak-frame playback are implemented. The 3-D model and time-labelled cascade now share a side-by-side command view and branch selector; the default scenario reports a nine-hour modelled source-to-Rishikesh interval, a conditional secondary-breach branch and three affected synthetic assets, all visibly labelled as synthetic and uncalibrated.
- Geospatial-context review: the local 3-D model has a cached Sentinel-2 2024 texture, 525 OSM road segments and 18 labels. The regional reservoir view uses a 96 × 96 Mapzen elevation grid, a second Sentinel-2 texture, 223 roads, 12 waterways, 90 place records and four verified cascade nodes. Imagery is presentation context only and the regional route is explicitly schematic.
- Full-corridor routing review: the cropped Rishikesh domain now uses the mapped Ganges centreline to condition discontinuous over-water DEM elevations and exposes only the south downstream edge. The default conditional run reaches the outlet at about 20 minutes, retains six wet outlet cells at the final frame, and reports zero rounded mass-balance error. Playback stops on that final downstream frame rather than jumping back to peak extent.
- Unit audit: rainfall uses mm, discharge m³/s, depth/dimensions m, elevation m AMSL, storage BCM/MCM, elapsed time min/h, and timestamps IST. INR displays use Indian grouping and lakh/crore scales. The hydrograph has labelled dual axes with checked nice-number scales, and the GeoTIFF now stores declared Float32 metre values instead of implicit centimetres.
