import httpx
import pytest
from fastmcp.exceptions import ToolError

from app.tools.weather_server import WeatherService


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_weather_service_resolves_korean_city_and_returns_current_weather() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "nominatim.test":
            assert request.url.path == "/search"
            assert dict(request.url.params) == {
                "q": "서울",
                "format": "jsonv2",
                "limit": "2",
                "featureType": "city",
                "accept-language": "ko",
            }
            return httpx.Response(
                200,
                json=[
                    {
                        "display_name": "서울특별시, 대한민국",
                        "lat": "37.5666791",
                        "lon": "126.9782914",
                    }
                ],
            )

        assert request.url.host == "weather.test"
        assert request.url.path == "/v1/forecast"
        assert dict(request.url.params) == {
            "latitude": "37.5666791",
            "longitude": "126.9782914",
            "current": "temperature_2m,weather_code",
            "timezone": "auto",
        }
        return httpx.Response(
            200,
            json={
                "timezone": "Asia/Seoul",
                "current": {
                    "time": "2026-07-23T14:00",
                    "temperature_2m": 31.2,
                    "weather_code": 1,
                },
            },
        )

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        geocoder_base_url="https://nominatim.test",
        weather_base_url="https://weather.test",
        user_agent="my-ai-assistant-test/0.1",
    )

    weather = await service.get_current_weather(" 서울 ")

    assert weather == {
        "location": "서울특별시, 대한민국",
        "latitude": 37.5666791,
        "longitude": 126.9782914,
        "temperature_celsius": 31.2,
        "weather_code": 1,
        "timezone": "Asia/Seoul",
        "observed_at": "2026-07-23T14:00",
    }
    assert requests[0].headers["user-agent"] == "my-ai-assistant-test/0.1"


@pytest.mark.asyncio
async def test_weather_service_rejects_ambiguous_city_instead_of_guessing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "nominatim.test"
        assert dict(request.url.params)["limit"] == "2"
        return httpx.Response(
            200,
            json=[
                {
                    "display_name": "Springfield, Illinois, United States",
                    "lat": "39.7989763",
                    "lon": "-89.6443688",
                },
                {
                    "display_name": "Springfield, Massachusetts, United States",
                    "lat": "42.1014831",
                    "lon": "-72.589811",
                },
            ],
        )

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        geocoder_base_url="https://nominatim.test",
        weather_base_url="https://weather.test",
        user_agent="my-ai-assistant-test/0.1",
    )

    with pytest.raises(ToolError, match="more specific city"):
        await service.get_current_weather("Springfield")
