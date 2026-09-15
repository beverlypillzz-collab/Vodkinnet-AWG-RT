"""
AWG-RT panel entrypoint.

Local dev:
    uvicorn src.main:app --reload --port 8000
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api import auth, nodes, peers, routers, web
from src.core.config import get_settings
from src.core.logging_config import configure_logging
from src.services.monitoring import start_monitoring, stop_monitoring

_settings = get_settings()
configure_logging(_settings.LOG_LEVEL)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AWG-RT panel starting up (env=%s)", _settings.APP_ENV)
    if _settings.APP_ENV != "test":
        start_monitoring()
    yield
    stop_monitoring()
    logger.info("AWG-RT panel shutting down")


app = FastAPI(
    title="Vodkinnet AWG-RT — panel",
    description="Management panel for AmneziaWG nodes and the OpenWrt/Keenetic router fleet.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="src/web/static"), name="static")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    start = time.monotonic()
    logger.info("[%s] --> %s %s", request_id, request.method, request.url.path)

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.monotonic() - start) * 1000
        logger.exception(
            "[%s] <-- %s %s FAILED after %.1fms",
            request_id, request.method, request.url.path, duration_ms,
        )
        raise

    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "[%s] <-- %s %s %d (%.1fms)",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An internal error occurred"},
    )


app.include_router(auth.router)
app.include_router(nodes.router)
app.include_router(routers.router)
app.include_router(peers.router)
app.include_router(web.router)
