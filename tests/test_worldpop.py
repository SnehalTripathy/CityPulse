import numpy as np
import pytest
import rasterio
import pandas as pd
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from ingestion.worldpop import (
    circle_geojson,
    fetch_population_context,
    fetch_population_raster,
    fetch_worldpop_event_exposure,
)


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload
        self.content = b""
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_circle_geojson_is_closed_and_uses_lon_lat_order():
    result = circle_geojson(12.0, 77.0, radius_km=5, vertices=24)
    ring = result["coordinates"][0]
    assert result["type"] == "Polygon"
    assert len(ring) == 25
    assert ring[0] == ring[-1]
    assert ring[0][0] > 76.9
    assert ring[0][1] == 12.0


def test_population_context_parses_ring_counts_and_age_groups(monkeypatch):
    captured = []

    def fake_post(url, json=None, **kwargs):
        captured.append((url, json))
        if url.endswith("/catchment"):
            return JsonResponse({
                "data_year": 2025,
                "points": [{"id":"city-centre","rings":[
                    {"from_km":0,"to_km":1,"population":1000,"cumulative":1000},
                    {"from_km":1,"to_km":3,"population":5000,"cumulative":6000},
                    {"from_km":3,"to_km":5,"population":9000,"cumulative":15000},
                    {"from_km":5,"to_km":10,"population":20000,"cumulative":35000},
                ]}],
            })
        return JsonResponse({
            "data_year":2025,
            "data_source":"WorldPop Global2 R2025A, 100 m",
            "area_km2":314.0,
            "total_population":35000,
            "groups":[
                {"name":"under_5","population":3500,"share":0.10},
                {"name":"age_65_plus","population":2100,"share":0.06},
                {"name":"age_15_64","population":25000,"share":0.714},
            ],
        })

    monkeypatch.setattr("ingestion.worldpop.requests.post", fake_post)
    result = fetch_population_context(12.0,77.0)
    assert result["data_year"] == 2025
    assert result["total_population_10km"] == 35000
    assert result["population_density_km2"] == pytest.approx(35000 / 314.0)
    assert "R2025A" in result["data_source"]
    assert result["rings"][1]["population"] == 5000
    assert result["demographic_groups"]["under_5"]["share"] == 0.10
    assert len(captured) == 2
    assert captured[0][1]["radii_km"] == [1,3,5,10]
    assert captured[1][1]["groups"] == ["under_5","age_65_plus","age_15_64"]


def test_population_raster_reads_only_inhabited_cells(monkeypatch):
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff", width=2, height=2, count=1,
            dtype="float32", crs="EPSG:4326",
            transform=from_origin(77.0,13.0,0.01,0.01), nodata=-99999,
        ) as dataset:
            dataset.write(np.array([[10,0],[25,-99999]], dtype="float32"), 1)
        raster_bytes = memory.read()

    class RasterResponse:
        content = raster_bytes
        headers = {"content-type":"image/tiff"}

        def raise_for_status(self):
            return None

    captured = {}
    def fake_post(url, json=None, **kwargs):
        captured.update(json)
        return RasterResponse()

    monkeypatch.setattr("ingestion.worldpop.requests.post", fake_post)
    result = fetch_population_raster(12.0,77.0)
    assert len(result) == 2
    assert set(result["population_per_cell"]) == {10.0,25.0}
    assert "geojson" in captured
    assert captured["resolution"] == "1km"


def test_worldpop_exposure_supports_multiple_event_features(monkeypatch):
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured.update(json)
        return JsonResponse({
            "data_year":2025,"radius_km":2,"p":1,"decay":"worldpop",
            "total":{"exposed_population":1200,"population_within":3000,"rings":[]},
            "features":[],
        })

    monkeypatch.setattr("ingestion.worldpop.requests.post", fake_post)
    features = {"type":"FeatureCollection","features":[
        {"type":"Feature","id":"sensor-1","properties":{},"geometry":{"type":"Point","coordinates":[77.0,12.0]}},
        {"type":"Feature","id":"sensor-2","properties":{},"geometry":{"type":"Point","coordinates":[77.1,12.1]}},
    ]}
    result = fetch_worldpop_event_exposure({},2,features=features)
    assert result["exposed_population"] == 1200
    assert result["population_within"] == 3000
    assert captured["features"] == features
    assert captured["decay"] == "worldpop"
    assert captured["p"] == 1


def test_worldpop_year_and_catchment_radius_validation_happens_before_requests(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("WorldPop request should not be made for invalid inputs")

    monkeypatch.setattr("ingestion.worldpop.requests.post", fail_if_called)
    with pytest.raises(ValueError):
        fetch_population_context(12.0, 77.0, year=2031)
    with pytest.raises(ValueError):
        fetch_population_context(12.0, 77.0, year=2025.5)
    with pytest.raises(ValueError):
        fetch_population_context(12.0, 77.0, radii_km=(1, 3.5, 10))
    with pytest.raises(ValueError):
        fetch_population_raster(12.0, 77.0, year=2014)


def test_worldpop_exposure_rejects_invalid_coordinates_and_feature_shapes(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("WorldPop request should not be made for invalid geometry")

    monkeypatch.setattr("ingestion.worldpop.requests.post", fail_if_called)
    with pytest.raises(ValueError):
        fetch_worldpop_event_exposure(
            {"type":"Point","coordinates":[181,12]}, 2
        )
    with pytest.raises(ValueError):
        fetch_worldpop_event_exposure(
            {"type":"Point","coordinates":[77,12]}, 2, year=2031
        )
    with pytest.raises(ValueError):
        fetch_worldpop_event_exposure(
            {}, 2, features={"type":"FeatureCollection","features":[{"type":"Feature","geometry":None}]}
        )


def test_worldpop_context_rejects_malformed_catchment_rings(monkeypatch):
    def fake_post(url, json=None, **kwargs):
        if url.endswith("/catchment"):
            return JsonResponse({
                "points":[{"id":"city-centre","rings":[
                    {"from_km":0,"to_km":1,"population":-10,"cumulative":-10}
                ]}]
            })
        return JsonResponse({
            "area_km2":314,"total_population":1000,
            "groups":[{"name":"under_5","population":100,"share":0.1}]
        })

    monkeypatch.setattr("ingestion.worldpop.requests.post", fake_post)
    from ingestion.worldpop import WorldPopUnavailable

    with pytest.raises(WorldPopUnavailable):
        fetch_population_context(12.0, 77.0)


def test_worldpop_exposure_rejects_invalid_service_population_result(monkeypatch):
    def fake_post(url, json=None, **kwargs):
        return JsonResponse({
            "total":{"exposed_population":float("nan"),"population_within":1000}
        })

    monkeypatch.setattr("ingestion.worldpop.requests.post", fake_post)
    from ingestion.worldpop import WorldPopUnavailable

    with pytest.raises(WorldPopUnavailable):
        fetch_worldpop_event_exposure(
            {"type":"Point","coordinates":[77,12]}, 2
        )
