import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=(settings.LOG_LEVEL == "DEBUG" and settings.APP_ENV != "test"),
            pool_pre_ping=True,
        )
        logger.debug("Database engine created")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_db_session():
    """FastAPI dependency — yields a session, always closes it."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


@asynccontextmanager
async def db_session_context():
    """
    Non-FastAPI-dependency version for use in background tasks (the
    monitoring loop) where there's no request to hang a Depends() off.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
