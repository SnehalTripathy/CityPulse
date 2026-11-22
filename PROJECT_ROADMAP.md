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
  - [x] Add multi-city daily trend comparison with shared UTC windows, stable station IDs, PM unit normalization, pollutant-specific observation ages and a minimum common-history gate
  - [x] Build and commit a compressed 365-day station/day archive in the scheduled collector
  - [ ] Confirm the first scheduled archive run and accumulate at least three shared observed UTC days in two or more cities (data-dependent)
- [x] **2. Advanced Zone Intelligence — station coverage, validated spatial estimates, satellite surface-temperature analysis and mapped green-space context delivered with explicit data limits**
  - [x] Interactive station map with pollutant-aware detail and station selection
  - [x] Show fixed/mobile station distribution, a 5 km returned-sample coverage grid, timestamp quality, freshness, source/owner/license provenance and the OpenAQ query footprint; empty cells do not prove no monitor exists
  - [x] Screen for relative elevated clusters using at least six recent fixed stations with the same pollutant/unit; only multi-station high-value groups within 5 km are shown
  - [x] Add bounded IDW station-footprint estimates only within the convex hull, within 3 km of a recent fixed station, and only when leave-one-out MAE beats the median baseline
  - [x] Add multi-scene Landsat Collection 2 Level-2 surface-temperature contrast, using QA-masked thermal/reflectance pixels, urban/vegetated proxy pools and ST-QA uncertainty; label as exploratory, not climatological or official UHI
  - [x] Add OpenStreetMap green-space discovery with straight-line proximity and endpoint failover
  - [ ] Verify live OpenStreetMap green-space lookup across fallback endpoints
  - [x] Remove ESA WorldCover and NASA MODIS WMS overlays because their third-party map-proxy dependencies were unreliable
  - [x] Remove optional walk-network routing from the user interface to avoid a second high-volume Overpass query and overclaiming citywide pedestrian access
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
- [x] Normalize pollutant aliases and comparable PM concentration units for city comparison, daily trends and the experimental CityPulse Index
- [x] Display pollutant-level analytics and time freshness
- [ ] Separate official AQI values (where an official feed exists) from the experimental CityPulse Index
- [x] Build daily historical comparison trends on shared UTC windows, retaining stable station IDs and converting compatible PM mass units to µg/m³
- [ ] Add source provenance and quality indicators to dashboard metrics
- [x] Add a compressed 365-day station/day archive and scheduled collector upsert; [ ] verify first real remote archive run and multi-city trend population

## Phase 2 — Geospatial intelligence
- [x] Replace the basic station pin view with a richer interactive station map
- [x] Add station-level drill-down and a sparse-coverage warning
- [x] Add IDW pollution-surface estimates only inside the fixed-station convex hull, with six recent comparable stations, a 3 km nearest-station bound and leave-one-station-out MAE beating a median baseline
- [x] Add QA-masked multi-scene Landsat surface-temperature contrast and NASA MODIS context imagery; exploratory urban/vegetated proxy contrast is not an official or seasonal UHI estimate
- [x] Add OSM mapped green spaces with straight-line proximity and endpoint failover
- [x] Remove unreliable third-party WorldCover/MODIS WMS overlays and optional high-volume walk-network routing
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
- [x] Run CI and resolve regressions (56 tests passed in the latest verified run)
- [ ] Verify the deployed Streamlit app where deployment status is observable

## Release quality gates
- [x] No synthetic or silently imputed measurements in new comparison, trend, station-grid, interpolation, cluster, Landsat or OSM workflows; CityPulse Index is withheld when required weather, PM or rainfall inputs are missing
- [ ] Complete a project-wide audit of remaining legacy dashboard views for silent defaults and imputation
- [x] Distinguish modelled grid-cell weather, OpenAQ station measurements, provider forecasts, experimental CityPulse outputs and spatial estimates in the new comparison/zone views
- [x] Show timestamps, units, source provenance, station-age ranges and missing/future-data states in comparison and zone views
- [x] Confirm city timezone handling for every country (all registry timezones validated and passed to weather requests)
- [x] Automated tests pass (56 tests passed in GitHub Actions)
- [x] README accurately describes released features and limitations
- [ ] Streamlit deployment successfully starts and core pages render
