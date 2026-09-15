import pytest

pytestmark = pytest.mark.asyncio


async def test_create_and_list_router(app_client, auth_headers):
    create_resp = await app_client.post(
        "/api/routers",
        headers=auth_headers,
        json={
            "name": "VodkinR1_Router",
            "type": "openwrt",
            "model": "Cudy WBR3000AX",
            "remote_hub": "owrt-remote",
            "remote_hub_url": "https://example-hub.example.com/routers/1",
        },
    )
    assert create_resp.status_code == 201
    router = create_resp.json()
    assert router["name"] == "VodkinR1_Router"
    assert router["awg_link_status"] == "unknown"

    list_resp = await app_client.get("/api/routers", headers=auth_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_get_nonexistent_router_404(app_client, auth_headers):
    response = await app_client.get(
        "/api/routers/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert response.status_code == 404


async def test_update_router(app_client, auth_headers):
    create_resp = await app_client.post(
        "/api/routers",
        headers=auth_headers,
        json={"name": "OldName", "type": "keenetic"},
    )
    router_id = create_resp.json()["id"]

    update_resp = await app_client.patch(
        f"/api/routers/{router_id}",
        headers=auth_headers,
        json={"name": "NewName"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "NewName"
    assert update_resp.json()["type"] == "keenetic"  # unchanged fields survive


async def test_delete_router(app_client, auth_headers):
    create_resp = await app_client.post(
        "/api/routers",
        headers=auth_headers,
        json={"name": "ToDelete", "type": "openwrt"},
    )
    router_id = create_resp.json()["id"]

    delete_resp = await app_client.delete(f"/api/routers/{router_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    get_resp = await app_client.get(f"/api/routers/{router_id}", headers=auth_headers)
    assert get_resp.status_code == 404


async def test_invalid_router_type_rejected(app_client, auth_headers):
    response = await app_client.post(
        "/api/routers",
        headers=auth_headers,
        json={"name": "BadType", "type": "not-a-real-type"},
    )
    assert response.status_code == 422


async def test_empty_string_optional_fields_treated_as_none(app_client, auth_headers):
    """
    Regression guard: the web dashboard's create-router form submits
    an unselected <select> (remote_hub) and blank text inputs (model,
    remote_hub_url) as empty strings, not as absent fields — plain
    HTML has no other way to represent "not provided" for a <select>.
    Without RouterCreateRequest's blank-to-None validators, "" fails
    Literal-type validation outright and this endpoint 422s on every
    router created via the web form with the hub dropdown left blank.
    """
    response = await app_client.post(
        "/api/routers",
        headers=auth_headers,
        json={
            "name": "BlankFieldsRouter",
            "type": "openwrt",
            "model": "",
            "remote_hub": "",
            "remote_hub_url": "",
        },
    )
    assert response.status_code == 201
    router = response.json()
    assert router["model"] is None
    assert router["remote_hub"] is None
    assert router["remote_hub_url"] is None
