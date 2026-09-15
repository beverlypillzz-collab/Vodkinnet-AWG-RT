"""
Peer creation/deletion, orchestrating the agent call + DB write +
Redis cache, per the security model in docs/architecture.md:

  - private key: returned to the caller of create_peer() ONCE, cached
    in Redis with a TTL, NEVER written to a Peer row in Postgres.
  - public key + metadata: written to the Peer row, kept indefinitely
    (soft-deleted via revoked_at, not hard-deleted, for audit history).
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import redis_client
from src.db.models import Node, Peer
from src.schemas.peer import PeerCreateRequest
from src.services import agent_client

logger = logging.getLogger(__name__)


class NodeNotInitialisedError(Exception):
    pass


async def list_peers_for_node(session: AsyncSession, node_id: uuid.UUID) -> list[Peer]:
    result = await session.execute(
        select(Peer).where(Peer.node_id == node_id, Peer.revoked_at.is_(None))
    )
    return list(result.scalars().all())


async def get_peer(session: AsyncSession, peer_id: uuid.UUID) -> Peer | None:
    return await session.get(Peer, peer_id)


async def create_peer(
    session: AsyncSession, node: Node, payload: PeerCreateRequest
) -> tuple[Peer, str]:
    """
    Returns (peer_row, config_file). config_file is ephemeral — the
    caller (API route) hands it to the admin in the HTTP response and
    it also gets cached in Redis by this function, but it is
    deliberately not part of what gets returned from any future GET
    on this peer.
    """
    if not node.public_key:
        raise NodeNotInitialisedError(
            f"Node {node.name} has no public key yet — run server/init first"
        )

    awg_overrides = payload.awg_overrides.model_dump(exclude_none=True)
    result = await agent_client.create_peer(node, payload.allowed_ips, awg_overrides)

    config_file = result["config_file"]
    # Substitute the real endpoint if the agent left a placeholder
    # (see node-agent/src/api/peers.py) — the panel is the
    # authoritative source for a node's externally reachable hostname.
    config_file = config_file.replace(
        "__NEEDS_PANEL_SUBSTITUTION__", node.hostname
    )

    peer = Peer(
        node_id=node.id,
        router_id=payload.router_id,
        public_key=result["public_key"],
        allowed_ips=payload.allowed_ips,
        awg_overrides=awg_overrides or None,
    )
    session.add(peer)
    await session.commit()
    await session.refresh(peer)

    await redis_client.cache_peer_config(str(peer.id), config_file)

    logger.info(
        "Created peer id=%s public_key=%s on node=%s router_id=%s "
        "(private key handed to caller + cached in Redis, not persisted to Postgres)",
        peer.id,
        peer.public_key,
        node.name,
        payload.router_id,
    )

    return peer, config_file


async def get_peer_config(peer_id: uuid.UUID) -> str | None:
    """
    Re-fetch a previously issued config within the TTL window. Returns
    None if the TTL has expired or it was never cached — callers
    should tell the admin the config must be regenerated (which means
    creating a brand new peer, since the private key itself is gone).
    """
    return await redis_client.get_cached_peer_config(str(peer_id))


async def revoke_peer(session: AsyncSession, node: Node, peer: Peer) -> None:
    await agent_client.delete_peer(node, peer.public_key)
    peer.revoked_at = peer.revoked_at or datetime.now(timezone.utc)
    await session.commit()
    await redis_client.delete_cached_peer_config(str(peer.id))
    logger.info("Revoked peer id=%s public_key=%s", peer.id, peer.public_key)
