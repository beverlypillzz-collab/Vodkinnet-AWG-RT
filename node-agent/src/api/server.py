import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.auth import verify_agent_token
from src.core.config import get_settings
from src.docker_control.executor import AwgContainerUnavailable
from src.wg import config_builder
from src.wg.interface import get_interface_status
from src.wg.keygen import generate_keypair

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/server",
    tags=["server"],
    dependencies=[Depends(verify_agent_token)],
)


class AwgParams(BaseModel):
    """
    Direct mirror of AmneziaWG's obfuscation fields. All optional —
    omitted fields fall back to protocol defaults inside the config
    file (see config_builder.render_server_config).
    """

    Jc: int | None = Field(default=None, ge=1, le=128)
    Jmin: int | None = Field(default=None, ge=0)
    Jmax: int | None = Field(default=None, ge=0)
    S1: int | None = None
    S2: int | None = None
    H1: int | None = None
    H2: int | None = None
    H3: int | None = None
    H4: int | None = None

    def to_config_dict(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ServerInitRequest(BaseModel):
    listen_port: int
    awg_params: AwgParams = Field(default_factory=AwgParams)


class ServerInitResponse(BaseModel):
    public_key: str
    listen_port: int
    interface: str


class PeerStatusResponse(BaseModel):
    public_key: str
    endpoint: str | None
    allowed_ips: str
    last_handshake: str | None  # ISO 8601, or null if never
    rx_bytes: int
    tx_bytes: int


class ServerStatusResponse(BaseModel):
    interface_up: bool
    public_key: str | None
    listen_port: int | None
    peers: list[PeerStatusResponse]


@router.post("/init", response_model=ServerInitResponse)
async def init_server(payload: ServerInitRequest):
    """
    Idempotent-ish first-time setup: generates a server keypair if the
    interface isn't already up, writes the config file, and brings the
    interface up. If the interface is already up (agent restarted, or
    panel retried this call), returns the existing public key instead
    of generating a new one — regenerating here would silently break
    every already-connected client.
    """
    existing = get_interface_status()
    if existing.interface_up and existing.public_key:
        logger.info(
            "server/init called but interface already up "
            "(public_key=%s) — returning existing key, not regenerating",
            existing.public_key,
        )
        return ServerInitResponse(
            public_key=existing.public_key,
            listen_port=existing.listen_port or payload.listen_port,
            interface="awg0",
        )

    keypair = generate_keypair()

    rendered = config_builder.render_server_config(
        server_private_key=keypair.private_key,
        listen_port=payload.listen_port,
        awg_params=payload.awg_params.to_config_dict(),
        peers=[],
    )
    config_builder.write_server_config(rendered)

    try:
        config_builder.reload_interface()
    except Exception:
        # First-time bring-up: syncconf requires an existing interface,
        # so this is the expected path on a genuinely fresh node —
        # bring it up via awg-quick instead.
        logger.info(
            "syncconf failed on first init (expected for a fresh "
            "interface) — bringing up via awg-quick"
        )
        from src.docker_control.executor import run_awg_command

        run_awg_command(["awg-quick", "up", config_builder.CONFIG_PATH])

    logger.info(
        "Server initialised: public_key=%s listen_port=%s",
        keypair.public_key,
        payload.listen_port,
    )

    return ServerInitResponse(
        public_key=keypair.public_key,
        listen_port=payload.listen_port,
        interface="awg0",
    )


@router.get("/status", response_model=ServerStatusResponse)
async def server_status():
    try:
        current = get_interface_status()
    except AwgContainerUnavailable as exc:
        logger.warning("server/status: AWG container unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AWG container is not running on this node",
        ) from exc

    return ServerStatusResponse(
        interface_up=current.interface_up,
        public_key=current.public_key,
        listen_port=current.listen_port,
        peers=[
            PeerStatusResponse(
                public_key=p.public_key,
                endpoint=p.endpoint,
                allowed_ips=p.allowed_ips,
                last_handshake=(
                    p.last_handshake.isoformat() if p.last_handshake else None
                ),
                rx_bytes=p.rx_bytes,
                tx_bytes=p.tx_bytes,
            )
            for p in current.peers
        ],
    )
