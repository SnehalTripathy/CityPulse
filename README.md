# CityPulse — Urban Stress Intelligence

CityPulse is a portfolio project exploring urban environmental conditions through live data feeds, transparent analytics and (in later phases) validated machine-learning models.

## Pilot
- **City:** Bengaluru, Karnataka, India
- **Weather:** Open-Meteo forecast API
- **Air quality:** OpenAQ API v3 (requires an API key)

## Current application foundation
- Premium dark command-centre interface
- Current modelled weather conditions and 7-day hourly forecast
- Nearby OpenAQ station discovery and latest available sensor readings
- Transparent weather-only stress heuristic
- Environmental trend explorer and methodology disclosures
- Automated Python compile and test checks through GitHub Actions

## Automated observation history
A scheduled GitHub Actions workflow runs every three hours and appends deduplicated observations to `data/raw/observations.csv`. Weather snapshots work without a credential. OpenAQ readings require a repository Actions secret named `OPENAQ_API_KEY`.

To configure the collector:
1. Open **Settings → Secrets and variables → Actions** in this repository.
2. Select **New repository secret**.
3. Name it `OPENAQ_API_KEY` and paste the regenerated key value.
4. Save. Do not place the key in source files, commits, issues or chat.

You can also run collection manually from **Actions → CityPulse Data Collection → Run workflow**.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
streamlit run app.py
```

For OpenAQ access locally, add `OPENAQ_API_KEY` to `.streamlit/secrets.toml` (never commit that file).

## Deploy on Streamlit Community Cloud
1. Select this GitHub repository and branch `main`.
2. Set the main file path to `app.py`.
3. Under App settings → Secrets, add:
   ```toml
   OPENAQ_API_KEY = "your-private-key"
   ```
4. Deploy.

## Important limitations
- Open-Meteo values are provider-supplied modelled conditions/forecasts, not a dense network of street-level sensors.
- OpenAQ station coverage varies; some stations may not report recent observations.
- The displayed weather stress signal is an experimental weather-only heuristic, not an official or validated Urban Stress Index.
- No trained prediction or anomaly-detection model is claimed in this first application foundation. These will be added after sufficient time-series observations have been collected and validated.

## Roadmap
1. Scheduled environmental observation history
2. Multi-dimensional Urban Stress Index with documented calibration
3. Forecast baselines and evaluation
4. Explainable anomaly detection
5. Geospatial zone intelligence
6. Scenario analysis and downloadable reports
