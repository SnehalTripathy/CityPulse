from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from config.cities import CITIES, COUNTRY_CITIES
from ingestion.weather_api import fetch_forecast
from ingestion.openaq_api import fetch_latest_measurements
from analytics.stress_index import add_weather_stress
from analytics.data_quality import summarize_air_quality
from analytics.comparison import build_city_comparison_record
from analytics.trends import TREND_METRICS, build_city_trend_frame
from analytics.zone_intelligence import build_zone_coverage, detect_observed_hotspot_clusters
from ingestion.geo_layers import fetch_green_spaces, fetch_nasa_land_surface_temperature, fetch_esa_worldcover
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
all_history = history.copy()

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
def load_worldcover(lat: float, lon: float) -> bytes:
    return fetch_esa_worldcover(lat, lon)

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
        trend_days = st.selectbox("History window", [7, 30, 90, 180], index=1, format_func=lambda value: f"Last {value} days", key="comparison_trend_days")
    if len(comparison_cities) < 2:
        st.info("Choose at least two cities above to compare historical trends.")
    elif all_history.empty:
        st.info("The shared observation archive is not available in this deployment yet. Historical comparisons will appear as scheduled collection builds city records.")
    else:
        trend_frame, trend_coverage = build_city_trend_frame(
            all_history, comparison_cities, trend_metric, days=trend_days
        )
        if trend_frame.empty:
            st.info(f"No archived {trend_metric} observations were found for these cities in the selected {trend_days}-day window.")
        else:
            st.markdown("#### History coverage")
            st.dataframe(trend_coverage, use_container_width=True, hide_index=True)
            eligible_cities = trend_coverage.loc[trend_coverage["Days with data"] >= 3, "City"].tolist()
            if len(eligible_cities) >= 2:
                chart_data = trend_frame.loc[trend_frame["city"].isin(eligible_cities)].copy()
                fig = px.line(
                    chart_data, x="date", y="value", color="city", markers=True,
                    hover_data=["reading_count", "station_count"], template="plotly_dark",
                    labels={"date":"UTC date", "value":trend_metric, "city":"City"},
                )
                fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#152238", legend_title_text="City")
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Each point is a daily median. PM values aggregate station-day medians and retain only mass-concentration units (µg/m³). Weather values are Open-Meteo modelled grid-cell data. Daily coverage is shown above; trend lines do not imply equal sensor density.")
            else:
                st.info("At least three observed UTC days in each of two cities are needed before a trend is drawn. The archive is still building or coverage is uneven.")
