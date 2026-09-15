import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 32)
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")  # separate DB index for tests
os.environ.setdefault("LOG_LEVEL", "DEBUG")

from src.db.models import Base, Admin  # noqa: E402
from src.core.security import hash_password  # noqa: E402


@pytest_asyncio.fixture
async def db_engine():
    # A fresh in-memory SQLite DB per test — StaticPool keeps it alive
    # across the multiple connections async SQLAlchemy opens.
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def app_client(db_engine, monkeypatch):
    """
    A real ASGI test client wired to the in-memory DB via dependency
    override, so route handlers run exactly as in production.
    """
    from src.main import app
    from src.db.session import get_db_session

    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db_session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_admin(db_session):
    admin = Admin(
        id=uuid.uuid4(),
        username="testadmin",
        password_hash=hash_password("testpass123"),
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def auth_headers(app_client, test_admin):
    response = await app_client.post(
        "/api/auth/login",
        json={"username": "testadmin", "password": "testpass123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
