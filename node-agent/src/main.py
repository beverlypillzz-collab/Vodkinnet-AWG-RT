"""
node-agent entrypoint.

Run locally for development:
    uvicorn src.main:app --reload --port 8181

In production this runs inside its own container, separate from the
amnezia-awg2 container, talking to it only via the Docker socket
(see docker_control/executor.py) — never sharing a container with it.
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api import health, peers, server
from src.core.config import get_settings
from src.core.logging_config import configure_logging

# Configure logging before anything else logs a line, including
# get_settings() itself.
_settings_for_logging_bootstrap = get_settings()
configure_logging(_settings_for_logging_bootstrap.LOG_LEVEL)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "node-agent starting up: container=%s interface=%s listen=%s:%s",
        settings.AWG_CONTAINER_NAME,
        settings.AWG_INTERFACE,
        settings.LISTEN_HOST,
        settings.LISTEN_PORT,
    )
    yield
    logger.info("node-agent shutting down")


app = FastAPI(
    title="Vodkinnet AWG-RT — node-agent",
    description=(
        "Internal API used by the AWG-RT panel to manage a single "
        "AmneziaWG node. Not intended to be exposed beyond the panel's "
        "IP — see README.md for network setup."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Every request gets a short correlation id so a single request's
    log lines can be grepped together — useful when debugging a
    failed peer creation that touches config, docker exec, and the
    live interface across multiple modules.
    """
    request_id = uuid.uuid4().hex[:8]
    start = time.monotonic()

    logger.info(
        "[%s] --> %s %s", request_id, request.method, request.url.path
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.monotonic() - start) * 1000
        logger.exception(
            "[%s] <-- %s %s FAILED after %.1fms",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "[%s] <-- %s %s %d (%.1fms)",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all so an unexpected error (e.g. Docker socket unreachable)
    returns a clean 500 with no stack trace leaked to the panel, while
    the full traceback still goes to our own logs via the middleware's
    logger.exception() above (this handler runs after that log call).
    """
    logger.error("Unhandled exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An internal error occurred"},
    )


app.include_router(health.router)
app.include_router(server.router)
app.include_router(peers.router)
