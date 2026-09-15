import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_admin
from src.db.session import get_db_session
from src.schemas.router import RouterCreateRequest, RouterResponse, RouterUpdateRequest
from src.services import router_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/routers",
    tags=["routers"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=list[RouterResponse])
async def list_routers(session: AsyncSession = Depends(get_db_session)):
    return await router_service.list_routers(session)


@router.post("", response_model=RouterResponse, status_code=status.HTTP_201_CREATED)
async def create_router(
    payload: RouterCreateRequest, session: AsyncSession = Depends(get_db_session)
):
    return await router_service.create_router(session, payload)


@router.get("/{router_id}", response_model=RouterResponse)
async def get_router(router_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    r = await router_service.get_router(session, router_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Router not found")
    return r


@router.patch("/{router_id}", response_model=RouterResponse)
async def update_router(
    router_id: uuid.UUID,
    payload: RouterUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    r = await router_service.get_router(session, router_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Router not found")
    return await router_service.update_router(session, r, payload)


@router.delete("/{router_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_router(
    router_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
):
    r = await router_service.get_router(session, router_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Router not found")
    await router_service.delete_router(session, r)
