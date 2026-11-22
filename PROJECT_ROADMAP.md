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
  - [ ] Confirm the first scheduled archive run and accumulate at least three shared observed UTC days in two or more cities (data-dependent; raw and processed archive files are still absent from main)
- [x] **2. Advanced Zone Intelligence — station coverage, validated spatial estimates, satellite surface-temperature analysis and park access delivered with explicit data limits**
  - [x] Interactive station map with pollutant-aware detail and station selection
  - [x] Show fixed/mobile station distribution, a 5 km returned-sample coverage grid, timestamp quality, freshness, source/owner/license provenance and the OpenAQ query footprint; empty cells do not prove no monitor exists
  - [x] Screen for relative elevated clusters using at least six recent fixed stations with the same pollutant/unit; only multi-station high-value groups within 5 km are shown
  - [x] Add bounded IDW station-footprint estimates only within the convex hull, within 3 km of a recent fixed station, and only when leave-one-out MAE beats the median baseline
  - [x] Add multi-scene Landsat Collection 2 Level-2 surface-temperature contrast, using QA-masked thermal/reflectance pixels, urban/vegetated proxy pools and ST-QA uncertainty; label as exploratory, not climatological or official UHI
  - [x] Add ESA WorldCover 2021 and OpenStreetMap green-space layers with straight-line proximity
  - [x] Add bounded OSM walk-network estimates with snap-distance/route caveats; no public park entrance or citywide network completeness is claimed
- [x] **3. Environmental Health & Exposure — first implementation**
  - [x] Add WorldPop Global2 population distribution using the documented 100 m estimates, with a 1 km grid overlay and 1/3/5/10 km city-centre catchment counts
  - [x] Estimate distance-weighted population near an elevated city-centre heat signal or threshold-crossing fixed pollution monitors using the WorldPop exposure endpoint; label as proximity estimates, not people confirmed affected
  - [x] Add under-5 and age-65+ demographic context as cautious sensitivity indicators; do not produce an unsupported composite heat-vulnerability score
  - [x] Show the WorldPop year, source, licence, buffer assumptions and limitations; avoid clinical or individual health claims
- [x] **4. Smart Alerts & Recommendations — first implementation**
  - [x] Add session-configurable thresholds for apparent temperature, preceding-hour rainfall, PM2.5 and PM10
  - [x] Separate current modelled weather conditions, next-24-hour provider forecast triggers and recent fixed-station particulate triggers
  - [x] Explain each trigger with its value, configured threshold, timestamp, source and eligible station count
  - [x] Provide practical next steps tied to heat, rainfall and particulate triggers; distinguish user triggers from official warnings
  - [x] Add browser-session alert history with duplicate suppression and CSV export
  - [ ] Add durable cross-session alert persistence, notification delivery channels and saved user preferences after selecting and securing a persistence/notification service
- [x] **5. Data Quality & Confidence Layer — first implementation**
  - [x] Per-source freshness and last-observed timestamp
  - [x] Sensor/station coverage and missing-data indicators for returned OpenAQ sample
  - [x] Unit-presence, timestamp, non-numeric and broad plausible-range validation
  - [x] Coverage labels based on station counts and observed freshness, not invented probabilities
  - [x] Preserve provenance in source-specific views and quality audit
  - [ ] Complete an app-wide provenance audit of every legacy metric and all future data sources

## Phase 1 — Better intelligence
- [x] Normalize pollutant aliases and comparable PM concentration units for city comparison, daily trends and the experimental CityPulse Index
- [x] Display pollutant-level analytics and time freshness
- [x] Separate official AQI values (where an official feed exists) from the experimental CityPulse Index; current connected feeds do not supply an official AQI, and the UI labels this explicitly
- [x] Build daily historical comparison trends on shared UTC windows, retaining stable station IDs and converting compatible PM mass units to µg/m³
- [x] Add source provenance and quality indicators to dashboard metrics across Command Center, City Comparison, Air Quality Intelligence and Zone Intelligence
- [x] Add a compressed 365-day station/day archive and scheduled collector upsert; [ ] verify first real remote archive run and multi-city trend population

