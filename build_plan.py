from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable, NextPageTemplate,
)


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "pdf" / "HYDRA_Project_Plan.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

NAVY = colors.HexColor("#123047")
BLUE = colors.HexColor("#176B99")
TEAL = colors.HexColor("#008A86")
PALE = colors.HexColor("#EAF4F7")
LIGHT = colors.HexColor("#F4F7F8")
MID = colors.HexColor("#D4E1E6")
TEXT = colors.HexColor("#253A46")
MUTED = colors.HexColor("#58707B")
AMBER = colors.HexColor("#C66A13")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleX", fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=NAVY, spaceAfter=12))
styles.add(ParagraphStyle(name="SubtitleX", fontName="Helvetica", fontSize=12, leading=17, textColor=BLUE, spaceAfter=18))
styles.add(ParagraphStyle(name="H1X", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=NAVY, spaceBefore=17, spaceAfter=8, keepWithNext=True))
styles.add(ParagraphStyle(name="H2X", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=BLUE, spaceBefore=11, spaceAfter=5, keepWithNext=True))
styles.add(ParagraphStyle(name="BodyX", fontName="Helvetica", fontSize=9.3, leading=13.8, textColor=TEXT, spaceAfter=7))
styles.add(ParagraphStyle(name="SmallX", fontName="Helvetica", fontSize=8, leading=11.2, textColor=TEXT, spaceAfter=5))
styles.add(ParagraphStyle(name="TinyX", fontName="Helvetica", fontSize=7.3, leading=9.7, textColor=TEXT))
styles.add(ParagraphStyle(name="CaptionX", fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED, spaceAfter=6))
styles.add(ParagraphStyle(name="BulletX", fontName="Helvetica", fontSize=9.2, leading=13.3, leftIndent=13, firstLineIndent=-8, textColor=TEXT, spaceAfter=4))
styles.add(ParagraphStyle(name="CalloutX", fontName="Helvetica-Bold", fontSize=10, leading=15, textColor=NAVY, spaceAfter=0))
styles.add(ParagraphStyle(name="CoverLabelX", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=TEAL, spaceAfter=8))
styles.add(ParagraphStyle(name="SourceX", fontName="Helvetica", fontSize=7.0, leading=9.0, textColor=TEXT, spaceAfter=1, wordWrap="CJK"))


def P(s, style="BodyX"):
    return Paragraph(s, styles[style])


def h1(s):
    story.append(P(s, "H1X"))


def h2(s):
    story.append(P(s, "H2X"))


def body(s):
    story.append(P(s))


def bullet(s):
    story.append(P("&#8226; " + s, "BulletX"))


def callout(s, color=PALE):
    t = Table([[P(s, "CalloutX")]], colWidths=[7.08*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), color),
        ("BOX", (0,0), (-1,-1), 0.6, MID),
        ("LEFTPADDING", (0,0), (-1,-1), 13),
        ("RIGHTPADDING", (0,0), (-1,-1), 13),
        ("TOPPADDING", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 11),
    ]))
    story.extend([Spacer(1, 5), t, Spacer(1, 8)])


def table(headers, rows, widths, font=7.6):
    head = [P(x, "TinyX") for x in headers]
    data = [head] + [[P(str(x), "TinyX") for x in row] for row in rows]
    t = Table(data, colWidths=[w*inch for w in widths], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), PALE),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
        ("GRID", (0,0), (-1,-1), 0.35, MID),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.extend([t, Spacer(1, 8)])


def link(label, url):
    return f'<link href="{url}" color="#176B99"><u>{label}</u></link>'


def footer(canvas, doc):
    canvas.saveState()
    w, h = doc.pagesize
    canvas.setStrokeColor(MID)
    canvas.setLineWidth(0.6)
    canvas.line(0.72*inch, 0.54*inch, w-0.72*inch, 0.54*inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.72*inch, 0.36*inch, "HYDRA | Hydrological Disaster Risk Analysis")
    canvas.drawRightString(w-0.72*inch, 0.36*inch, str(doc.page))
    if doc.page > 1:
        canvas.setFillColor(BLUE)
        canvas.rect(0, h-0.08*inch, w, 0.08*inch, fill=1, stroke=0)
    canvas.restoreState()


