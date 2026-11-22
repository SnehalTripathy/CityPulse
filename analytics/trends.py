from __future__ import annotations

import pandas as pd


def _parameter_token(value: object) -> str:
    return str(value).lower().replace(".", "").replace("_", "").replace(" ", "").replace("₂", "2")


def _unit_token(value: object) -> str:
    return str(value).lower().replace(" ", "").replace("μ", "µ").replace("³", "3").replace("^", "")


TREND_METRICS = {
    "Temperature (°C)": {"source": "open-meteo", "parameters": {"temperature2m"}, "units": {"°c", "c"}},
    "Feels-like temperature (°C)": {"source": "open-meteo", "parameters": {"apparenttemperature"}, "units": {"°c", "c"}},
    "Rainfall (mm)": {"source": "open-meteo", "parameters": {"precipitation"}, "units": {"mm"}},
    "PM2.5 (µg/m³)": {"source": "openaq", "parameters": {"pm25", "pm25mass"}, "units": {"µg/m3", "ug/m3"}},
    "PM10 (µg/m³)": {"source": "openaq", "parameters": {"pm10", "pm10mass"}, "units": {"µg/m3", "ug/m3"}},
}


def build_city_trend_frame(
    observations: pd.DataFrame,
    cities: list[str],
    metric: str,
    days: int = 30,
    now: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build comparable daily city trends from archived provider observations.

    All cities share a UTC calendar-day window. Weather values are modelled
    Open-Meteo grid-cell outputs; pollutant values are OpenAQ station reports.
    No values are filled or interpolated.
    """
    trend_columns = ["city", "date", "value", "reading_count", "station_count"]
    coverage_columns = ["City", "Days with data", "Readings", "First day (UTC)", "Last day (UTC)"]
    empty_trend = pd.DataFrame(columns=trend_columns)
    empty_coverage = pd.DataFrame(columns=coverage_columns)

    specification = TREND_METRICS.get(metric)
    required = {"city", "source", "parameter", "value", "unit", "datetime_utc"}
    if observations.empty or not required.issubset(observations.columns) or not cities or specification is None:
        return empty_trend, empty_coverage

    frame = observations.loc[
        observations["city"].isin(cities)
        & (observations["source"] == specification["source"])
    ].copy()
    frame["parameter_token"] = frame["parameter"].map(_parameter_token)
    frame["unit_token"] = frame["unit"].map(_unit_token)
    frame = frame.loc[
        frame["parameter_token"].isin(specification["parameters"])
        & frame["unit_token"].isin(specification["units"])
    ].copy()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["value", "datetime_utc"])
    if frame.empty:
        return empty_trend, empty_coverage

    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    cutoff = now - pd.Timedelta(days=max(1, int(days)))
    frame = frame.loc[frame["datetime_utc"] >= cutoff].copy()
    if frame.empty:
        return empty_trend, empty_coverage

    frame["date"] = frame["datetime_utc"].dt.floor("D")
    station_key = "station" if "station" in frame.columns else "_station"
    if station_key == "_station":
        frame[station_key] = frame["city"]
    # For air quality, first summarize repeated reports per station/day, then
    # summarize across stations. For weather, daily median is the grid-cell series.
    station_daily = frame.groupby(
        ["city", "date", station_key], dropna=False, as_index=False
    ).agg(value=("value", "median"), reading_count=("value", "size"))
    trend = station_daily.groupby(["city", "date"], as_index=False).agg(
        value=("value", "median"),
        reading_count=("reading_count", "sum"),
        station_count=(station_key, "nunique"),
    )
    # Reindex to a complete shared UTC calendar so charts can display real
    # breaks where no daily observation exists. These rows remain NaN.
    date_index = pd.date_range(
        start=cutoff.floor("D"), end=now.floor("D"), freq="D", tz="UTC"
    )
    full_index = pd.MultiIndex.from_product(
        [cities, date_index], names=["city", "date"]
    )
    trend = trend.set_index(["city", "date"]).reindex(full_index).reset_index()
    trend["reading_count"] = trend["reading_count"].fillna(0).astype(int)
    trend["station_count"] = trend["station_count"].fillna(0).astype(int)
    trend = trend.sort_values(["date", "city"]).reset_index(drop=True)

    observed_trend = trend.loc[trend["value"].notna()].copy()
    coverage = observed_trend.groupby("city").agg(
        days_with_data=("date", "nunique"),
        readings=("reading_count", "sum"),
        first_day=("date", "min"),
        last_day=("date", "max"),
    ).reset_index().rename(columns={
        "city": "City",
        "days_with_data": "Days with data",
        "readings": "Readings",
        "first_day": "First day (UTC)",
        "last_day": "Last day (UTC)",
    })
    return trend, coverage
