# CityPulse — Urban Stress Intelligence Platform

**Explore environmental conditions and urban stress signals across major cities around the world.**

[**Open the live CityPulse dashboard →**](https://citypulse-101.streamlit.app/)

CityPulse is an interactive urban intelligence platform that brings together weather information, nearby air-quality observations and analytical tools in one place. Select a country and city to explore local environmental conditions, compare signals and investigate patterns.

## What you can explore

- **City Command Center** — an at-a-glance view of current weather conditions, hourly outlook, nearby air-quality readings and the experimental CityPulse Index when sufficient data is available.
- **City Comparison** — compare up to three cities using live weather and fresh fixed-station PM2.5/PM10 medians normalized to µg/m³, with pollutant-specific station counts, timestamps and station-age ranges. Compare daily historical trends across shared UTC dates when the retained archive contains enough real observations.
- **Air Quality Intelligence** — inspect pollutant-level summaries, station counts, sensor readings and observation freshness.
- **Environmental Analytics** — explore weather forecasts and available historical weather and air-quality observations.
- **Predictive Intelligence** — compare the Open-Meteo provider outlook with CityPulse-trained 24-, 48- and 72-hour estimates for apparent temperature, air temperature, humidity, hourly precipitation and wind; evaluate fixed-station PM2.5/PM10 outlooks from 3-hour concentration series. Each model uses a chronological holdout with a horizon embargo and is displayed only when it beats persistence.
- **Anomaly Detection** — identify unusual weather patterns relative to the platform's collected historical baseline.
- **Zone Intelligence** — inspect fixed/mobile station coverage, freshness and station provenance; view the returned-sample coverage grid; screen for recent relative pollution clusters; optionally show an inverse-distance-weighted pollution surface only inside the fixed-station convex hull and only when leave-one-station-out MAE beats a median baseline; analyze multi-scene Landsat surface-temperature contrasts; explore ESA land cover, mapped green spaces, bounded OpenStreetMap walking-network estimates, Copernicus DEM GLO-30 elevation/slope/topographic-position and D8 flow-accumulation layers, plus mapped rivers, streams, canals, drains and water bodies.
- **Environmental Health & Exposure** — view WorldPop population estimates in distance rings around a city-centre point, inspect under-5 and age-65+ demographic context, optionally view a 1 km population grid, and estimate distance-weighted population proximity around an elevated heat point or qualifying pollution monitors.
- **Smart Alerts & Recommendations** — configure per-city dashboard thresholds for heat, rainfall, PM2.5 and PM10; inspect current and forecast triggers, source-grounded next steps and saved history. A separate three-hour scheduled monitor also checks all configured cities using deployment-wide thresholds.
- **Data Quality & Confidence** — inspect source freshness, returned-station coverage, future timestamps, missing units/station identities, invalid values and broad plausibility flags; export an audit summary. Smart-alert history can be exported from the saved SQLite history.
- **Scenario Simulator** — adjust environmental assumptions and explore how they affect the project's experimental index.
- **Methodology** — understand the data sources, index approach and current limitations.

## Global city coverage

CityPulse currently includes **32 countries and 236 city locations** across Asia, Europe, Africa, North America, South America and Oceania.

Choose a country first, then select one of its available cities. India is pinned at the top of the country list, with its cities arranged alphabetically. Other countries and their cities are also listed alphabetically.

Coverage includes India, Australia, Bangladesh, Brazil, Canada, China, Egypt, Finland, France, Iceland, Israel, Italy, Japan, the Maldives, Mexico, New Zealand, North Korea, Pakistan, Qatar, Russia, Saudi Arabia, South Africa, South Korea, Spain, Sri Lanka, Switzerland, Thailand, Turkey, the UAE, the United Kingdom, the United States and Zimbabwe.

City locations use approximate city-centre coordinates. Weather and air-quality data availability varies by location.

## Data sources

- **Weather:** [Open-Meteo](https://open-meteo.com/) — modelled current conditions and weather forecasts.
- **Air quality:** [OpenAQ](https://openaq.org/) — observations reported by nearby monitoring stations.
- **Population and demographic context:** [WorldPop Global2 API](https://api.worldpop.org/v3/documentation) — approximately 100 m modelled population estimates and age-group totals (CC BY 4.0; [population dataset DOI](https://doi.org/10.5258/SOTON/WP00839), [age/sex dataset DOI](https://doi.org/10.5258/SOTON/WP00841)).
- **Satellite land-surface temperature:** [USGS Landsat Collection 2 Level-2](https://www.usgs.gov/landsat-missions/landsat-collection-2) accessed through the [Microsoft Planetary Computer STAC catalog](https://planetarycomputer.microsoft.com/catalog/dataset/landsat-c2-l2) — thermal surface-temperature, reflectance and quality bands for scene-based analysis.
- **Terrain:** [Copernicus DEM GLO-30](https://planetarycomputer.microsoft.com/dataset/cop-dem-glo-30) accessed through the [Microsoft Planetary Computer STAC API](https://planetarycomputer.microsoft.com/docs/) — approximately 30 m digital surface model used for local slope and relative topographic-position screening.
- **Satellite context imagery:** [NASA Global Imagery Browse Services](https://gibs.earthdata.nasa.gov/) — MODIS Terra daytime land-surface temperature imagery (about 1 km).
- **Land cover:** [ESA WorldCover](https://esa-worldcover.org/en/data-access) — 2021 land-cover classification at 10 m resolution.
- **Parks, waterways and green spaces:** [OpenStreetMap](https://www.openstreetmap.org/) — community-mapped parks, gardens, forests, grassland, rivers, streams, canals, drains and surface-water features (© OpenStreetMap contributors; [attribution](https://www.openstreetmap.org/copyright)).

The platform presents provider weather forecasts separately from its own experimental analytics. Air-quality station coverage, pollutants and observation recency vary between cities. A city appearing in the selector does not guarantee that nearby live air-quality readings are available.

## Understanding the CityPulse Index

The CityPulse Index is an experimental project-level environmental signal combining:

- Heat signal
- Particulate matter signal (PM2.5 and PM10)
- Rainfall signal

The current heuristic weights these components at 50%, 35% and 15%, respectively. The particulate component uses recent available readings, and the composite is withheld when required inputs are missing rather than filling gaps with invented values.

**The CityPulse Index is not an official AQI, regulatory measurement, health assessment or public warning.** It is a prototype indicator intended for exploration. For official air-quality information, consult the relevant national or local environmental authority.

## Comparison and spatial methodology

- City comparisons use the latest eligible reading from each fixed OpenAQ station within 48 hours, exclude mobile sensors, normalize supported mass-concentration units, and report how recent the oldest/median station reports are. The CityPulse Index remains a separate experimental composite.
- Zone coverage describes the stations OpenAQ actually returned (maximum 12 locations within a 25 km query radius). Empty 5 km cells mean no fixed station was returned in that sample; they do not prove that no monitor exists there.
- The relative-cluster screen requires at least six recent fixed stations for one pollutant and unit, then groups upper-quartile readings within 5 km. It is not an official air-quality alert.
- Terrain screening uses Copernicus DEM GLO-30 resampled to a local analysis grid. Slope is derived from elevation gradients; topographic position is elevation minus a roughly 1 km neighbourhood mean. "Relatively low-lying & gentle" marks cells in the lowest 20% of local topographic-position values with slope ≤5°. The DEM is a digital surface model (buildings and vegetation included), and these indicators are not flood probability, flow accumulation, water depth or drainage-capacity estimates.
- Rainfall context is the selected city's Open-Meteo hourly precipitation forecast summed over the next 24/72 hours. It is a modelled city grid-cell forecast, not zone-level rainfall. OpenStreetMap water features are community-mapped centre points rather than a verified, complete drainage or hydrography network.
- Spatial interpolation uses inverse-distance weighting within the Delaunay convex hull of eligible fixed stations, with a 3 km nearest-station limit and leave-one-station-out comparison against a median baseline. It is shown only when IDW performs better on that diagnostic.

## Alert persistence and email configuration

The Smart Alerts page stores per-city dashboard preferences and deduplicated page-evaluation history in `data/processed/citypulse_state.sqlite3`; set `CITYPULSE_STATE_DB` to a path on a persistent mounted volume when deploying to retain those settings across redeployments. Preferences are application-level per city, not per authenticated user; the current app does not implement user accounts. Separately, the scheduled GitHub Actions data-collection job evaluates current conditions and the next 24-hour forecast every three hours for all configured cities, persists deduplicated background events in `data/processed/scheduled_alert_state.sqlite3`, and commits that public, non-secret event history to the repository. The dashboard displays that scheduled history when the latest state file has been deployed.

Email notifications are opt-in per city and sent only to the deployment administrator address. Configure these Streamlit secrets or environment variables. Streamlit Secrets may use flat root-level keys:

- `CITYPULSE_SMTP_HOST`
- `CITYPULSE_SMTP_PORT`
- `CITYPULSE_SMTP_FROM`
- `CITYPULSE_ALERT_EMAIL`
- Optional: `CITYPULSE_SMTP_USERNAME`
- Optional: `CITYPULSE_SMTP_PASSWORD`

Alternatively, use a `[smtp]` table in Streamlit Secrets with `host`, `port`, `from_address`, `alert_email`, and (optionally) `username` and `password` keys. Do not commit SMTP credentials or recipient details to the repository. The dashboard's optional email checkbox sends only newly recorded events when that page is evaluated. For unattended monitoring, add the same six `CITYPULSE_SMTP_*` / `CITYPULSE_ALERT_EMAIL` values as GitHub Actions repository secrets. Email from the scheduled monitor is off by default: set the GitHub Actions repository variable `CITYPULSE_SCHEDULED_EMAIL_ENABLED=true` to enable one consolidated email per three-hour monitoring run. The worker uses deployment-wide GitHub Actions variables `CITYPULSE_ALERT_HEAT_C`, `CITYPULSE_ALERT_RAINFALL_MM`, `CITYPULSE_ALERT_PM25_UG_M3` and `CITYPULSE_ALERT_PM10_UG_M3`; if unset it uses 40 °C, 20 mm, 60 µg/m³ and 100 µg/m³. These are separate from the per-city thresholds saved in the interactive dashboard. Failed delivery is recorded but is not automatically retried. SMTP must permit STARTTLS on the configured port. The interactive dashboard's SQLite preferences/history survive restarts only when `CITYPULSE_STATE_DB` points to a durable mounted volume. Background monitor event history is committed separately to the repository and contains environmental alert metadata, not SMTP credentials or recipient details.

A separate [WorldPop Live API Smoke Check workflow](https://github.com/SnehalTripathy/CityPulse/actions/workflows/worldpop-live-smoke.yml) checks catchment rings and age-group totals for Bengaluru, London and Nairobi, plus the 1 km raster and distance-weighted exposure endpoints. It is scheduled weekly and can also be run manually from GitHub Actions. This is a service-contract check; it does not replace verifying the live Streamlit page.

## Important notes

- Weather values are modelled grid-cell data, not street-level measurements. CityPulse's 24–72-hour experimental models use archived Open-Meteo observations and fixed-station OpenAQ pollutant samples; they are suppressed whenever they fail a chronological holdout comparison against persistence. The projected CityPulse Index combines validated apparent-temperature, hourly-rainfall and PM forecasts using the existing experimental 50/35/15 weighting. Model availability depends on the quantity, regularity and freshness of actual city history.
- Air-quality readings come from monitoring stations; coverage and reporting times are not uniform.
- Historical records build over time as scheduled data collection runs. Newly added cities may not yet have sufficient history for trend analysis or machine-learning features.
- Historical city trends use a compressed, retained 365-day station/day archive. Weather and sensor reports are summarized by UTC day; particulate values are converted to µg/m³ where supported. A chart requires at least two cities with three observed days each and at least three shared dates. Missing dates remain visible gaps, not filled values. The scheduled collector must accumulate real observations before this feature becomes populated.
- Relative pollution clusters use only recent, comparable fixed-station observations; they are sample-relative signals, not regulatory thresholds or health warnings. IDW surfaces are estimates—not measurements—and are withheld unless at least six recent fixed stations support a convex-hull surface and spatial cross-validation beats a median baseline. Surfaces are limited to 3 km from a station.
- Copernicus terrain screening maps elevation, slope, local topographic position and simple D8 upslope-cell accumulation. Routing follows each cell's steepest strictly lower neighbour; closed depressions and flats remain sinks, and no hydrological conditioning is applied. OpenStreetMap water features and selected-city Open-Meteo rainfall forecast provide additional context. These are exploratory layers, not a calibrated flood model: they do not predict flood extent/probability, estimate water depth, or assess drainage infrastructure.
- Landsat surface-temperature analysis compares an approximate low-NDVI urban-core proxy with a vegetated outer reference across up to three usable scenes. Cloud, shadow, snow, fill, water, saturation and terrain-occlusion pixels are masked, and ST-QA uncertainty is reported where available. The contrast is an exploratory surface-temperature proxy, not near-surface air temperature, an official UHI metric or a long-term seasonal climatology. ESA WorldCover is a dated 2021 layer.
- OpenStreetMap green-space coverage depends on community mapping. The optional walking estimate follows a bounded sample of mapped walkable ways to the nearest network node of each mapped feature centre; it is not a verified entrance route or complete citywide pedestrian accessibility analysis. Distances, walk times and routes are approximate.
- Predictive and anomaly-detection features are experimental and are shown only when their data requirements are met.
- Environmental Health & Exposure uses WorldPop Global2 modelled population estimates. The default display year is 2025; the 1 km map aggregates the source grid to 1 km cells, while population rings and demographic groups are computed for a 10 km geometric buffer around the configured city-centre coordinate. This is not a municipal boundary or live census. Under-5 and age-65+ totals are demographic context, not a validated heat-vulnerability score.
- WorldPop proximity exposure uses the documented distance-decay method (p=1) around the selected modelled heat grid point or threshold-crossing fixed monitoring stations. For multiple pollution features, each person is assigned to the nearest feature to avoid double counting. These figures are not confirmed affected people or evidence of health impacts.
- Smart Alerts uses user-configurable prototype triggers (defaults: apparent temperature 40 °C, preceding-hour rainfall 20 mm, PM2.5 60 µg/m³ and PM10 100 µg/m³). Current Open-Meteo conditions, its next-24-hour forecast and recent fixed OpenAQ station medians are reported as separate trigger types. PM medians use readings no more than 24 hours old and compatible mass units. These triggers are not official warnings or regulatory AQI thresholds. Alert thresholds and deduplicated alert history are stored in a local SQLite state database. Optional email delivery is supported through deployment-configured SMTP settings; SMS and push delivery are not included.
- CityPulse is an exploratory information platform, not an emergency-response or health-advice service.

