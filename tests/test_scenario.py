import pandas as pd

from analytics.scenario import build_scenario_weather


def test_scenario_applies_requested_changes_to_observed_weather():
    result, error = build_scenario_weather(
        {"apparent_temperature": 31.0, "precipitation": 2.0, "temperature_2m": 29.0},
        2.5,
        1.5,
    )
    assert error is None
    assert result["apparent_temperature"] == 33.5
    assert result["precipitation"] == 3.0
    assert result["temperature_2m"] == 29.0


def test_scenario_does_not_replace_missing_rainfall_with_zero():
    result, error = build_scenario_weather(
        {"apparent_temperature": 31.0, "precipitation": None},
        2.0,
        1.0,
    )
    assert result is None
    assert "rainfall is missing" in error


def test_scenario_does_not_replace_missing_apparent_temperature():
    result, error = build_scenario_weather(
        {"apparent_temperature": None, "precipitation": 0.0},
        2.0,
        1.0,
    )
    assert result is None
    assert "apparent temperature is missing" in error


def test_scenario_rejects_negative_rainfall():
    result, error = build_scenario_weather(
        {"apparent_temperature": 31.0, "precipitation": -1.0},
        2.0,
        1.0,
    )
    assert result is None
    assert "non-negative" in error
