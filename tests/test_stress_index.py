import pandas as pd

from analytics.stress_index import add_weather_stress

def test_weather_stress_is_bounded():
    frame = pd.DataFrame({
        "apparent_temperature": [20.0, 32.0, 45.0],
        "relative_humidity_2m": [0.0, 50.0, 100.0],
        "precipitation": [0.0, 5.0, 20.0],
    })
    result = add_weather_stress(frame)
    assert result["weather_stress"].between(0, 100).all()
    assert result["weather_stress"].iloc[0] < result["weather_stress"].iloc[-1]
