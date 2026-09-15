import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.schemas.node import AwgParamsSchema


class PeerCreateRequest(BaseModel):
    node_id: uuid.UUID
    router_id: uuid.UUID | None = None
    allowed_ips: str
    awg_overrides: AwgParamsSchema = AwgParamsSchema()


class PeerResponse(BaseModel):
    id: uuid.UUID
    node_id: uuid.UUID
    router_id: uuid.UUID | None
    public_key: str
    allowed_ips: str
    last_handshake_at: datetime | None
    rx_bytes: int
    tx_bytes: int
    revoked_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PeerCreatedResponse(PeerResponse):
    """
    Returned ONLY at creation time. config_file contains the client's
    private key — the panel does not persist this response body
    anywhere except the short-TTL Redis cache; see
    db/redis_client.py and docs/architecture.md.
    """

    config_file: str
