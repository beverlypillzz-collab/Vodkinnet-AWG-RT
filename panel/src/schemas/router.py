import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RouterCreateRequest(BaseModel):
    name: str
    type: Literal["openwrt", "keenetic"]
    model: str | None = None
    firmware_version: str | None = None
    remote_hub: Literal["owrt-remote", "netcraze-remote"] | None = None
    remote_hub_url: str | None = None


class RouterUpdateRequest(BaseModel):
    name: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    remote_hub: Literal["owrt-remote", "netcraze-remote"] | None = None
    remote_hub_url: str | None = None


class RouterResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    model: str | None
    firmware_version: str | None
    remote_hub: str | None
    remote_hub_url: str | None
    awg_link_status: str
    last_handshake_at: datetime | None
    last_checked_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
