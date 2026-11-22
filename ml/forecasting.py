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
    }