PAGE = (8.5*inch, 11*inch)
doc = BaseDocTemplate(str(OUT), pagesize=PAGE, leftMargin=0.72*inch,
                      rightMargin=0.70*inch, topMargin=0.66*inch,
                      bottomMargin=0.73*inch, title="HYDRA - Hydrological Disaster Risk Analysis",
                      author="HYDRA Project Team")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates(PageTemplate(id="all", frames=[frame], onPage=footer))
story = []

# Cover
story.append(Spacer(1, 0.48*inch))
story.append(P("SMART INDIA HACKATHON PROJECT PLAN", "CoverLabelX"))
story.append(P("HYDRA", "TitleX"))
story.append(P("<b>Hydrological Disaster Risk Analysis</b><br/>An open-data software framework for monitoring, forecasting, simulation and downstream damage assessment in India", "SubtitleX"))
story.append(HRFlowable(width="100%", thickness=2, color=TEAL))
story.append(Spacer(1, 0.28*inch))
callout("Core idea: combine satellite and agency data to watch water and rain upstream, estimate incoming water, run realistic failure scenarios, and show who and what is at risk downstream.")
story.append(Spacer(1, 0.18*inch))
body("<b>Project type:</b> Software-only. No on-site sensors are required. The system accepts official feeds, satellite products and user-uploaded data, records their age and uncertainty, and continues with fallback sources when a feed is unavailable.")
body("<b>Required modelling:</b> Smooth Particle Hydrodynamics (SPH) for detailed breach or surge behaviour, and Delft3D Flexible Mesh / D-Flow FM for river and floodplain flow. The same scenario is compared across both where their spatial scales overlap.")
body("<b>Main deliverables:</b> interactive dashboard; monitored water/rain/inflow; dam, lake and blockage scenarios; <b>multi-site cascading-event predictions</b>; inundation and arrival-time maps; structural and economic loss estimates; downloadable report and KML/SHP results.")
story.append(Spacer(1, 0.14*inch))
table(["Document", "Planning assumption", "How to use it"], [
    ["Version", "29 September 2026", "Implementation blueprint for an SIH prototype and later production upgrade."],
    ["Demonstration", "One Indian dam catchment plus one natural-blockage replay", "Choose the actual sites after confirming terrain, exposure and observed event data."],
    ["Safety", "Decision-support prototype", "Never present unvalidated outputs as an official flood warning or dam-safety judgement."],
], [1.33, 2.55, 3.20])
story.append(Spacer(1, 0.18*inch))
body("The design separates <b>observations</b> (what the data show), <b>forecasts</b> (what may arrive), and <b>scenarios</b> (what would happen if a specified failure occurred). This distinction is central to a trustworthy dashboard.")
story.append(PageBreak())

h1("1. What the finished system should do")
body("A user selects a dam, natural lake, river blockage or upstream catchment. The software gathers the best available data, estimates the current state and incoming water, lets the user define a plausible event, runs the flood models, and returns downstream impacts with clear uncertainty labels.")
table(["Question", "Answer shown by the system"], [
    ["How much water is there?", "Observed gauge or reservoir values where available; satellite-derived lake area, level and storage-change estimates where defensible."],
    ["How much rain is falling upstream?", "Rainfall totals and maps for the contributing catchment, time trend, intensity and source age."],
    ["How much water may arrive?", "A range of inflow hydrographs, peak flow, arrival time and expected water-volume increase."],
    ["What if the dam or blockage fails?", "Breach assumptions, outflow hydrograph, downstream depth, speed, extent and travel time."],
    ["What about downstream dams?", "A linked prediction: surge arrival, peak inflow and level at each downstream asset, possible release/overtopping, and the next flood wave."],
    ["Who and what is affected?", "Population, buildings, roads, bridges, land use and crop exposure; low/central/high direct-loss estimates."],
    ["Could the river change course?", "A screened avulsion-risk map and alternative flow-path scenarios, with field-validation flags."],
], [2.10, 4.98])
h2("End-to-end flow")
table(["1. Ingest", "2. Check", "3. Estimate", "4. Simulate", "5. Explain and export"], [[
    "Feeds and uploaded files", "Quality, age and coordinate checks", "Water state and inflow range", "SPH near breach; Delft3D downstream", "Maps, costs, report, KML/SHP"
]], [1.12, 1.22, 1.22, 1.55, 1.97])
callout("Build the prototype around one fully working catchment first. The architecture should be general, but a convincing, calibrated end-to-end demo beats a map of many sites with untested predictions.")
h2("What is not directly observable")
body("A satellite image cannot by itself reveal the exact storage volume of every lake or the strength of a dam. Lake volume needs a known stage-volume curve or a terrain/bathymetry-based estimate; dam failure probability needs engineering inspection data. Without these, show ranges and user-defined scenarios, not false precision.")

