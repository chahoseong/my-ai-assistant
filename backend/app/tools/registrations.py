from collections.abc import Mapping

from app.tools.runtime import ToolsetRegistration
from app.tools.toolsets import opgg_tft_registration
from app.tools.weather_toolset import weather_registration


def default_toolset_registrations(
    environment: Mapping[str, str],
) -> tuple[ToolsetRegistration, ...]:
    return (weather_registration(environment), opgg_tft_registration(environment))
