from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from config.cities import CITIES
from ingestion.weather_api import fetch_forecast
from ingestion.openaq_api import fetch_latest_measurements
from analytics.stress_index import add_weather_stress
from analytics.urban_stress import calculate_urban_stress
from ml.anomaly import detect_recent_weather_anomaly
from ml.forecasting import train_next_observation_model
from utils.storage import ensure_data_dirs, load_observations

st.set_page_config(
    page_title="CityPulse | Urban Stress Intelligence",
    page_icon="🌆",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_data_dirs()

@st.cache_data(ttl=300, show_spinner=False)
def load_history() -> pd.DataFrame:
    return load_observations()

history = load_history()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { --bg:#0B1220; --panel:#152238; --cyan:#52C8FF; --violet:#9B8AFF; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background:var(--bg); color:#E8F0FA; }
.block-container { padding-top:2rem; max-width:1500px; }
h1,h2,h3 { font-family:'Space Grotesk',sans-serif; }
[data-testid="stMetric"] { background:var(--panel); border:1px solid #233754; padding:18px; border-radius:14px; }
[data-testid="stSidebar"] { background:#0E192B; border-right:1px solid #20324B; }
div[data-testid="stAlert"] { border-radius:12px; }
.pulse { color:var(--cyan); letter-spacing:.15em; font-size:.75rem; font-weight:700; }
.subtle { color:#91A4BC; }
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("## 🌆 CityPulse")
st.sidebar.caption("URBAN STRESS INTELLIGENCE")
city_name = st.sidebar.selectbox("Pilot city", list(CITIES.keys()), index=0)
city = CITIES[city_name]
page = st.sidebar.radio(
    "Workspace",
    ["Command Center", "Environmental Analytics", "Predictive Intelligence", "Anomaly Detection", "Zone Intelligence", "Scenario Simulator", "Methodology"],
)
st.sidebar.divider()
st.sidebar.caption("Data: Open-Meteo · OpenAQ")
st.sidebar.caption(f"Last refreshed: {datetime.now().astimezone().strftime('%d %b %Y, %H:%M')}")

@st.cache_data(ttl=900, show_spinner=False)
def load_weather(lat: float, lon: float) -> pd.DataFrame:
    return fetch_forecast(lat, lon)

@st.cache_data(ttl=900, show_spinner=False)
def load_air(lat: float, lon: float, key: str | None) -> pd.DataFrame:
    return fetch_latest_measurements(lat, lon, key)

def get_forward_hours(frame: pd.DataFrame, current: dict, count: int) -> pd.DataFrame:
    if frame.empty or "time" not in frame.columns:
        return frame.head(count)
    timestamps = pd.to_datetime(frame["time"], errors="coerce")
    current_time = pd.to_datetime(current.get("time"), errors="coerce") if current else pd.NaT
    if pd.notna(current_time):
        if timestamps.dt.tz is None and current_time.tzinfo is not None:
            current_time = current_time.tz_localize(None)
        elif timestamps.dt.tz is not None and current_time.tzinfo is None:
            current_time = current_time.tz_localize(timestamps.dt.tz)
        filtered = frame.loc[timestamps >= current_time.floor("h")]
        if not filtered.empty:
            return filtered.head(count)
    return frame.head(count)

weather = pd.DataFrame()
air = pd.DataFrame()
weather_error = None
air_error = None
try:
    with st.spinner("Loading live weather conditions and forecast…"):
        weather = load_weather(city["latitude"], city["longitude"])
except Exception as exc:
    weather_error = str(exc)
try:
    with st.spinner("Checking nearby air-quality observations…"):
        api_key = None
        try:
            api_key = st.secrets.get("OPENAQ_API_KEY")
        except Exception:
            api_key = os.getenv("OPENAQ_API_KEY")
        air = load_air(city["latitude"], city["longitude"], api_key)
except Exception as exc:
    air_error = str(exc)

weather_current = weather.attrs.get("current", {}) if not weather.empty else {}
usi = calculate_urban_stress(weather_current, air) if weather_current else {"index": None, "reason": "Current weather data is unavailable."}
if not weather.empty:
    weather = add_weather_stress(weather)

st.markdown('<div class="pulse">LIVE URBAN INTELLIGENCE / PILOT 01</div>', unsafe_allow_html=True)
st.title(f"{city_name} Urban Stress Monitor")
st.markdown('<p class="subtle">A data-driven view of environmental conditions, emerging patterns and potential urban stress.</p>', unsafe_allow_html=True)

if page == "Command Center":
    st.subheader("City overview")
    if weather_error:
        st.error(f"Weather feed unavailable: {weather_error}")
    if weather.empty:
        st.warning("Weather data is not available right now. Please refresh shortly.")
    else:
        if weather_current:
            current_df = pd.DataFrame([weather_current])
            current_score = float(add_weather_stress(current_df).iloc[0]["weather_stress"])
            temp = weather_current.get("temperature_2m")
            humidity = weather_current.get("relative_humidity_2m")
            wind = weather_current.get("wind_speed_10m")
            current_time = weather_current.get("time", "Current API timestamp unavailable")
            st.caption(f"Open-Meteo current conditions · {current_time} · modelled grid-cell data")
        else:
            first_forecast = weather.iloc[0]
            current_score = float(first_forecast["weather_stress"])
            temp = first_forecast.get("temperature_2m")
            humidity = first_forecast.get("relative_humidity_2m")
            wind = first_forecast.get("wind_speed_10m")
            st.caption("Current-conditions payload unavailable; values below use the first hourly forecast slot.")
        cols = st.columns(4)
        cols[0].metric("Temperature", f"{float(temp):.1f} °C" if pd.notna(temp) else "—")
        cols[1].metric("Relative humidity", f"{float(humidity):.0f}%" if pd.notna(humidity) else "—")
        cols[2].metric("Wind speed", f"{float(wind):.1f} km/h" if pd.notna(wind) else "—")
        composite_value = usi.get("index")
        cols[3].metric(
            "Experimental CityPulse Index",
            f"{composite_value:.0f}/100" if composite_value is not None else "Partial data",
            help="Project-specific environmental signal; not the official Indian AQI or a health advisory",
        )
        parts = st.columns(3)
        parts[0].metric("Heat signal", f"{usi.get('heat_score', current_score):.0f}/100")
        parts[1].metric("Particulate signal", f"{usi['air_score']:.0f}/100" if usi.get("air_score") is not None else "Unavailable")
        parts[2].metric("Rain signal", f"{usi.get('rain_score', 0):.0f}/100")
        if composite_value is None:
            st.caption(f"Composite index withheld: {usi.get('reason', 'Required data is not available.')}")
        else:
            st.caption("Experimental composite: 50% heat + 35% particulate signal + 15% rainfall. Based on available recent data within the 25 km search area.")
        st.markdown("### Hourly outlook")
        hourly = get_forward_hours(weather, weather_current, 24)
        fig = px.line(hourly, x="time", y=["temperature_2m", "apparent_temperature"], markers=True,
                      labels={"value":"Temperature (°C)","time":"Forecast time","variable":"Series"},
                      template="plotly_dark", color_discrete_sequence=["#52C8FF","#9B8AFF"])
        fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238", legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("### Nearby air quality")
    if air_error:
        st.warning(f"Air-quality feed issue: {air_error}")
    if air.empty:
        st.info("No nearby OpenAQ readings were returned. This can mean no stations are available within 25 km, readings are unavailable, or the API key is not configured.")
    else:
        st.caption("Latest reported sensor values from nearby stations. Values can have different timestamps; check the timestamp column before comparing.")
        st.dataframe(air, use_container_width=True, hide_index=True)
    if not history.empty:
        last_collected = history["observed_at_utc"].max() if "observed_at_utc" in history else None
        st.caption(f"Local observation archive: {len(history):,} rows" + (f" · latest collection {last_collected}" if pd.notna(last_collected) else ""))
elif page == "Environmental Analytics":
    st.subheader("Environmental analytics")
    tabs = st.tabs(["Live weather forecast", "Collected weather history", "Air-quality history"])
    with tabs[0]:
        if weather.empty:
            st.info("Weather data is not currently available.")
        else:
            vars_ = [c for c in ["temperature_2m","apparent_temperature","relative_humidity_2m","precipitation","wind_speed_10m"] if c in weather]
            selected = st.multiselect("Forecast metrics", vars_, default=vars_[:3])
            if selected:
                fig = px.line(get_forward_hours(weather, weather_current, 72), x="time", y=selected, template="plotly_dark")
                fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238")
                st.plotly_chart(fig, use_container_width=True)
    with tabs[1]:
        weather_history = history[history["source"] == "open-meteo"] if not history.empty else pd.DataFrame()
        if weather_history.empty:
            st.info("The scheduled collector has not stored weather history yet. It runs every three hours.")
        else:
            choices = sorted(weather_history["parameter"].dropna().unique().tolist())
            chosen = st.multiselect("Historical weather variables", choices, default=choices[:2])
            if chosen:
                filtered = weather_history[weather_history["parameter"].isin(chosen)]
                fig = px.line(filtered, x="datetime_utc", y="value", color="parameter", markers=True, template="plotly_dark")
                fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238")
                st.plotly_chart(fig, use_container_width=True)
            st.caption(f"{len(weather_history):,} archived weather readings")
    with tabs[2]:
        air_history = history[history["source"] == "openaq"] if not history.empty else pd.DataFrame()
        if air_history.empty:
            st.info("No archived OpenAQ readings yet. Add OPENAQ_API_KEY as a GitHub Actions secret to enable collection.")
        else:
            choices = sorted(air_history["parameter"].dropna().unique().tolist())
            chosen = st.multiselect("Pollutants", choices, default=choices[:2])
            filtered = air_history[air_history["parameter"].isin(chosen)]
            if not filtered.empty:
                fig = px.scatter(filtered, x="datetime_utc", y="value", color="parameter", hover_name="station", template="plotly_dark")
                fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238")
                st.plotly_chart(fig, use_container_width=True)
            st.dataframe(air_history.sort_values("datetime_utc", ascending=False).head(100), use_container_width=True, hide_index=True)
elif page == "Predictive Intelligence":
    st.subheader("Predictive intelligence")
    st.markdown("### Provider forecast")
    if not weather.empty:
        st.caption("Open-Meteo forecast, shown separately from CityPulse's trained model.")
        st.dataframe(get_forward_hours(weather, weather_current, 48), use_container_width=True, hide_index=True)
    st.markdown("### CityPulse machine-learning estimate")
    forecast_result = train_next_observation_model(history)
    if forecast_result["status"] != "ready":
        st.info(f"Model is in data-collection mode: {forecast_result['samples']} valid samples. {forecast_result['reason']}")
    else:
        metric_cols = st.columns(3)
        metric_cols[0].metric("Training pairs", f"{forecast_result['samples']:,}")
        metric_cols[1].metric("Holdout MAE", f"{forecast_result['mae']:.2f} °C")
        metric_cols[2].metric("Persistence baseline MAE", f"{forecast_result['persistence_mae']:.2f} °C")
        if forecast_result["beats_persistence"]:
            st.metric("Next-step apparent temperature estimate", f"{forecast_result['prediction']:.1f} °C", help="Experimental Random Forest estimate for the next scheduled observation, approximately three hours later.")
        else:
            st.warning("The model did not outperform the simple persistence baseline on the time-ordered holdout. Its next-step estimate is withheld until it demonstrates improvement.")
        st.caption(f"Model: {forecast_result['model']} · RMSE: {forecast_result['rmse']:.2f} °C · Last sample: {forecast_result['last_observation']}")
    st.caption("The model uses only historical Open-Meteo snapshots. It is not a substitute for the provider forecast or an official warning.")
elif page == "Anomaly Detection":
    st.subheader("Weather pattern anomaly detection")
    anomaly = detect_recent_weather_anomaly(history)
    if anomaly["status"] != "ready":
        st.info(f"Baseline-building mode: {anomaly['samples']} complete snapshots. {anomaly['reason']}")
    else:
        cols = st.columns(3)
        cols[0].metric("Baseline snapshots", f"{anomaly['samples']:,}")
        cols[1].metric("Anomalies in history", anomaly["anomalies"])
        cols[2].metric("Latest anomaly score", f"{anomaly['latest_score']:.4f}")
        if anomaly["latest_is_anomaly"]:
            st.warning("The latest weather snapshot is unusual relative to the collected baseline.")
        else:
            st.success("The latest weather snapshot is within the model's learned baseline.")
        st.caption(f"Model: {anomaly['model']} · Latest point: {anomaly['latest_timestamp']}")
    st.caption("Isolation Forest flags statistical outliers in local weather features. It does not assess health risk or prove an environmental incident.")
elif page == "Zone Intelligence":
    st.subheader("Zone intelligence")
    if not air.empty and {"latitude", "longitude"}.issubset(air.columns):
        points = air.dropna(subset=["latitude", "longitude"]).drop_duplicates(subset=["location_id"])
        if not points.empty:
            st.caption("Map points are actual OpenAQ station locations within the 25 km search radius.")
            st.map(points.rename(columns={"latitude":"lat","longitude":"lon"})[["lat","lon"]], latitude="lat", longitude="lon")
            st.dataframe(air.groupby(["station","parameter","unit"], dropna=False)["value"].median().reset_index(), use_container_width=True, hide_index=True)
        else:
            st.info("OpenAQ returned no geocoded station coordinates.")
    else:
        st.info("No geocoded OpenAQ stations are available. The map shows the Bengaluru pilot centre, not neighbourhood measurements.")
        st.map(pd.DataFrame({"lat":[city["latitude"]],"lon":[city["longitude"]]}), latitude="lat", longitude="lon")
elif page == "Scenario Simulator":
    st.subheader("Scenario simulator")
    st.caption("Explore a hypothetical sensitivity scenario. This changes selected inputs in the project heuristic; it is not a forecast.")
    if weather_current:
        delta_temp = st.slider("Apparent-temperature change (°C)", -2.0, 8.0, 2.0, 0.5)
        particulate_factor = st.slider("Particulate concentration multiplier", 0.5, 2.0, 1.0, 0.1)
        rainfall_factor = st.slider("Rainfall multiplier", 0.0, 2.0, 1.0, 0.1)
        baseline = calculate_urban_stress(weather_current, air)
        scenario_weather = dict(weather_current)
        scenario_weather["apparent_temperature"] = float(scenario_weather.get("apparent_temperature", 30.0)) + delta_temp
        scenario_weather["precipitation"] = float(scenario_weather.get("precipitation") or 0.0) * rainfall_factor
        scenario_air = air.copy()
        if not scenario_air.empty:
            scenario_air["value"] = pd.to_numeric(scenario_air["value"], errors="coerce") * particulate_factor
        projected = calculate_urban_stress(scenario_weather, scenario_air)
        st.metric("Scenario temperature", f"{scenario_weather['apparent_temperature']:.1f} °C", f"{delta_temp:+.1f} °C")
        left, right = st.columns(2)
        left.metric("Baseline CityPulse Index", f"{baseline['index']:.1f}/100" if baseline.get("index") is not None else "Unavailable")
        right.metric("Scenario CityPulse Index", f"{projected['index']:.1f}/100" if projected.get("index") is not None else "Unavailable")
        if baseline.get("index") is None or projected.get("index") is None:
            st.info("A composite scenario requires a recent PM2.5 or PM10 reading. The model will not invent missing air-quality data.")
        else:
            st.caption(f"Change in project index: {projected['index'] - baseline['index']:+.1f} points. This is a sensitivity calculation using the documented heuristic, not a prediction of actual city conditions.")
    else:
        st.info("Current weather inputs are unavailable, so the scenario cannot be calculated.")

else:
    st.subheader("Methodology & data notes")
    st.markdown("""
**Pilot geography:** Bengaluru, Karnataka, India.

**Weather:** Open-Meteo forecast API. Current modelled conditions and hourly forecasts are displayed separately.

**Air quality:** OpenAQ API v3. CityPulse discovers nearby monitoring locations and retrieves each location’s latest sensor measurements. Nearby coverage and reporting times vary. Missing readings are not imputed.

**Experimental CityPulse Index:** 50% heat signal + 35% particulate signal + 15% rainfall signal. The particulate signal uses the higher of the citywide median PM2.5/PM10 readings, normalized against 60 and 100 µg/m³ respectively. A reading must be no more than 48 hours old. These are project normalisation anchors, not an official AQI calculation: the CPCB AQI uses pollutant-specific breakpoints and prescribed averaging periods, while this prototype uses latest sensor readings. See the [CPCB National AQI methodology](https://airquality.cpcb.gov.in/ccr_docs/About_AQI.pdf). The CityPulse index is not an official rating or health advisory.

**Weather-only signal:** If recent PM2.5/PM10 readings are missing, the composite index is withheld rather than substituting a weather-only value.

**Machine learning:** Predictive models and anomaly detection will only be published after collection of adequate time-series data, baseline evaluation and leakage checks. Until then, API forecasts are clearly distinguished from model predictions.
    """)
    st.markdown("**Application data timestamp (UTC):** " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