h1("2. Data plan: what to collect and what each source is for")
body("Each source is an adapter. Store the original download, the processed version, timestamp, licensing/access conditions, spatial resolution, and a confidence flag. When two sources disagree, show both and prefer validated in-situ measurements for their exact location.")
table(["Need", "Primary sources", "Purpose and access reality"], [
    ["River and reservoir levels", "CWC RSMS / flood information; India-WRIS", "Official observations and reservoir bulletins. Public portals exist; do not assume a stable, unrestricted API. Confirm access, cadence and permissions per feed."],
    ["Lake level and area", "SWOT LakeSP; DAHITI; Sentinel-1/2", "SWOT/DAHITI provide satellite water-level series; Sentinel gives water extent. These are revisit-based, not continuous real-time gauges. DAHITI API needs a key."],
    ["Historical water", "JRC Global Surface Water", "Baseline for seasonal/permanent water and new-lake detection; the released 1984-2021 series is historical, not a current feed."],
    ["Rain gauges and gridded rain", "IMD AWS/ARG and basin products; MOSDAC INSAT; NASA IMERG Early", "Gauge-led where accessible, satellite-based coverage and backup. IMERG Early is about 4-hour latency, not zero-delay real time. MOSDAC/IMERG require accounts."],
    ["Terrain and drainage", "Copernicus DEM GLO-30; HydroBASINS/HydroRIVERS", "Catchment boundaries, slopes and flow paths. DEM is a surface model; channels, embankments and bridges may need corrections."],
    ["Assets and people", "OpenStreetMap, WorldPop, ESA WorldCover", "Buildings, roads, population and land use; completeness varies by place. Add local official asset data if available."],
], [1.37, 2.33, 3.38])
body("<b>Helpful extra sources:</b> ERA5-Land for antecedent wetness; GloFAS as an independent flow-forecast cross-check; historical Sentinel/Landsat flood images for validation; CPWD/state schedule-of-rates for asset valuation. Source names and links are listed in Section 14.")
story.append(Spacer(1, 8))

h1("3. Data ingestion: make large, mixed datasets usable")
h2("Accepted inputs")
table(["Category", "Supported formats", "Validation at upload"], [
    ["Time series", "CSV, JSON, NetCDF, Parquet", "Column names, units, timezone, duplicates, missing values, abnormal jumps."],
    ["Terrain / imagery", "GeoTIFF / Cloud Optimized GeoTIFF, NetCDF, Zarr", "Coordinate system, pixel size, nodata, vertical datum, coverage."],
    ["Features / boundaries", "GeoJSON, GPKG, SHP (zipped), KML", "Geometry validity, spatial reference, site overlap, attribute schema."],
    ["Model input", "Delft3D mesh/boundaries, hydrograph CSV/NetCDF, SPH geometry and parameters", "Required fields, units, scenario version and model compatibility."],
], [1.22, 2.34, 3.52])
body("Use a small adapter per data provider. A scheduled job checks for new products, writes the raw copy to object storage, converts them to a common schema, and updates a catalogue. Large rasters stay as tiled files; the database keeps metadata and vector results. Process only the selected catchment and time window, not all of India for each request.")
h2("Common record for every observation")
body("Site ID; source; observed time; publication time; download time; latitude/longitude and coordinate system; value and unit; quality flag; licence/access; processing version; URL or file checksum. This makes old or questionable data visible instead of quietly filling gaps.")
h2("A sensible technology stack")
table(["Layer", "Suggested tool", "Reason"], [
    ["Processing", "Python, xarray, rasterio, GDAL, GeoPandas", "Practical for time-series and geospatial workflows."],
    ["Storage", "PostgreSQL/PostGIS + object storage", "Searchable features and scalable raster/time-series files."],
    ["Background jobs", "Celery/RQ plus Redis (or equivalent queue)", "Long simulations do not block the dashboard."],
    ["API and dashboard", "FastAPI + React/MapLibre (or Streamlit for MVP)", "A clear map, scenario controls and downloadable results."],
    ["Reproducibility", "Docker images, versioned scenario manifest, logs", "The same inputs can rerun the same result."],
], [1.08, 2.38, 3.62])
callout("Fallback rule: if a primary feed is missing, switch to a named backup and widen the uncertainty range. Never silently label an older satellite pass as a current measurement.")

