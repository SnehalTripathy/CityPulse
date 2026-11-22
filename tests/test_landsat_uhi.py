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



def test_scene_contrast_summary_reports_multi_date_spread_and_uncertainty():
    from ingestion.landsat_uhi import summarize_scene_contrasts

    result = summarize_scene_contrasts([
        {
            "surface_temperature_contrast_c":8.0,
            "urban_proxy_median_c":40.0,
            "vegetated_reference_median_c":32.0,
            "median_st_uncertainty_k":1.4,
            "acquired":"2026-08-01T05:00:00Z",
        },
        {
            "surface_temperature_contrast_c":6.0,
            "urban_proxy_median_c":38.0,
            "vegetated_reference_median_c":32.0,
            "median_st_uncertainty_k":1.6,
            "acquired":"2026-11-01T05:00:00Z",
        },
        {
            "surface_temperature_contrast_c":7.0,
            "urban_proxy_median_c":39.0,
            "vegetated_reference_median_c":32.0,
            "median_st_uncertainty_k":1.5,
            "acquired":"2026-09-01T05:00:00Z",
        },
    ])
    assert result["scene_count"] == 3
    assert result["surface_temperature_contrast_c"] == 7.0
    assert result["contrast_min_c"] == 6.0
    assert result["contrast_max_c"] == 8.0
    assert result["temporal_span_days"] == 92
    assert result["median_st_uncertainty_k"] == 1.5


def test_surface_temperature_summary_exposes_st_qa_by_land_pool():
    from ingestion.landsat_uhi import summarize_surface_temperature_contrast

    rows = []
    for index in range(35):
        rows.append({
            "temperature_c":40.0,
            "ndvi":0.1,
            "distance_km":2.0,
            "st_uncertainty_k":1.2,
        })
        rows.append({
            "temperature_c":32.0,
            "ndvi":0.6,
            "distance_km":15.0,
            "st_uncertainty_k":1.8,
        })
    result=summarize_surface_temperature_contrast(pd.DataFrame(rows))
    assert result["median_st_uncertainty_k"] == 1.5
    assert result["urban_st_uncertainty_median_k"] == 1.2
    assert result["vegetated_st_uncertainty_median_k"] == 1.8
