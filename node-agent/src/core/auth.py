"""
Bearer token authentication for the panel -> agent API.

Every route except /health requires this. Uses secrets.compare_digest
to avoid timing-attack leakage of the token, even though the agent
port should already be firewalled to the panel's IP only — defense in
depth costs nothing here.
"""

import logging
import secrets

from fastapi import Header, HTTPException, status

from src.core.config import get_settings

logger = logging.getLogger(__name__)


async def verify_agent_token(authorization: str = Header(default="")) -> None:
    settings = get_settings()

    if not authorization.startswith("Bearer "):
        logger.warning(
            "Rejected request with malformed Authorization header "
            "(missing 'Bearer ' prefix)"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    presented_token = authorization.removeprefix("Bearer ").strip()

    if not secrets.compare_digest(presented_token, settings.AGENT_TOKEN):
        # Never log the presented token, even a fragment of it — if a
        # typo'd real token ends up in logs, that's still a leak.
        logger.warning("Rejected request with invalid bearer token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    logger.debug("Request authenticated successfully")
