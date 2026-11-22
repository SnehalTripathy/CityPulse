import pandas as pd

from analytics.exposure import build_pollution_event_features


def test_pollution_exposure_features_include_only_fresh_fixed_threshold_crossings():
    now = pd.Timestamp("2026-11-22T18:00:00Z")
    air = pd.DataFrame([
        {"parameter":"pm25","unit":"mg/m³","value":0.080,"datetime_utc":"2026-11-22T17:00:00Z","location_id":1,"station":"A","latitude":12.1,"longitude":77.1,"is_mobile":False},
        {"parameter":"PM₂.₅","unit":"µg/m³","value":75,"datetime_utc":"2026-11-22T16:00:00Z","location_id":2,"station":"B","latitude":12.2,"longitude":77.2,"is_mobile":False},
        {"parameter":"pm25","unit":"µg/m³","value":200,"datetime_utc":"2026-11-22T17:00:00Z","location_id":3,"station":"Mobile","latitude":12.3,"longitude":77.3,"is_mobile":True},
        {"parameter":"pm25","unit":"µg/m³","value":300,"datetime_utc":"2026-11-20T00:00:00Z","location_id":4,"station":"Old","latitude":12.4,"longitude":77.4,"is_mobile":False},
        {"parameter":"pm25","unit":"µg/m³","value":400,"datetime_utc":"2026-11-23T00:00:00Z","location_id":5,"station":"Future","latitude":12.5,"longitude":77.5,"is_mobile":False},
        {"parameter":"pm25","unit":"ppm","value":999,"datetime_utc":"2026-11-22T17:00:00Z","location_id":6,"station":"Unit mismatch","latitude":12.6,"longitude":77.6,"is_mobile":False},
    ])
    result = build_pollution_event_features(air, "pm25", 60, now=now)
    assert len(result["features"]) == 2
    assert {item["properties"]["station"] for item in result["features"]} == {"A", "B"}
    assert result["features"][0]["geometry"]["type"] == "Point"
    assert all(item["properties"]["value_ug_m3"] >= 60 for item in result["features"])


def test_pollution_exposure_features_empty_when_no_station_qualifies():
    result = build_pollution_event_features(
        pd.DataFrame(),
        "pm25",
        60,
        now=pd.Timestamp("2026-11-22T18:00:00Z"),
    )
    assert result == {"type":"FeatureCollection","features":[]}
