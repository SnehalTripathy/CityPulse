# CityPulse 2.0 — Master Delivery Checklist

This is the working project checklist. Check an item only after implementation and verification. "Data-dependent" items require suitable external data coverage and must not be represented with synthetic observations.

## Current product foundation
- [x] Multi-country and city selector with India pinned first and alphabetical city lists
- [x] Global city directory with city-centre coordinates and timezones
- [x] Live weather integration through Open-Meteo
- [x] Nearby air-quality observations through OpenAQ (coverage varies)
- [x] Experimental CityPulse Index with missing-data safeguards
- [x] Historical observation collector and city-specific analytics
- [x] Initial command centre, environmental analytics, predictive, anomaly, zone and scenario pages
- [x] GitHub Actions CI and scheduled collection workflows
- [x] Public-facing README and live Streamlit link

## Five priority product capabilities
- [x] **1. City Comparison Engine**
  - [x] Compare 2–3 selected cities side by side
  - [x] Compare weather, PM2.5, PM10, rainfall and the experimental CityPulse Index
  - [x] Show pollutant availability, observation timestamps and fair-comparison caveats
  - [x] Add multi-city daily trend comparison with shared UTC windows, pollutant-unit filtering and a minimum-history gate; results remain withheld until sufficient archive coverage exists
- [x] **2. Advanced Zone Intelligence — station, satellite-context and mapped-green-space scope delivered with explicit data limits**
  - [x] Interactive station map with pollutant-aware detail and station selection
  - [x] Show returned-station distribution, occupied 5 km cells, station freshness and the OpenAQ query footprint; do not infer confirmed gaps from empty cells
  - [x] Screen for relative elevated station clusters only with at least six recent comparable stations and a multi-station group within 5 km; otherwise withhold
  - [x] Add NASA MODIS daytime land-surface temperature imagery as UHI investigation context; a numeric urban-versus-rural UHI estimate is not claimed
  - [x] Add ESA WorldCover land-cover and OpenStreetMap green-space layers with straight-line park-proximity indicators; walking-network accessibility remains a future enhancement
- [ ] **3. Environmental Health & Exposure**
  - [ ] Add population distribution and exposure overlays using reputable gridded data
  - [ ] Estimate population exposed to elevated heat or pollution with documented assumptions
  - [ ] Add heat vulnerability / sensitive-population indicators where defensible data exists
  - [ ] Show uncertainty and avoid clinical or individual health claims
- [ ] **4. Smart Alerts & Recommendations**
  - [ ] Configurable thresholds for heat, rainfall and pollutant readings
  - [ ] Alert on observed threshold crossings and forecast risk, clearly distinguished
  - [ ] Explain which measurements triggered an alert
  - [ ] Recommend practical, source-grounded mitigation actions
  - [ ] Add delivery channel and user preferences only after alert logic is validated
- [ ] **5. Data Quality & Confidence Layer**
  - [x] Per-source freshness and last-observed timestamp
  - [ ] Sensor/station coverage and missing-data indicators
  - [ ] Unit, timestamp and plausible-range validation
  - [ ] Confidence/coverage labels based on observable evidence, not invented probabilities
  - [ ] Preserve provenance for every displayed metric

## Phase 1 — Better intelligence
- [ ] Normalize pollutant names and units across sources
- [x] Display pollutant-level analytics and time freshness
- [ ] Separate official AQI values (where an official feed exists) from the experimental CityPulse Index
- [x] Build daily historical comparison trends on shared UTC windows, retaining only compatible pollutant concentration units; live snapshots remain timestamp-led
- [ ] Add source provenance and quality indicators to dashboard metrics
- [ ] Expand historical views after validating persistent archive access

## Phase 2 — Geospatial intelligence
- [x] Replace the basic station pin view with a richer interactive station map
- [x] Add station-level drill-down and a sparse-coverage warning
- [ ] Add pollution hotspot interpolation only when station density and validation permit
- [x] Add NASA MODIS daytime land-surface temperature context imagery; quantitative UHI contrast is still unvalidated
- [x] Add ESA WorldCover 2021 land-cover imagery and OpenStreetMap mapped green-space features
- [ ] Add rainfall accumulation and flood-susceptibility layers from authoritative datasets
- [ ] Add geospatial population exposure overlays

## Phase 3 — Predictive intelligence
- [ ] Build a validated multi-variable 24–72 hour stress forecast
- [ ] Forecast pollutant deterioration only where a suitable history/feed exists
- [ ] Model heatwave and heavy-rainfall risk from appropriate inputs
- [ ] Use time-ordered evaluation, persistence baselines and leakage checks
- [ ] Add model monitoring, drift checks and explainability
- [ ] Display prediction intervals / uncertainty when calibrated and supported

## Phase 4 — Actionable intelligence
- [ ] Explain why a city's stress signal changed
- [ ] Add threshold-based heat, pollution and rainfall alerts
- [ ] Add city/zone-specific recommendations with supporting rationale
- [ ] Add environmental summary reports and export
- [ ] Add population exposure / planning insights for policymakers
- [ ] Add alert preferences and delivery integrations after validation

## Final project closeout
- [ ] Remove this master checklist (`PROJECT_ROADMAP.md`) from the public GitHub repository after all project features, release checks and documentation are complete.

## Five-hour implementation sprint — target 12:30 AM IST, 23 November 2026
- [x] Fix global-city timezone handling in weather requests
- [x] Build a 2–3 city comparison view using live provider responses
- [x] Add pollutant breakdown, station count and reading freshness to air-quality analytics
- [x] Upgrade Zone Intelligence station map and station drill-down
- [x] Add a transparent data freshness / coverage panel
- [x] Add or update tests for city comparison metrics, timezone handling, air-quality freshness and global city registry
- [x] Run CI and resolve regressions (26 tests passed in the latest verified run)
- [ ] Verify the deployed Streamlit app where deployment status is observable

## Release quality gates
- [ ] No synthetic or silently imputed live environmental measurements
- [ ] Distinguish modelled weather, sensor measurements, provider forecasts and CityPulse model outputs
- [x] Show timestamps, units, sources and missing-data states for current live comparison and air-quality views
- [x] Confirm city timezone handling for every country (all registry timezones validated and passed to weather requests)
- [x] Automated tests pass (20 tests passed in GitHub Actions)
- [x] README accurately describes released features and limitations
- [ ] Streamlit deployment successfully starts and core pages render
