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
from utils.storage import ensure_data_dirs

st.set_page_config(
    page_title="CityPulse | Urban Stress Intelligence",
    page_icon="🌆",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_data_dirs()

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
        cols[3].metric("Weather stress signal", f"{current_score:.0f}/100", help="Prototype weather-only indicator, not an official city rating")
        st.markdown("### Hourly outlook")
        hourly = weather.head(24)
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
elif page == "Environmental Analytics":
    st.subheader("Environmental analytics")
    if weather.empty:
        st.info("Weather data is not currently available.")
    else:
        vars_ = [c for c in ["temperature_2m","apparent_temperature","relative_humidity_2m","precipitation","wind_speed_10m"] if c in weather]
        selected = st.multiselect("Metrics", vars_, default=vars_[:3])
        if selected:
            fig = px.line(weather.head(72), x="time", y=selected, template="plotly_dark")
            fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238")
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(weather.head(72), use_container_width=True, hide_index=True)
elif page == "Predictive Intelligence":
    st.subheader("Predictive intelligence")
    st.info("Forecast charts currently use Open-Meteo forecast fields. A trained local model will be introduced only after sufficient aligned historical observations have been collected and validated.")
    if not weather.empty:
        st.dataframe(weather.head(48), use_container_width=True, hide_index=True)
elif page == "Anomaly Detection":
    st.subheader("Anomaly detection")
    st.info("Anomaly detection is planned after a reliable rolling observation history is available. A single live API response is not enough to claim statistically meaningful anomalies.")
elif page == "Zone Intelligence":
    st.subheader("Zone intelligence")
    st.info("The first release is city-level. Zone-level comparisons require geocoded station observations or a verified spatial dataset; we will not fabricate neighbourhood readings.")
    st.map(pd.DataFrame({"lat":[city["latitude"]],"lon":[city["longitude"]]}), latitude="lat", longitude="lon")
elif page == "Scenario Simulator":
    st.subheader("Scenario simulator")
    st.caption("Explore hypothetical changes to heat exposure. This is a transparent sensitivity illustration, not an official forecast.")
    if weather_current and weather_current.get("temperature_2m") is not None:
        baseline = float(weather_current["temperature_2m"])
    elif not weather.empty:
        baseline = float(weather.iloc[0]["temperature_2m"])
    else:
        baseline = 30.0
    delta = st.slider("Hypothetical temperature increase (°C)", 0.0, 8.0, 2.0, 0.5)
    st.metric("Illustrative temperature", f"{baseline + delta:.1f} °C", f"+{delta:.1f} °C")
    st.caption("The scenario changes temperature only; it does not model health outcomes or infrastructure impacts.")
else:
    st.subheader("Methodology & data notes")
    st.markdown("""
**Pilot geography:** Bengaluru, Karnataka, India.

**Weather:** Open-Meteo forecast API. Current modelled conditions and hourly forecasts are displayed separately.

**Air quality:** OpenAQ API v3. CityPulse discovers nearby monitoring locations and retrieves each location’s latest sensor measurements. Nearby coverage and reporting times vary. Missing readings are not imputed.

**Weather stress indicator:** A prototype heuristic derived from apparent temperature, relative humidity and precipitation. It is not an official Urban Stress Index, health assessment, or government rating. The full multi-dimensional CityPulse index will be defined and validated when suitable air-quality and precipitation observations are available.

**Machine learning:** Predictive models and anomaly detection will only be published after collection of adequate time-series data, baseline evaluation and leakage checks. Until then, API forecasts are clearly distinguished from model predictions.
    """)
    st.markdown("**Application data timestamp (UTC):** " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
