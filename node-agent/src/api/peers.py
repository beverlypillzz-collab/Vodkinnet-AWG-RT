import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.server import AwgParams
from src.core.auth import verify_agent_token
from src.core.config import get_settings
from src.docker_control.executor import AgentCommandError
from src.wg import config_builder
from src.wg.interface import (
    add_peer,
    get_own_private_key_for_persistence,
    remove_peer,
    update_peer_allowed_ips,
)
from src.wg.keygen import generate_keypair

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/peers",
    tags=["peers"],
    dependencies=[Depends(verify_agent_token)],
)


class CreatePeerRequest(BaseModel):
    allowed_ips: str = Field(
        ..., description="e.g. '10.8.0.7/32' — the client's tunnel address"
    )
    awg_overrides: AwgParams = Field(default_factory=AwgParams)


class CreatePeerResponse(BaseModel):
    public_key: str
    private_key: str
    config_file: str


class UpdatePeerRequest(BaseModel):
    allowed_ips: str | None = None
    awg_overrides: AwgParams | None = None


def _persist(awg_params_for_server: dict) -> None:
    """
    Shared helper: after any peer mutation, rewrite the on-disk config
    from current live state so a container restart doesn't lose it.
    Fetches the server's own private key internally — never returns
    it, never logs it (get_own_private_key_for_persistence already
    guarantees the latter).
    """
    settings = get_settings()
    private_key = get_own_private_key_for_persistence()
    config_builder.persist_current_peers(
        server_private_key=private_key,
        listen_port=settings.AWG_LISTEN_PORT,
        awg_params=awg_params_for_server,
    )


@router.post("", response_model=CreatePeerResponse, status_code=status.HTTP_201_CREATED)
async def create_peer(payload: CreatePeerRequest):
    settings = get_settings()

    keypair = generate_keypair()

    try:
        add_peer(public_key=keypair.public_key, allowed_ips=payload.allowed_ips)
    except AgentCommandError as exc:
        logger.error("Failed to add peer to live interface: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add peer to interface",
        ) from exc

    # Persist to disk so this survives a restart. Uses the server's
    # base awg_params, not the per-peer override — AmneziaWG applies
    # obfuscation params at the interface level, not per-peer, so
    # awg_overrides here is currently accepted for forward-compat with
    # a future protocol version but has no effect yet. See
    # docs/api-contract.md for the caveat.
    _persist(awg_params_for_server={})

    # We need the server's public key to build the client config.
    # Safe to call — get_interface_status() never returns the private key.
    from src.wg.interface import get_interface_status

    current = get_interface_status()
    if not current.public_key:
        logger.error("Cannot build client config: server has no public key yet")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server is not initialised (call /server/init first)",
        )

    if settings.AWG_PUBLIC_ENDPOINT:
        endpoint = f"{settings.AWG_PUBLIC_ENDPOINT}:{settings.AWG_LISTEN_PORT}"
    else:
        # Agent doesn't always know its own externally-reachable
        # address (NAT, multiple interfaces). If AWG_PUBLIC_ENDPOINT
        # isn't configured, we leave a clearly-marked placeholder and
        # let the panel substitute the node's known hostname — the
        # panel already has this in nodes.hostname, so it's the
        # authoritative source anyway.
        endpoint = f"__NEEDS_PANEL_SUBSTITUTION__:{settings.AWG_LISTEN_PORT}"
        logger.debug(
            "AWG_PUBLIC_ENDPOINT not set — panel must substitute the "
            "real endpoint before handing this config to a client"
        )

    client_config = config_builder.render_client_config(
        client_private_key=keypair.private_key,
        client_address=payload.allowed_ips,
        server_public_key=current.public_key,
        server_endpoint=endpoint,
        awg_params=payload.awg_overrides.to_config_dict(),
    )

    logger.info(
        "Created peer public_key=%s allowed_ips=%s (private key redacted)",
        keypair.public_key,
        payload.allowed_ips,
    )

    return CreatePeerResponse(
        public_key=keypair.public_key,
        private_key=keypair.private_key,
        config_file=client_config,
    )


@router.delete("/{public_key}")
async def delete_peer(public_key: str):
    try:
        remove_peer(public_key)
    except AgentCommandError as exc:
        logger.warning(
            "Attempted to remove peer %s: %s", public_key, exc
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Peer not found on this node",
        ) from exc

    _persist(awg_params_for_server={})
    logger.info("Removed peer %s", public_key)
    return {"removed": True}


@router.patch("/{public_key}")
async def patch_peer(public_key: str, payload: UpdatePeerRequest):
    if payload.allowed_ips is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="allowed_ips is currently the only mutable field",
        )

    try:
        update_peer_allowed_ips(public_key, payload.allowed_ips)
    except AgentCommandError as exc:
        logger.warning("Attempted to update peer %s: %s", public_key, exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Peer not found on this node",
        ) from exc

    _persist(awg_params_for_server={})
    logger.info("Updated peer %s allowed_ips=%s", public_key, payload.allowed_ips)
    return {"updated": True}
