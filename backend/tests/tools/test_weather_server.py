import os
from pathlib import Path
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
import httpx
import pytest
from fastmcp.exceptions import ToolError

from app.tools.weather_server import WeatherService, create_weather_server


pytestmark = pytest.mark.unit


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_weather_service_returns_current_conditions() -> None:
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
            "current": "temperature_2m,weather_code,precipitation",
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
                    "precipitation": 0,
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
        "temperature_celsius": 31.2,
        "condition": "대체로 맑음",
        "is_precipitating": False,
        "precipitation_millimeters": 0.0,
    }
    assert requests[0].headers["user-agent"] == "my-ai-assistant-test/0.1"


@pytest.mark.asyncio
async def test_weather_service_returns_daily_forecast_for_requested_days() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nominatim.test":
            return httpx.Response(
                200,
                json=[
                    {
                        "display_name": "부천시, 대한민국",
                        "lat": "37.5034",
                        "lon": "126.7660",
                    }
                ],
            )

        assert dict(request.url.params) == {
            "latitude": "37.5034",
            "longitude": "126.766",
            "daily": (
                "weather_code,temperature_2m_min,temperature_2m_max,"
                "precipitation_probability_max,precipitation_sum"
            ),
            "forecast_days": "2",
            "timezone": "auto",
        }
        return httpx.Response(
            200,
            json={
                "timezone": "Asia/Seoul",
                "daily": {
                    "time": ["2026-07-24", "2026-07-25"],
                    "weather_code": [3, 63],
                    "temperature_2m_min": [24.1, 23.5],
                    "temperature_2m_max": [31.8, 29.4],
                    "precipitation_probability_max": [20, 70],
                    "precipitation_sum": [0.0, 4.6],
                },
            },
        )

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        geocoder_base_url="https://nominatim.test",
        weather_base_url="https://weather.test",
        user_agent="my-ai-assistant-test/0.1",
    )

    forecast = await service.get_daily_forecast("부천", days=2)

    assert forecast == {
        "location": "부천시, 대한민국",
        "daily": [
            {
                "date": "2026-07-24",
                "condition": "흐림",
                "temperature_min_celsius": 24.1,
                "temperature_max_celsius": 31.8,
                "precipitation_probability_max_percent": 20.0,
                "precipitation_sum_millimeters": 0.0,
            },
            {
                "date": "2026-07-25",
                "condition": "비",
                "temperature_min_celsius": 23.5,
                "temperature_max_celsius": 29.4,
                "precipitation_probability_max_percent": 70.0,
                "precipitation_sum_millimeters": 4.6,
            },
        ],
    }


@pytest.mark.asyncio
async def test_weather_service_rejects_out_of_range_forecast_days() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("out-of-range days must be rejected before an upstream request")

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        user_agent="my-ai-assistant-test/0.1",
    )

    with pytest.raises(ToolError, match="between 1 and 7"):
        await service.get_daily_forecast("서울", days=8)


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


@pytest.mark.asyncio
async def test_weather_service_caches_resolved_city_coordinates() -> None:
    geocoding_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal geocoding_requests
        if request.url.host == "nominatim.test":
            geocoding_requests += 1
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
        return httpx.Response(
            200,
            json={
                "timezone": "Asia/Seoul",
                "current": {
                    "time": "2026-07-23T14:00",
                    "temperature_2m": 31.2,
                    "weather_code": 1,
                    "precipitation": 0,
                },
            },
        )

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        geocoder_base_url="https://nominatim.test",
        weather_base_url="https://weather.test",
        user_agent="my-ai-assistant-test/0.1",
    )

    await service.get_current_weather("서울")
    await service.get_current_weather(" 서울 ")

    assert geocoding_requests == 1


@pytest.mark.asyncio
async def test_weather_service_waits_before_a_second_uncached_geocoding_request() -> None:
    clock_values = iter([0.0, 0.25, 1.0])
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nominatim.test":
            city = dict(request.url.params)["q"]
            return httpx.Response(
                200,
                json=[
                    {
                        "display_name": f"{city}, 대한민국",
                        "lat": "37.5666791",
                        "lon": "126.9782914",
                    }
                ],
            )
        return httpx.Response(
            200,
            json={
                "timezone": "Asia/Seoul",
                "current": {
                    "time": "2026-07-23T14:00",
                    "temperature_2m": 31.2,
                    "weather_code": 1,
                    "precipitation": 0,
                },
            },
        )

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        geocoder_base_url="https://nominatim.test",
        weather_base_url="https://weather.test",
        user_agent="my-ai-assistant-test/0.1",
        clock=lambda: next(clock_values),
        sleep=record_sleep,
    )

    await service.get_current_weather("서울")
    await service.get_current_weather("부산")

    assert delays == [0.75]


@pytest.mark.asyncio
async def test_weather_service_rejects_blank_city_without_calling_upstream() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("blank city must be rejected before an upstream request")

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        user_agent="my-ai-assistant-test/0.1",
    )

    with pytest.raises(ToolError, match="city name is required"):
        await service.get_current_weather("  ")


@pytest.mark.asyncio
async def test_weather_service_reports_city_not_found_separately() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        geocoder_base_url="https://nominatim.test",
        user_agent="my-ai-assistant-test/0.1",
    )

    with pytest.raises(ToolError, match="No matching city"):
        await service.get_current_weather("없는도시")


@pytest.mark.asyncio
async def test_weather_service_masks_upstream_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timeout", request=request)

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        geocoder_base_url="https://nominatim.test",
        user_agent="my-ai-assistant-test/0.1",
    )

    with pytest.raises(ToolError, match="temporarily unavailable"):
        await service.get_current_weather("서울")


@pytest.mark.asyncio
async def test_weather_service_masks_upstream_http_status_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "maintenance"})

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        geocoder_base_url="https://nominatim.test",
        user_agent="my-ai-assistant-test/0.1",
    )

    with pytest.raises(ToolError, match="temporarily unavailable"):
        await service.get_current_weather("서울")


@pytest.mark.asyncio
async def test_weather_service_masks_invalid_weather_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nominatim.test":
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
        return httpx.Response(200, json={"timezone": "Asia/Seoul"})

    service = WeatherService(
        transport=httpx.MockTransport(handler),
        geocoder_base_url="https://nominatim.test",
        weather_base_url="https://weather.test",
        user_agent="my-ai-assistant-test/0.1",
    )

    with pytest.raises(ToolError, match="temporarily unavailable"):
        await service.get_current_weather("서울")


@pytest.mark.asyncio
async def test_weather_server_exposes_current_and_daily_weather_tools() -> None:
    server = create_weather_server(
        WeatherService(user_agent="my-ai-assistant-test/0.1")
    )

    tools = await server.list_tools()

    assert [tool.name for tool in tools] == [
        "get_current_weather",
        "get_daily_forecast",
    ]


@pytest.mark.asyncio
async def test_weather_server_initializes_over_stdio() -> None:
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "app.tools.weather_server"],
        cwd=str(PROJECT_ROOT),
        env={
            **os.environ,
            "NOMINATIM_USER_AGENT": "my-ai-assistant-test/0.1",
        },
    )

    async with Client(transport, init_timeout=5) as client:
        tools = await client.list_tools()

    assert [tool.name for tool in tools] == [
        "get_current_weather",
        "get_daily_forecast",
    ]
