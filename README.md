# CityPulse — Urban Stress Intelligence Platform

**Explore environmental conditions and urban stress signals across major cities around the world.**

[**Open the live CityPulse dashboard →**](https://citypulse-101.streamlit.app/)

CityPulse is an interactive urban intelligence platform that brings together weather information, nearby air-quality observations and analytical tools in one place. Select a country and city to explore local environmental conditions, compare signals and investigate patterns.

## What you can explore

- **City Command Center** — an at-a-glance view of current weather conditions, hourly outlook, nearby air-quality readings and the experimental CityPulse Index when sufficient data is available.
- **City Comparison** — compare up to three cities using live weather and fresh fixed-station PM2.5/PM10 medians normalized to µg/m³, with pollutant-specific station counts, timestamps and station-age ranges. Compare daily historical trends across shared UTC dates when the retained archive contains enough real observations.
- **Air Quality Intelligence** — inspect pollutant-level summaries, station counts, sensor readings and observation freshness.
- **Environmental Analytics** — explore weather forecasts and available historical weather and air-quality observations.
- **Predictive Intelligence** — view experimental machine-learning estimates when enough historical observations are available and the model performs better than a simple baseline.
- **Anomaly Detection** — identify unusual weather patterns relative to the platform's collected historical baseline.
- **Zone Intelligence** — inspect fixed/mobile station coverage, freshness and station provenance; view the returned-sample coverage grid; screen for recent relative pollution clusters; optionally show an inverse-distance-weighted pollution surface only inside the fixed-station convex hull and only when leave-one-station-out MAE beats a median baseline; analyze multi-scene Landsat surface-temperature contrasts; explore ESA land cover, mapped green spaces and bounded OpenStreetMap walking-network estimates.
- **Environmental Health & Exposure** — view WorldPop population estimates in distance rings around a city-centre point, inspect under-5 and age-65+ demographic context, optionally view a 1 km population grid, and estimate distance-weighted population proximity around an elevated heat point or qualifying pollution monitors.
- **Smart Alerts & Recommendations** — configure prototype thresholds for heat, rainfall, PM2.5 and PM10; distinguish current modelled conditions, hourly forecasts and recent fixed-station readings; inspect trigger evidence and source-grounded next steps.
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
- **Satellite context imagery:** [NASA Global Imagery Browse Services](https://gibs.earthdata.nasa.gov/) — MODIS Terra daytime land-surface temperature imagery (about 1 km).
- **Land cover:** [ESA WorldCover](https://esa-worldcover.org/en/data-access) — 2021 land-cover classification at 10 m resolution.
- **Parks and green spaces:** [OpenStreetMap](https://www.openstreetmap.org/) — community-mapped parks, gardens, forests and grassland features (© OpenStreetMap contributors; [attribution](https://www.openstreetmap.org/copyright)).

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
- Spatial interpolation uses inverse-distance weighting within the Delaunay convex hull of eligible fixed stations, with a 3 km nearest-station limit and leave-one-station-out comparison against a median baseline. It is shown only when IDW performs better on that diagnostic.

## Important notes

- Weather values are modelled grid-cell data, not street-level measurements.
- Air-quality readings come from monitoring stations; coverage and reporting times are not uniform.
- Historical records build over time as scheduled data collection runs. Newly added cities may not yet have sufficient history for trend analysis or machine-learning features.
- Historical city trends use a compressed, retained 365-day station/day archive. Weather and sensor reports are summarized by UTC day; particulate values are converted to µg/m³ where supported. A chart requires at least two cities with three observed days each and at least three shared dates. Missing dates remain visible gaps, not filled values. The scheduled collector must accumulate real observations before this feature becomes populated.
- Relative pollution clusters use only recent, comparable fixed-station observations; they are sample-relative signals, not regulatory thresholds or health warnings. IDW surfaces are estimates—not measurements—and are withheld unless at least six recent fixed stations support a convex-hull surface and spatial cross-validation beats a median baseline. Surfaces are limited to 3 km from a station.
- Landsat surface-temperature analysis compares an approximate low-NDVI urban-core proxy with a vegetated outer reference across up to three usable scenes. Cloud, shadow, snow, fill, water, saturation and terrain-occlusion pixels are masked, and ST-QA uncertainty is reported where available. The contrast is an exploratory surface-temperature proxy, not near-surface air temperature, an official UHI metric or a long-term seasonal climatology. ESA WorldCover is a dated 2021 layer.
- OpenStreetMap green-space coverage depends on community mapping. The optional walking estimate follows a bounded sample of mapped walkable ways to the nearest network node of each mapped feature centre; it is not a verified entrance route or complete citywide pedestrian accessibility analysis. Distances, walk times and routes are approximate.
- Predictive and anomaly-detection features are experimental and are shown only when their data requirements are met.
- Environmental Health & Exposure uses WorldPop Global2 modelled population estimates. The default display year is 2025; the 1 km map aggregates the source grid to 1 km cells, while population rings and demographic groups are computed for a 10 km geometric buffer around the configured city-centre coordinate. This is not a municipal boundary or live census. Under-5 and age-65+ totals are demographic context, not a validated heat-vulnerability score.
- WorldPop proximity exposure uses the documented distance-decay method (p=1) around the selected modelled heat grid point or threshold-crossing fixed monitoring stations. For multiple pollution features, each person is assigned to the nearest feature to avoid double counting. These figures are not confirmed affected people or evidence of health impacts.
- Smart Alerts uses user-configurable prototype triggers (defaults: apparent temperature 40 °C, preceding-hour rainfall 20 mm, PM2.5 60 µg/m³ and PM10 100 µg/m³). Current Open-Meteo conditions, its next-24-hour forecast and recent fixed OpenAQ station medians are reported as separate trigger types. PM medians use readings no more than 24 hours old and compatible mass units. These triggers are not official warnings or regulatory AQI thresholds. Threshold settings are session-only; email, SMS and push delivery are not implemented.
- CityPulse is an exploratory information platform, not an emergency-response or health-advice service.

