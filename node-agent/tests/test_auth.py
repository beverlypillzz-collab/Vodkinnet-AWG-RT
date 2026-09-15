import pytest
from fastapi import HTTPException

from src.core.auth import verify_agent_token
from src.core.config import get_settings


@pytest.mark.asyncio
async def test_valid_token_passes():
    settings = get_settings()
    await verify_agent_token(authorization=f"Bearer {settings.AGENT_TOKEN}")
    # No exception raised = success


@pytest.mark.asyncio
async def test_missing_bearer_prefix_rejected():
    with pytest.raises(HTTPException) as exc_info:
        await verify_agent_token(authorization="just-a-token-no-prefix")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_rejected():
    with pytest.raises(HTTPException) as exc_info:
        await verify_agent_token(authorization="Bearer totally-wrong-token")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_empty_authorization_rejected():
    with pytest.raises(HTTPException) as exc_info:
        await verify_agent_token(authorization="")
    assert exc_info.value.status_code == 401
