from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from ml.features import WEATHER_FEATURES, weather_observations_to_wide

MIN_TRAINING_SAMPLES = 80
HORIZON_HOURS = 3


def train_next_observation_model(observations: pd.DataFrame) -> dict:
    """Train/evaluate an exploratory 3-hour apparent-temperature model.

    Uses time-ordered holdout evaluation and compares against a persistence
    baseline. Returns an insufficient-data state until enough clean samples exist.
    """
    wide = weather_observations_to_wide(observations)
    if wide.empty or len(wide) < MIN_TRAINING_SAMPLES + 3:
        return {
            "status": "insufficient_data",
            "samples": int(len(wide)),
            "minimum_samples": MIN_TRAINING_SAMPLES,
            "reason": "Collect at least 80 valid next-step pairs before fitting the model.",
        }

    feature_frame = pd.DataFrame(index=wide.index)
    for column in WEATHER_FEATURES:
        feature_frame[column] = wide[column]
        feature_frame[f"{column}_lag1"] = wide[column].shift(1)
        feature_frame[f"{column}_lag2"] = wide[column].shift(2)
    hours = wide.index.hour + wide.index.minute / 60.0
    feature_frame["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    feature_frame["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    feature_frame["weekday_sin"] = np.sin(2 * np.pi * wide.index.dayofweek / 7)
    feature_frame["weekday_cos"] = np.cos(2 * np.pi * wide.index.dayofweek / 7)

    target = wide["apparent_temperature"].shift(-1)
    next_time = pd.Series(wide.index, index=wide.index).shift(-1)
    interval_hours = (next_time - pd.Series(wide.index, index=wide.index)).dt.total_seconds() / 3600
    supervised = feature_frame.copy()
    supervised["target"] = target
    supervised["interval_hours"] = interval_hours
    supervised = supervised[
        supervised["interval_hours"].between(1.0, 4.5)
    ].dropna()

    if len(supervised) < MIN_TRAINING_SAMPLES:
        return {
            "status": "insufficient_data",
            "samples": int(len(supervised)),
            "minimum_samples": MIN_TRAINING_SAMPLES,
            "reason": "Not enough regularly spaced weather observations have been collected yet.",
        }

    feature_columns = feature_frame.columns.tolist()
    x = supervised[feature_columns]
    y = supervised["target"]
    split = max(int(len(supervised) * 0.8), MIN_TRAINING_SAMPLES - 10)
    split = min(split, len(supervised) - 10)
    x_train, x_test = x.iloc[:split], x.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    model = RandomForestRegressor(
        n_estimators=160,
        min_samples_leaf=2,
        max_features=0.85,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    test_prediction = model.predict(x_test)
    model_mae = float(mean_absolute_error(y_test, test_prediction))
    model_rmse = float(np.sqrt(mean_squared_error(y_test, test_prediction)))
    persistence_mae = float(mean_absolute_error(y_test, x_test["apparent_temperature"]))

    # Refit on all observed targets and predict the next scheduled observation.
    final_model = RandomForestRegressor(
        n_estimators=160,
        min_samples_leaf=2,
        max_features=0.85,
        random_state=42,
        n_jobs=-1,
    )
    final_model.fit(x, y)
    latest_features = feature_frame.tail(1)
    prediction = float(final_model.predict(latest_features)[0])

    return {
        "status": "ready",
        "samples": int(len(supervised)),
        "mae": round(model_mae, 2),
        "rmse": round(model_rmse, 2),
        "persistence_mae": round(persistence_mae, 2),
        "beats_persistence": model_mae < persistence_mae,
        "prediction": round(prediction, 2),
        "last_observation": wide.index[-1].isoformat(),
        "horizon_hours": HORIZON_HOURS,
        "model": "RandomForestRegressor",
        "target": "apparent_temperature",
    }\n
FORECAST_HORIZONS_HOURS = (24, 48, 72)
MIN_HORIZON_PAIRS = 80
MIN_TRAIN_PAIRS = 40
HORIZON_WEATHER_TARGETS = (
    "apparent_temperature", "temperature_2m", "relative_humidity_2m",
    "precipitation", "wind_speed_10m",
)
POLLUTANT_PARAMETERS = {
    "PM2.5": {"pm25", "pm25mass"},
    "PM10": {"pm10", "pm10mass"},
}
POLLUTANT_UNIT_FACTORS = {"µg/m3": 1.0, "ug/m3": 1.0, "mg/m3": 1000.0, "ng/m3": 0.001}


def _calendar_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    hour = index.hour + index.minute / 60.0
    weekday = index.dayofweek
    return pd.DataFrame({
        "hour_sin": np.sin(2 * np.pi * hour / 24.0),
        "hour_cos": np.cos(2 * np.pi * hour / 24.0),
        "weekday_sin": np.sin(2 * np.pi * weekday / 7.0),
        "weekday_cos": np.cos(2 * np.pi * weekday / 7.0),
    }, index=index)


def _build_weather_horizon_features(wide: pd.DataFrame) -> pd.DataFrame:
    features = wide[WEATHER_FEATURES].copy()
    for lag in (1, 2, 4, 8):
        for column in WEATHER_FEATURES:
            features[f"{column}_lag{lag}"] = wide[column].shift(lag)
    return pd.concat([features, _calendar_features(wide.index)], axis=1)


def _fit_time_horizon_model(
    features: pd.DataFrame,
    target: pd.Series,
    horizon_hours: int,
    *,
    cadence_hours: int = 3,
    minimum_pairs: int = MIN_HORIZON_PAIRS,
) -> dict:
    """Fit one leakage-controlled, time-ordered forecast and persistence check."""
    empty = {
        "status": "insufficient_data", "horizon_hours": int(horizon_hours),
        "samples": 0, "minimum_samples": int(minimum_pairs),
        "reason": "Not enough regularly spaced historical observations for this horizon.",
    }
    if features.empty or target.empty:
        return empty
    features = features.copy().sort_index().replace([np.inf, -np.inf], np.nan)
    target = pd.to_numeric(target, errors="coerce").dropna().sort_index()
    desired_times = features.index + pd.Timedelta(hours=int(horizon_hours))
    tolerance = pd.Timedelta(minutes=max(60, int(cadence_hours * 30)))
    matched_target = target.reindex(desired_times, method="nearest", tolerance=tolerance)
    target_time_lookup = pd.Series(target.index, index=target.index)
    matched_target_time = target_time_lookup.reindex(
        desired_times, method="nearest", tolerance=tolerance
    )
    pairs = features.copy()
    pairs["_target"] = matched_target.to_numpy()
    pairs["_target_time"] = matched_target_time.to_numpy()
    pairs["_baseline"] = target.reindex(features.index).to_numpy()
    pairs = pairs.dropna()
    feature_columns = features.columns.tolist()
    if len(pairs) < minimum_pairs:
        return {**empty, "samples": int(len(pairs)),
                "reason": f"{len(pairs)} aligned examples are available; at least {minimum_pairs} are required."}

    split_position = max(int(len(pairs) * 0.8), 1)
    if len(pairs) - split_position < 10:
        return {**empty, "samples": int(len(pairs)),
                "reason": "At least ten final chronological holdout examples are required."}
    holdout_start = pairs.index[split_position]
    # Do not train on a label whose observation occurs at/after the holdout origin.
    target_times = pd.to_datetime(pairs["_target_time"], utc=True)
    train = pairs.loc[(pairs.index < holdout_start) & (target_times < holdout_start)]
    test = pairs.loc[pairs.index >= holdout_start]
    if len(train) < MIN_TRAIN_PAIRS or len(test) < 10:
        return {**empty, "samples": int(len(pairs)),
                "reason": "The horizon embargo leaves too few training examples. Collect more historical data."}

    model = RandomForestRegressor(
        n_estimators=80, min_samples_leaf=3, max_features=0.85,
        random_state=42, n_jobs=-1,
    )
    model.fit(train[feature_columns], train["_target"])
    test_prediction = model.predict(test[feature_columns])
    model_mae = float(mean_absolute_error(test["_target"], test_prediction))
    model_rmse = float(np.sqrt(mean_squared_error(test["_target"], test_prediction)))
    baseline_mae = float(mean_absolute_error(test["_target"], test["_baseline"]))

    final_model = RandomForestRegressor(
        n_estimators=80, min_samples_leaf=3, max_features=0.85,
        random_state=42, n_jobs=-1,
    )
    final_model.fit(pairs[feature_columns], pairs["_target"])
    latest_features = features.dropna().tail(1)
    if latest_features.empty:
        return {**empty, "samples": int(len(pairs)),
                "reason": "The latest observation does not contain a complete feature set."}
    prediction = float(final_model.predict(latest_features[feature_columns])[0])
    current_value = float(target.reindex(latest_features.index).iloc[0])
    difference = prediction - current_value
    scale = max(0.5, abs(current_value) * 0.03)
    direction = "rising" if difference > scale else ("falling" if difference < -scale else "approximately stable")
    return {
        "status": "ready", "horizon_hours": int(horizon_hours),
        "samples": int(len(pairs)), "training_samples": int(len(train)),
        "holdout_samples": int(len(test)), "mae": round(model_mae, 3),
        "rmse": round(model_rmse, 3), "persistence_mae": round(baseline_mae, 3),
        "beats_persistence": bool(model_mae < baseline_mae),
        "prediction": round(prediction, 3), "current_value": round(current_value, 3),
        "change": round(difference, 3), "direction": direction,
        "last_observation": latest_features.index[-1].isoformat(),
        "model": "RandomForestRegressor",
        "validation": "chronological 80/20 holdout with horizon embargo",
    }


def train_multi_horizon_weather_forecast(observations: pd.DataFrame) -> dict:
    """Train 24/48/72-hour weather forecasts and compare each with persistence."""
    wide = weather_observations_to_wide(observations)
    if wide.empty or len(wide) < MIN_HORIZON_PAIRS:
        return {"status": "insufficient_data", "snapshots": int(len(wide)),
                "reason": "Collect more complete Open-Meteo snapshots before fitting 24–72-hour models.",
                "horizons": {}}
    features = _build_weather_horizon_features(wide)
    horizons = {}
    for horizon in FORECAST_HORIZONS_HOURS:
        horizons[str(horizon)] = {}
        for parameter in HORIZON_WEATHER_TARGETS:
            if parameter in wide:
                horizons[str(horizon)][parameter] = _fit_time_horizon_model(
                    features, wide[parameter], horizon
                )
    ready_count = sum(
        result.get("status") == "ready"
        for horizon in horizons.values() for result in horizon.values()
    )
    return {
        "status": "ready" if ready_count else "insufficient_data",
        "snapshots": int(len(wide)), "ready_models": int(ready_count),
        "horizons": horizons, "source": "Historical Open-Meteo observations",
    }


def _pollutant_series(observations: pd.DataFrame, pollutant: str) -> pd.Series:
    required = {"source", "parameter", "unit", "value", "datetime_utc"}
    if observations.empty or not required.issubset(observations.columns):
        return pd.Series(dtype=float)
    frame = observations.loc[observations["source"].astype(str).str.lower() == "openaq"].copy()
    token = frame["parameter"].astype(str).str.lower().str.replace(".", "", regex=False)
    token = token.str.replace("_", "", regex=False).str.replace(" ", "", regex=False)
    wanted = {item.replace(".", "") for item in POLLUTANT_PARAMETERS[pollutant]}
    frame = frame.loc[token.isin(wanted)].copy()
    unit = frame["unit"].astype(str).str.lower().str.replace(" ", "", regex=False)
    unit = unit.str.replace("μ", "µ", regex=False).str.replace("³", "3", regex=False)
    unit = unit.str.replace("^", "", regex=False)
    frame = frame.loc[unit.isin(POLLUTANT_UNIT_FACTORS)].copy()
    unit = unit.loc[frame.index]
    if "is_mobile" in frame:
        mobile = frame["is_mobile"].astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})
        frame = frame.loc[~mobile].copy()
        unit = unit.loc[frame.index]
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce") * unit.map(POLLUTANT_UNIT_FACTORS)
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["value", "datetime_utc"])
    frame = frame.loc[frame["value"].between(0, 2000)].copy()
    if frame.empty:
        return pd.Series(dtype=float)
    frame["time_bin"] = frame["datetime_utc"].dt.floor("3h")
    series = frame.groupby("time_bin")["value"].median().sort_index()
    if len(series) < 2:
        return pd.Series(dtype=float)
    full_index = pd.date_range(series.index.min(), series.index.max(), freq="3h", tz="UTC")
    return series.reindex(full_index).rename(pollutant)


