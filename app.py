from __future__ import annotations

import io
import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from config.cities import CITIES, COUNTRY_CITIES
from ingestion.weather_api import fetch_forecast
from ingestion.openaq_api import fetch_latest_measurements
from analytics.stress_index import add_weather_stress
from analytics.data_quality import summarize_air_quality
from analytics.comparison import build_city_comparison_record
from analytics.trends import TREND_METRICS, build_city_trend_frame
from analytics.zone_intelligence import build_zone_coverage, detect_observed_hotspot_clusters
from analytics.zone_grid import build_zone_coverage_grid
from ingestion.geo_layers import (
    fetch_green_spaces, fetch_walking_park_access,
    fetch_nasa_land_surface_temperature, fetch_esa_worldcover,
)
from analytics.spatial_interpolation import interpolate_station_surface
from ingestion.landsat_uhi import fetch_landsat_surface_temperature_analysis
from analytics.urban_stress import calculate_urban_stress
from ml.anomaly import detect_recent_weather_anomaly
from ml.forecasting import train_next_observation_model
from utils.storage import ensure_data_dirs, load_observations, load_daily_observations

st.set_page_config(
    page_title="CityPulse | Urban Stress Intelligence",
    page_icon="🌆",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_data_dirs()

@st.cache_data(ttl=600, show_spinner=False)
def load_history() -> pd.DataFrame:
    """Load local detailed history, with a shared GitHub fallback."""
    local = load_observations()
    if not local.empty:
        return local
    archive_url = "https://raw.githubusercontent.com/SnehalTripathy/CityPulse/main/data/raw/observations.csv"
    try:
        response = requests.get(archive_url, timeout=(4, 25))
        if response.status_code == 200 and response.content:
            remote = pd.read_csv(io.BytesIO(response.content))
            if not remote.empty:
                if "datetime_utc" in remote.columns:
                    remote["datetime_utc"] = pd.to_datetime(remote["datetime_utc"], errors="coerce", utc=True)
                if "observed_at_utc" in remote.columns:
                    remote["observed_at_utc"] = pd.to_datetime(remote["observed_at_utc"], errors="coerce", utc=True)
                if "value" in remote.columns:
                    remote["value"] = pd.to_numeric(remote["value"], errors="coerce")
                return remote
    except (requests.RequestException, OSError, pd.errors.ParserError, ValueError):
        pass
    return local

@st.cache_data(ttl=600, show_spinner=False)
def load_daily_history() -> pd.DataFrame:
    local = load_daily_observations()
    archive_url = "https://raw.githubusercontent.com/SnehalTripathy/CityPulse/main/data/processed/daily_city_observations.csv"
    try:
        response = requests.get(archive_url, timeout=(4, 25))
        if response.status_code == 200 and response.content:
            remote = pd.read_csv(io.BytesIO(response.content))
            if "date" in remote.columns:
                remote["date"] = pd.to_datetime(remote["date"], errors="coerce", utc=True)
            for column in ["median_value", "reading_count", "latitude", "longitude"]:
                if column in remote.columns:
                    remote[column] = pd.to_numeric(remote[column], errors="coerce")
            return remote
    except (requests.RequestException, OSError, pd.errors.ParserError, ValueError):
        pass
    return local

history = load_history()
all_history = history.copy()
daily_history = load_daily_history()
all_daily_history = daily_history.copy()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
:root {
 --bg:#080D1B; --panel:#111B31; --panel2:#172541; --text:#F4F7FF; --muted:#9BAAC4;
 --cyan:#39D5F6; --violet:#A78BFA; --pink:#FB7185; --orange:#F59E0B; --lime:#A3E635; --blue:#60A5FA;
}
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp {
 background:
 radial-gradient(ellipse at 12% 0%, rgba(57,213,246,.13), transparent 28%),
 radial-gradient(ellipse at 88% 8%, rgba(167,139,250,.15), transparent 30%),
 radial-gradient(ellipse at 70% 90%, rgba(251,113,133,.025), transparent 24%), var(--bg);
 color:var(--text);
}
.block-container { padding-top:4.7rem !important; padding-bottom:3rem !important; max-width:1560px; }
h1,h2,h3,h4 { font-family:'Space Grotesk',sans-serif !important; letter-spacing:-.035em; color:#F8FAFF; }
h1 { font-size:clamp(2rem,4vw,3.2rem) !important; line-height:1.12 !important; margin:.25rem 0 .55rem !important; }
h2 { font-size:1.75rem !important; }
h3 { font-size:1.25rem !important; }
p, label, .stMarkdown { color:#DCE6F7; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#111C34 0%,#0B1325 100%); border-right:1px solid rgba(96,165,250,.18); }
[data-testid="stSidebar"] h2 { background:linear-gradient(90deg,var(--cyan),var(--violet),var(--pink)); -webkit-background-clip:text; color:transparent !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { border-radius:10px; padding:.35rem .55rem; transition:all .2s ease; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background:rgba(57,213,246,.10); }
.pulse {
 display:inline-flex; align-items:center; gap:.55rem; color:#72E7FF;
 letter-spacing:.16em; font-size:.72rem; font-weight:800; line-height:1.6;
 padding:.38rem .75rem; margin:0 0 .65rem; border:1px solid rgba(57,213,246,.3);
 border-radius:999px; background:linear-gradient(90deg,rgba(57,213,246,.12),rgba(167,139,250,.12));
 overflow:visible; position:relative;
}
.pulse:before { content:''; width:7px; height:7px; border-radius:50%; background:#A3E635; box-shadow:0 0 12px #A3E635; }
.subtle { color:var(--muted) !important; font-size:1rem; max-width:850px; }
[data-testid="stMetric"] {
 background:linear-gradient(145deg,rgba(25,41,70,.96),rgba(15,26,47,.96));
 border:1px solid rgba(130,160,210,.20); padding:1rem 1.1rem; border-radius:18px;
 box-shadow:0 10px 28px rgba(0,0,0,.16); min-height:118px;
}
[data-testid="stHorizontalBlock"] [data-testid="stMetric"]:nth-child(1) { border-top:3px solid var(--cyan); }
[data-testid="stHorizontalBlock"] [data-testid="stMetric"]:nth-child(2) { border-top:3px solid var(--violet); }
[data-testid="stHorizontalBlock"] [data-testid="stMetric"]:nth-child(3) { border-top:3px solid var(--pink); }
[data-testid="stHorizontalBlock"] [data-testid="stMetric"]:nth-child(4) { border-top:3px solid var(--lime); }
[data-testid="stMetricLabel"] { color:#AFC0DA !important; font-weight:600; }
[data-testid="stMetricValue"] { color:#FFFFFF !important; font-family:'Space Grotesk',sans-serif; }
[data-testid="stMetricDelta"] { font-weight:700; }
.stTabs [data-baseweb="tab-list"] { gap:.45rem; background:rgba(17,27,49,.8); padding:.4rem; border-radius:14px; }
.stTabs [data-baseweb="tab"] { border-radius:10px; color:#B8C7DE; padding:.55rem 1rem; }
.stTabs [aria-selected="true"] { background:linear-gradient(100deg,rgba(57,213,246,.2),rgba(167,139,250,.22)); color:#FFFFFF !important; }
.stButton button, .stDownloadButton button { border:0; border-radius:12px; color:#07111F; font-weight:800; background:linear-gradient(100deg,var(--cyan),var(--violet),var(--pink)); }
.stButton button:hover, .stDownloadButton button:hover { filter:brightness(1.12); transform:translateY(-1px); }
/* Fine-align the hero CTA with the visual centre of the city heading. */
.st-key-hero_zone_intelligence { transform:translateY(6px); }
.stSelectbox [data-baseweb="select"], .stMultiSelect [data-baseweb="select"] { border-radius:12px; }
[data-testid="stAlert"] { border-radius:14px; border:1px solid rgba(130,160,210,.2); }
[data-testid="stDataFrame"] { border:1px solid rgba(130,160,210,.2); border-radius:14px; overflow:hidden; }
[data-testid="stPlotlyChart"] { background:linear-gradient(145deg,rgba(17,27,49,.6),rgba(23,37,65,.35)); border:1px solid rgba(130,160,210,.16); border-radius:18px; padding:.35rem; }
hr { border-color:rgba(130,160,210,.18) !important; }
.stSlider [data-baseweb="slider"] div[role="slider"] { background:#39D5F6; }
footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("## 🌆 CityPulse")
st.sidebar.caption("URBAN STRESS INTELLIGENCE")
country_options = ["India"] + sorted(country for country in COUNTRY_CITIES if country != "India")
country_name = st.sidebar.selectbox(
    "Country",
    country_options,
    index=0,
    key="selected_country",
    format_func=lambda country: country,
)
available_cities = COUNTRY_CITIES[country_name]
if st.session_state.get("selected_city") not in available_cities:
    st.session_state["selected_city"] = "Bengaluru" if country_name == "India" else available_cities[0]
city_name = st.sidebar.selectbox("City", available_cities, key="selected_city")
city = CITIES[city_name]
st.sidebar.caption(f"Selected location · {country_name}")
if not history.empty and "city" in history.columns:
    history = history.loc[history["city"] == city_name].copy()
def _open_zone_intelligence():
    st.session_state["workspace_page"] = "Zone Intelligence"

page = st.sidebar.radio(
    "Workspace",
    ["Command Center", "City Comparison", "Air Quality Intelligence", "Environmental Analytics", "Predictive Intelligence", "Anomaly Detection", "Zone Intelligence", "Scenario Simulator", "Methodology"],
    key="workspace_page",
)
st.sidebar.divider()
st.sidebar.caption("Data: Open-Meteo · OpenAQ")
st.sidebar.caption(f"Last refreshed: {datetime.now().astimezone().strftime('%d %b %Y, %H:%M')}")

@st.cache_data(ttl=900, show_spinner=False)
def load_weather(lat: float, lon: float, timezone_name: str = "auto") -> pd.DataFrame:
    return fetch_forecast(lat, lon, timezone_name)

@st.cache_data(ttl=900, show_spinner=False)
def load_air(lat: float, lon: float, key: str | None) -> pd.DataFrame:
    return fetch_latest_measurements(lat, lon, key)

@st.cache_data(ttl=86400, show_spinner=False)
def load_green_spaces(lat: float, lon: float) -> pd.DataFrame:
    return fetch_green_spaces(lat, lon)

@st.cache_data(ttl=86400, show_spinner=False)
def load_walking_access(lat: float, lon: float, green: pd.DataFrame):
    return fetch_walking_park_access(lat, lon, green)

@st.cache_data(ttl=86400, show_spinner=False)
def load_worldcover(lat: float, lon: float) -> bytes:
    return fetch_esa_worldcover(lat, lon)

@st.cache_data(ttl=604800, show_spinner=False)
def load_landsat_analysis(lat: float, lon: float):
    return fetch_landsat_surface_temperature_analysis(lat, lon)

@st.cache_data(ttl=43200, show_spinner=False)
def load_land_surface_temperature(lat: float, lon: float):
    return fetch_nasa_land_surface_temperature(lat, lon)

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
        weather = load_weather(city["latitude"], city["longitude"], city["timezone"])
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

st.markdown('<div class="pulse">LIVE URBAN INTELLIGENCE &nbsp;·&nbsp; PILOT 01</div>', unsafe_allow_html=True)
hero_title, hero_action = st.columns([5, 2], vertical_alignment="center")
with hero_title:
    st.title(f"{city_name} Urban Stress Monitor")
with hero_action:
    st.button(
        "Explore Zone Intelligence  →",
        key="hero_zone_intelligence",
        type="primary",
        use_container_width=True,
        on_click=_open_zone_intelligence,
        help=f"Open the zone intelligence view for {city_name}",
    )
st.markdown('<p class="subtle">See the city in colour — environmental signals, emerging patterns and experimental urban intelligence in one workspace.</p>', unsafe_allow_html=True)
st.markdown('<div style="height:1px;background:linear-gradient(90deg,#39D5F6,#A78BFA,#FB7185,#F59E0B,#A3E635);opacity:.7;margin:1rem 0 1.35rem;border-radius:4px"></div>', unsafe_allow_html=True)

if page == "City Comparison":
    st.subheader("City comparison")
    st.caption("Compare up to three cities using the same live provider sources. Missing measurements remain blank; values are not imputed.")
    comparison_cities = st.multiselect(
        "Choose 2–3 cities",
        options=sorted(CITIES.keys()),
        default=[city_name],
        max_selections=3,
        key="comparison_cities",
    )
    if st.button("Run city comparison", type="primary", key="run_city_comparison"):
        if len(comparison_cities) < 2:
            st.warning("Select at least two cities to compare.")
        else:
            comparison_rows = []
            comparison_errors = []
            progress = st.progress(0, text="Fetching selected city conditions…")
            for index, comparison_name in enumerate(comparison_cities):
                comparison_city = CITIES[comparison_name]
                try:
                    if comparison_name == city_name:
                        comparison_weather, comparison_air = weather, air
                    else:
                        comparison_weather = load_weather(
                            comparison_city["latitude"],
                            comparison_city["longitude"],
                            comparison_city["timezone"],
                        )
                        comparison_air = load_air(
                            comparison_city["latitude"],
                            comparison_city["longitude"],
                            api_key,
                        )
                    current = comparison_weather.attrs.get("current", {}) if not comparison_weather.empty else {}
                    current = dict(current)
                    current["timezone"] = comparison_city["timezone"]
                    comparison_rows.append(
                        build_city_comparison_record(comparison_name, current, comparison_air)
                    )
                except Exception as exc:
                    comparison_errors.append(f"{comparison_name}: {exc}")
                progress.progress((index + 1) / len(comparison_cities), text=f"Processed {comparison_name}")
            progress.empty()
            st.session_state["city_comparison_result"] = pd.DataFrame(comparison_rows)
            st.session_state["city_comparison_errors"] = comparison_errors
    comparison_result = st.session_state.get("city_comparison_result", pd.DataFrame())
    if not comparison_result.empty:
        st.markdown("### Comparison snapshot")
        st.dataframe(
            comparison_result.style.format({
                "Temperature (°C)": "{:.1f}",
                "Feels like (°C)": "{:.1f}",
                "Humidity (%)": "{:.0f}",
                "Rainfall (mm)": "{:.1f}",
                "PM2.5 (µg/m³)": "{:.1f}",
                "PM10 (µg/m³)": "{:.1f}",
                "CityPulse Index": "{:.1f}",
                "PM2.5 oldest station age (h)": "{:.1f}",
                "PM2.5 median station age (h)": "{:.1f}",
                "PM10 oldest station age (h)": "{:.1f}",
                "PM10 median station age (h)": "{:.1f}",
            }, na_rep="—"),
            use_container_width=True,
            hide_index=True,
        )
        temperature_chart = comparison_result.dropna(subset=["Temperature (°C)"])
        if not temperature_chart.empty:
            fig = px.bar(temperature_chart, x="City", y=["Temperature (°C)", "Feels like (°C)"], barmode="group", template="plotly_dark", color_discrete_sequence=["#39D5F6", "#A78BFA"])
            fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238", legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        pollutant_chart = comparison_result.melt(
            id_vars="City",
            value_vars=["PM2.5 (µg/m³)", "PM10 (µg/m³)"],
            var_name="Pollutant",
            value_name="Concentration (µg/m³)",
        ).dropna(subset=["Concentration (µg/m³)"])
        if not pollutant_chart.empty:
            fig = px.bar(pollutant_chart, x="City", y="Concentration (µg/m³)", color="Pollutant", barmode="group", template="plotly_dark", color_discrete_sequence=["#FB7185", "#F59E0B"])
            fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238")
            st.plotly_chart(fig, use_container_width=True)
        index_chart = comparison_result.dropna(subset=["CityPulse Index"])
        if not index_chart.empty:
            fig = px.bar(index_chart, x="City", y="CityPulse Index", template="plotly_dark", color="CityPulse Index", color_continuous_scale="Turbo")
            fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238", coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        st.caption("Comparison values are point-in-time provider observations. Sensor coverage, observation times and modelled weather grid cells differ by city; compare timestamps and coverage before drawing conclusions.")
    for error in st.session_state.get("city_comparison_errors", []):
        st.warning(error)
    if st.session_state.get("city_comparison_result", pd.DataFrame()).empty:
        st.info("Select at least two cities and run the comparison. City comparison calls are cached to reduce repeat requests.")

    st.divider()
    st.markdown("### Historical multi-city trends")
    st.caption("Daily medians from the committed observation archive. Cities share the same UTC calendar-day window; missing days are left blank, never interpolated.")
    trend_cols = st.columns([2, 1])
    with trend_cols[0]:
        trend_metric = st.selectbox("Trend metric", list(TREND_METRICS), key="comparison_trend_metric")
    with trend_cols[1]:
        trend_days = st.selectbox("History window", [7, 30, 90, 180, 365], index=1, format_func=lambda value: f"Last {value} days", key="comparison_trend_days")
    if len(comparison_cities) < 2:
        st.info("Choose at least two cities above to compare historical trends.")
    elif all_history.empty and all_daily_history.empty:
        st.info("The shared observation archive is not available in this deployment yet. The scheduled collector builds raw observations and a compact 365-day station/day archive; charts appear as real data accumulates.")
    else:
        trend_source = all_daily_history if not all_daily_history.empty else all_history
        trend_frame, trend_coverage = build_city_trend_frame(
            trend_source, comparison_cities, trend_metric, days=trend_days
        )
        if trend_frame.empty:
            st.info(f"No archived {trend_metric} observations were found for these cities in the selected {trend_days}-day window.")
        else:
            st.markdown("#### History coverage")
            eligible_cities = trend_coverage.loc[trend_coverage["Days with data"] >= 3, "City"].tolist()
            common_days = 0
            if len(eligible_cities) >= 2:
                shared = trend_frame.loc[trend_frame["city"].isin(eligible_cities)].pivot(
                    index="date", columns="city", values="value"
                )
                common_days = int(shared.dropna(subset=eligible_cities).shape[0])
            trend_coverage["Shared observed days"] = common_days
            st.dataframe(trend_coverage, use_container_width=True, hide_index=True)
            st.metric("Shared observed UTC days across compared cities", f"{common_days:,}")
            if len(eligible_cities) >= 2 and common_days >= 3:
                chart_data = trend_frame.loc[trend_frame["city"].isin(eligible_cities)].copy()
                fig = px.line(
                    chart_data, x="date", y="value", color="city", markers=True,
                    hover_data=["reading_count", "station_count"], template="plotly_dark",
                    labels={"date":"UTC date", "value":trend_metric, "city":"City"},
                    connectgaps=False,
                )
                fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238", legend_title_text="City")
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Each point is a daily median. PM values aggregate station-day medians and retain only mass-concentration units (µg/m³). Weather values are Open-Meteo modelled grid-cell data. Daily coverage is shown above; trend lines do not imply equal sensor density.")
            else:
                st.info("At least two cities with three observed days each and three shared UTC dates are required before a comparative trend is drawn. The archive is still building or date coverage is uneven.")
elif page == "Air Quality Intelligence":
    st.subheader("Air quality intelligence")
    if air.empty:
        st.info("No nearby OpenAQ readings are available for this city right now. This may reflect station coverage, an unavailable feed or missing API access.")
        if air_error:
            st.warning(f"Provider message: {air_error}")
    else:
        air_summary = summarize_air_quality(air)
        station_count = air["location_id"].nunique() if "location_id" in air.columns else air["station"].nunique()
        valid_ages = pd.to_numeric(air_summary["age_hours"], errors="coerce").dropna() if not air_summary.empty else pd.Series(dtype=float)
        newest_age = float(valid_ages.min()) if not valid_ages.empty else None
        kpis = st.columns(3)
        kpis[0].metric("Monitoring stations", f"{station_count:,}")
        kpis[1].metric("Pollutants reported", f"{air_summary['parameter'].nunique():,}")
        kpis[2].metric("Newest observation", f"{newest_age:.1f} h ago" if newest_age is not None else "Unavailable")
        if not air_summary.empty:
            st.markdown("### Pollutant summary")
            st.caption("Median is calculated from the returned station readings for each pollutant and unit. This is not an official AQI.")
            st.dataframe(
                air_summary.style.format({
                    "median_value": "{:.2f}",
                    "min_value": "{:.2f}",
                    "max_value": "{:.2f}",
                    "age_hours": "{:.1f}",
                }),
                use_container_width=True,
                hide_index=True,
            )
            plot_summary = air_summary.copy()
            plot_summary["pollutant_label"] = plot_summary["parameter"] + " · " + plot_summary["unit"]
            fig = px.bar(plot_summary, x="pollutant_label", y="median_value", color="freshness", hover_data=["station_count", "reading_count", "latest_utc", "age_hours"], template="plotly_dark", color_discrete_map={"Fresh":"#A3E635","Recent":"#39D5F6","Stale":"#FB7185"})
            fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238", xaxis_title="Pollutant", yaxis_title="Median reported value", legend_title_text="Observation freshness")
            st.plotly_chart(fig, use_container_width=True)
        parameters = sorted(air["parameter"].dropna().astype(str).unique().tolist()) if "parameter" in air.columns else []
        if parameters:
            selected_parameter = st.selectbox("Inspect pollutant readings", parameters, key="air_quality_parameter")
            detail = air.loc[air["parameter"].astype(str) == selected_parameter].copy()
            detail_columns = [column for column in ["station", "location_id", "locality", "value", "unit", "datetime_local", "datetime_utc", "distance_m", "is_mobile", "provider", "owner", "licenses"] if column in detail.columns]
            st.markdown("### Sensor-level readings")
            st.dataframe(detail[detail_columns].sort_values("datetime_utc", ascending=False) if "datetime_utc" in detail.columns else detail[detail_columns], use_container_width=True, hide_index=True)
        if newest_age is not None and newest_age > 48:
            st.warning("The newest reading is older than 48 hours. It is displayed for context but should not be treated as current.")
        elif newest_age is not None:
            st.caption("Freshness labels use provider observation timestamps. They do not measure instrument calibration or guarantee representative citywide coverage.")

elif page == "Command Center":
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
                      template="plotly_dark", color_discrete_sequence=["#39D5F6","#A78BFA","#FB7185","#F59E0B","#A3E635","#60A5FA"])
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
    st.markdown("### Data freshness & coverage")
    quality_cols = st.columns(3)
    weather_age = None
    if weather_current.get("time"):
        weather_stamp = pd.Timestamp(weather_current["time"])
        if weather_stamp.tzinfo is None:
            weather_stamp = weather_stamp.tz_localize(city["timezone"])
        weather_age = max(0.0, (pd.Timestamp.now(tz="UTC") - weather_stamp.tz_convert("UTC")).total_seconds() / 3600)
    quality_cols[0].metric("Weather timestamp age", f"{weather_age:.1f} h" if weather_age is not None else "Unavailable")
    if air.empty:
        quality_cols[1].metric("Air monitoring stations", "0")
        quality_cols[2].metric("Newest air observation", "Unavailable")
    else:
        air_summary = summarize_air_quality(air)
        station_total = air["location_id"].nunique() if "location_id" in air.columns else air["station"].nunique()
        valid_ages = pd.to_numeric(air_summary["age_hours"], errors="coerce").dropna() if not air_summary.empty else pd.Series(dtype=float)
        freshest_age = float(valid_ages.min()) if not valid_ages.empty else None
        quality_cols[1].metric("Air monitoring stations", f"{station_total:,}")
        quality_cols[2].metric("Newest air observation", f"{freshest_age:.1f} h ago" if freshest_age is not None else "Unavailable")
        if freshest_age is not None and freshest_age > 48:
            st.warning("The newest nearby air-quality observation is older than 48 hours. Treat it as stale, not live.")
        else:
            st.caption("Freshness uses provider observation timestamps. Station counts indicate returned coverage, not complete city coverage.")
    if weather_age is not None and weather_age > 12:
        st.warning("The selected city's weather timestamp is more than 12 hours old.")
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
                fig = px.line(get_forward_hours(weather, weather_current, 72), x="time", y=selected, template="plotly_dark", color_discrete_sequence=["#39D5F6","#A78BFA","#FB7185","#F59E0B","#A3E635","#60A5FA"])
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
    st.caption("Explore returned OpenAQ station observations, their spatial distribution, mapped green spaces and satellite context. Station points are measurements; satellite layers are contextual imagery.")
    show_green = st.checkbox("Show mapped parks and green/vegetated spaces (OpenStreetMap)", value=True, key="zone_show_green")
    green_spaces = pd.DataFrame()
    green_error = None
    if show_green:
        try:
            with st.spinner("Loading nearby mapped green spaces…"):
                green_spaces = load_green_spaces(city["latitude"], city["longitude"])
        except Exception as exc:
            green_error = str(exc)

    coverage, station_inventory, occupied_cells = build_zone_coverage(
        air, city["latitude"], city["longitude"]
    ) if not air.empty else (
        {"station_count":0, "geocoded_station_count":0, "nearest_station_km":None,
         "median_station_distance_km":None, "farthest_station_km":None,
         "occupied_grid_cells":0, "fresh_stations":0, "recent_stations":0,
         "stale_stations":0, "future_timestamp_stations":0, "fixed_stations":0, "mobile_stations":0, "query_radius_km":25.0},
        pd.DataFrame(), pd.DataFrame()
    )
    if not air.empty and {"latitude", "longitude"}.issubset(air.columns):
        geo = air.dropna(subset=["latitude", "longitude"]).copy()
    else:
        geo = pd.DataFrame()

    coverage_cols = st.columns(4)
    coverage_cols[0].metric("Returned stations", f"{coverage['station_count']:,}")
    coverage_cols[1].metric("Fixed stations", f"{coverage['fixed_stations']:,}")
    coverage_cols[2].metric("Mobile stations", f"{coverage['mobile_stations']:,}")
    coverage_cols[3].metric("Fresh stations (≤6 h)", f"{coverage['fresh_stations']:,}")
    st.caption(
        f"Coverage describes OpenAQ's returned sample (up to 12 nearby locations within an approximately 25 km query radius). "
        f"Occupied cells show where returned stations fall; empty cells are not treated as confirmed monitoring gaps."
    )
    distance_cols = st.columns(3)
    distance_cols[0].metric("Nearest fixed station", f"{coverage['nearest_station_km']:.1f} km" if coverage["nearest_station_km"] is not None else "Unavailable")
    distance_cols[1].metric("Median fixed-station distance", f"{coverage['median_station_distance_km']:.1f} km" if coverage["median_station_distance_km"] is not None else "Unavailable")
    distance_cols[2].metric("Future-dated stations", f"{coverage['future_timestamp_stations']:,}")

    map_age = st.selectbox(
        "Map observation age",
        ["Within 48 hours", "Within 6 hours", "All returned observations"],
        index=0,
        key="zone_map_age",
    )
    map_source = geo.copy()
    if not map_source.empty and "datetime_utc" in map_source.columns:
        map_source["datetime_utc"] = pd.to_datetime(map_source["datetime_utc"], errors="coerce", utc=True)
        current_utc = pd.Timestamp.now(tz="UTC")
        if map_age == "Within 48 hours":
            map_source = map_source.loc[
                (map_source["datetime_utc"] >= current_utc - pd.Timedelta(hours=48))
                & (map_source["datetime_utc"] <= current_utc + pd.Timedelta(minutes=15))
            ].copy()
        elif map_age == "Within 6 hours":
            map_source = map_source.loc[
                (map_source["datetime_utc"] >= current_utc - pd.Timedelta(hours=6))
                & (map_source["datetime_utc"] <= current_utc + pd.Timedelta(minutes=15))
            ].copy()
    parameters = sorted(map_source["parameter"].dropna().astype(str).unique().tolist()) if not map_source.empty else []
    selected_parameter = st.selectbox("Map pollutant", parameters, key="zone_map_parameter") if parameters else None
    parameter_data = map_source.loc[map_source["parameter"].astype(str) == selected_parameter].copy() if selected_parameter else pd.DataFrame()
    map_units = sorted(parameter_data["unit"].dropna().astype(str).unique().tolist()) if not parameter_data.empty and "unit" in parameter_data.columns else []
    selected_unit = st.selectbox("Measurement unit", map_units, key="zone_map_unit") if map_units else None
    map_data = parameter_data.loc[parameter_data["unit"].astype(str) == selected_unit].copy() if selected_unit else pd.DataFrame()
    if not map_data.empty:
        station_key = "location_id" if "location_id" in map_data.columns else "station"
        map_data["datetime_utc"] = pd.to_datetime(map_data["datetime_utc"], errors="coerce", utc=True)
        map_data = map_data.sort_values("datetime_utc").drop_duplicates(subset=[station_key], keep="last")
        show_interpolation = st.checkbox(
            "Generate exploratory interpolated surface (requires six recent fixed stations)",
            value=False,
            key="zone_show_interpolation",
        )
        interpolation_status = None
        interpolation_frame = pd.DataFrame()
        interpolation_details = {}
        if show_interpolation:
            interpolation_status, interpolation_frame, interpolation_details = interpolate_station_surface(
                geo, selected_parameter, selected_unit, freshness_hours=12,
                minimum_stations=6, grid_spacing_km=1.0, maximum_nearest_station_km=3.0,
            )
        fig = px.scatter_mapbox(
            map_data, lat="latitude", lon="longitude", color="value",
            hover_name="station",
            hover_data=[column for column in ["parameter", "value", "unit", "datetime_local", "datetime_utc", "distance_m", "is_mobile", "provider"] if column in map_data.columns],
            color_continuous_scale="Turbo", zoom=9, height=560,
        )
        if interpolation_status == "ready" and not interpolation_frame.empty:
            fig.add_trace(go.Scattermapbox(
                lat=interpolation_frame["latitude"],
                lon=interpolation_frame["longitude"],
                mode="markers",
                name="IDW estimated surface (inside station hull)",
                marker={
                    "size":14,
                    "color":interpolation_frame["estimated_value"],
                    "colorscale":"Turbo",
                    "opacity":0.42,
                    "showscale":True,
                    "colorbar":{"title":f"Estimated {selected_parameter} ({selected_unit})"},
                },
                customdata=interpolation_frame[["estimated_value", "nearest_station_km"]].to_numpy(),
                hovertemplate="IDW estimate: %{customdata[0]:.2f} %{text}<br>Nearest station: %{customdata[1]:.2f} km<extra>Exploratory estimate</extra>",
                text=[selected_unit] * len(interpolation_frame),
            ))
        if show_green and not green_spaces.empty:
            fig.add_scattermapbox(
                lat=green_spaces["latitude"], lon=green_spaces["longitude"],
                mode="markers", name="Mapped green spaces",
                marker={"size":11, "color":"#7CDE8B", "opacity":0.9},
                text=green_spaces["name"] + " · " + green_spaces["category"],
                hovertemplate="%{text}<extra>OpenStreetMap</extra>",
            )
        fig.update_layout(
            mapbox_style="carto-darkmatter",
            mapbox_center={"lat":city["latitude"], "lon":city["longitude"]},
            paper_bgcolor="#0B1220", margin={"l":0, "r":0, "t":10, "b":0},
            coloraxis_colorbar_title=f"{selected_parameter} ({selected_unit})",
            legend={"bgcolor":"rgba(11,18,32,.7)"},
        )
        st.plotly_chart(fig, use_container_width=True)
        if show_interpolation:
            if interpolation_status == "ready":
                validation_cols = st.columns(4)
                validation_cols[0].metric("Fixed stations used", f"{interpolation_details['station_count']:,}")
                validation_cols[1].metric("Supported grid cells", f"{interpolation_details['grid_cells']:,}")
                validation_cols[2].metric("IDW leave-one-out MAE", f"{interpolation_details['leave_one_out_mae']:.2f} {selected_unit}" if interpolation_details["leave_one_out_mae"] is not None else "Unavailable")
                validation_cols[3].metric("Median-baseline MAE", f"{interpolation_details['median_baseline_mae']:.2f} {selected_unit}" if interpolation_details["median_baseline_mae"] is not None else "Unavailable")
                st.caption(
                    "Inverse-distance weighting (power 2), restricted to the convex hull of recent fixed stations and within 3 km of a station. "
                    "The surface is shown only when leave-one-station-out MAE is lower than a citywide-median baseline. "
                    "This is a spatial cross-validation diagnostic, not a confidence interval. Estimated cells are not measurements."
                )
            else:
                if interpolation_status == "failed_cross_validation":
                    st.info(
                        f"Interpolation withheld: IDW did not outperform the median baseline "
                        f"(IDW MAE {interpolation_details['leave_one_out_mae']:.2f} vs "
                        f"baseline MAE {interpolation_details['median_baseline_mae']:.2f} {selected_unit}). "
                        "The station data are shown without a modelled surface."
                    )
                else:
                    st.info(f"Interpolation withheld: {interpolation_status.replace('_', ' ')}. At least six recent, geocoded, distinct fixed stations with the same pollutant and unit are required.")
    elif geo.empty:
        st.info("No geocoded OpenAQ stations are available for this city. The map cannot show measured neighbourhood pollution.")
    elif map_source.empty:
        st.info(f"No station observations fall within the selected map age filter ({map_age.lower()}). Older readings remain visible in the station inventory.")
    else:
        st.info("No readings are available for the selected pollutant/unit combination.")

    st.markdown("### Station inventory and freshness")
    if station_inventory.empty:
        st.info("Station-level inventory is unavailable because no timestamped station records were returned.")
    else:
        st.dataframe(
            station_inventory[["station", "location_id", "distance_km", "latest_utc", "age_hours", "freshness", "future_timestamp_readings", "is_mobile", "pollutant_count", "reading_count"]].style.format({"distance_km":"{:.2f}", "age_hours":"{:.1f}"}),
            use_container_width=True, hide_index=True,
        )
        with st.expander("Station data provenance"):
            provenance = station_inventory[["station", "location_id", "provider", "owner", "licenses", "timezone"]]
            st.dataframe(provenance, use_container_width=True, hide_index=True)
        st.caption("Fresh ≤6 hours · Recent 6–48 hours · Stale >48 hours · Future timestamp = provider time more than 15 minutes ahead and excluded from age labels and spatial analytics. These labels do not measure instrument calibration. The map filter above is independent of this inventory.")
    st.markdown("### Returned-station coverage grid")
    coverage_grid = build_zone_coverage_grid(
        occupied_cells, city["latitude"], city["longitude"], radius_km=25, grid_km=5
    )
    if not coverage_grid.empty:
        coverage_grid["marker_size"] = coverage_grid["station_count"].clip(lower=1) * 2 + 7
        coverage_fig = px.scatter_mapbox(
            coverage_grid,
            lat="latitude",
            lon="longitude",
            color="coverage_status",
            size="marker_size",
            size_max=18,
            hover_data=["station_count", "station_names", "cell_centre_distance_km"],
            color_discrete_map={
                "Returned fixed station":"#39D5F6",
                "No fixed station returned in sample":"#FB7185",
            },
            zoom=9,
            height=430,
            labels={"coverage_status":"Returned sample"},
        )
        coverage_fig.update_layout(
            mapbox_style="carto-darkmatter",
            mapbox_center={"lat":city["latitude"], "lon":city["longitude"]},
            paper_bgcolor="#0B1220",
            margin={"l":0, "r":0, "t":10, "b":0},
            legend_title_text="OpenAQ sample",
        )
        st.plotly_chart(coverage_fig, use_container_width=True)
        st.caption(
            "Each marker is the centre of a 5 km grid cell within approximately 25 km of the selected city centre. "
            "A pink/empty cell means no fixed station was returned in that cell by the current nearby-location response. "
            "OpenAQ is queried for at most 12 nearby locations, so this is a returned-sample coverage view—not proof "
            "that no station exists in an empty cell and not a city-boundary coverage assessment."
        )
    if not occupied_cells.empty:
        st.markdown("#### Cells with returned fixed stations")
        st.dataframe(
            occupied_cells.rename(columns={
                "grid_x":"5 km grid X (local offset)",
                "grid_y":"5 km grid Y (local offset)",
                "station_count":"Fixed stations in cell",
                "station_names":"Returned stations",
            }),
            use_container_width=True, hide_index=True,
        )

    st.markdown("### Observed pollution cluster screening")
    st.caption("Screens for a cluster of relatively elevated, recent fixed-station values: at least six fixed stations with the same pollutant/unit, each observed within six hours; high values must be in a multi-station group within 5 km.")
    if selected_parameter and selected_unit:
        hotspot_status, hotspot_stations, hotspot_sample_count = detect_observed_hotspot_clusters(
            geo, selected_parameter, selected_unit
        )
        if hotspot_status == "cluster_found":
            st.warning(f"Relative elevated station cluster found among {hotspot_sample_count} recent stations. This is a local sample comparison, not an official threshold, health warning or interpolated neighbourhood surface.")
            st.dataframe(hotspot_stations, use_container_width=True, hide_index=True)
        elif hotspot_status == "insufficient_station_density":
            st.info(f"Only {hotspot_sample_count} recent, comparable stations are available. At least six are required; no hotspot inference is made.")
        elif hotspot_status == "no_fresh_observations":
            st.info("There are no observations within the six-hour screening window. Historical readings are shown for context only.")
        elif hotspot_status == "no_cluster":
            st.info(f"No multi-station cluster of relatively high readings was identified among {hotspot_sample_count} recent stations.")
        else:
            st.info("The selected pollutant/unit does not have sufficient comparable station data for cluster screening.")

    st.markdown("### Green space and vegetation context")
    if green_error:
        st.warning(f"OpenStreetMap green-space lookup unavailable: {green_error}")
    elif not show_green:
        st.caption("Enable the green-space layer above to query mapped parks, gardens, forests and grass areas.")
    elif green_spaces.empty:
        st.info("No nearby mapped green spaces were returned. This may reflect OpenStreetMap coverage, not an absence of green space.")
    else:
        park_cols = st.columns(3)
        park_cols[0].metric("Mapped green features (5 km)", f"{len(green_spaces):,}")
        park_cols[1].metric("Within 1 km (straight-line)", f"{int((green_spaces['distance_km'] <= 1).sum()):,}")
        nearest_green = float(green_spaces["distance_km"].min()) if "distance_km" in green_spaces and not green_spaces.empty else None
        park_cols[2].metric("Nearest from city centre", f"{nearest_green:.2f} km" if nearest_green is not None else "Unavailable")
        st.dataframe(
            green_spaces[["name", "category", "distance_km", "latitude", "longitude"]]
            .sort_values(["distance_km", "name"])
            .style.format({"distance_km":"{:.2f}"}),
            use_container_width=True, hide_index=True,
        )
        st.caption("OpenStreetMap is community-mapped (© OpenStreetMap contributors). Straight-line distances are measured to mapped feature centres; they are not walking routes or verified entrances. [Map data attribution](https://www.openstreetmap.org/copyright).")
        if st.checkbox("Estimate walk-network access to mapped green spaces", value=False, key="zone_walk_access"):
            try:
                with st.spinner("Calculating approximate walking-network access…"):
                    walking_access, walking_summary = load_walking_access(
                        city["latitude"], city["longitude"], green_spaces
                    )
                if walking_summary.get("status") == "ready":
                    walk_cols = st.columns(3)
                    walk_cols[0].metric("Parks with estimated walk route", f"{walking_summary['routed_green_spaces']:,}")
                    walk_cols[1].metric("Walk-network nodes", f"{walking_summary['network_nodes']:,}")
                    walk_cols[2].metric("Origin snap distance", f"{walking_summary['origin_snap_distance_m']:.0f} m")
                    st.dataframe(
                        walking_access.style.format({
                            "straight_line_km":"{:.2f}",
                            "walking_network_km":"{:.2f}",
                            "estimated_walk_minutes":"{:.1f}",
                            "park_snap_distance_m":"{:.0f}",
                        }),
                        use_container_width=True, hide_index=True,
                    )
                    st.caption(
                        f"Walking time uses an assumed pace of {walking_summary['assumed_walking_speed_kmh']:.1f} km/h. "
                        "The route endpoint is the nearest mapped walk-network node to a green-space feature centre, not a verified public entrance. "
                        "This is a bounded OSM network sample, not a complete citywide pedestrian-accessibility assessment."
                    )
                else:
                    st.info(f"Walking access could not be estimated from the returned network: {walking_summary.get('status')}.")
            except Exception as exc:
                st.warning(f"OpenStreetMap walking-network lookup is temporarily unavailable: {exc}")

    st.markdown("### Landsat surface-temperature contrast")
    st.caption("CityPulse searches recent Landsat Collection 2 Level-2 scenes, masks cloud/shadow/snow/fill/water pixels, applies the USGS temperature scale factor and compares measured thermal pixels.")
    run_landsat = st.checkbox("Run latest usable Landsat analysis", value=False, key="zone_run_landsat_analysis")
    if run_landsat:
        try:
            with st.spinner("Searching and processing recent Landsat scenes…"):
                landsat_pixels, landsat_info = load_landsat_analysis(city["latitude"], city["longitude"])
            if landsat_info.get("status") == "ready":
                st.metric(
                    "Median scene-based surface-temperature contrast",
                    f"{landsat_info['surface_temperature_contrast_c']:+.1f} °C",
                    help="Median across usable Landsat overpasses of urban-core proxy median minus vegetated-reference median. This is exploratory surface-temperature contrast, not an official or climatological UHI metric.",
                )
                temporal_cols = st.columns(4)
                temporal_cols[0].metric("Usable scenes", f"{landsat_info['scene_count']:,}")
                temporal_cols[1].metric("Scene date span", f"{landsat_info['temporal_span_days']:,} days")
                temporal_cols[2].metric(
                    "Between-scene contrast range",
                    f"{landsat_info['contrast_min_c']:.1f} to {landsat_info['contrast_max_c']:.1f} °C",
                )
                uncertainty = landsat_info.get("median_st_uncertainty_k")
                temporal_cols[3].metric(
                    "Median ST-QA uncertainty",
                    f"{uncertainty:.2f} K" if uncertainty is not None else "Unavailable",
                )
                scene_cols = st.columns(4)
                scene_cols[0].metric("Latest usable scene", str(landsat_info.get("acquired", "Unavailable"))[:10])
                scene_cols[1].metric("Clear valid pixels", f"{landsat_info['valid_pixels']:,}")
                scene_cols[2].metric("Urban proxy pixels", f"{landsat_info['urban_pixels']:,}")
                scene_cols[3].metric("Vegetated reference pixels", f"{landsat_info['reference_pixels']:,}")
                cloud_cover = landsat_info.get("cloud_cover_scene_pct")
                cloud_cover_label = f"{float(cloud_cover):.1f}%" if cloud_cover is not None else "Unavailable"
                st.caption(
                    f"Latest scene urban-core median: {landsat_info['urban_proxy_median_c']:.1f} °C · "
                    f"latest vegetated reference median: {landsat_info['vegetated_reference_median_c']:.1f} °C · "
                    f"latest scene-wide cloud estimate: {cloud_cover_label} · "
                    f"scene: {landsat_info.get('scene_id')}"
                )
                if not landsat_pixels.empty:
                    map_hover = ["surface_class", "ndvi", "distance_km"]
                    if "st_uncertainty_k" in landsat_pixels.columns:
                        map_hover.append("st_uncertainty_k")
                    lst_fig = px.scatter_mapbox(
                        landsat_pixels,
                        lat="latitude",
                        lon="longitude",
                        color="temperature_c",
                        hover_data=map_hover,
                        color_continuous_scale="Turbo",
                        zoom=9,
                        height=500,
                        labels={
                            "temperature_c":"Surface temp (°C)",
                            "st_uncertainty_k":"ST-QA uncertainty (K)",
                        },
                    )
                    lst_fig.update_layout(
                        mapbox_style="carto-darkmatter",
                        mapbox_center={"lat":city["latitude"], "lon":city["longitude"]},
                        paper_bgcolor="#0B1220",
                        margin={"l":0, "r":0, "t":10, "b":0},
                    )
                    st.plotly_chart(lst_fig, use_container_width=True)
                scene_table = pd.DataFrame(landsat_info.get("scene_contrasts", []))
                if not scene_table.empty:
                    with st.expander("Scene-by-scene surface-temperature contrasts"):
                        st.dataframe(
                            scene_table.rename(columns={
                                "date":"Scene date (UTC)",
                                "contrast_c":"Surface-temperature contrast (°C)",
                                "urban_median_c":"Urban-proxy median (°C)",
                                "vegetated_median_c":"Vegetated-reference median (°C)",
                                "valid_pixels":"Valid pixels",
                                "cloud_cover_scene_pct":"Scene-wide cloud estimate (%)",
                            }).style.format({
                                "Surface-temperature contrast (°C)":"{:.2f}",
                                "Urban-proxy median (°C)":"{:.2f}",
                                "Vegetated-reference median (°C)":"{:.2f}",
                                "Scene-wide cloud estimate (%)":"{:.1f}",
                            }),
                            use_container_width=True,
                            hide_index=True,
                        )
                if landsat_info["scene_count"] < 3:
                    st.warning(
                        f"Only {landsat_info['scene_count']} usable scene(s) met the clear-pixel requirements. "
                        "Treat the contrast as provisional; a multi-season UHI assessment needs more usable dates."
                    )
                else:
                    st.info(
                        f"The displayed contrast is the median across {landsat_info['scene_count']} usable scenes. "
                        "The date range and scene-by-scene spread are shown above; this is not a long-term seasonal climatology."
                    )
                st.warning(
                    "The urban-core proxy is within 5 km of the approximate city centre with NDVI ≤0.20; "
                    "the vegetated reference is 10–25 km away with NDVI ≥0.35. Low NDVI is only a built/bare proxy, "
                    "not a verified urban land-cover class. Cloud gaps, season, weather, terrain and the approximate "
                    "city-centre point affect the contrast."
                )
                st.caption(
                    "Landsat Collection 2 Level-2 ST is scaled as DN × 0.00341802 + 149 K, then converted to °C. "
                    "Reflectance bands use DN × 0.0000275 − 0.2 for NDVI. QA_PIXEL cloud/shadow/snow/fill/water "
                    "and QA_RADSAT thermal-saturation/terrain flags are excluded. ST-QA uncertainty is shown where available."
                )
            else:
                st.info(f"Landsat analysis unavailable: {landsat_info.get('status', 'unknown status')}. {landsat_info.get('error', 'No suitable recent scene had enough valid urban and vegetated-reference pixels.')}")
        except Exception as exc:
            st.warning(f"Landsat analysis is temporarily unavailable: {exc}")
    else:
        st.info("Enable the analysis to search for a recent clear Landsat scene. Processing is cached for seven days per city.")

    st.markdown("[USGS Landsat Collection 2 surface-temperature product](https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature) · [Microsoft Planetary Computer STAC catalog](https://planetarycomputer.microsoft.com/catalog/dataset/landsat-c2-l2)")
    if st.checkbox("Show NASA MODIS daily temperature context image", value=False, key="zone_load_nasa_lst"):
        try:
            with st.spinner("Loading NASA MODIS context imagery…"):
                lst_image, lst_date = load_land_surface_temperature(city["latitude"], city["longitude"])
            st.image(lst_image, caption=f"NASA GIBS · MODIS Terra daytime surface temperature · {lst_date}", use_container_width=True)
        except Exception as exc:
            st.warning(f"NASA satellite context layer is temporarily unavailable: {exc}")

    st.markdown("### Land-cover classification")
    st.caption("ESA WorldCover 2021 at 10 m resolution. The classification is a dated reference layer, not a live vegetation monitor.")
    if st.checkbox("Load ESA WorldCover 2021 layer", value=True, key="zone_load_worldcover"):
        try:
            with st.spinner("Loading ESA land-cover classification…"):
                cover_image = load_worldcover(city["latitude"], city["longitude"])
            st.image(cover_image, caption="ESA WorldCover 2021 · 10 m land-cover classification", use_container_width=True)
            st.caption("Classes include tree cover, shrubland, grassland, cropland, built-up, bare/sparse vegetation, water, wetland, mangroves and moss/lichen. [Dataset access and attribution](https://esa-worldcover.org/en/data-access)")
        except Exception as exc:
            st.warning(f"ESA WorldCover layer is temporarily unavailable: {exc}")
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
**Geographic coverage:** India plus selected major cities across Japan, China, the United States, the United Kingdom, France, Russia, Brazil, Mexico, Egypt, Thailand, South Africa and Italy. City coordinates are approximate city-centre reference points.

**Weather:** Open-Meteo forecast API. Current modelled conditions and hourly forecasts are displayed separately.

**Air quality:** OpenAQ API v3. CityPulse discovers nearby monitoring locations and retrieves each location’s latest sensor measurements. Nearby coverage and reporting times vary. Missing readings are not imputed.

**Experimental CityPulse Index:** 50% heat signal + 35% particulate signal + 15% rainfall signal. The particulate signal uses the higher of the citywide median PM2.5/PM10 readings, normalized against 60 and 100 µg/m³ respectively. A reading must be no more than 48 hours old. These are project normalisation anchors, not an official AQI calculation: the CPCB AQI uses pollutant-specific breakpoints and prescribed averaging periods, while this prototype uses latest sensor readings. See the [CPCB National AQI methodology](https://airquality.cpcb.gov.in/ccr_docs/About_AQI.pdf). The CityPulse index is not an official rating or health advisory.

**Weather-only signal:** If recent PM2.5/PM10 readings are missing, the composite index is withheld rather than substituting a weather-only value.

**Machine learning:** Predictive models and anomaly detection will only be published after collection of adequate time-series data, baseline evaluation and leakage checks. Until then, API forecasts are clearly distinguished from model predictions.
    """)
    st.markdown("**Application data timestamp (UTC):** " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