h1("4. Water level and new-lake monitoring")
bullet("Maintain a site registry with dam/lake polygon, river reach, catchment, downstream network, gauge links, stage-storage curve if known, and last verified observation.")
bullet("For reservoirs, use CWC/WRIS level or storage when legally accessible. Treat their data-release frequency as site-specific and verify it during integration.")
bullet("For lakes, segment water from Sentinel-1 radar during cloud/monsoon conditions and Sentinel-2 optical images when cloud-free; compare with JRC baseline to flag unusual expansion or a newly formed water body.")
bullet("Use SWOT or DAHITI elevation where available. Fit a stage-area-volume relationship only when terrain or bathymetry supports it. Otherwise report surface area and a broad storage interval.")
bullet("Watch time change: level, area, rate of rise, distance to an assumed overflow level, and whether river flow appears blocked upstream or reduced downstream.")
body("New-lake detection requires human review: radar shadows, snow, sediment and cloud can look like water. A blocked river is inferred from multiple signals (landslide image, upstream ponding, downstream flow drop), not one pixel change.")
story.append(Spacer(1, 8))

h1("5. Rainfall analysis and incoming-water forecast")
h2("Where the rainfall comes from")
body("Draw the entire upstream catchment from a drainage dataset and corrected DEM. Collect IMD AWS/ARG stations inside and near it; mosaic MOSDAC rain estimates; use NASA IMERG Early if local feeds are delayed or unavailable. Keep each product's own timestamp and spatial resolution. A gauge measures a point; a satellite pixel averages a larger area.")
h2("Forecast calculation")
bullet("Convert rain to basin-average and sub-basin rainfall for the last 1, 3, 6, 12, 24 and 72 hours. Compare with local historical extremes and antecedent wetness.")
bullet("Run a rainfall-runoff model such as open-source Wflow, or a transparent simpler unit-hydrograph model for the first prototype. Calibrate it with observed discharge where possible.")
bullet("Estimate a hydrograph: river flow at each hour, peak inflow, total arriving volume and time to peak. Include controlled dam releases if relevant and publicly available.")
bullet("For reservoir/lake state, update storage using a water balance: next storage = current storage + inflow - controlled outflow - spill - other losses. Use a real stage-storage curve when available.")
bullet("Generate low, central and high inflow cases based on rainfall/gauge disagreement, forecast errors and storage uncertainty; compare against GloFAS as an independent signal, not as ground truth.")
body("A forecast is useful only if tested against past events. For each demo basin, replay at least one flood and one normal period, then show timing error, peak-flow error and coverage of the uncertainty interval.")

h1("6. Scenario engine: one place for all incident types")
table(["Scenario", "User-supplied or estimated inputs", "Model output"], [
    ["Dam breach", "Starting reservoir level/volume; breach location, final width, depth and formation time; current inflow; downstream terrain", "Outflow hydrograph, inundation, arrival time, depth and speed."],
    ["Sudden release / surge", "Gate release hydrograph or specified pulse; starting river flow", "Downstream travel and flood extent without claiming the dam failed."],
    ["Natural-lake / moraine / landslide-dam burst", "Lake volume range, barrier height/material proxy, breach timing, overflow/erosion assumptions", "Lake drainage hydrograph and downstream flood."],
    ["River blockage", "Blockage position, debris height/width, inflow, impounded volume, overtopping time", "Upstream ponding, downstream low-flow phase, possible burst wave."],
    ["Cascade", "Upstream event; connected dams, lakes, tributaries and settlements; starting storage and operating rules", "A time-ordered chain of arrival, peak level, release/overtopping and conditional failure, with downstream flood and damage maps."],
    ["Avulsion", "Alternative low paths, embankment/bank failure locations, sediment/deposition indicators", "Conditional alternate-channel flood maps and risk screening."],
], [1.43, 2.65, 3.00])
body("Each run saves a scenario manifest: all inputs, their origin and age, model versions, assumptions, computational domain and output files. Separate <b>what-if</b> assumptions from measured facts in the dashboard and report.")
story.append(Spacer(1, 8))

