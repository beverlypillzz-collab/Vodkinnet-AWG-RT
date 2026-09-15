"""
Password hashing and JWT session tokens for admin logins.

Passwords are hashed with bcrypt (via passlib). JWTs carry only the
admin's id and username — never a password, never a node/router
secret.
"""

import logging
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from src.core.config import get_settings

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(admin_id: str, username: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_EXPIRE_MINUTES
    )
    payload = {
        "sub": admin_id,
        "username": username,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    logger.debug("Issued access token for admin_id=%s, expires=%s", admin_id, expire)
    return token


def decode_access_token(token: str) -> dict:
    """
    Raises jwt.PyJWTError subclasses on invalid/expired tokens —
    callers (see api/dependencies.py) turn that into a 401.
    """
    settings = get_settings()
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
