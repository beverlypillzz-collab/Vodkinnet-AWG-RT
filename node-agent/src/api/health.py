import logging

from fastapi import APIRouter

from src.docker_control.executor import container_is_running

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

AGENT_VERSION = "1.0.0"


@router.get("/health")
async def health():
    """
    Deliberately unauthenticated — this only confirms the agent
    process itself is alive and can see its AWG container. It leaks
    no sensitive information (no keys, no peer list), so requiring a
    token here would only complicate uptime monitoring for no security
    benefit.
    """
    awg_running = container_is_running()
    logger.debug("Health check: awg_container_running=%s", awg_running)
    return {
        "status": "ok",
        "agent_version": AGENT_VERSION,
        "awg_container_running": awg_running,
    }
