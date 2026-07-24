import asyncio
import math
import os
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from time import monotonic
from typing import Annotated, TypedDict

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

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
                        "current": "temperature_2m,weather_code,precipitation",
                        "timezone": "auto",
                    },
                )
                weather_response.raise_for_status()
                return self._parse_current_weather(weather_response.json(), location)
        except ToolError:
            raise
        except httpx.HTTPError, TypeError, ValueError, KeyError:
            raise ToolError("The weather service is temporarily unavailable.") from None

    async def get_daily_forecast(
        self, city: str, *, days: int = 1
    ) -> dict[str, object]:
        if not 1 <= days <= 7:
            raise ToolError("Forecast days must be between 1 and 7.")

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
                        "daily": (
                            "weather_code,temperature_2m_min,temperature_2m_max,"
                            "precipitation_probability_max,precipitation_sum"
                        ),
                        "forecast_days": days,
                        "timezone": "auto",
                    },
                )
                weather_response.raise_for_status()
                return self._parse_daily_forecast(
                    weather_response.json(), location, days
                )
        except ToolError:
            raise
        except httpx.HTTPError, TypeError, ValueError, KeyError:
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
            raise ToolError(
                "No matching city was found. Ask the user for a more specific city."
            )
        if len(payload) > 1:
            raise ToolError(
                "Multiple cities matched. Ask the user for a more specific city."
            )

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
    def _parse_current_weather(
        payload: object, location: ResolvedLocation
    ) -> dict[str, object]:
        if not isinstance(payload, Mapping):
            raise ToolError("The weather service is temporarily unavailable.")

        current = payload.get("current")
        if not isinstance(current, Mapping):
            raise ToolError("The weather service is temporarily unavailable.")

        temperature = WeatherService._finite_float(current.get("temperature_2m"))
        weather_code = WeatherService._finite_float(current.get("weather_code"))
        precipitation = WeatherService._finite_float(current.get("precipitation"))
        current_condition = WeatherService._weather_condition(weather_code)

        if temperature is None or current_condition is None or precipitation is None:
            raise ToolError("The weather service is temporarily unavailable.")

        return {
            "location": location["location"],
            "temperature_celsius": temperature,
            "condition": current_condition,
            "is_precipitating": precipitation > 0,
            "precipitation_millimeters": precipitation,
        }

    @staticmethod
    def _parse_daily_forecast(
        payload: object, location: ResolvedLocation, days: int
    ) -> dict[str, object]:
        if not isinstance(payload, Mapping):
            raise ToolError("The weather service is temporarily unavailable.")

        daily = payload.get("daily")
        if not isinstance(daily, Mapping):
            raise ToolError("The weather service is temporarily unavailable.")

        dates = WeatherService._daily_values(daily, "time", days)
        weather_codes = WeatherService._daily_values(daily, "weather_code", days)
        temperature_mins = WeatherService._daily_values(
            daily, "temperature_2m_min", days
        )
        temperature_maxes = WeatherService._daily_values(
            daily, "temperature_2m_max", days
        )
        precipitation_probabilities = WeatherService._daily_values(
            daily, "precipitation_probability_max", days
        )
        precipitation_sums = WeatherService._daily_values(
            daily, "precipitation_sum", days
        )
        if (
            dates is None
            or weather_codes is None
            or temperature_mins is None
            or temperature_maxes is None
            or precipitation_probabilities is None
            or precipitation_sums is None
        ):
            raise ToolError("The weather service is temporarily unavailable.")

        daily_records: list[dict[str, object]] = []
        for index in range(days):
            date = dates[index]
            condition = WeatherService._weather_condition(
                WeatherService._finite_float(weather_codes[index])
            )
            temperature_min = WeatherService._finite_float(temperature_mins[index])
            temperature_max = WeatherService._finite_float(temperature_maxes[index])
            precipitation_probability = WeatherService._finite_float(
                precipitation_probabilities[index]
            )
            precipitation_sum = WeatherService._finite_float(precipitation_sums[index])
            if (
                not isinstance(date, str)
                or condition is None
                or temperature_min is None
                or temperature_max is None
                or precipitation_probability is None
                or precipitation_sum is None
            ):
                raise ToolError("The weather service is temporarily unavailable.")

            daily_records.append(
                {
                    "date": date,
                    "condition": condition,
                    "temperature_min_celsius": temperature_min,
                    "temperature_max_celsius": temperature_max,
                    "precipitation_probability_max_percent": precipitation_probability,
                    "precipitation_sum_millimeters": precipitation_sum,
                }
            )

        return {"location": location["location"], "daily": daily_records}

    @staticmethod
    def _daily_values(
        daily: Mapping[str, object], name: str, days: int
    ) -> list[object] | None:
        values = daily.get(name)
        if not isinstance(values, list) or len(values) < days:
            return None
        return values

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
        except TypeError, ValueError:
            return None
        return result if math.isfinite(result) else None


def create_weather_server(service: WeatherService | None = None) -> FastMCP:
    mcp = FastMCP(name="Weather", mask_error_details=True)
    weather_service = service or WeatherService()

    @mcp.tool(
        meta={
            "my_ai_assistant": {
                "selection_message": "현재 날씨를 확인하고 있어요.",
            }
        }
    )
    async def get_current_weather(city: str) -> dict[str, object]:
        """Return the weather right now for a city, not a future forecast."""
        return await weather_service.get_current_weather(city)

    @mcp.tool(
        meta={
            "my_ai_assistant": {
                "selection_message": "일별 날씨 예보를 확인하고 있어요.",
            }
        }
    )
    async def get_daily_forecast(
        city: str, days: Annotated[int, Field(ge=1, le=7)] = 1
    ) -> dict[str, object]:
        """Return daily forecast records for today and the requested upcoming days."""
        return await weather_service.get_daily_forecast(city, days=days)

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
