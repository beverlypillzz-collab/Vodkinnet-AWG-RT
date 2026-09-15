"""
Configuration for node-agent.

All values are read from environment variables (populated via .env in
docker-compose, which is NOT committed — see .env.example at repo root
of node-agent/).

Nothing sensitive has a default value here. If AGENT_TOKEN or
AWG_CONTAINER_NAME is missing, the agent must refuse to start rather
than fall back to something guessable — a silent default is how
secrets leak in public repos.
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

    # --- Required, no defaults on purpose ---
    AGENT_TOKEN: str = Field(
        ...,
        description="Bearer token the panel must present. Generate with "
        "e.g. `openssl rand -hex 32`. Never log this value.",
    )
    AWG_CONTAINER_NAME: str = Field(
        ...,
        description="Name of the AmneziaWG docker container this agent "
        "is allowed to exec into. The agent must NEVER accept a "
        "container name from an inbound API request — it is fixed here "
        "at deploy time to prevent a compromised panel/token from "
        "reaching arbitrary containers on the host.",
    )

    # --- Network ---
    LISTEN_HOST: str = "127.0.0.1"
    LISTEN_PORT: int = 8181

    # --- WireGuard / AmneziaWG defaults ---
    AWG_INTERFACE: str = "awg0"
    AWG_LISTEN_PORT: int = Field(
        ..., description="UDP port the AmneziaWG server listens on."
    )
    AWG_PUBLIC_ENDPOINT: str | None = Field(
        default=None,
        description="Publicly reachable hostname/IP for this node, "
        "used as the Endpoint in generated client configs. If unset, "
        "client configs contain a placeholder the panel must "
        "substitute with nodes.hostname before handing the config to "
        "a user — see docs/api-contract.md.",
    )

    # --- Docker ---
    DOCKER_SOCKET: str = "unix:///var/run/docker.sock"
    DOCKER_EXEC_TIMEOUT_SECONDS: int = 10

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    @field_validator("AGENT_TOKEN")
    @classmethod
    def token_must_be_reasonably_long(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "AGENT_TOKEN looks too short to be a real secret "
                "(expected 32+ chars, e.g. from `openssl rand -hex 32`). "
                "Refusing to start with a weak token."
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
    """
    Cached settings instance. Raises pydantic.ValidationError at import
    time if required env vars are missing — fail fast and loud instead
    of limping along with an agent that has no token or no target
    container configured.
    """
    settings = Settings()
    logger.debug(
        "Settings loaded: container=%s interface=%s listen_port=%s "
        "awg_listen_port=%s log_level=%s (AGENT_TOKEN redacted)",
        settings.AWG_CONTAINER_NAME,
        settings.AWG_INTERFACE,
        settings.LISTEN_PORT,
        settings.AWG_LISTEN_PORT,
        settings.LOG_LEVEL,
    )
    return settings