## Phase 2 — Geospatial intelligence
- [x] Replace the basic station pin view with a richer interactive station map
- [x] Add station-level drill-down and a sparse-coverage warning
- [x] Add IDW pollution-surface estimates only inside the fixed-station convex hull, with six recent comparable stations, a 3 km nearest-station bound and leave-one-station-out MAE beating a median baseline
- [x] Add QA-masked multi-scene Landsat surface-temperature contrast and NASA MODIS context imagery; exploratory urban/vegetated proxy contrast is not an official or seasonal UHI estimate
- [x] Add ESA WorldCover 2021 land-cover imagery, OSM mapped green spaces and approximate walk-network park access
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
- [x] Add threshold-based heat, pollution and rainfall alerts (prototype; session-only thresholds)
- [x] Add city-specific recommendations with supporting rationale
- [x] Add alert history CSV export and quality-audit export
- [x] Add first population exposure / demographic planning context
- [ ] Add zone-specific recommendation evidence, downloadable multi-page environmental summary reports, and validated policymaker planning workflows
- [ ] Add durable alert preferences and delivery integrations after validation

## Priority 3–4 readiness note

The first Environmental Health & Exposure implementation uses WorldPop Global2 (100 m source data, optional 1 km display grid, CC BY 4.0) and its catchment, age-group and distance-weighted exposure endpoints. The default population year is 2025. Counts describe an approximate city-centre buffer, not an administrative city boundary or live census. Age groups are context only; no vulnerability score is inferred.

The first Smart Alerts implementation provides configurable, session-only thresholds for modelled current apparent temperature, preceding-hour rainfall, next-24-hour forecast values and recent fixed-station PM medians. Each trigger identifies its source, value, timestamp and station count where applicable. Recommendations are informational and are not official warnings. Browser-session alert history and CSV export are implemented; durable persistence, email/SMS/push delivery and saved personal preferences require a selected secure external service.

The WorldPop, alert and data-quality modules are covered by automated tests (71 tests passed in GitHub Actions, run 45043246416). Live population context and the 1 km population overlay have rendered in the deployed Streamlit app. The latest density metadata/cache revision and Smart Alerts page still require a fresh deployed-app check; the WorldPop event-exposure button has not yet been verified against a live qualifying event.

## Priority 1–2 readiness note

The City Comparison Engine and Advanced Zone Intelligence implementations are code-complete, with 71 automated tests passing. Priority 1 is not release-verified until the scheduled collector creates both remote archives and enough real multi-city dates accumulate. Priority 2 is not live-verified until the deployed station, green-space and Landsat views have been checked against their external providers. These real-data checks must remain open; do not replace them with synthetic observations.

## Final project closeout
- [ ] Remove this master checklist (`PROJECT_ROADMAP.md`) from the public GitHub repository after all project features, release checks and documentation are complete.

## Five-hour implementation sprint — target 12:30 AM IST, 23 November 2026
- [x] Fix global-city timezone handling in weather requests
- [x] Build a 2–3 city comparison view using live provider responses
- [x] Add pollutant breakdown, station count and reading freshness to air-quality analytics
- [x] Upgrade Zone Intelligence station map and station drill-down
- [x] Add a transparent data freshness / coverage panel
- [x] Add or update tests for city comparison metrics, timezone handling, air-quality freshness and global city registry
- [x] Run CI and resolve regressions (61 tests passed in the latest verified run)
- [ ] Verify the deployed Streamlit app where deployment status is observable

## Release quality gates
- [x] No synthetic or silently imputed measurements in new comparison, trend, station-grid, interpolation, cluster, Landsat or OSM workflows; CityPulse Index is withheld when required weather, PM or rainfall inputs are missing
- [x] Audit legacy dashboard views for silent defaults and imputation; remove the scenario zero-rainfall and placeholder-temperature defaults, fix missing rain-score display, and stop relabelling weather-stress as a heat signal
- [x] Distinguish modelled grid-cell weather, OpenAQ station measurements, provider forecasts, experimental CityPulse outputs and spatial estimates in the new comparison/zone views
- [x] Show timestamps, units, source provenance, station-age ranges and missing/future-data states in comparison and zone views
- [x] Confirm city timezone handling for every country (all registry timezones validated and passed to weather requests)
- [x] Automated tests pass (61 tests passed in GitHub Actions before starting Priority 3 and 4; 71 tests passed in GitHub Actions; latest verified run 45043246416)
- [x] README accurately describes released features and limitations
- [ ] Streamlit deployment successfully starts and core pages render
- [ ] Recheck OpenStreetMap green-space lookup after adding a non-default CityPulse User-Agent (live 406 observed before this fix); external OpenStreetMap/ESA/Landsat service availability is not covered by CI
