"""
Panel configuration. All values from environment (.env, gitignored).

Same philosophy as node-agent/src/core/config.py: required secrets
have no default and the app refuses to start rather than silently
running with something insecure.
"""

import logging
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Database ---
    DATABASE_URL: str = Field(
        ...,
        description="postgresql+asyncpg://user:pass@host:5432/dbname "
        "for production, or sqlite+aiosqlite:///./test.db for local "
        "dev/tests.",
    )

    # --- Redis ---
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    PEER_CONFIG_TTL_SECONDS: int = Field(
        default=172800, description="48h -- see docs/architecture.md"
    )

    # --- Auth ---
    JWT_SECRET: str = Field(
        ..., description="Generate with: openssl rand -hex 32"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 12  # 12h admin session

    # --- Monitoring ---
    MONITORING_INTERVAL_SECONDS: int = 180
    HANDSHAKE_STALE_AFTER_SECONDS: int = 300
    HANDSHAKE_DOWN_AFTER_SECONDS: int = 900
    AGENT_REQUEST_TIMEOUT_SECONDS: int = 10

    # --- App ---
    LOG_LEVEL: str = "INFO"
    APP_ENV: str = "production"

    @field_validator("JWT_SECRET")
    @classmethod
    def secret_must_be_reasonably_long(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET looks too short (expected 32+ chars from "
                "`openssl rand -hex 32`). Refusing to start."
            )
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def log_level_must_be_valid(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}, got {v!r}")
        return v_upper


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    logger.debug(
        "Panel settings loaded: db_host=%s redis=%s env=%s log_level=%s "
        "(secrets redacted)",
        settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "sqlite",
        settings.REDIS_URL,
        settings.APP_ENV,
        settings.LOG_LEVEL,
    )
    return settings
