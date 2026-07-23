import math
import unicodedata
from collections.abc import Mapping
from typing import TypedDict

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError


NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
OPEN_METEO_BASE_URL = "https://api.open-meteo.com"


class ResolvedLocation(TypedDict):
    location: str
    latitude: float
    longitude: float


class WeatherService:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        geocoder_base_url: str = NOMINATIM_BASE_URL,
        weather_base_url: str = OPEN_METEO_BASE_URL,
        user_agent: str = "my-ai-assistant/0.1",
    ) -> None:
        self._transport = transport
        self._geocoder_base_url = geocoder_base_url.rstrip("/")
        self._weather_base_url = weather_base_url.rstrip("/")
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}

    async def get_current_weather(self, city: str) -> dict[str, object]:
        normalized_city = unicodedata.normalize("NFKC", city).strip()
        if not normalized_city:
            raise ToolError("A city name is required.")

        try:
            async with httpx.AsyncClient(
                transport=self._transport, headers=self._headers
            ) as client:
                geocoding_response = await client.get(
                    f"{self._geocoder_base_url}/search",
                    params={
                        "q": normalized_city,
                        "format": "jsonv2",
                        "limit": 2,
                        "featureType": "city",
                        "accept-language": "ko",
                    },
                )
                geocoding_response.raise_for_status()
                location = self._parse_location(geocoding_response.json())

                weather_response = await client.get(
                    f"{self._weather_base_url}/v1/forecast",
                    params={
                        "latitude": location["latitude"],
                        "longitude": location["longitude"],
                        "current": "temperature_2m,weather_code",
                        "timezone": "auto",
                    },
                )
                weather_response.raise_for_status()
                return self._parse_weather(weather_response.json(), location)
        except ToolError:
            raise
        except (httpx.HTTPError, TypeError, ValueError, KeyError):
            raise ToolError("The weather service is temporarily unavailable.") from None

    @staticmethod
    def _parse_location(payload: object) -> ResolvedLocation:
        if not isinstance(payload, list) or not payload:
            raise ToolError("No matching city was found. Ask the user for a more specific city.")
        if len(payload) > 1:
            raise ToolError("Multiple cities matched. Ask the user for a more specific city.")

        first = payload[0]
        if not isinstance(first, Mapping):
            raise ToolError("The weather service is temporarily unavailable.")

        display_name = first.get("display_name")
        latitude = WeatherService._finite_float(first.get("lat"))
        longitude = WeatherService._finite_float(first.get("lon"))
        if not isinstance(display_name, str) or not display_name.strip():
            raise ToolError("The weather service is temporarily unavailable.")
        if latitude is None or longitude is None:
            raise ToolError("The weather service is temporarily unavailable.")

        return {
            "location": display_name,
            "latitude": latitude,
            "longitude": longitude,
        }

    @staticmethod
    def _parse_weather(
        payload: object, location: ResolvedLocation
    ) -> dict[str, object]:
        if not isinstance(payload, Mapping):
            raise ToolError("The weather service is temporarily unavailable.")

        current = payload.get("current")
        timezone = payload.get("timezone")
        if not isinstance(current, Mapping) or not isinstance(timezone, str):
            raise ToolError("The weather service is temporarily unavailable.")

        temperature = WeatherService._finite_float(current.get("temperature_2m"))
        weather_code = WeatherService._finite_float(current.get("weather_code"))
        observed_at = current.get("time")
        if temperature is None or weather_code is None or not isinstance(observed_at, str):
            raise ToolError("The weather service is temporarily unavailable.")

        return {
            **location,
            "temperature_celsius": temperature,
            "weather_code": int(weather_code),
            "timezone": timezone,
            "observed_at": observed_at,
        }

    @staticmethod
    def _finite_float(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None


def create_weather_server(service: WeatherService | None = None) -> FastMCP:
    mcp = FastMCP(name="Weather", mask_error_details=True)
    weather_service = service or WeatherService()

    @mcp.tool
    async def get_current_weather(city: str) -> dict[str, object]:
        """Return the current weather for a city after resolving it to coordinates."""
        return await weather_service.get_current_weather(city)

    return mcp


mcp = create_weather_server()


if __name__ == "__main__":
    mcp.run()
