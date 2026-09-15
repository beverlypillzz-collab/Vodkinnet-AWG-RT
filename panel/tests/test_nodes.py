import pytest

pytestmark = pytest.mark.asyncio


async def test_create_node_agent_unreachable_degrades_gracefully(app_client, auth_headers):
    """
    Regression guard for the exact scenario tested manually during
    development: creating a node whose agent can't be reached must
    still succeed at the DB level (status='unknown', public_key=None)
    rather than raising a 500. See services/node_service.create_node.
    """
    response = await app_client.post(
        "/api/nodes",
        headers=auth_headers,
        json={
            "name": "unreachable-node",
            "hostname": "127.0.0.1",
            "agent_port": 1,  # nothing listens here
            "agent_token": "x" * 32,
            "listen_port": 55632,
            "awg_params": {"Jc": 4, "Jmin": 40, "Jmax": 70},
        },
    )
    assert response.status_code == 201
    node = response.json()
    assert node["status"] == "unknown"
    assert node["public_key"] is None


async def test_get_nonexistent_node_404(app_client, auth_headers):
    response = await app_client.get(
        "/api/nodes/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert response.status_code == 404


async def test_list_nodes_empty_initially(app_client, auth_headers):
    response = await app_client.get("/api/nodes", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []
