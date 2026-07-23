from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class DatabaseSettings:
    url: str


def load_database_settings(env: Mapping[str, str]) -> DatabaseSettings:
    url = env.get("DATABASE_URL")
    if url is None:
        raise ValueError("DATABASE_URL must be set")

    return DatabaseSettings(url=url)


@dataclass(frozen=True)
class WeatherSettings:
    geocoder_user_agent: str
    geocoder_base_url: str
    weather_base_url: str


def load_weather_settings(env: Mapping[str, str]) -> WeatherSettings:
    geocoder_user_agent = env.get("NOMINATIM_USER_AGENT", "").strip()
    if not geocoder_user_agent:
        raise ValueError("NOMINATIM_USER_AGENT must be set")

    return WeatherSettings(
        geocoder_user_agent=geocoder_user_agent,
        geocoder_base_url=env.get(
            "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
        ),
        weather_base_url=env.get("OPEN_METEO_BASE_URL", "https://api.open-meteo.com"),
    )


@dataclass(frozen=True)
class OpggTftSettings:
    mcp_url: str | None
    cache_ttl_seconds: float


def load_opgg_tft_settings(env: Mapping[str, str]) -> OpggTftSettings:
    raw_ttl = env.get("OPGG_TFT_CACHE_TTL_SECONDS", "300")
    try:
        cache_ttl_seconds = float(raw_ttl)
    except ValueError:
        raise ValueError("OPGG_TFT_CACHE_TTL_SECONDS must be a positive number") from None
    if not isfinite(cache_ttl_seconds) or cache_ttl_seconds <= 0:
        raise ValueError("OPGG_TFT_CACHE_TTL_SECONDS must be a positive number")

    mcp_url = env.get("OPGG_MCP_URL", "").strip() or None
    return OpggTftSettings(
        mcp_url=mcp_url,
        cache_ttl_seconds=cache_ttl_seconds,
    )


@dataclass(frozen=True)
class AuthSettings:
    app_env: str
    cookie_secure: bool
    allowed_origins: frozenset[str]


def load_auth_settings(env: Mapping[str, str]) -> AuthSettings:
    app_env = env.get("APP_ENV", "local")
    cookie_secure = _parse_strict_boolean(
        env.get("SESSION_COOKIE_SECURE", "false"),
        variable_name="SESSION_COOKIE_SECURE",
    )
    allowed_origins = frozenset(
        origin.strip()
        for origin in env.get(
            "AUTH_ALLOWED_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if origin.strip()
    )

    if app_env != "local" and not cookie_secure:
        raise ValueError("SESSION_COOKIE_SECURE must be true outside local")

    return AuthSettings(
        app_env=app_env,
        cookie_secure=cookie_secure,
        allowed_origins=allowed_origins,
    )


def _parse_strict_boolean(value: str, *, variable_name: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{variable_name} must be either true or false")
