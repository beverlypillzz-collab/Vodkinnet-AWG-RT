"""
Shared API dependencies.

get_current_admin accepts EITHER:
  - a Bearer JWT in the Authorization header (used by /api/auth/login
    clients — external tooling, future CLI, etc.)
  - a session_token cookie (used by the browser-facing web/* routes,
    which share the same /api/* endpoints via HTMX form posts rather
    than duplicating create/delete logic in a second set of routes)

Both carry the same JWT payload format (see core/security.py) — the
only difference is where the token travels. This lets the HTMX forms
in the web UI submit straight to /api/peers etc. without needing a
separate cookie-auth-only copy of every route.
"""

import logging
import uuid

from fastapi import Cookie, Depends, HTTPException, Request, status
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import decode_access_token
from src.db.models import Admin
from src.db.session import get_db_session

logger = logging.getLogger(__name__)


async def get_current_admin(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    session_token: str | None = Cookie(default=None),
) -> Admin:
    token: str | None = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    elif session_token:
        token = session_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = decode_access_token(token)
    except PyJWTError as exc:
        logger.warning("Rejected request with invalid/expired token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    admin = await session.get(Admin, uuid.UUID(payload["sub"]))
    if admin is None:
        logger.warning("Token valid but admin_id=%s no longer exists", payload["sub"])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account no longer exists",
        )

    return admin
