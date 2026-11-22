from datetime import date

from ingestion.geo_layers import (
    OVERPASS_HEADERS,
    fetch_nasa_land_surface_temperature,
    fetch_green_spaces,
)


class FakeResponse:
    status_code = 200
    headers = {"content-type": "application/json"}

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "elements": [
                {"type": "node", "id": 1, "lat": 12.1, "lon": 77.1, "tags": {"leisure": "park", "name": "Central Park"}},
                {"type": "way", "id": 2, "center": {"lat": 12.2, "lon": 77.2}, "tags": {"landuse": "forest"}},
            ]
        }


def test_overpass_request_identifies_citypulse_with_a_non_default_user_agent(monkeypatch):
    captured = {}

    def fake_post(endpoint, data=None, headers=None, timeout=None):
        captured.update(headers or {})
        return FakeResponse()

    monkeypatch.setattr("ingestion.geo_layers.requests.post", fake_post)
    result = fetch_green_spaces(12.0, 77.0)
    assert len(result) == 2
    assert captured["User-Agent"] == OVERPASS_HEADERS["User-Agent"]
    assert "SnehalTripathy/CityPulse" in captured["User-Agent"]
    assert captured["Accept"] == "application/json"


def test_green_space_parser_keeps_osm_source_fields(monkeypatch):
    monkeypatch.setattr("ingestion.geo_layers.requests.post", lambda *args, **kwargs: FakeResponse())
    result = fetch_green_spaces(12.0, 77.0)
    assert len(result) == 2
    assert result.iloc[0]["name"] == "Central Park"
    assert result.iloc[1]["category"] == "forest"
    assert result["distance_km"].min() > 0


def test_nasa_layer_uses_requested_date(monkeypatch):
    captured = {}

    class ImageResponse:
        headers = {"content-type": "image/png"}
        content = b"png-data"

        def raise_for_status(self):
            return None

    def fake_get(endpoint, params=None, timeout=None):
        captured.update(params)
        return ImageResponse()

    monkeypatch.setattr("ingestion.geo_layers.requests.get", fake_get)
    image, selected = fetch_nasa_land_surface_temperature(12.0, 77.0, date(2026, 11, 20))
    assert image == b"png-data"
    assert selected == "2026-11-20"
    assert captured["layers"] == "MODIS_Terra_Land_Surface_Temp_Day"


def test_worldcover_request_does_not_send_a_time_dimension(monkeypatch):
    captured = {}

    class ImageResponse:
        headers = {"content-type": "image/png"}
        content = b"cover-png"

        def raise_for_status(self):
            return None

    def fake_get(endpoint, params=None, timeout=None):
        captured.update(params)
        return ImageResponse()

    monkeypatch.setattr("ingestion.geo_layers.requests.get", fake_get)
    from ingestion.geo_layers import fetch_esa_worldcover
    assert fetch_esa_worldcover(12.0, 77.0) == b"cover-png"
    assert captured["layers"] == "esa-worldcover-map-10m-2021-v2_map"
    assert "time" not in captured
