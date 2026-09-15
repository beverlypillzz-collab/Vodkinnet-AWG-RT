"""
Redis access, used for exactly one thing: caching a finished client
.conf file for PEER_CONFIG_TTL_SECONDS (48h default) so an admin can
re-download it if they missed it the first time, WITHOUT persisting
private key material in Postgres. See docs/architecture.md.
"""

import logging

import redis.asyncio as redis

from src.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        logger.debug("Redis client created for %s", settings.REDIS_URL)
    return _redis_client


def _config_cache_key(peer_id: str) -> str:
    return f"config:{peer_id}"


async def cache_peer_config(peer_id: str, config_file: str) -> None:
    settings = get_settings()
    client = get_redis_client()
    await client.set(
        _config_cache_key(peer_id),
        config_file,
        ex=settings.PEER_CONFIG_TTL_SECONDS,
    )
    logger.info(
        "Cached config for peer_id=%s with TTL=%ds",
        peer_id,
        settings.PEER_CONFIG_TTL_SECONDS,
    )


async def get_cached_peer_config(peer_id: str) -> str | None:
    client = get_redis_client()
    value = await client.get(_config_cache_key(peer_id))
    logger.debug(
        "Config cache %s for peer_id=%s",
        "hit" if value else "miss",
        peer_id,
    )
    return value


async def delete_cached_peer_config(peer_id: str) -> None:
    client = get_redis_client()
    await client.delete(_config_cache_key(peer_id))
