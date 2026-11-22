# CityPulse — Urban Stress Intelligence Platform

**Explore environmental conditions and urban stress signals across major cities around the world.**

[**Open the live CityPulse dashboard →**](https://citypulse-101.streamlit.app/)

CityPulse is an interactive urban intelligence platform that brings together weather information, nearby air-quality observations and analytical tools in one place. Select a country and city to explore local environmental conditions, compare signals and investigate patterns.

## What you can explore

- **City Command Center** — an at-a-glance view of current weather conditions, hourly outlook, nearby air-quality readings and the experimental CityPulse Index when sufficient data is available.
- **Environmental Analytics** — explore weather forecasts and available historical weather and air-quality observations.
- **Predictive Intelligence** — view experimental machine-learning estimates when enough historical observations are available and the model performs better than a simple baseline.
- **Anomaly Detection** — identify unusual weather patterns relative to the platform's collected historical baseline.
- **Zone Intelligence** — explore the locations of nearby air-quality monitoring stations on a map.
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
- Predictive and anomaly-detection features are experimental and are shown only when their data requirements are met.
- CityPulse is an exploratory information platform, not an emergency-response or health-advice service.

## Project

CityPulse is an evolving urban environmental intelligence project. Its aim is to make city-level environmental information easier to explore while clearly communicating data availability, uncertainty and the limits of experimental indicators.

[**Launch CityPulse on Streamlit →**](https://citypulse-101.streamlit.app/)