def train_pollutant_deterioration_forecast(observations: pd.DataFrame, pollutant: str) -> dict:
    """Train 24/48/72-hour PM models from fixed OpenAQ stations, if validated."""
    if pollutant not in POLLUTANT_PARAMETERS:
        raise ValueError(f"Unsupported pollutant: {pollutant}")
    series = _pollutant_series(observations, pollutant)
    if series.empty:
        return {"status": "insufficient_data", "pollutant": pollutant, "samples": 0,
                "reason": "No compatible fixed-station history is available.", "horizons": {}}
    features = pd.DataFrame({"current": series})
    for lag in (1, 2, 8, 16):
        features[f"lag_{lag}"] = series.shift(lag)
    features["rolling_mean_8"] = series.rolling(8, min_periods=6).mean()
    features["rolling_std_8"] = series.rolling(8, min_periods=6).std().fillna(0.0)
    features = pd.concat([features, _calendar_features(series.index)], axis=1)
    horizons = {
        str(horizon): _fit_time_horizon_model(features, series, horizon, cadence_hours=3)
        for horizon in FORECAST_HORIZONS_HOURS
    }
    ready_count = sum(result.get("status") == "ready" for result in horizons.values())
    return {
        "status": "ready" if ready_count else "insufficient_data",
        "pollutant": pollutant, "samples": int(series.notna().sum()),
        "horizons": horizons, "source": "OpenAQ fixed-station observations",
        "unit": "µg/m³",
    }
