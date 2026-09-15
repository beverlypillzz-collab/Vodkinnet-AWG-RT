import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


def _blank_to_none(v):
    """
    HTML forms (and HTMX's json-enc extension in particular) submit an
    unselected <select> or an empty text <input> as an empty string,
    not as an absent field — there's no way for plain HTML to send
    "this field wasn't provided" other than omitting the input
    entirely, which a <select> with a blank placeholder option can't
    do. Without this, "" fails Literal-type validation outright (not
    a value in the Literal) and gets stored as a literal empty string
    for free-text optional fields instead of the None that was
    actually meant. Applied at the schema level so every caller (web
    form, curl, future API consumers) gets the same forgiving
    behaviour, not just this one HTML form.
    """
    return None if v == "" else v


class RouterCreateRequest(BaseModel):
    name: str
    type: Literal["openwrt", "keenetic"]
    model: str | None = None
    firmware_version: str | None = None
    remote_hub: Literal["owrt-remote", "netcraze-remote"] | None = None
    remote_hub_url: str | None = None

    _blank_model = field_validator("model", mode="before")(_blank_to_none)
    _blank_firmware = field_validator("firmware_version", mode="before")(_blank_to_none)
    _blank_remote_hub = field_validator("remote_hub", mode="before")(_blank_to_none)
    _blank_remote_hub_url = field_validator("remote_hub_url", mode="before")(_blank_to_none)


class RouterUpdateRequest(BaseModel):
    name: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    remote_hub: Literal["owrt-remote", "netcraze-remote"] | None = None
    remote_hub_url: str | None = None

    _blank_model = field_validator("model", mode="before")(_blank_to_none)
    _blank_firmware = field_validator("firmware_version", mode="before")(_blank_to_none)
    _blank_remote_hub = field_validator("remote_hub", mode="before")(_blank_to_none)
    _blank_remote_hub_url = field_validator("remote_hub_url", mode="before")(_blank_to_none)


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
