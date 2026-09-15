"""
Server-rendered pages. These are separate from /api/* — the API is
JSON for programmatic use and potential future automation, the web/*
routes render HTML pages (and HTMX partials) for the browser.

Auth here uses a cookie-based session rather than the Bearer JWT the
JSON API uses, since browsers handle cookies more naturally than
manually attaching Authorization headers to every navigation.
"""

import logging
import uuid

from fastapi import APIRouter, Cookie, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, decode_access_token, verify_password
from src.db.models import Admin
from src.db.session import get_db_session
from src.services import node_service, peer_service, router_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="src/web/templates")


async def get_current_admin_from_cookie(
    session: AsyncSession = Depends(get_db_session),
    session_token: str | None = Cookie(default=None),
) -> Admin | None:
    if not session_token:
        return None
    try:
        payload = decode_access_token(session_token)
    except Exception:
        return None
    return await session.get(Admin, uuid.UUID(payload["sub"]))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(select(Admin).where(Admin.username == username))
    admin = result.scalar_one_or_none()

    if admin is None or not verify_password(password, admin.password_hash):
        logger.warning("Failed web login attempt for username=%s", username)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Неверное имя пользователя или пароль"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_access_token(str(admin.id), admin.username)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        "session_token", token, httponly=True, samesite="lax", max_age=60 * 60 * 12
    )
    logger.info("Admin %s logged in via web UI", admin.username)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("session_token")
    return response


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    admin: Admin | None = Depends(get_current_admin_from_cookie),
):
    if admin is None:
        return RedirectResponse(url="/login")

    nodes = await node_service.list_nodes(session)
    routers = await router_service.list_routers(session)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "admin": admin,
            "nodes": nodes,
            "routers": routers,
        },
    )


@router.get("/nodes/{node_id}", response_class=HTMLResponse)
async def node_detail(
    request: Request,
    node_id: str,
    session: AsyncSession = Depends(get_db_session),
    admin: Admin | None = Depends(get_current_admin_from_cookie),
):
    if admin is None:
        return RedirectResponse(url="/login")

    node = await node_service.get_node(session, uuid.UUID(node_id))
    if node is None:
        return HTMLResponse("Node not found", status_code=404)

    peers = await peer_service.list_peers_for_node(session, node.id)

    return templates.TemplateResponse(
        request,
        "nodes/detail.html",
        {"admin": admin, "node": node, "peers": peers},
    )


@router.get("/routers/partial", response_class=HTMLResponse)
async def routers_table_partial(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    admin: Admin | None = Depends(get_current_admin_from_cookie),
):
    """
    HTMX polls this endpoint to refresh just the routers table body
    without a full page reload — see dashboard.html's hx-get.
    """
    if admin is None:
        return HTMLResponse("", status_code=401)

    routers = await router_service.list_routers(session)
    return templates.TemplateResponse(
        request, "partials/routers_table.html", {"routers": routers}
    )