elif page == "Air Quality Intelligence":
    st.subheader("Air quality intelligence")
    if air.empty:
        st.info("No nearby OpenAQ readings are available for this city right now. This may reflect station coverage, an unavailable feed or missing API access.")
        if air_error:
            st.warning(f"Provider message: {air_error}")
    else:
        air_summary = summarize_air_quality(air)
        station_count = air["location_id"].nunique() if "location_id" in air.columns else air["station"].nunique()
        newest_age = float(air_summary["age_hours"].min()) if not air_summary.empty else None
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
            detail_columns = [column for column in ["station", "locality", "value", "unit", "datetime_local", "datetime_utc", "distance_m"] if column in detail.columns]
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
        freshest_age = float(air_summary["age_hours"].min()) if not air_summary.empty else None
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
         "stale_stations":0, "query_radius_km":25.0},
        pd.DataFrame(), pd.DataFrame()
    )
    if not air.empty and {"latitude", "longitude"}.issubset(air.columns):
        geo = air.dropna(subset=["latitude", "longitude"]).copy()
    else:
        geo = pd.DataFrame()

    coverage_cols = st.columns(4)
    coverage_cols[0].metric("Returned stations", f"{coverage['station_count']:,}")
    coverage_cols[1].metric("Geocoded stations", f"{coverage['geocoded_station_count']:,}")
    coverage_cols[2].metric("Fresh stations (≤6 h)", f"{coverage['fresh_stations']:,}")
    coverage_cols[3].metric("Occupied 5 km cells", f"{coverage['occupied_grid_cells']:,}")
    st.caption(
        f"Coverage describes OpenAQ's returned sample (up to 12 nearby locations within an approximately 25 km query radius). "
        f"Occupied cells show where returned stations fall; empty cells are not treated as confirmed monitoring gaps."
    )
    distance_cols = st.columns(3)
    distance_cols[0].metric("Nearest returned station", f"{coverage['nearest_station_km']:.1f} km" if coverage["nearest_station_km"] is not None else "Unavailable")
    distance_cols[1].metric("Median station distance", f"{coverage['median_station_distance_km']:.1f} km" if coverage["median_station_distance_km"] is not None else "Unavailable")
    distance_cols[2].metric("Stale stations (>48 h)", f"{coverage['stale_stations']:,}")

    parameters = sorted(geo["parameter"].dropna().astype(str).unique().tolist()) if not geo.empty else []
    selected_parameter = st.selectbox("Map pollutant", parameters, key="zone_map_parameter") if parameters else None
    parameter_data = geo.loc[geo["parameter"].astype(str) == selected_parameter].copy() if selected_parameter else pd.DataFrame()
    map_units = sorted(parameter_data["unit"].dropna().astype(str).unique().tolist()) if not parameter_data.empty and "unit" in parameter_data.columns else []
    selected_unit = st.selectbox("Measurement unit", map_units, key="zone_map_unit") if map_units else None
    map_data = parameter_data.loc[parameter_data["unit"].astype(str) == selected_unit].copy() if selected_unit else pd.DataFrame()
    if not map_data.empty:
        station_key = "location_id" if "location_id" in map_data.columns else "station"
        map_data["datetime_utc"] = pd.to_datetime(map_data["datetime_utc"], errors="coerce", utc=True)
        map_data = map_data.sort_values("datetime_utc").drop_duplicates(subset=[station_key], keep="last")
        fig = px.scatter_mapbox(
            map_data, lat="latitude", lon="longitude", color="value",
            hover_name="station",
            hover_data=[column for column in ["parameter", "value", "unit", "datetime_local", "datetime_utc", "distance_m"] if column in map_data.columns],
            color_continuous_scale="Turbo", zoom=9, height=560,
        )
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
    elif geo.empty:
        st.info("No geocoded OpenAQ stations are available for this city. The map cannot show measured neighbourhood pollution.")
    else:
        st.info("No readings are available for the selected pollutant/unit combination.")

    st.markdown("### Station inventory and freshness")
    if station_inventory.empty:
        st.info("Station-level inventory is unavailable because no timestamped station records were returned.")
    else:
        st.dataframe(
            station_inventory[["station", "distance_km", "latest_utc", "age_hours", "freshness", "pollutant_count", "reading_count"]].style.format({"distance_km":"{:.2f}", "age_hours":"{:.1f}"}),
            use_container_width=True, hide_index=True,
        )
        st.caption("Fresh ≤6 hours · Recent 6–48 hours · Stale >48 hours. These labels describe the newest provider timestamp per returned station, not instrument calibration.")
    if not occupied_cells.empty:
        st.markdown("### Returned-station distribution")
        st.dataframe(occupied_cells.rename(columns={"grid_x":"5 km grid X (local offset)", "grid_y":"5 km grid Y (local offset)", "station_count":"Stations in occupied cell", "station_names":"Returned stations"}), use_container_width=True, hide_index=True)
        st.caption("Grid coordinates are relative to the selected city centre. Only occupied cells are listed; this is not a city-boundary coverage or interpolation map.")

    st.markdown("### Observed pollution cluster screening")
    st.caption("Screens for a cluster of relatively elevated, recent station values: at least six stations with the same pollutant/unit, each observed within six hours; high values must be in a multi-station group within 5 km.")
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
        st.dataframe(green_spaces[["name", "category", "distance_km", "latitude", "longitude"]].sort_values(["distance_km", "name"]).style.format({"distance_km":"{:.2f}"}), use_container_width=True, hide_index=True)
        st.caption("OpenStreetMap is community-mapped (© OpenStreetMap contributors). Distances are straight-line from the approximate city centre to mapped feature centres, not walking routes; listings are not a complete inventory of parks or tree cover. [Map data attribution](https://www.openstreetmap.org/copyright).")

    st.markdown("### Satellite land-surface temperature")
    st.caption("NASA MODIS Terra daytime land-surface temperature imagery (about 1 km, daily). This is surface temperature, not near-surface air temperature; cloud gaps and the overpass snapshot mean it is context for UHI investigation, not a standalone urban-heat-island score.")
    if st.checkbox("Load NASA daytime land-surface temperature layer", value=True, key="zone_load_nasa_lst"):
        try:
            with st.spinner("Loading NASA satellite temperature imagery…"):
                lst_image, lst_date = load_land_surface_temperature(city["latitude"], city["longitude"])
            st.image(lst_image, caption=f"NASA GIBS · MODIS Terra daytime land-surface temperature · {lst_date}", use_container_width=True)
        except Exception as exc:
            st.warning(f"NASA satellite layer is temporarily unavailable: {exc}")
    st.markdown("[NASA Global Imagery Browse Services](https://gibs.earthdata.nasa.gov/) · [MODIS layer description](https://geodiscovery.uwm.edu/catalog/nasa-gibs-modis_terra_land_surface_temp_day)")

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