h1("7. Two-model workflow: SPH and Delft3D")
h2("Why use both")
body("SPH follows many moving water particles and can represent complex, fast local flow around a breaking barrier. It is computationally demanding, so use it for a short reach near the dam, lake outlet or blockage. Delft3D Flexible Mesh / D-Flow FM solves flow over a river-and-floodplain mesh, so use it to carry the flood downstream across a larger area. The models are complementary, not interchangeable.")
table(["Step", "SPH near source", "Delft3D downstream"], [
    ["Geometry", "Local high-detail DEM, barrier/breach shape, initial water body", "Corrected terrain, river bathymetry if available, levees/roads, 2D flexible mesh"],
    ["Boundary", "Water level/volume and upstream inflow; breach opening rule", "SPH-derived or independently specified inflow hydrograph; downstream stage/normal-depth condition"],
    ["Primary result", "Breach-wave behaviour, velocity and discharge across a hand-off section", "Depth, velocity, extent and arrival time across river and floodplain"],
    ["Comparison", "Compare discharge and water level at shared section", "Check mass balance and similar wave timing in overlap reach"],
    ["Run cost", "High; use short time and small domain", "Larger domain, multiple scenarios and uncertainty ensemble"],
], [1.15, 2.89, 3.04])
h2("Practical run sequence")
bullet("Prepare one corrected terrain and consistent vertical datum. Document where river cross-sections are missing or estimated.")
bullet("Create identical starting water state and breach assumptions. Run DualSPHysics (open-source SPH) near the source. Measure discharge versus time at a fixed cross-section downstream of the breach.")
bullet("Feed that hydrograph into D-Flow FM. Run 2D floodplain propagation and compute maximum depth, maximum speed, first arrival, peak arrival and inundation duration.")
bullet("Run an independent Delft3D breach-hydrograph case for comparison, especially if SPH is too expensive for many runs. Explain differences from mesh, geometry and numerical assumptions.")
bullet("Repeat low/central/high scenarios. Do not put a precise depth at a building on the map if input terrain is only 30 m resolution.")
callout("Minimum credible comparison: same initial storage, breach assumptions and upstream inflow; compare the outflow hydrograph and water level at a common section before comparing downstream flood maps.")
h2("Calibration and checks")
body("Test model setup first against standard dam-break cases. Then replay an Indian historical flood using observed levels, hydrographs or satellite flood extent. Check mass balance, flood extent overlap, peak timing and water-level error. Distinguish a validated forecast from a plausible but unvalidated what-if scenario.")

h1("8. Cascading-event prediction - a core feature")
body("A cascading event means one upstream incident changes the water reaching several downstream places. The tool must predict the <b>sequence</b>, not just draw one large flood polygon: when the wave reaches each dam, lake, river junction and settlement; how high the water may rise; what is released or spilled; and how each new wave changes downstream impacts.")
h2("8.1 Build an Indian river-network map")
body("Create a directed map of river reaches and junctions using HydroRIVERS/HydroBASINS, then verify each connection against Indian maps, DEM flow paths and satellite imagery. Add every dam, reservoir, natural lake, blockage and important settlement as a node. At each dam/lake, store current level or storage, capacity and stage-storage relationship where available, spillway/gate information, operating or release assumptions, and the age/source of each value. Use CWC/India-WRIS and state/project records when available. A missing rule becomes a clearly labelled scenario input, not an invented fact.")
h2("8.2 Predict the chain step by step")
table(["Step", "Calculation", "Question answered"], [
    ["1. Start event", "Choose dam breach, lake burst, blockage failure or sudden release. SPH supplies a local outflow hydrograph, or a measured/user-specified hydrograph is used.", "How much water leaves the first site, and when?"],
    ["2. Route downstream", "D-Flow FM routes the wave along river reaches and across floodplain. Add tributary inflow and local rain-runoff at junctions without counting the same water twice.", "When and how strongly does it reach the next node?"],
    ["3. Update each reservoir", "At each time step: new storage = old storage + incoming flow - gate release - spill - other losses. Convert storage to level using the site curve.", "Could the downstream level exceed a chosen threshold?"],
    ["4. Branch outcomes", "Run separate cases: no secondary failure; controlled/automatic release; overtopping or conditional breach. Use documented trigger assumptions.", "What changes if the next structure responds differently?"],
    ["5. Continue the chain", "Turn any secondary release/breach into a new hydrograph, combine it with ongoing river flow, and repeat through all connected downstream nodes.", "What reaches the next dam and downstream communities?"],
    ["6. Summarize impacts", "Overlay every scenario's depth, speed and arrival time with settlements, assets and cost layers.", "Who is at risk at each stage, and what is the loss range?"],
], [1.18, 4.20, 1.70])
body("Run low, central and high water/parameter cases. Branches represent <b>conditional possibilities</b>, not an automatic claim that every downstream dam will fail. If real-time gate operations or structural condition are unknown, the system must state that the result is a what-if scenario.")
h2("8.3 What the dashboard and report must show")
table(["Output", "Minimum content"], [
    ["Chain timeline", "For every node: incoming-wave arrival, peak inflow, maximum level, spill/release start, any conditional breach time, and next-wave arrival."],
    ["Network map", "Upstream-to-downstream links, branches, affected settlements and the status of each dam/lake; click a node for its hydrograph and assumptions."],
    ["Scenario comparison", "No secondary failure vs release vs conditional breach, each with separate inundation, arrival-time, people-exposed and direct-loss ranges."],
    ["Uncertainty and traceability", "Low/central/high envelope, data freshness, missing rules, trigger assumptions, model version and mass-balance result."],
], [1.62, 5.46])
h2("8.4 Minimum proof in the SIH demo")
body("Choose an Indian river system with <b>at least two connected water-control or natural-storage sites</b> and a downstream settlement, once data access is confirmed. Trigger a surge at the first site. Show the routed hydrograph at the second site, its storage/level response, a no-failure and a conditional-failure branch, then the changed flood arrival and damage at the settlement. Test a simple pulse where arrival order is physically sensible; check that inflow, storage change and outflow approximately balance; and replay any available historical level or flood-extent evidence. If only one site has enough public data, use an explicitly synthetic second structure for the demonstration and label it as such.")
h2("Avulsion / river changing course")
body("Screen for low alternative paths using DEM flow directions, historical channels, floodplain depressions, Sentinel/JRC water history, OSM infrastructure and land-cover change. Increase priority where bends are sharp, sediment deposition is visible, blockage diverts water, or bank/embankment heights are low. Simulate one or two plausible break-in paths in Delft3D. This is a <b>conditional susceptibility map</b>, not a reliable prediction of the exact new river course or time without detailed field survey and sediment data.")
story.append(Spacer(1, 8))

