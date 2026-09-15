import pytest

pytestmark = pytest.mark.asyncio


async def test_login_success(app_client, test_admin):
    response = await app_client.post(
        "/api/auth/login",
        json={"username": "testadmin", "password": "testpass123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


async def test_login_wrong_password(app_client, test_admin):
    response = await app_client.post(
        "/api/auth/login",
        json={"username": "testadmin", "password": "wrongpass"},
    )
    assert response.status_code == 401


async def test_login_nonexistent_user_same_error_as_wrong_password(app_client, test_admin):
    """
    Regression guard: the error message/status for 'no such user' and
    'wrong password' must be identical, or an attacker can enumerate
    valid usernames by comparing responses.
    """
    wrong_password_resp = await app_client.post(
        "/api/auth/login",
        json={"username": "testadmin", "password": "wrongpass"},
    )
    no_user_resp = await app_client.post(
        "/api/auth/login",
        json={"username": "definitely-does-not-exist", "password": "whatever"},
    )
    assert wrong_password_resp.status_code == no_user_resp.status_code
    assert wrong_password_resp.json() == no_user_resp.json()


async def test_protected_route_without_token_rejected(app_client):
    response = await app_client.get("/api/nodes")
    assert response.status_code in (401, 403)


async def test_protected_route_with_valid_token(app_client, auth_headers):
    response = await app_client.get("/api/nodes", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []
