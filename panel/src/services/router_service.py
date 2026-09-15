import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Router
from src.schemas.router import RouterCreateRequest, RouterUpdateRequest

logger = logging.getLogger(__name__)


async def list_routers(session: AsyncSession) -> list[Router]:
    result = await session.execute(select(Router).order_by(Router.name))
    return list(result.scalars().all())


async def get_router(session: AsyncSession, router_id: uuid.UUID) -> Router | None:
    return await session.get(Router, router_id)


async def create_router(session: AsyncSession, payload: RouterCreateRequest) -> Router:
    router = Router(
        name=payload.name,
        type=payload.type,
        model=payload.model,
        firmware_version=payload.firmware_version,
        remote_hub=payload.remote_hub,
        remote_hub_url=payload.remote_hub_url,
        awg_link_status="unknown",
    )
    session.add(router)
    await session.commit()
    await session.refresh(router)
    logger.info("Created router %s (id=%s, type=%s)", router.name, router.id, router.type)
    return router


async def update_router(
    session: AsyncSession, router: Router, payload: RouterUpdateRequest
) -> Router:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(router, field, value)
    await session.commit()
    await session.refresh(router)
    logger.info("Updated router %s (id=%s)", router.name, router.id)
    return router


async def delete_router(session: AsyncSession, router: Router) -> None:
    logger.info("Deleting router %s (id=%s)", router.name, router.id)
    await session.delete(router)
    await session.commit()
