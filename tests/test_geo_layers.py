import requests

from ingestion.geo_layers import fetch_green_spaces, OverpassUnavailable


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


def test_green_space_parser_keeps_osm_source_fields(monkeypatch):
    monkeypatch.setattr("ingestion.geo_layers.requests.post", lambda *args, **kwargs: FakeResponse())
    result = fetch_green_spaces(12.0, 77.0)
    assert len(result) == 2
    assert result.iloc[0]["name"] == "Central Park"
    assert result.iloc[1]["category"] == "forest"
    assert result["distance_km"].min() > 0


def test_overpass_fails_over_to_secondary_endpoint(monkeypatch):
    calls = []

    def fake_post(endpoint, **kwargs):
        calls.append(endpoint)
        if len(calls) == 1:
            response = requests.Response()
            response.status_code = 406
            raise requests.HTTPError("not acceptable", response=response)
        return FakeResponse()

    monkeypatch.setattr("ingestion.geo_layers.requests.post", fake_post)
    result = fetch_green_spaces(12.0, 77.0)
    assert len(result) == 2
    assert len(calls) == 2
    assert "overpass-api.de" in calls[0]
    assert "overpass.kumi.systems" in calls[1]


def test_overpass_failure_returns_friendly_error_after_all_fallbacks(monkeypatch):
    def fake_post(endpoint, **kwargs):
        response = requests.Response()
        response.status_code = 503
        raise requests.HTTPError("service unavailable", response=response)

    monkeypatch.setattr("ingestion.geo_layers.requests.post", fake_post)
    try:
        fetch_green_spaces(12.0, 77.0)
    except OverpassUnavailable as exc:
        assert "temporarily busy or unavailable" in str(exc)
        assert "tried 3 endpoints" in str(exc)
    else:
        raise AssertionError("Expected all Overpass endpoints to fail")
