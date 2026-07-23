import pytest

from app.tools.registrations import default_toolset_registrations


pytestmark = pytest.mark.unit


def test_default_toolset_registrations_include_weather_and_opgg() -> None:
    registrations = default_toolset_registrations({})

    assert tuple(registration.name for registration in registrations) == (
        "weather",
        "opgg_tft",
    )
