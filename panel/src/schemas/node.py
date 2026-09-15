import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AwgParamsSchema(BaseModel):
    Jc: int | None = None
    Jmin: int | None = None
    Jmax: int | None = None
    S1: int | None = None
    S2: int | None = None
    H1: int | None = None
    H2: int | None = None
    H3: int | None = None
    H4: int | None = None


class NodeCreateRequest(BaseModel):
    name: str
    hostname: str
    agent_port: int = 8181
    agent_token: str = Field(..., min_length=32)
    listen_port: int
    awg_params: AwgParamsSchema = Field(default_factory=AwgParamsSchema)


class NodeResponse(BaseModel):
    id: uuid.UUID
    name: str
    hostname: str
    agent_port: int
    public_key: str | None
    listen_port: int
    awg_params: dict
    protocol_version: str
    status: str
    last_seen_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
