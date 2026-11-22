import pandas as pd

from ingestion.landsat_uhi import summarize_surface_temperature_contrast


def test_surface_temperature_contrast_uses_urban_and_vegetated_reference_pools():
    rows = []
    for index in range(40):
        rows.append({
            "temperature_c": 39.0 + index * 0.01,
            "ndvi": 0.10,
            "distance_km": 2.0,
        })
        rows.append({
            "temperature_c": 31.0 + index * 0.01,
            "ndvi": 0.55,
            "distance_km": 15.0,
        })
    result = summarize_surface_temperature_contrast(pd.DataFrame(rows))
    assert result["status"] == "ready"
    assert result["urban_pixels"] == 40
    assert result["reference_pixels"] == 40
    assert abs(result["surface_temperature_contrast_c"] - 8.0) < 0.02


def test_surface_temperature_contrast_is_withheld_without_enough_clear_pixels():
    frame = pd.DataFrame([
        {"temperature_c": 40.0, "ndvi": 0.1, "distance_km": 1.0},
        {"temperature_c": 30.0, "ndvi": 0.6, "distance_km": 15.0},
    ])
    result = summarize_surface_temperature_contrast(frame)
    assert result["status"] == "insufficient_reference_pixels"
    assert result["surface_temperature_contrast_c"] is None
