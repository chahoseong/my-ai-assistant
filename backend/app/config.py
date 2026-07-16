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
