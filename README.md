# CityPulse — Urban Stress Intelligence Platform

**Explore environmental conditions and urban stress signals across major cities around the world.**

[**Open the live CityPulse dashboard →**](https://citypulse-101.streamlit.app/)

CityPulse is an interactive urban intelligence platform that brings together weather information, nearby air-quality observations and analytical tools in one place. Select a country and city to explore local environmental conditions, compare signals and investigate patterns.

## What you can explore

- **City Command Center** — an at-a-glance view of current weather conditions, hourly outlook, nearby air-quality readings and the experimental CityPulse Index when sufficient data is available.
- **City Comparison** — compare up to three cities using live weather, available PM2.5/PM10 observations, rainfall and the experimental CityPulse Index; inspect daily historical trends when the archive has enough comparable data.
- **Air Quality Intelligence** — inspect pollutant-level summaries, station counts, sensor readings and observation freshness.
- **Environmental Analytics** — explore weather forecasts and available historical weather and air-quality observations.
- **Predictive Intelligence** — view experimental machine-learning estimates when enough historical observations are available and the model performs better than a simple baseline.
- **Anomaly Detection** — identify unusual weather patterns relative to the platform's collected historical baseline.
- **Zone Intelligence** — inspect returned monitoring stations, their spatial distribution and freshness; screen for relative clusters only when enough recent comparable stations exist; explore mapped green spaces, NASA daytime land-surface temperature imagery and ESA land-cover context.
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
- **Satellite land-surface temperature:** [NASA Global Imagery Browse Services](https://gibs.earthdata.nasa.gov/) — MODIS Terra daytime land-surface temperature imagery (about 1 km).
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

## Important notes

- Weather values are modelled grid-cell data, not street-level measurements.
- Air-quality readings come from monitoring stations; coverage and reporting times are not uniform.
- Historical records build over time as scheduled data collection runs. Newly added cities may not yet have sufficient history for trend analysis or machine-learning features.
- Historical city trends use common UTC calendar-day windows, report coverage and remain unavailable until enough archived observations exist; missing days are not filled.
- Relative pollution clusters use only recent, comparable station observations and are not official thresholds, health warnings or interpolated neighbourhood measurements.
- NASA surface-temperature imagery is a satellite context layer, not near-surface air temperature or a computed urban-heat-island score. ESA WorldCover is a dated 2021 layer.
- OpenStreetMap green-space coverage depends on community mapping. Park proximity is straight-line distance to mapped feature centres, not walking-route accessibility.
- Predictive and anomaly-detection features are experimental and are shown only when their data requirements are met.
- CityPulse is an exploratory information platform, not an emergency-response or health-advice service.

