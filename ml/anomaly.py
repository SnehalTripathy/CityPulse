from __future__ import annotations

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from ml.features import WEATHER_FEATURES, weather_observations_to_wide

MIN_ANOMALY_SAMPLES = 30


def detect_recent_weather_anomaly(observations: pd.DataFrame) -> dict:
    """Fit an Isolation Forest to historical weather observations."""
    wide = weather_observations_to_wide(observations)
    if wide.empty:
        return {
            "status": "insufficient_data",
            "samples": 0,
            "minimum_samples": MIN_ANOMALY_SAMPLES,
            "reason": "No weather observation history is available yet.",
        }

    clean = wide[WEATHER_FEATURES].dropna()
    if len(clean) < MIN_ANOMALY_SAMPLES:
        return {
            "status": "insufficient_data",
            "samples": int(len(clean)),
            "minimum_samples": MIN_ANOMALY_SAMPLES,
            "reason": "Collect at least 30 complete weather snapshots to establish a baseline.",
        }

    scaler = StandardScaler()
    values = scaler.fit_transform(clean)
    model = IsolationForest(
        n_estimators=200,
        contamination=0.05,
        random_state=42,
    )
    labels = model.fit_predict(values)
    scores = model.decision_function(values)
    latest_label = int(labels[-1])
    latest_score = float(scores[-1])
    anomalous_count = int((labels == -1).sum())

    return {
        "status": "ready",
        "samples": int(len(clean)),
        "anomalies": anomalous_count,
        "latest_is_anomaly": latest_label == -1,
        "latest_score": round(latest_score, 4),
        "latest_timestamp": clean.index[-1].isoformat(),
        "model": "IsolationForest",
        "features": WEATHER_FEATURES,
    }
