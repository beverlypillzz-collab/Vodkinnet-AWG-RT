import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Node
from src.schemas.node import NodeCreateRequest
from src.services import agent_client

logger = logging.getLogger(__name__)


async def list_nodes(session: AsyncSession) -> list[Node]:
    result = await session.execute(select(Node).order_by(Node.name))
    return list(result.scalars().all())


async def get_node(session: AsyncSession, node_id: uuid.UUID) -> Node | None:
    return await session.get(Node, node_id)


async def create_node(session: AsyncSession, payload: NodeCreateRequest) -> Node:
    """
    Creates the DB record, then calls the agent's /server/init to
    generate the server keypair. If the agent call fails, the node
    row is still saved (status stays 'unknown') so the admin can
    retry initialisation later without re-entering everything.
    """
    node = Node(
        name=payload.name,
        hostname=payload.hostname,
        agent_port=payload.agent_port,
        agent_token=payload.agent_token,
        listen_port=payload.listen_port,
        awg_params=payload.awg_params.model_dump(exclude_none=True),
        status="unknown",
    )
    session.add(node)
    await session.commit()
    await session.refresh(node)

    logger.info("Created node %s (id=%s), attempting server init", node.name, node.id)

    try:
        result = await agent_client.init_server(node)
        node.public_key = result["public_key"]
        node.status = "online"
        await session.commit()
        await session.refresh(node)
        logger.info("Node %s initialised, public_key=%s", node.name, node.public_key)
    except (agent_client.AgentUnreachableError, agent_client.AgentError) as exc:
        logger.warning(
            "Node %s created but server/init failed (%s) — status stays "
            "'unknown', admin can retry from the node detail page",
            node.name,
            exc,
        )

    return node


async def delete_node(session: AsyncSession, node: Node) -> None:
    logger.info("Deleting node %s (id=%s)", node.name, node.id)
    await session.delete(node)
    await session.commit()
