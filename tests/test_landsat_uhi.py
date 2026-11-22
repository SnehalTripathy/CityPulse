import numpy as np
import pandas as pd
from types import SimpleNamespace

from ingestion import landsat_uhi
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



def test_landsat_fetch_aggregates_multiple_scenes_and_uses_qa_assets(monkeypatch):
    width = height = 250
    latitudes = np.linspace(25 / 111.32, -25 / 111.32, height)
    longitudes = np.linspace(-25 / 111.32, 25 / 111.32, width)
    yy, xx = np.meshgrid(latitudes, longitudes, indexing="ij")
    distance = np.sqrt((yy * 111.32) ** 2 + (xx * 111.32) ** 2)
    urban = distance <= 5
    vegetated = (distance >= 10) & (distance <= 25)

    lst = np.full((height, width), 48000, dtype=np.float32)
    lst[urban] = 50000
    lst[vegetated] = 47000
    red = np.full((height, width), 14545, dtype=np.float32)
    nir = np.full((height, width), 16000, dtype=np.float32)
    red[vegetated] = 10909
    nir[vegetated] = 25454

    item_list = []
    for index, month in enumerate(["2026-05-01", "2026-08-01", "2026-11-01"]):
        assets = {
            name: SimpleNamespace(href=f"{name}_{index}")
            for name in ["lwir11", "qa_pixel", "red", "nir08", "qa", "qa_radsat"]
        }
        item_list.append(SimpleNamespace(
            assets=assets,
            properties={"datetime": month + "T05:00:00Z", "eo:cloud_cover": 10.0},
            id=f"scene-{index}",
        ))

    class FakeSearch:
        def items(self):
            return item_list

    class FakeCatalog:
        def search(self, **kwargs):
            assert kwargs["collections"] == [landsat_uhi.COLLECTION]
            assert kwargs["query"]["eo:cloud_cover"]["lt"] == 65
            return FakeSearch()

    monkeypatch.setattr(landsat_uhi.pystac_client.Client, "open", lambda *_: FakeCatalog())
    monkeypatch.setattr(landsat_uhi.planetary_computer, "sign", lambda item: item)

    def fake_read(href, bbox, width, height, resampling):
        if href.startswith("lwir11_"):
            return lst.copy(), None
        if href.startswith("qa_pixel_") or href.startswith("qa_radsat_"):
            return np.zeros((height, width), dtype=np.float32), None
        if href.startswith("red_"):
            return red.copy(), None
        if href.startswith("nir08_"):
            return nir.copy(), None
        if href.startswith("qa_"):
            return np.full((height, width), 150, dtype=np.float32), None
        raise AssertionError(href)

    monkeypatch.setattr(landsat_uhi, "_read_asset_on_grid", fake_read)
    pixels, info = landsat_uhi.fetch_landsat_surface_temperature_analysis(
        0.0, 0.0, maximum_scenes=3, target_usable_scenes=3
    )
    assert info["status"] == "ready"
    assert info["scene_count"] == 3
    assert info["scene_dates"] == ["2026-05-01", "2026-08-01", "2026-11-01"]
    assert info["median_st_uncertainty_k"] == 1.5
    assert info["surface_temperature_contrast_c"] > 0
    assert not pixels.empty