h1("9. Damage, people affected and cost analysis")
h2("Exposure overlay")
body("Overlay flood depth, speed, arrival time and duration on buildings, roads, bridges, power and health facilities, cropland and population. For each feature, report whether touched, the relevant hazard values, data source and confidence. Do not equate exposure with actual loss: a mapped building may be elevated, stronger or empty.")
h2("Direct damage method")
bullet("Classify buildings by use and approximate construction type. Apply local depth-damage curves and asset value per square metre; use CPWD or state schedule-of-rates only as a starting benchmark and adjust for local market and structure type.")
bullet("For roads and bridges, estimate repair/replacement from length or area affected, hazard severity and unit cost. For crops, use flooded area, crop type/season, expected yield and farm-gate value.")
bullet("Estimate people exposed from WorldPop and local settlement data. Report people <i>potentially exposed</i>, not casualties. Critical facilities should be individually listed rather than buried in a total.")
bullet("Produce low, central and high costs by varying flood depth, affected asset inventory and unit-rate/damage-function assumptions. Include a separate uncosted or qualitative section for indirect losses and ecological impacts.")
body("The report should show an itemized table, not just one total: asset type, count or area, estimated damage fraction, unit cost, estimated direct loss, and confidence. Quote costs in INR with a stated price year and source.")
h2("Report contents")
table(["Page / section", "What it contains"], [
    ["Executive summary", "Site, event type, scenario severity, maximum inundation, key settlements and earliest arrival."],
    ["Evidence", "Latest water/rain observations, source age, missing data, inferred storage and forecast interval."],
    ["Model method", "SPH and Delft3D inputs, breach assumptions, grid resolution, calibration status, uncertainty."],
    ["Impact", "Maps and tables for depth, speed, arrival, duration, population and critical assets."],
    ["Economics", "Itemized direct-loss ranges, cost basis, exclusions and sensitivity."],
    ["Actionable notes", "High-priority areas for verification and evacuation planning, not an official warning order."],
], [1.35, 5.73])

