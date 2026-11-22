# CityPulse — Urban Stress Intelligence

CityPulse is a portfolio project exploring urban environmental conditions through live data feeds, transparent analytics and (in later phases) validated machine-learning models.

## Pilot
- **City:** Bengaluru, Karnataka, India
- **Weather:** Open-Meteo forecast API
- **Air quality:** OpenAQ API v3 (requires an API key)

## Features in the initial foundation
- Dark command-centre interface
- Current modelled weather conditions and 7-day hourly forecast
- Air-quality station discovery through OpenAQ
- Transparent weather-only stress heuristic
- Environmental trend explorer
- Explicit methodology and data-coverage disclosures

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

For OpenAQ access, add `OPENAQ_API_KEY` to `.streamlit/secrets.toml` (never commit that file).

## Deploy on Streamlit Community Cloud
1. Select this GitHub repository and branch `main`.
2. Set the main file path to `app.py`.
3. Under App settings > Secrets, add:
   ```toml
   OPENAQ_API_KEY = "your-private-key"
   ```
4. Deploy.

## Important limitations
- Open-Meteo values are provider-supplied modelled conditions/forecasts, not a dense network of street-level sensors.
- OpenAQ station coverage varies; no station measurement is invented when data is absent.
- The displayed weather stress signal is an experimental weather-only heuristic, not an official or validated Urban Stress Index.
- No trained prediction or anomaly-detection model is claimed in this first foundation. These will be added after time-series observations are collected and validated.

## Roadmap
1. Reliable scheduled ingestion and observation history
2. Multi-dimensional Urban Stress Index with documented calibration
3. Forecast baselines and evaluation
4. Explainable anomaly detection
5. Geospatial zone intelligence
6. Scenario analysis and downloadable reports
