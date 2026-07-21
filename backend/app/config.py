from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseSettings:
    url: str


def load_database_settings(env: Mapping[str, str]) -> DatabaseSettings:
    url = env.get("DATABASE_URL")
    if url is None:
        raise ValueError("DATABASE_URL must be set")

    return DatabaseSettings(url=url)


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
