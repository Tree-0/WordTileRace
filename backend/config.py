from __future__ import annotations

from dataclasses import dataclass
import os

from backend.game_store import DEFAULT_GAME_TTL_SECONDS


@dataclass(frozen=True)
class AppConfig:
    secret_key: str
    redis_url: str | None
    allowed_origins: str | list[str]
    game_ttl_seconds: int
    host: str
    port: int
    web_threads: int

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            secret_key=os.getenv("SECRET_KEY", "dev-secret-key"),
            redis_url=_empty_to_none(os.getenv("REDIS_URL")),
            allowed_origins=_parse_allowed_origins(
                os.getenv("ALLOWED_ORIGINS", "*")
            ),
            game_ttl_seconds=_parse_int(
                os.getenv("GAME_TTL_SECONDS"),
                DEFAULT_GAME_TTL_SECONDS,
            ),
            host=os.getenv("HOST", "127.0.0.1"),
            port=_parse_int(os.getenv("PORT"), 5050),
            web_threads=_parse_int(os.getenv("WEB_THREADS"), 20),
        )


def _empty_to_none(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def _parse_allowed_origins(value: str) -> str | list[str]:
    normalized = value.strip()
    if normalized == "*":
        return "*"
    return [
        origin.strip()
        for origin in normalized.split(",")
        if origin.strip()
    ]


def _parse_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)
