import asyncio
import math
import os
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from time import monotonic
from typing import TypedDict

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from app.config import load_weather_settings

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
OPEN_METEO_BASE_URL = "https://api.open-meteo.com"
WEATHER_CONDITIONS = {
    0: "맑음",
    1: "대체로 맑음",
    2: "구름 조금",
    3: "흐림",
    45: "안개",
    48: "안개",
    51: "이슬비",
    53: "이슬비",
    55: "이슬비",
    56: "어는 이슬비",
    57: "어는 이슬비",
    61: "비",
    63: "비",
    65: "비",
    66: "어는 비",
    67: "어는 비",
    71: "눈",
    73: "눈",
    75: "눈",
    77: "눈",
    80: "소나기",
    81: "소나기",
    82: "소나기",
    85: "눈 소나기",
    86: "눈 소나기",
    95: "뇌우",
    96: "우박을 동반한 뇌우",
    99: "우박을 동반한 뇌우",
}


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
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._transport = transport
        self._geocoder_base_url = geocoder_base_url.rstrip("/")
        self._weather_base_url = weather_base_url.rstrip("/")
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._clock = clock
        self._sleep = sleep
        self._location_cache: dict[str, ResolvedLocation] = {}
        self._geocoding_lock = asyncio.Lock()
        self._last_geocoding_at: float | None = None

    async def get_current_weather(self, city: str) -> dict[str, object]:
        normalized_city = unicodedata.normalize("NFKC", city).strip()
        if not normalized_city:
            raise ToolError("A city name is required.")

        try:
            async with httpx.AsyncClient(
                transport=self._transport, headers=self._headers
            ) as client:
                location = await self._resolve_location(client, normalized_city)

                weather_response = await client.get(
                    f"{self._weather_base_url}/v1/forecast",
                    params={
                        "latitude": location["latitude"],
                        "longitude": location["longitude"],
                        "current": "temperature_2m,weather_code",
                        "daily": (
                            "weather_code,temperature_2m_min,temperature_2m_max,"
                            "precipitation_probability_max,precipitation_sum"
                        ),
                        "forecast_days": 1,
                        "timezone": "auto",
                    },
                )
                weather_response.raise_for_status()
                return self._parse_weather(weather_response.json(), location)
        except ToolError:
            raise
        except (httpx.HTTPError, TypeError, ValueError, KeyError):
            raise ToolError("The weather service is temporarily unavailable.") from None

    async def _resolve_location(
        self, client: httpx.AsyncClient, normalized_city: str
    ) -> ResolvedLocation:
        cached_location = self._location_cache.get(normalized_city)
        if cached_location is not None:
            return cached_location

        async with self._geocoding_lock:
            cached_location = self._location_cache.get(normalized_city)
            if cached_location is not None:
                return cached_location

            if self._last_geocoding_at is not None:
                delay = 1.0 - (self._clock() - self._last_geocoding_at)
                if delay > 0:
                    await self._sleep(delay)

            try:
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
            finally:
                self._last_geocoding_at = self._clock()

            geocoding_response.raise_for_status()
            location = self._parse_location(geocoding_response.json())
            self._location_cache[normalized_city] = location
            return location

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
        daily = payload.get("daily")
        timezone = payload.get("timezone")
        if (
            not isinstance(current, Mapping)
            or not isinstance(daily, Mapping)
            or not isinstance(timezone, str)
        ):
            raise ToolError("The weather service is temporarily unavailable.")

        temperature = WeatherService._finite_float(current.get("temperature_2m"))
        weather_code = WeatherService._finite_float(current.get("weather_code"))
        observed_at = current.get("time")
        current_condition = WeatherService._weather_condition(weather_code)

        today_date = WeatherService._daily_string(daily, "time")
        today_weather_code = WeatherService._daily_number(daily, "weather_code")
        today_condition = WeatherService._weather_condition(today_weather_code)
        temperature_min = WeatherService._daily_number(daily, "temperature_2m_min")
        temperature_max = WeatherService._daily_number(daily, "temperature_2m_max")
        precipitation_probability = WeatherService._daily_number(
            daily, "precipitation_probability_max"
        )
        precipitation_sum = WeatherService._daily_number(daily, "precipitation_sum")

        if (
            temperature is None
            or current_condition is None
            or not isinstance(observed_at, str)
            or today_date is None
            or today_condition is None
            or temperature_min is None
            or temperature_max is None
            or precipitation_probability is None
            or precipitation_sum is None
        ):
            raise ToolError("The weather service is temporarily unavailable.")

        return {
            "location": location["location"],
            "timezone": timezone,
            "current": {
                "temperature_celsius": temperature,
                "condition": current_condition,
                "observed_at": observed_at,
            },
            "today": {
                "date": today_date,
                "condition": today_condition,
                "temperature_min_celsius": temperature_min,
                "temperature_max_celsius": temperature_max,
                "precipitation_probability_max_percent": precipitation_probability,
                "precipitation_sum_millimeters": precipitation_sum,
            },
        }

    @staticmethod
    def _daily_string(daily: Mapping[str, object], name: str) -> str | None:
        values = daily.get(name)
        if not isinstance(values, list) or not values or not isinstance(values[0], str):
            return None
        return values[0]

    @staticmethod
    def _daily_number(daily: Mapping[str, object], name: str) -> float | None:
        values = daily.get(name)
        if not isinstance(values, list) or not values:
            return None
        return WeatherService._finite_float(values[0])

    @staticmethod
    def _weather_condition(weather_code: float | None) -> str | None:
        if weather_code is None or not weather_code.is_integer():
            return None
        return WEATHER_CONDITIONS.get(int(weather_code))

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
        """Return current conditions and today's forecast for a city."""
        return await weather_service.get_current_weather(city)

    return mcp


def create_weather_server_from_environment(env: Mapping[str, str]) -> FastMCP:
    settings = load_weather_settings(env)
    return create_weather_server(
        WeatherService(
            geocoder_base_url=settings.geocoder_base_url,
            weather_base_url=settings.weather_base_url,
            user_agent=settings.geocoder_user_agent,
        )
    )


if __name__ == "__main__":
    create_weather_server_from_environment(os.environ).run()
