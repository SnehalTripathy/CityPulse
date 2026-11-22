from pathlib import Path

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

def ensure_data_dirs() -> None:
    for folder in (RAW_DIR, PROCESSED_DIR):
        folder.mkdir(parents=True, exist_ok=True)