h1("10. Dashboard, map products and exports")
body("The landing screen shows a map of sites and catchments. Selecting a site opens: (1) observations with source and last-updated time; (2) upstream rainfall and inflow forecast; (3) a scenario builder with breach, surge, blockage and cascade settings; (4) a job-progress panel; (5) downstream flood layers and a time slider; (6) damage tables and a report download.")
body("Let users compare two scenarios side by side and click a map point to see depth, speed and arrival time. All map legends must label units and whether the layer is observed, forecast or simulated.")
h2("Output package")
bullet("KML: flood-extent polygons, key affected locations and selected contours for viewing in Google Earth. Keep geometry simplified enough to open reliably.")
bullet("Shapefile: zipped .shp/.shx/.dbf/.prj for polygons and feature tables; use short field names because SHP has legacy limits. Offer GeoPackage/GeoJSON as richer optional alternatives.")
bullet("Raster: GeoTIFF or Cloud Optimized GeoTIFF for depth, velocity and arrival-time grids. KML/SHP alone cannot faithfully preserve dense continuous grids.")
bullet("PDF: scenario report and data/model provenance. Include a machine-readable JSON manifest for repeatability.")
story.append(Spacer(1, 8))

h1("11. Near-real-time analysis through Earth Engine")
body("Google Earth Engine can rapidly query Sentinel-1, Sentinel-2 and JRC water layers to detect new water, change in lake area and recent flood extent. An automated job requests imagery for the selected catchment, applies quality masks, derives water polygons, and sends a reviewed change layer to the main system. Earth Engine is a hosted service, <b>not</b> an open-source dependency; check project eligibility, quotas and access terms. Keep an alternative local Sentinel processing route for portability.")
body("Near-real-time here means <b>latest available pass</b>, not continuous camera coverage. Clouds affect optical data; radar has terrain shadow and surface roughness errors. Display the acquisition time prominently and verify major changes against another product or manual review.")

h1("12. Build roadmap and acceptance tests")
table(["Phase", "Target time", "Build and demonstrate", "Done when..."], [
    ["A. Site and data", "Week 1-2", "Select Indian dam, natural-blockage case and a two-site cascade chain; assemble catchment, verified network, DEM and assets.", "Each feed and downstream connection has evidence, licence/access note, timestamp and fallback."],
    ["B. Monitoring", "Week 3-4", "Ingestion jobs, database, map, rain/water charts, Sentinel water change and quality flags.", "A user can see latest observations and historical trends without manually preparing files."],
    ["C. Inflow and scenarios", "Week 5-6", "Catchment rainfall, runoff forecast, site water balance and linked cascade graph; breach/release/secondary-failure branches.", "A test hydrograph reaches nodes in the right order and three uncertainty cases run."],
    ["D. Hydraulic models", "Week 7-8", "SPH source model; Delft3D downstream routing through the next dam/lake; hydrograph and storage hand-offs.", "Two connected sites run on one scenario; timing and mass-balance checks are recorded."],
    ["E. Impacts and exports", "Week 9", "Cascade timeline and branch comparison; exposure, direct-cost ranges, KML/SHP/GeoTIFF and PDF report.", "The two cascade branches change downstream maps/costs; exports open and assumptions are traceable."],
    ["F. Validation and demo", "Week 10", "Replay historical evidence; stress-test the chain; rehearse live refresh and a cached backup demo.", "The team can reproduce every node's hydrograph, level, branch and impact from the saved manifest."],
], [0.95, 0.72, 3.05, 2.36])
h2("SIH minimum viable demo")
body("If hackathon time is shorter, narrow the scope to one catchment, one dam-break scenario, one natural-blockage replay, <b>a two-node cascade with two outcome branches</b>, live-ish rain/water ingest, one SPH-to-Delft3D hand-off, flood map, basic exposure/cost, and KML/SHP export. Avulsion may remain a labelled prototype screening module. Do not present an uncalibrated nationwide prediction system as finished.")
h2("Suggested demo storyline")
body("Open a monitored Indian basin, point to the latest observations and their timestamps, and show upstream rainfall and inflow range. Trigger a breach or sudden release. Follow the wave to the next dam/lake, compare its no-failure and conditional-failure branches, and show how arrival, depth and itemized damage change at a downstream settlement. Export KML/SHP and the report. Switch to the natural-blockage case to show a second source of cascading risk.")

h1("13. Risks, safeguards and realistic accuracy")
table(["Risk", "Response"], [
    ["No stable public API or delayed feed", "Access check before committing; cached official files, alternate satellite product, manual import and explicit stale-data badge."],
    ["Unknown bathymetry, breach properties or barrier strength", "Parameter ranges, sensitivity runs, site survey request; scenario label rather than probability claim."],
    ["30 m DEM misses channels and embankments", "Local terrain correction and cross-sections where available; warn against building-level precision."],
    ["Compute-heavy SPH / large rasters", "Small SPH domain, queued jobs, tiling and precomputed demo cases; benchmark run time."],
    ["Incomplete asset maps or weak cost curves", "Data completeness score, local validation and low/central/high cost range."],
    ["High-stakes interpretation", "Clear assumptions, uncertainty, last-updated time and human review; no automated public warning or claim of official authority."],
], [2.15, 4.93])
body("A useful quality panel should grade each run on four separate axes: observation freshness, terrain quality, hydraulic calibration, and exposure/cost completeness. A single generic 'accuracy percentage' would hide the real limitations.")
story.append(Spacer(1, 8))

h1("14. Source and implementation links")
body("These are starting points for the data agreements, adapters and model installation. Confirm current terms and product availability at implementation time. Some sources are open data but require free registration or impose use conditions.")
sources = [
    ("CWC Reservoir Storage Monitoring System", "https://rsms.cwc.gov.in/", "Official reservoir bulletins/portal; verify the specific site and cadence."),
    ("India-WRIS", "https://indiawris.gov.in/wris/", "Indian water-resource portal; inspect available series and access routes."),
    ("IMD public API reference", "https://api.imd.gov.in/public/api_reference.html", "AWS mapping/data and basin products; verify rainfall fields and access requirements."),
    ("MOSDAC download API", "https://mosdac.gov.in/downloadapi-manual", "Registered access to ISRO satellite products."),
    ("NASA IMERG", "https://gpm.nasa.gov/data/imerg", "Half-hourly satellite precipitation; Early run has roughly four-hour latency."),
    ("NASA SWOT LakeSP", "https://podaac.jpl.nasa.gov/dataset/SWOT_L2_HR_LakeSP_D", "Satellite lake elevation/area/storage-change product."),
    ("DAHITI API v2", "https://dahiti.dgfi.tum.de/en/api/doc/v2/", "Water-level/area/volume services; API key required."),
    ("Sentinel-1 on Earth Engine", "https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD", "Radar water extent with terrain/error checks."),
    ("Sentinel-2 on Earth Engine", "https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED", "Optical water/land-cover change where cloud-free."),
    ("JRC Global Surface Water", "https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater", "Historical water baseline, not a live observation."),
    ("Copernicus DEM GLO-30", "https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM", "Regional terrain starting point."),
    ("HydroSHEDS / HydroBASINS", "https://www.hydrosheds.org/products/hydrobasins", "Catchments and drainage topology."),
    ("HydroRIVERS", "https://www.hydrosheds.org/products/hydrorivers", "River links for cascades."),
    ("Wflow", "https://github.com/Deltares/Wflow.jl", "Open-source rainfall-runoff modelling."),
    ("DualSPHysics", "https://github.com/DualSPHysics/DualSPHysics", "Open-source SPH with dam-break examples."),
    ("Delft3D Flexible Mesh", "https://github.com/Deltares/Delft3D", "Open-source hydraulic modelling kernels."),
    ("D-Flow FM user manual", "https://content.oss.deltares.nl/delft3dfm1d2d/D-Flow_FM_User_Manual_1D2D.pdf", "Mesh, boundaries and 1D/2D model setup."),
    ("WorldCover", "https://esa-worldcover.org/en/data-access", "10 m global land-cover layer."),
    ("WorldPop India", "https://hub.worldpop.org/geodata/summary?id=81567", "Population exposure starting point."),
    ("OpenStreetMap Overpass", "https://wiki.openstreetmap.org/wiki/Overpass_API", "Buildings, roads and critical assets; completeness varies."),
    ("ERA5-Land", "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land", "Antecedent moisture and historical weather context."),
    ("GloFAS", "https://www.globalfloods.eu/general-information/data-and-services/", "Independent flow forecast cross-check."),
    ("CPWD Plinth Area Rates 2025", "https://cpwd.gov.in/Publication/PLINTH_AREA_RATES_2025.pdf", "Starting construction-cost benchmark; local validation essential."),
    ("CWC dam flood-risk mapping guideline", "https://damsafety.cwc.gov.in/ecm-includes/PDFs/Guidelines_for_Mapping_Flood_Risks_Associated_with_Dams.pdf", "Indian risk-mapping context."),
]
for name, url, note in sources:
    story.append(P(f"<b>{link(name, url)}</b> - {note}", "SourceX"))

doc.build(story)
print(OUT)
