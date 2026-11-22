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
from analytics.quality import validate_observations, coverage_label, source_quality_summary
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
from analytics.urban_stress import calculate_urban_stress, calculate_projected_urban_stress
from analytics.scenario import build_scenario_weather
from analytics.alerts import DEFAULT_ALERT_THRESHOLDS, build_alert_assessment
from analytics.alert_store import (load_city_preferences, save_city_preferences, record_alerts, list_alert_history, clear_alert_history, mark_notification, send_alert_email, email_delivery_configured)
from analytics.exposure import build_pollution_event_features
from ingestion.worldpop import (
    DEFAULT_YEAR as WORLDPOP_DEFAULT_YEAR,
    fetch_population_context,
    fetch_population_raster,
    fetch_worldpop_event_exposure,
)
from ml.anomaly import detect_recent_weather_anomaly
from ml.forecasting import (
    train_next_observation_model,
    train_multi_horizon_weather_forecast,
    train_pollutant_deterioration_forecast,
)
from ingestion.terrain_hydrology import fetch_terrain_susceptibility, fetch_hydro_features
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
    archive_url = "https://raw.githubusercontent.com/SnehalTripathy/CityPulse/main/data/processed/daily_city_observations.csv.gz"
    try:
        response = requests.get(archive_url, timeout=(4, 25))
        if response.status_code == 200 and response.content:
            remote = pd.read_csv(io.BytesIO(response.content), compression="gzip")
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
    ["Command Center", "City Comparison", "Air Quality Intelligence", "Environmental Analytics", "Predictive Intelligence", "Anomaly Detection", "Zone Intelligence", "Environmental Health & Exposure", "Smart Alerts & Recommendations", "Data Quality & Confidence", "Scenario Simulator", "Methodology"],
    key="workspace_page",
)
st.sidebar.divider()
st.sidebar.caption("Data: Open-Meteo · OpenAQ · WorldPop")
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

@st.cache_data(ttl=604800, show_spinner=False)
def load_terrain_screen(lat: float, lon: float):
    return fetch_terrain_susceptibility(lat, lon)

@st.cache_data(ttl=86400, show_spinner=False)
def load_hydro_features(lat: float, lon: float):
    return fetch_hydro_features(lat, lon)

@st.cache_data(ttl=3600, show_spinner=False)
def load_weather_horizon_models(observations: pd.DataFrame):
    return train_multi_horizon_weather_forecast(observations)

@st.cache_data(ttl=3600, show_spinner=False)
def load_pollutant_horizon_models(observations: pd.DataFrame, pollutant: str):
    return train_pollutant_deterioration_forecast(observations, pollutant)

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

@st.cache_data(ttl=86400, show_spinner=False)
def load_worldpop_context(lat: float, lon: float, year: int, cache_revision: str = "density-r2"):
    # Bump this revision when the response schema/derived fields change.
    return fetch_population_context(lat, lon, year)


@st.cache_data(ttl=604800, show_spinner=False)
def load_worldpop_raster(lat: float, lon: float, year: int):
    return fetch_population_raster(lat, lon, year, radius_km=10.0)


@st.cache_data(ttl=86400, show_spinner=False)
def load_worldpop_exposure(geometry: dict, radius_km: float, year: int, features: dict | None = None):
    return fetch_worldpop_event_exposure(
        geometry, radius_km=radius_km, year=year, features=features
    )

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
        st.caption("Weather source: Open-Meteo modelled grid-cell data. Air-quality source: OpenAQ fixed-station sensor observations. Official AQI is not supplied by the connected feeds; the CityPulse Index is a separate experimental metric.")
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
            st.caption("Median is calculated from returned OpenAQ station readings for each pollutant and unit. These are pollutant concentrations, not AQI values. No official AQI feed is currently connected.")
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
        future_count = int(pd.to_numeric(air_summary.get("future_timestamp_readings", 0), errors="coerce").fillna(0).sum()) if "future_timestamp_readings" in air_summary else 0
        if future_count:
            st.warning(f"{future_count} provider reading(s) have timestamps more than 15 minutes in the future and were excluded from pollutant statistics.")
        if newest_age is not None and newest_age > 48:
            st.warning("The newest valid reading is older than 48 hours. It is displayed for context but should not be treated as current.")
        elif newest_age is not None:
            st.caption("Freshness labels use provider observation timestamps. They do not measure instrument calibration or guarantee representative citywide coverage.")
        elif future_count:
            st.caption("No valid observation timestamp is available for this pollutant selection.")

