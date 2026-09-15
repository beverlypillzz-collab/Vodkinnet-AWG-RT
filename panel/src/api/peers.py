import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_admin
from src.db.session import get_db_session
from src.schemas.peer import PeerCreatedResponse, PeerCreateRequest, PeerResponse
from src.services import agent_client, node_service, peer_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/peers",
    tags=["peers"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=list[PeerResponse])
async def list_peers(node_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    return await peer_service.list_peers_for_node(session, node_id)


@router.post("", response_model=PeerCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_peer(
    payload: PeerCreateRequest, session: AsyncSession = Depends(get_db_session)
):
    node = await node_service.get_node(session, payload.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    try:
        peer, config_file = await peer_service.create_peer(session, node, payload)
    except peer_service.NodeNotInitialisedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (agent_client.AgentUnreachableError, agent_client.AgentError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Node agent error: {exc}",
        ) from exc

    return PeerCreatedResponse(
        **PeerResponse.model_validate(peer).model_dump(),
        config_file=config_file,
    )


@router.get("/{peer_id}/config")
async def redownload_config(peer_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    """
    Re-fetch the config within its TTL window (see
    services/peer_service.get_peer_config). Returns 410 Gone if the
    TTL expired — the private key is gone from Redis by design, so
    there is nothing to return; the only remedy is issuing a new peer.
    """
    peer = await peer_service.get_peer(session, peer_id)
    if peer is None:
        raise HTTPException(status_code=404, detail="Peer not found")

    config = await peer_service.get_peer_config(peer_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "This config's cache window has expired. The private "
                "key was never stored permanently — create a new peer "
                "to issue a fresh one."
            ),
        )
    return {"config_file": config}


@router.delete("/{peer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_peer(peer_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    peer = await peer_service.get_peer(session, peer_id)
    if peer is None:
        raise HTTPException(status_code=404, detail="Peer not found")

    node = await node_service.get_node(session, peer.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node for this peer not found")

    try:
        await peer_service.revoke_peer(session, node, peer)
    except (agent_client.AgentUnreachableError, agent_client.AgentError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Node agent error: {exc}",
        ) from exc
