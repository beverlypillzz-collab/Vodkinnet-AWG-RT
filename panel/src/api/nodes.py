import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_admin
from src.db.models import Admin, Node
from src.db.session import get_db_session
from src.schemas.node import NodeCreateRequest, NodeResponse
from src.services import agent_client, node_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/nodes",
    tags=["nodes"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=list[NodeResponse])
async def list_nodes(session: AsyncSession = Depends(get_db_session)):
    return await node_service.list_nodes(session)


@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    payload: NodeCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    admin: Admin = Depends(get_current_admin),
):
    node = await node_service.create_node(session, payload)
    logger.info("Admin %s created node %s", admin.username, node.name)
    return node


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(node_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    node = await node_service.get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.post("/{node_id}/retry-init", response_model=NodeResponse)
async def retry_init(node_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    """
    Manually retry /server/init for a node whose initial creation
    succeeded in the DB but failed to reach the agent (see
    node_service.create_node's error handling).
    """
    node: Node | None = await node_service.get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    try:
        result = await agent_client.init_server(node)
    except (agent_client.AgentUnreachableError, agent_client.AgentError) as exc:
        logger.warning("Retry init failed for node %s: %s", node.name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach node agent: {exc}",
        ) from exc

    node.public_key = result["public_key"]
    node.status = "online"
    await session.commit()
    await session.refresh(node)
    return node


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    admin: Admin = Depends(get_current_admin),
):
    node = await node_service.get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    logger.info("Admin %s deleting node %s", admin.username, node.name)
    await node_service.delete_node(session, node)