elif page == "Command Center":
    st.subheader("City overview")
    if weather_error:
        st.error(f"Weather feed unavailable: {weather_error}")
    if weather.empty:
        st.warning("Weather data is not available right now. Please refresh shortly.")
    else:
        if weather_current:
            temp = weather_current.get("temperature_2m")
            humidity = weather_current.get("relative_humidity_2m")
            wind = weather_current.get("wind_speed_10m")
            current_time = weather_current.get("time", "Current API timestamp unavailable")
            st.caption(f"Open-Meteo current conditions · {current_time} · modelled grid-cell data")
        else:
            first_forecast = weather.iloc[0]
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
        heat_score = usi.get("heat_score")
        rain_score = usi.get("rain_score")
        parts[0].metric("Heat signal", f"{heat_score:.0f}/100" if heat_score is not None else "Unavailable")
        parts[1].metric("Particulate signal", f"{usi['air_score']:.0f}/100" if usi.get("air_score") is not None else "Unavailable")
        parts[2].metric("Rain signal", f"{rain_score:.0f}/100" if rain_score is not None else "Unavailable")
        if composite_value is None:
            st.caption(f"Composite index withheld: {usi.get('reason', 'Required data is not available.')}")
        else:
            st.caption("Experimental composite: 50% heat + 35% particulate signal + 15% rainfall. Based on available recent data within the 25 km search area.")
        st.caption("Official AQI: not available from the currently connected feeds. The CityPulse Index is a separate experimental project signal, not an official AQI.")
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
        future_count = int(pd.to_numeric(air_summary.get("future_timestamp_readings", 0), errors="coerce").fillna(0).sum()) if "future_timestamp_readings" in air_summary else 0
        if future_count:
            st.warning(f"{future_count} air-quality reading(s) have invalid future timestamps and are excluded from current freshness and pollutant calculations.")
        if freshest_age is not None and freshest_age > 48:
            st.warning("The newest valid nearby air-quality observation is older than 48 hours. Treat it as stale, not live.")
        elif freshest_age is not None:
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
    st.caption("CityPulse experimental models are evaluated against a simple persistence baseline. Forecasts that fail the holdout comparison are withheld; Open-Meteo provider output remains separate.")

    st.markdown("### Provider forecast · 72-hour context")
    if not weather.empty:
        provider_72 = get_forward_hours(weather, weather_current, 72)
        provider_variables = [column for column in [
            "apparent_temperature", "relative_humidity_2m",
            "precipitation", "wind_speed_10m",
        ] if column in provider_72.columns]
        if provider_variables:
            provider_fig = px.line(
                provider_72, x="time", y=provider_variables,
                template="plotly_dark",
                color_discrete_sequence=["#39D5F6", "#A78BFA", "#FB7185", "#F59E0B"],
                labels={"value":"Provider forecast", "time":"Local forecast time", "variable":"Variable"},
            )
            provider_fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238")
            st.plotly_chart(provider_fig, use_container_width=True)
        st.caption("Open-Meteo multi-model forecast at the selected city grid cell; not a CityPulse-trained prediction.")
    else:
        st.info("The provider forecast is unavailable.")

    st.markdown("### CityPulse multi-variable weather forecast")
    with st.spinner("Evaluating 24-, 48- and 72-hour weather models against the historical baseline…"):
        weather_models = load_weather_horizon_models(history)
    if weather_models.get("status") != "ready":
        st.info(
            f"Weather models are in data-collection mode ({weather_models.get('snapshots', 0):,} complete snapshots). "
            f"{weather_models.get('reason', 'More complete historical records are required.')}"
        )
    else:
        st.caption(
            f"{weather_models.get('ready_models', 0)} model/horizon combinations have enough observations for evaluation. "
            "Each model uses recent weather plus lagged observations and calendar features."
        )
        weather_units = {
            "apparent_temperature": "°C",
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "precipitation": "mm in the forecast hour",
            "wind_speed_10m": "km/h",
        }
        weather_labels = {
            "apparent_temperature": "Feels-like temperature",
            "temperature_2m": "Air temperature",
            "relative_humidity_2m": "Relative humidity",
            "precipitation": "Hourly precipitation",
            "wind_speed_10m": "Wind speed",
        }
        tabs = st.tabs(["24 hours", "48 hours", "72 hours"])
        for tab, horizon in zip(tabs, ["24", "48", "72"]):
            with tab:
                rows = []
                for parameter, result in weather_models.get("horizons", {}).get(horizon, {}).items():
                    passed = result.get("status") == "ready" and result.get("beats_persistence")
                    rows.append({
                        "Variable": weather_labels.get(parameter, parameter),
                        "Model estimate": (
                            f"{result['prediction']:.2f} {weather_units.get(parameter, '')}"
                            if passed else "Withheld"
                        ),
                        "Change vs latest": (
                            f"{result['change']:+.2f} {weather_units.get(parameter, '')}"
                            if passed else "—"
                        ),
                        "Direction": result.get("direction") if passed else ("Withheld — baseline not beaten" if result.get("status") == "ready" else "Insufficient history"),
                        "Holdout MAE": result.get("mae"),
                        "Persistence MAE": result.get("persistence_mae"),
                        "Validation": "Beat baseline" if passed else ("Did not beat baseline" if result.get("status") == "ready" else "Insufficient data"),
                        "Training pairs": result.get("training_samples", result.get("samples", 0)),
                    })
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.info("No forecast models have enough aligned observations for this horizon.")
        st.caption(
            "Weather model estimates are published only when their chronological holdout MAE is lower than persistence. "
            "Precipitation is the predicted accumulation for the individual forecast hour, not the total over the preceding 24/48/72 hours."
        )

    st.markdown("### Particulate deterioration outlook")
    st.caption(
        "PM models use fixed-station OpenAQ observations only. Compatible concentration units are normalized to µg/m³; "
        "readings are aggregated as the median of available stations in 3-hour UTC bins. Mobile sensors and unsupported units are excluded."
    )
    pollutant_cols = st.columns(2)
    pollutant_models = {}
    for column, pollutant in zip(pollutant_cols, ["PM2.5", "PM10"]):
        with column:
            st.markdown(f"#### {pollutant}")
            with st.spinner(f"Evaluating {pollutant} 24–72-hour models…"):
                pollutant_model = load_pollutant_horizon_models(history, pollutant)
            pollutant_models[pollutant] = pollutant_model
            if pollutant_model.get("status") != "ready":
                st.info(
                    f"Insufficient history ({pollutant_model.get('samples', 0):,} usable 3-hour bins). "
                    f"{pollutant_model.get('reason', 'More compatible fixed-station readings are required.')}"
                )
                continue
            pollutant_rows = []
            for horizon in ["24", "48", "72"]:
                result = pollutant_model["horizons"].get(horizon, {})
                passed = result.get("status") == "ready" and result.get("beats_persistence")
                pollutant_rows.append({
                    "Horizon": f"{horizon} h",
                    "Forecast (µg/m³)": f"{result['prediction']:.2f}" if passed else "Withheld",
                    "Change": f"{result['change']:+.2f}" if passed else "—",
                    "Direction": result.get("direction") if passed else ("Withheld — baseline not beaten" if result.get("status") == "ready" else "Insufficient history"),
                    "Holdout MAE": result.get("mae"),
                    "Baseline MAE": result.get("persistence_mae"),
                    "Validation": "Beat baseline" if passed else ("Did not beat baseline" if result.get("status") == "ready" else "Insufficient data"),
                })
            st.dataframe(pd.DataFrame(pollutant_rows), use_container_width=True, hide_index=True)
    st.markdown("### Projected CityPulse Index · combined environmental outlook")
    st.caption(
        "This combines only model forecasts that pass their own chronological persistence check. "
        "The same experimental 50% heat + 35% particulate + 15% hourly-rainfall formula is used. "
        "A horizon is withheld whenever a required component forecast is unavailable or fails validation."
    )
    projected_rows = []
    for horizon in ["24", "48", "72"]:
        weather_horizon = weather_models.get("horizons", {}).get(horizon, {})
        def validated_weather_value(parameter):
            result = weather_horizon.get(parameter, {})
            return (
                result.get("prediction")
                if result.get("status") == "ready" and result.get("beats_persistence")
                else None
            )
        pm_values = {}
        for pollutant, key_name in [("PM2.5", "pm25"), ("PM10", "pm10")]:
            result = pollutant_models.get(pollutant, {}).get("horizons", {}).get(horizon, {})
            if result.get("status") == "ready" and result.get("beats_persistence"):
                pm_values[key_name] = result.get("prediction")
        assessment = calculate_projected_urban_stress(
            {
                "apparent_temperature": validated_weather_value("apparent_temperature"),
                "precipitation": validated_weather_value("precipitation"),
            },
            pm_values.get("pm25"),
            pm_values.get("pm10"),
        )
        projected_rows.append({
            "Horizon": f"{horizon} h",
            "Projected CityPulse Index": (
                f"{assessment['index']:.1f}/100" if assessment.get("index") is not None else "Withheld"
            ),
            "Heat signal": assessment.get("heat_score"),
            "Particulate signal": assessment.get("air_score"),
            "Rain signal": assessment.get("rain_score"),
            "PM forecasts used": ", ".join(pm_values.keys()) if pm_values else "None",
            "Explanation": assessment.get("reason") or "All required components passed validation",
        })
    st.dataframe(pd.DataFrame(projected_rows), use_container_width=True, hide_index=True)

    st.warning(
        "These are experimental, city-sample estimates—not official AQI forecasts, regulatory warnings or individual exposure predictions. "
        "A forecast is withheld whenever its chronological holdout does not outperform persistence. Sparse monitoring history can leave some horizons unavailable."
    )

    st.markdown("### Existing next-observation diagnostic")
    forecast_result = train_next_observation_model(history)
    if forecast_result["status"] != "ready":
        st.info(f"Three-hour diagnostic: {forecast_result['samples']} valid samples. {forecast_result['reason']}")
    else:
        metric_cols = st.columns(3)
        metric_cols[0].metric("Training pairs", f"{forecast_result['samples']:,}")
        metric_cols[1].metric("Holdout MAE", f"{forecast_result['mae']:.2f} °C")
        metric_cols[2].metric("Persistence MAE", f"{forecast_result['persistence_mae']:.2f} °C")
        if forecast_result["beats_persistence"]:
            st.metric("Next-step feels-like estimate", f"{forecast_result['prediction']:.1f} °C")
        else:
            st.warning("The three-hour estimate is withheld because it did not outperform persistence.")
    st.caption("Model: Random Forest. Training and validation use historical Open-Meteo snapshots only. Provider forecasts and CityPulse model estimates are kept separate.")
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

    st.markdown("### Terrain, rainfall & mapped waterway context")
    st.caption(
        "The terrain layer uses Copernicus DEM GLO-30. It identifies relative low terrain and slope patterns; "
        "it is not a flood forecast and does not model drainage capacity, soil infiltration or water depth."
    )
    forecast_for_hydrology = get_forward_hours(weather, weather_current, 72) if not weather.empty else pd.DataFrame()
    if not forecast_for_hydrology.empty and "precipitation" in forecast_for_hydrology:
        forecast_rain = pd.to_numeric(forecast_for_hydrology["precipitation"], errors="coerce")
        rain24 = forecast_rain.head(24).sum(min_count=1)
        rain72 = forecast_rain.head(72).sum(min_count=1)
        rain_peak = forecast_rain.head(72).max()
        rainfall_cols = st.columns(3)
        rainfall_cols[0].metric("Provider rainfall · next 24 h", f"{rain24:.1f} mm" if pd.notna(rain24) else "Unavailable")
        rainfall_cols[1].metric("Provider rainfall · next 72 h", f"{rain72:.1f} mm" if pd.notna(rain72) else "Unavailable")
        rainfall_cols[2].metric("Peak forecast hour · next 72 h", f"{rain_peak:.1f} mm" if pd.notna(rain_peak) else "Unavailable")
        st.caption("Rainfall values are Open-Meteo modelled hourly precipitation totals at the selected city grid cell; they are not zone-level rainfall measurements.")
    else:
        st.info("Hourly rainfall forecast is unavailable for this city right now.")

    load_terrain = st.checkbox("Load Copernicus DEM terrain screen (30 m source)", value=False, key="zone_load_terrain_screen")
    if load_terrain:
        try:
            with st.spinner("Searching Copernicus DEM tiles and deriving terrain indicators…"):
                terrain_frame, terrain_info = load_terrain_screen(city["latitude"], city["longitude"])
            if terrain_info.get("status") == "ready" and not terrain_frame.empty:
                terrain_cols = st.columns(5)
                terrain_cols[0].metric("Elevation median", f"{terrain_info['elevation_median_m']:.0f} m")
                terrain_cols[1].metric("Median slope", f"{terrain_info['slope_median_degrees']:.1f}°")
                terrain_cols[2].metric("Relative low/gentle cells", f"{terrain_info['relative_low_gentle_cells']:,}")
                terrain_cols[3].metric("High-contributing cells", f"{terrain_info['cells_with_at_least_five_upslope_cells']:,}")
                terrain_cols[4].metric("DEM tiles used", f"{terrain_info['tiles_used']:,}")
                terrain_layers = {
                    "Topographic position": ("topographic_position_m", "Local terrain position (m)", 0),
                    "Slope": ("slope_degrees", "Slope (degrees)", None),
                    "D8 flow accumulation": ("flow_accumulation_area_km2", "Upslope contributing grid area (km²)", None),
                }
                selected_terrain_layer = st.selectbox(
                    "Terrain map layer", list(terrain_layers), key="zone_terrain_layer"
                )
                terrain_column, terrain_label, terrain_midpoint = terrain_layers[selected_terrain_layer]
                terrain_fig = px.scatter_mapbox(
                    terrain_frame,
                    lat="latitude", lon="longitude", color=terrain_column,
                    hover_data=[
                        "elevation_m", "slope_degrees", "topographic_position_m",
                        "flow_accumulation_cells", "flow_accumulation_area_km2", "terrain_class",
                    ],
                    color_continuous_scale="RdYlBu" if terrain_midpoint == 0 else "Turbo",
                    color_continuous_midpoint=terrain_midpoint,
                    zoom=8, height=520,
                    labels={
                        terrain_column:terrain_label,
                        "topographic_position_m":"Local terrain position (m)",
                        "elevation_m":"Surface elevation (m)",
                        "slope_degrees":"Slope (degrees)",
                        "flow_accumulation_cells":"Upslope cells (D8)",
                        "flow_accumulation_area_km2":"Upslope contributing grid area (km²)",
                    },
                )
                terrain_fig.update_traces(marker={"size":6, "opacity":0.78})
                terrain_fig.update_layout(
                    mapbox_style="carto-darkmatter",
                    mapbox_center={"lat":city["latitude"], "lon":city["longitude"]},
                    paper_bgcolor="#0B1220", margin={"l":0, "r":0, "t":10, "b":0},
                )
                st.plotly_chart(terrain_fig, use_container_width=True)
                st.dataframe(
                    terrain_frame.groupby("terrain_class", as_index=False).agg(
                        sampled_cells=("terrain_class", "size"),
                        median_slope_degrees=("slope_degrees", "median"),
                        median_elevation_m=("elevation_m", "median"),
                    ).sort_values("sampled_cells", ascending=False),
                    use_container_width=True, hide_index=True,
                )
                st.caption(
                    f"Source: Copernicus DEM GLO-30 (nominal 30 m DSM); analysis grid is approximately "
                    f"{terrain_info['resolution_x_m']:.0f} × {terrain_info['resolution_y_m']:.0f} m. "
                    "Relative terrain position is elevation minus a local ~1 km neighbourhood mean. "
                    f"The low-lying/gentle category is the lowest 20% of local terrain-position values with slope ≤5°. "
                    f"D8 routing highlights relative upslope grid-cell accumulation (maximum {terrain_info['maximum_d8_flow_accumulation_cells']:,} cells); "
                    "depressions/flats remain sinks and are not filled. DSM elevations include buildings and vegetation. "
                    "This is not flood extent/probability, water depth, drainage capacity or a calibrated hydrological model."
                )
            else:
                st.info(f"Terrain screen unavailable: {terrain_info.get('status', 'no usable DEM')}.")
        except Exception as exc:
            st.warning(f"Copernicus terrain service is temporarily unavailable: {exc}")
    else:
        st.caption("Terrain processing is on demand and cached for seven days per city.")

    load_waterways = st.checkbox("Show mapped rivers, streams, canals and water bodies (OpenStreetMap)", value=False, key="zone_load_hydro_features")
    if load_waterways:
        try:
            with st.spinner("Loading mapped waterways and surface-water features…"):
                hydro_frame = load_hydro_features(city["latitude"], city["longitude"])
            if hydro_frame.empty:
                st.info("No nearby mapped water features were returned. OpenStreetMap coverage is incomplete, so this does not confirm that water features are absent.")
            else:
                hydro_cols = st.columns(3)
                hydro_cols[0].metric("Mapped water features", f"{len(hydro_frame):,}")
                hydro_cols[1].metric("Within 2 km", f"{int((hydro_frame['distance_km'] <= 2).sum()):,}")
                hydro_cols[2].metric("Feature categories", f"{hydro_frame['category'].nunique():,}")
                hydro_fig = px.scatter_mapbox(
                    hydro_frame, lat="latitude", lon="longitude",
                    color="category", hover_name="name",
                    hover_data=["distance_km", "osm_type", "osm_id"],
                    zoom=9, height=440,
                )
                hydro_fig.update_traces(marker={"size":9, "opacity":0.85})
                hydro_fig.update_layout(
                    mapbox_style="carto-darkmatter",
                    mapbox_center={"lat":city["latitude"], "lon":city["longitude"]},
                    paper_bgcolor="#0B1220", margin={"l":0, "r":0, "t":10, "b":0},
                )
                st.plotly_chart(hydro_fig, use_container_width=True)
                st.dataframe(
                    hydro_frame.sort_values("distance_km").head(100),
                    use_container_width=True, hide_index=True,
                )
                st.caption(
                    "OpenStreetMap features are community mapped and displayed at their mapped centre points, "
                    "not as surveyed channel geometry. Missing features or drains may simply be unmapped. "
                    "© OpenStreetMap contributors · https://www.openstreetmap.org/copyright"
                )
        except Exception as exc:
            st.warning(f"OpenStreetMap water-feature lookup is temporarily unavailable: {exc}")

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
        scenario_weather, scenario_input_error = build_scenario_weather(
            weather_current, delta_temp, rainfall_factor
        )
        if scenario_weather is None:
            st.info(f"Scenario unavailable: {scenario_input_error} CityPulse will not substitute placeholder temperature or zero rainfall.")
        else:
            baseline = calculate_urban_stress(weather_current, air)
            scenario_air = air.copy()
            if not scenario_air.empty:
                scenario_air["value"] = pd.to_numeric(scenario_air["value"], errors="coerce") * particulate_factor
            projected = calculate_urban_stress(scenario_weather, scenario_air)
            st.metric("Scenario temperature", f"{scenario_weather['apparent_temperature']:.1f} °C", f"{delta_temp:+.1f} °C")
            left, right = st.columns(2)
            left.metric("Baseline CityPulse Index", f"{baseline['index']:.1f}/100" if baseline.get("index") is not None else "Unavailable")
            right.metric("Scenario CityPulse Index", f"{projected['index']:.1f}/100" if projected.get("index") is not None else "Unavailable")
            if baseline.get("index") is None or projected.get("index") is None:
                st.info(f"The composite scenario is withheld: {projected.get('reason') or baseline.get('reason') or 'Required current measurements are unavailable.'}")
            else:
                st.caption(f"Change in project index: {projected['index'] - baseline['index']:+.1f} points. This is a sensitivity calculation using the documented heuristic, not a prediction of actual city conditions.")
    else:
        st.info("Current weather inputs are unavailable, so the scenario cannot be calculated.")

