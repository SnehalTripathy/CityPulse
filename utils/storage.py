from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OBSERVATIONS_PATH = RAW_DIR / "observations.csv"


def ensure_data_dirs() -> None:
    for folder in (RAW_DIR, PROCESSED_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def load_observations(path: str | Path = OBSERVATIONS_PATH) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(source)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()
    if frame.empty:
        return frame
    if "datetime_utc" in frame.columns:
        frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], errors="coerce", utc=True)
    if "observed_at_utc" in frame.columns:
        frame["observed_at_utc"] = pd.to_datetime(frame["observed_at_utc"], errors="coerce", utc=True)
    if "value" in frame.columns:
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame
