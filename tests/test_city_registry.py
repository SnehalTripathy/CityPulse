from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.cities import CITIES, COUNTRY_CITIES


def test_india_is_pinned_then_countries_are_alphabetical():
    countries = list(COUNTRY_CITIES)
    assert countries[0] == "India"
    assert countries[1:] == sorted(countries[1:])


def test_city_lists_are_alphabetical_and_match_registry():
    for country, cities in COUNTRY_CITIES.items():
        assert cities == sorted(cities)
        assert cities
        assert all(CITIES[city]["country"] == country for city in cities)


def test_all_city_coordinates_and_timezones_are_valid():
    for city, details in CITIES.items():
        assert -90 <= details["latitude"] <= 90, city
        assert -180 <= details["longitude"] <= 180, city
        try:
            ZoneInfo(details["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise AssertionError(f"Invalid timezone for {city}: {details['timezone']}") from exc


def test_country_and_city_registry_counts():
    assert len(COUNTRY_CITIES) == 32
    assert len(CITIES) == 236
