"""
Background monitoring loop.

Every MONITORING_INTERVAL_SECONDS (default 180s / 3min):
  for each node:
    - call /server/status
    - unreachable -> node.status = 'offline', all its routers ->
      awg_link_status = 'unknown' (we genuinely don't know, the node
      that would tell us is down)
    - reachable -> node.status = 'online', update each peer's
      last_handshake_at / rx_bytes / tx_bytes from the response, then
      derive the linked router's awg_link_status:
        < HANDSHAKE_STALE_AFTER_SECONDS (5min)  -> 'up'
        < HANDSHAKE_DOWN_AFTER_SECONDS (15min)  -> 'stale'
        else, or peer missing from response      -> 'down'

This runs as a plain asyncio background task started at app startup
(see main.py) rather than pulling in APScheduler/Celery — the poll
interval is coarse enough (minutes, not seconds) that a bare
`while True: await asyncio.sleep(...)` loop is simpler to reason about
and debug than an external scheduler, for a fleet this size.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from src.core.config import get_settings
from src.db.models import Node, Peer, Router
from src.db.session import db_session_context
from src.services import agent_client

logger = logging.getLogger(__name__)

_monitoring_task: asyncio.Task | None = None


def _handshake_status(
    last_handshake_iso: str | None, now: datetime, settings
) -> str:
    if not last_handshake_iso:
        return "down"
    last_handshake = datetime.fromisoformat(last_handshake_iso)
    if last_handshake.tzinfo is None:
        last_handshake = last_handshake.replace(tzinfo=timezone.utc)
    age_seconds = (now - last_handshake).total_seconds()

    if age_seconds < settings.HANDSHAKE_STALE_AFTER_SECONDS:
        return "up"
    if age_seconds < settings.HANDSHAKE_DOWN_AFTER_SECONDS:
        return "stale"
    return "down"


async def poll_node_once(node: Node) -> None:
    """
    Polls a single node and applies all resulting DB updates in one
    session/commit. Exposed separately from the loop so it can be
    called on-demand (e.g. a "refresh now" button in the UI) without
    waiting for the next scheduled tick.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)

    async with db_session_context() as session:
        # Re-fetch inside this session so we're not holding a
        # detached instance from a different session across an await.
        db_node = await session.get(Node, node.id)
        if db_node is None:
            logger.warning("Node %s disappeared during poll, skipping", node.id)
            return

        try:
            status_response = await agent_client.get_server_status(db_node)
        except (agent_client.AgentUnreachableError, agent_client.AgentError) as exc:
            logger.warning(
                "Node %s unreachable during poll (%s) — marking offline",
                db_node.name,
                exc,
            )
            db_node.status = "offline"

            result = await session.execute(
                select(Router)
                .join(Peer, Peer.router_id == Router.id)
                .where(Peer.node_id == db_node.id, Peer.revoked_at.is_(None))
            )
            for router in result.scalars().all():
                router.awg_link_status = "unknown"
                router.last_checked_at = now

            await session.commit()
            return

        db_node.status = "online" if status_response.get("interface_up") else "offline"
        db_node.last_seen_at = now

        peers_by_pubkey = {p["public_key"]: p for p in status_response.get("peers", [])}

        result = await session.execute(
            select(Peer).where(Peer.node_id == db_node.id, Peer.revoked_at.is_(None))
        )
        db_peers = list(result.scalars().all())

        for peer in db_peers:
            agent_peer = peers_by_pubkey.get(peer.public_key)

            if agent_peer is None:
                logger.debug(
                    "Peer %s not present in agent response for node %s",
                    peer.public_key,
                    db_node.name,
                )
                new_status = "down"
            else:
                peer.rx_bytes = agent_peer.get("rx_bytes", 0)
                peer.tx_bytes = agent_peer.get("tx_bytes", 0)
                if agent_peer.get("last_handshake"):
                    peer.last_handshake_at = datetime.fromisoformat(
                        agent_peer["last_handshake"]
                    )
                new_status = _handshake_status(
                    agent_peer.get("last_handshake"), now, settings
                )

            if peer.router_id:
                router = await session.get(Router, peer.router_id)
                if router:
                    router.awg_link_status = new_status
                    router.last_handshake_at = peer.last_handshake_at
                    router.last_checked_at = now

        await session.commit()
        logger.debug(
            "Polled node %s: status=%s, %d peer(s) checked",
            db_node.name,
            db_node.status,
            len(db_peers),
        )


async def poll_all_nodes_once() -> None:
    async with db_session_context() as session:
        result = await session.execute(select(Node))
        nodes = list(result.scalars().all())

    logger.info("Monitoring tick: polling %d node(s)", len(nodes))
    for node in nodes:
        try:
            await poll_node_once(node)
        except Exception:
            # One node's failure must never kill the whole loop —
            # log it fully and move on to the next node.
            logger.exception("Unexpected error polling node %s", node.name)


async def _monitoring_loop() -> None:
    settings = get_settings()
    logger.info(
        "Monitoring loop starting, interval=%ds", settings.MONITORING_INTERVAL_SECONDS
    )
    while True:
        try:
            await poll_all_nodes_once()
        except Exception:
            logger.exception("Monitoring tick failed unexpectedly")
        await asyncio.sleep(settings.MONITORING_INTERVAL_SECONDS)


def start_monitoring() -> None:
    global _monitoring_task
    if _monitoring_task is None or _monitoring_task.done():
        _monitoring_task = asyncio.create_task(_monitoring_loop())
        logger.info("Monitoring background task started")


def stop_monitoring() -> None:
    global _monitoring_task
    if _monitoring_task is not None:
        _monitoring_task.cancel()
        logger.info("Monitoring background task stopped")