elif page == "Environmental Health & Exposure":
    st.subheader("Environmental health & population exposure")
    st.caption("Population context from WorldPop Global2. CityPulse uses a 10 km geometric buffer around the configured city-centre point; it is not a municipal boundary or a census count.")
    pop_year = st.selectbox("WorldPop population estimate year", [2025, 2024, 2023], index=0, key="worldpop_year")
    st.markdown("[WorldPop Global2 API and data documentation](https://api.worldpop.org/v3/documentation) · [WorldPop data citation](https://hub.worldpop.org/doi/10.5258/SOTON/WP00839) · [CC BY 4.0 licence](https://creativecommons.org/licenses/by/4.0/)")
    try:
        with st.spinner("Loading population estimates and demographic groups from WorldPop…"):
            population_context = load_worldpop_context(
                city["latitude"], city["longitude"], int(pop_year), "density-r2"
            )
        pop_cols = st.columns(3)
        total_pop = population_context.get("total_population_10km")
        density = population_context.get("population_density_km2")
        area = population_context.get("area_km2")
        pop_cols[0].metric("Estimated population · 10 km", f"{total_pop:,.0f}" if total_pop is not None else "Unavailable")
        pop_cols[1].metric("Estimated density", f"{density:,.0f} people/km²" if density is not None else "Unavailable")
        pop_cols[2].metric("Buffer area", f"{area:,.1f} km²" if area is not None else "Unavailable")
        st.caption(
            f"Dataset: {population_context.get('data_source', 'WorldPop Global2')} · "
            f"data year {population_context.get('data_year', pop_year)} · "
            f"{population_context.get('licence', 'CC BY 4.0')}. Estimates are gridded modelled population, not a live population count."
        )

        st.markdown("### Population distribution by distance from city centre")
        rings = pd.DataFrame(population_context.get("rings", []))
        if not rings.empty:
            rings = rings.rename(columns={
                "from_km":"From (km)",
                "to_km":"To (km)",
                "population":"Population in ring",
                "cumulative":"Cumulative population",
            })
            st.dataframe(
                rings.style.format({
                    "From (km)":"{:.0f}",
                    "To (km)":"{:.0f}",
                    "Population in ring":"{:,.0f}",
                    "Cumulative population":"{:,.0f}",
                }),
                use_container_width=True,
                hide_index=True,
            )
            ring_chart = rings.copy()
            ring_chart["Distance band"] = ring_chart.apply(
                lambda row: f"{row['From (km)']:.0f}–{row['To (km)']:.0f} km", axis=1
            )
            fig = px.bar(
                ring_chart, x="Distance band", y="Population in ring",
                template="plotly_dark", color="Population in ring",
                color_continuous_scale="Turbo",
            )
            fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238", coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

        st.caption("Distance bands are radial catchments around the city-centre point. Demographic groups use a 10 km polygon approximation; totals can differ slightly because the two WorldPop queries use different geometric representations.")
        st.markdown("### Demographic context")
        groups = population_context.get("demographic_groups", {})
        demographic_rows = []
        for key, label in [
            ("under_5", "Children under 5"),
            ("age_65_plus", "Adults aged 65+"),
            ("age_15_64", "Population aged 15–64"),
        ]:
            value = groups.get(key, {})
            count = value.get("population")
            share = value.get("share")
            if count is not None and pd.notna(count):
                demographic_rows.append({
                    "Group": label,
                    "Estimated population": float(count),
                    "Share of 10 km population": float(share) if share is not None and pd.notna(share) else None,
                })
        if demographic_rows:
            demographic_frame = pd.DataFrame(demographic_rows)
            st.dataframe(
                demographic_frame.style.format({
                    "Estimated population":"{:,.0f}",
                    "Share of 10 km population":"{:.1%}",
                }, na_rep="—"),
                use_container_width=True,
                hide_index=True,
            )
                # Evidence availability is shown separately from demographic context; no synthetic confidence score.
        exposure_quality = source_quality_summary(weather_current, air)
        exposure_air = exposure_quality["air_quality"]
        st.markdown("### Exposure evidence and reliability")
        evidence_cols = st.columns(3)
        evidence_cols[0].metric("Population layer", "Available" if total_pop is not None else "Unavailable")
        evidence_cols[1].metric("Weather input age", f"{exposure_quality['weather_age_hours']:.1f} h" if exposure_quality["weather_age_hours"] is not None else "Unavailable")
        evidence_cols[2].metric("Air observations", f"{exposure_air['rows_valid']:,} valid / {exposure_air['rows_total']:,} inspected")
        st.caption("Reliability is described through source availability, freshness and validation counts—not a fabricated confidence percentage. Population estimates are modelled and dated; exposure is a proximity estimate, not a measured count of affected people.")
        st.info("Age-group counts are demographic context only. Children under 5 and adults 65+ are not converted into a heat-vulnerability score; vulnerability also depends on health, housing, income, occupation, cooling access and other local factors.")

        if st.checkbox("Load 1 km population distribution overlay", value=False, key="worldpop_load_raster"):
            try:
                with st.spinner("Loading WorldPop 1 km population grid…"):
                    population_grid = load_worldpop_raster(
                        city["latitude"], city["longitude"], int(pop_year)
                    )
                if population_grid.empty:
                    st.info("WorldPop returned no inhabited 1 km cells for this buffer.")
                else:
                    fig = px.scatter_mapbox(
                        population_grid,
                        lat="latitude",
                        lon="longitude",
                        color="population_per_cell",
                        size="population_per_cell",
                        size_max=18,
                        color_continuous_scale="Turbo",
                        zoom=9,
                        height=560,
                        hover_data={"population_per_cell":":,.0f","latitude":":.4f","longitude":":.4f"},
                        labels={"population_per_cell":"Estimated people per 1 km cell"},
                    )
                    fig.update_layout(
                        mapbox_style="carto-darkmatter",
                        mapbox_center={"lat":city["latitude"],"lon":city["longitude"]},
                        paper_bgcolor="#0B1220",
                        margin={"l":0,"r":0,"t":10,"b":0},
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("Each marker is a WorldPop 1 km grid-cell centre; circle size and colour reflect estimated people per cell. This is a population distribution layer, not a heat or pollution surface.")
            except Exception as exc:
                st.warning(f"WorldPop population grid is temporarily unavailable: {exc}")
    except Exception as exc:
        population_context = None
        st.warning(f"WorldPop population context is temporarily unavailable: {exc}")

    st.divider()
    st.markdown("### Population near a current elevated environmental signal")
    st.caption("Distance-weighted population proximity estimates use WorldPop's documented method. They are not a measured count of affected people or a health-impact estimate.")
    exposure_kind = st.selectbox(
        "Environmental signal",
        ["Current heat condition at city-centre grid point", "PM2.5 above configured trigger at monitoring stations", "PM10 above configured trigger at monitoring stations"],
        key="worldpop_exposure_kind",
    )
    exposure_radius = st.slider(
        "Population proximity radius (km)", 1.0, 10.0,
        5.0 if exposure_kind.startswith("Current heat") else 2.0,
        0.5, key="worldpop_exposure_radius",
    )
    heat_limit = float(st.session_state.get("alert_heat_threshold", DEFAULT_ALERT_THRESHOLDS["heat_c"]))
    pm25_limit = float(st.session_state.get("alert_pm25_threshold", DEFAULT_ALERT_THRESHOLDS["pm25_ug_m3"]))
    pm10_limit = float(st.session_state.get("alert_pm10_threshold", DEFAULT_ALERT_THRESHOLDS["pm10_ug_m3"]))
    st.caption(
        f"Current thresholds used: heat {heat_limit:.1f} °C · "
        f"PM2.5 {pm25_limit:.0f} µg/m³ · PM10 {pm10_limit:.0f} µg/m³. "
        "These are the session's prototype trigger settings, not official warning thresholds."
    )
    if st.button("Estimate nearby population", type="primary", key="run_worldpop_exposure"):
        try:
            event_geometry = {}
            event_features = None
            event_description = ""
            event_radius = float(exposure_radius)
            if exposure_kind.startswith("Current heat"):
                current_heat = pd.to_numeric(weather_current.get("apparent_temperature"), errors="coerce")
                if pd.isna(current_heat) or float(current_heat) < heat_limit:
                    st.info("The current Open-Meteo modelled apparent temperature does not cross the configured heat trigger. No heat exposure estimate was requested.")
                else:
                    event_geometry = {
                        "type":"Point",
                        "coordinates":[float(city["longitude"]), float(city["latitude"])],
                    }
                    event_description = f"Current modelled apparent temperature {float(current_heat):.1f} °C at the city-centre grid point"
            else:
                selected_pollutant = "pm25" if "PM2.5" in exposure_kind else "pm10"
                selected_limit = pm25_limit if selected_pollutant == "pm25" else pm10_limit
                event_features = build_pollution_event_features(
                    air, selected_pollutant, selected_limit, max_age_hours=24
                )
                if not event_features["features"]:
                    st.info(f"No eligible fixed station with a reading above {selected_limit:.0f} µg/m³ was found in the last 24 hours. No population estimate was requested.")
                else:
                    event_description = (
                        f"{len(event_features['features'])} fixed {selected_pollutant.upper()} station(s) "
                        f"above {selected_limit:.0f} µg/m³"
                    )
            should_estimate = bool(event_geometry) or (event_features is not None and bool(event_features.get("features")))
            if should_estimate:
                worldpop_year = int(st.session_state.get("worldpop_year", WORLDPOP_DEFAULT_YEAR))
                with st.spinner("Estimating nearby population using WorldPop…"):
                    exposure = load_worldpop_exposure(
                        event_geometry, float(event_radius), worldpop_year,
                        event_features,
                    )
                st.caption(event_description)
                exposure_cols = st.columns(2)
                exposure_cols[0].metric("Distance-weighted population estimate", f"{exposure['exposed_population']:,.0f}")
                exposure_cols[1].metric("Population within radius", f"{exposure['population_within']:,.0f}" if exposure.get("population_within") is not None else "Unavailable")
                st.caption(
                    f"WorldPop data year {exposure['data_year']} · radius {exposure['radius_km']:.1f} km · "
                    "WorldPop distance-decay weighting (p=1). For several monitoring sites, each person is assigned to the nearest feature to avoid double counting."
                )
                exposure_rings = pd.DataFrame(exposure.get("rings", []))
                if not exposure_rings.empty:
                    st.dataframe(exposure_rings, use_container_width=True, hide_index=True)
                st.warning("This estimates population near the supplied point(s) using a distance-decay model. It does not establish that every person in the area experienced the same conditions, that the conditions caused harm, or that the modelled population distribution matches a current census.")
        except Exception as exc:
            st.warning(f"WorldPop exposure estimation is temporarily unavailable: {exc}")

elif page == "Data Quality & Confidence":
    st.subheader("Data quality & confidence")
    st.caption("Evidence-based coverage, freshness and validation. CityPulse reports observable data quality; it does not invent confidence probabilities.")
    quality = source_quality_summary(weather_current, air)
    weather_cols = st.columns(3)
    weather_cols[0].metric("Weather source status", quality["weather_status"].title())
    weather_cols[1].metric("Weather age", f"{quality['weather_age_hours']:.1f} h" if quality["weather_age_hours"] is not None else "Unavailable")
    air_audit = quality["air_quality"]
    weather_cols[2].metric("Air observations inspected", f"{air_audit['rows_total']:,}")
    st.markdown("### Air-quality coverage")
    summaries = summarize_air_quality(air)
    if summaries.empty:
        st.info("No nearby OpenAQ observations are currently available. No station coverage is inferred.")
    else:
        coverage_rows = []
        for row in summaries.to_dict(orient="records"):
            coverage_rows.append({
                "Pollutant":row["parameter"],
                "Unit":row["unit"],
                "Stations returned":row["station_count"],
                "Readings":row["reading_count"],
                "Latest UTC":row["latest_utc"],
                "Age (hours)":row["age_hours"],
                "Freshness":row["freshness"],
                "Coverage description":coverage_label(row["station_count"],row["age_hours"]),
                "Future rows excluded":row["future_timestamp_readings"],
            })
        st.dataframe(pd.DataFrame(coverage_rows),use_container_width=True,hide_index=True)
    st.markdown("### Validation audit")
    metric_cols=st.columns(4)
    metric_cols[0].metric("Valid rows",f"{air_audit['rows_valid']:,}")
    metric_cols[1].metric("Invalid rows",f"{air_audit['rows_invalid']:,}")
    metric_cols[2].metric("Future rows",f"{air_audit['rows_future']:,}")
    metric_cols[3].metric("Out-of-range rows",f"{air_audit.get('rows_out_of_range',0):,}")
    for issue in air_audit["issues"]:
        st.write(f"• {issue}")
    if not air_audit["by_parameter"].empty:
        st.dataframe(air_audit["by_parameter"],use_container_width=True,hide_index=True)
    st.caption("Plausibility bounds are broad screening checks for recognized parameter names. They flag suspicious values; they do not prove a sensor is faulty. Unit absence and station identity gaps are reported separately and are not silently repaired.")
    audit_csv=air_audit["by_parameter"].to_csv(index=False).encode("utf-8")
    st.download_button("Export quality audit CSV",audit_csv,file_name=f"{city_name.lower().replace(' ','_')}_quality_audit.csv",mime="text/csv")

elif page == "Smart Alerts & Recommendations":
    st.subheader("Smart alerts & recommendations")
    st.caption("Configure prototype triggers for current provider conditions, hourly forecasts and recent fixed-station readings. These are not official warnings or regulatory AQI categories.")
    # Preferences/history use SQLite. Configure CITYPULSE_STATE_DB on a durable volume to
    # retain state across container replacement; Streamlit ephemeral disks are not durable.
    try:
        saved_preferences = load_city_preferences(city_name)
    except Exception as exc:
        saved_preferences = {**DEFAULT_ALERT_THRESHOLDS, "email_enabled": False}
        st.warning(f"Persistent alert settings are unavailable; defaults are being used. Details: {exc}")
    for key, preference_key in [
        ("alert_heat_threshold", "heat_c"),
        ("alert_rainfall_threshold", "rainfall_mm"),
        ("alert_pm25_threshold", "pm25_ug_m3"),
        ("alert_pm10_threshold", "pm10_ug_m3"),
    ]:
        st.session_state.setdefault(key, float(saved_preferences.get(preference_key, DEFAULT_ALERT_THRESHOLDS[preference_key])))
    threshold_cols = st.columns(2)
    with threshold_cols[0]:
        heat_threshold = st.slider("Apparent temperature trigger (°C)", 30.0, 50.0, float(st.session_state["alert_heat_threshold"]), 0.5, key="alert_heat_threshold")
        rainfall_threshold = st.slider("Hourly precipitation trigger (mm)", 1.0, 80.0, float(st.session_state["alert_rainfall_threshold"]), 1.0, key="alert_rainfall_threshold")
    with threshold_cols[1]:
        pm25_threshold = st.slider("PM2.5 trigger (µg/m³)", 10.0, 250.0, float(st.session_state["alert_pm25_threshold"]), 5.0, key="alert_pm25_threshold")
        pm10_threshold = st.slider("PM10 trigger (µg/m³)", 10.0, 400.0, float(st.session_state["alert_pm10_threshold"]), 5.0, key="alert_pm10_threshold")
    email_enabled = st.checkbox(
        "Enable email notifications for newly recorded alerts",
        value=bool(saved_preferences.get("email_enabled", False)),
        key=f"alert_email_enabled_{city_name}",
        help="Notifications go only to the deployment administrator address configured in environment/secrets. The app has no individual user accounts.",
    )
    thresholds = {"heat_c":heat_threshold,"rainfall_mm":rainfall_threshold,"pm25_ug_m3":pm25_threshold,"pm10_ug_m3":pm10_threshold,"email_enabled":email_enabled}
    if st.button("Save alert preferences", type="primary", key="save_alert_preferences"):
        try:
            save_city_preferences(city_name, thresholds)
            st.success(f"Alert preferences saved for {city_name}.")
        except Exception as exc:
            st.error(f"Could not save alert preferences: {exc}")
    if email_enabled and not email_delivery_configured():
        st.warning("Email delivery is not configured. Set CITYPULSE_SMTP_HOST, CITYPULSE_SMTP_PORT, CITYPULSE_SMTP_FROM and CITYPULSE_ALERT_EMAIL; optionally set CITYPULSE_SMTP_USERNAME and CITYPULSE_SMTP_PASSWORD.")
    elif email_enabled:
        st.caption("Email delivery is configured for the deployment administrator address.")
    assessment = build_alert_assessment(weather_current, weather, air, thresholds)
    try:
        newly_recorded = record_alerts(city_name, assessment["alerts"])
    except Exception as exc:
        newly_recorded = []
        st.warning(f"Durable alert history is unavailable. Details: {exc}")
    if newly_recorded and email_enabled:
        sent, delivery_error = send_alert_email(city_name, newly_recorded)
        for alert in newly_recorded:
            try:
                mark_notification(alert["fingerprint"], "sent" if sent else "failed", delivery_error)
            except Exception:
                pass
        if sent:
            st.success(f"Email notification sent for {len(newly_recorded)} new alert event(s).")
        else:
            st.warning(f"New alert(s) were recorded, but email delivery failed: {delivery_error}")
    st.divider()
    st.markdown("### Trigger assessment")
    if assessment["alerts"].empty:
        st.info("No configured thresholds are crossed by the currently available inputs. This does not mean conditions are risk-free.")
    else:
        st.warning(f"{len(assessment['alerts'])} configured trigger(s) crossed in the available data.")
        st.dataframe(assessment["alerts"].style.format({"Value":"{:.1f}","Configured threshold":"{:.1f}"}), use_container_width=True, hide_index=True)
        st.markdown("### Recommended next steps")
        for recommendation in assessment["recommendations"]:
            st.markdown(f"**{recommendation['signal']}**")
            st.write(recommendation["text"])
    with st.expander("Data availability and interpretation", expanded=bool(assessment["unavailable"])):
        for note in assessment["unavailable"]:
            st.write(f"• {note}")
        st.caption("Weather conditions and forecasts are Open-Meteo modelled grid-cell data. PM medians use the latest eligible fixed OpenAQ station values no more than 24 hours old, normalized to µg/m³. Missing, stale, incompatible and mobile readings do not trigger a PM alert.")
    st.markdown("### Alert history")
    st.caption("Alert events are durably stored in SQLite and deduplicated by city, signal, trigger basis, timestamp, value and threshold. Persistence across redeployments requires a durable mounted volume; otherwise the host may reset the database.")
    try:
        history_frame = list_alert_history(city_name)
    except Exception as exc:
        history_frame = pd.DataFrame()
        st.warning(f"Could not load durable alert history: {exc}")
    if not history_frame.empty:
        st.dataframe(history_frame, use_container_width=True, hide_index=True)
        st.download_button("Export alert history CSV", history_frame.to_csv(index=False).encode("utf-8"), file_name=f"{city_name.lower().replace(' ','_')}_alert_history.csv", mime="text/csv")
        if st.button("Clear saved alert history for this city", key="clear_alert_history"):
            try:
                clear_alert_history(city_name)
                st.success("Saved alert history cleared for this city.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not clear alert history: {exc}")
    else:
        st.info("No threshold crossings have been recorded for this city.")
    st.caption("Thresholds are saved per city at application level, not per authenticated user. Notifications are optional and go to the deployment administrator address. Rainfall triggers use the largest single preceding-hour accumulation, not a flood forecast.")

else:
    st.subheader("Methodology & data notes")
    st.markdown("""
**Geographic coverage:** India plus selected major cities across Japan, China, the United States, the United Kingdom, France, Russia, Brazil, Mexico, Egypt, Thailand, South Africa and Italy. City coordinates are approximate city-centre reference points.

**Weather:** Open-Meteo forecast API. Current modelled conditions and hourly forecasts are displayed separately.

**Air quality:** OpenAQ API v3. CityPulse discovers nearby monitoring locations and retrieves each location’s latest sensor measurements. Nearby coverage and reporting times vary. Missing readings are not imputed.

**Population and exposure:** WorldPop Global2 R2025A (CC BY 4.0) supplies approximately 100 m population estimates and demographic group counts. CityPulse summarises radial catchments and an approximate 10 km city-centre polygon, with an optional 1 km population grid. Its distance-weighted exposure estimate uses a point at the modelled city-centre weather grid or fixed monitors whose recent PM readings cross a user trigger. It is a proximity estimate, not an observed count of affected people.

**Smart alerts:** User-configurable prototype triggers compare Open-Meteo modelled current conditions and next-24-hour forecasts separately from recent fixed OpenAQ station medians. Trigger thresholds are not official warnings; recommendations are informational. Notification delivery is not enabled.

**Experimental CityPulse Index:** 50% heat signal + 35% particulate signal + 15% rainfall signal. The particulate signal uses the higher of the citywide median PM2.5/PM10 readings, normalized against 60 and 100 µg/m³ respectively. A reading must be no more than 48 hours old. These are project normalisation anchors, not an official AQI calculation: the CPCB AQI uses pollutant-specific breakpoints and prescribed averaging periods, while this prototype uses latest sensor readings. See the [CPCB National AQI methodology](https://airquality.cpcb.gov.in/ccr_docs/About_AQI.pdf). The CityPulse index is not an official rating or health advisory.

**Weather-only signal:** If recent PM2.5/PM10 readings are missing, the composite index is withheld rather than substituting a weather-only value.

**Machine learning:** CityPulse trains 24-, 48- and 72-hour Random Forest models for apparent temperature, air temperature, humidity, hourly precipitation and wind using historical Open-Meteo snapshots. Separate PM2.5/PM10 models use 3-hour fixed-station medians normalized to µg/m³. Models are evaluated on a chronological holdout with a horizon embargo against persistence; each estimate is withheld unless it beats that baseline. These experimental forecasts are not official warnings or AQI forecasts. The earlier next-observation model remains as a diagnostic.
    """)
    st.markdown("**Application data timestamp (UTC):** " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
