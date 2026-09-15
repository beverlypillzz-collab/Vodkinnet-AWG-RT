"""
Wraps every call from the panel to a node-agent. All timeouts and
retry logic live here so a single flaky node can't hang the
monitoring loop or an admin's request indefinitely.
"""

import logging

import httpx

from src.core.config import get_settings
from src.db.models import Node

logger = logging.getLogger(__name__)


class AgentUnreachableError(Exception):
    """Raised when a node-agent can't be reached at all (network/timeout)."""


class AgentError(Exception):
    """Raised when a node-agent responds with a non-2xx status."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Agent returned {status_code}: {detail}")


def _base_url(node: Node) -> str:
    return f"http://{node.hostname}:{node.agent_port}"


def _headers(node: Node) -> dict:
    return {"Authorization": f"Bearer {node.agent_token}"}


async def check_health(node: Node) -> dict:
    settings = get_settings()
    url = f"{_base_url(node)}/health"
    logger.debug("Checking health of node %s at %s", node.name, url)
    try:
        async with httpx.AsyncClient(timeout=settings.AGENT_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as exc:
        logger.warning("Node %s unreachable: %s", node.name, exc)
        raise AgentUnreachableError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Node %s /health returned %s", node.name, exc.response.status_code
        )
        raise AgentError(exc.response.status_code, exc.response.text) from exc


async def init_server(node: Node) -> dict:
    settings = get_settings()
    url = f"{_base_url(node)}/server/init"
    payload = {"listen_port": node.listen_port, "awg_params": node.awg_params}
    logger.info("Initialising server on node %s", node.name)
    try:
        async with httpx.AsyncClient(timeout=settings.AGENT_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=_headers(node))
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as exc:
        raise AgentUnreachableError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise AgentError(exc.response.status_code, exc.response.text) from exc


async def get_server_status(node: Node) -> dict:
    settings = get_settings()
    url = f"{_base_url(node)}/server/status"
    try:
        async with httpx.AsyncClient(timeout=settings.AGENT_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=_headers(node))
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as exc:
        logger.warning("Node %s /server/status unreachable: %s", node.name, exc)
        raise AgentUnreachableError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Node %s /server/status returned %s", node.name, exc.response.status_code
        )
        raise AgentError(exc.response.status_code, exc.response.text) from exc


async def create_peer(node: Node, allowed_ips: str, awg_overrides: dict) -> dict:
    settings = get_settings()
    url = f"{_base_url(node)}/peers"
    payload = {"allowed_ips": allowed_ips, "awg_overrides": awg_overrides}
    logger.info("Creating peer on node %s, allowed_ips=%s", node.name, allowed_ips)
    try:
        async with httpx.AsyncClient(timeout=settings.AGENT_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=_headers(node))
            response.raise_for_status()
            result = response.json()
            logger.info(
                "Peer created on node %s, public_key=%s (private key not logged)",
                node.name,
                result.get("public_key"),
            )
            return result
    except httpx.RequestError as exc:
        raise AgentUnreachableError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise AgentError(exc.response.status_code, exc.response.text) from exc


async def delete_peer(node: Node, public_key: str) -> None:
    settings = get_settings()
    url = f"{_base_url(node)}/peers/{public_key}"
    logger.info("Deleting peer %s from node %s", public_key, node.name)
    try:
        async with httpx.AsyncClient(timeout=settings.AGENT_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.delete(url, headers=_headers(node))
            response.raise_for_status()
    except httpx.RequestError as exc:
        raise AgentUnreachableError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise AgentError(exc.response.status_code, exc.response.text) from exc


async def update_peer(node: Node, public_key: str, allowed_ips: str) -> None:
    settings = get_settings()
    url = f"{_base_url(node)}/peers/{public_key}"
    payload = {"allowed_ips": allowed_ips}
    logger.info("Updating peer %s on node %s", public_key, node.name)
    try:
        async with httpx.AsyncClient(timeout=settings.AGENT_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.patch(url, json=payload, headers=_headers(node))
            response.raise_for_status()
    except httpx.RequestError as exc:
        raise AgentUnreachableError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise AgentError(exc.response.status_code, exc.response.text) from exc
