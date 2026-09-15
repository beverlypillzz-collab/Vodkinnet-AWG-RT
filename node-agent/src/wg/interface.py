"""
Reading and managing the awg0 interface state inside the AWG container.

`awg show <iface> dump` output format (tab-separated), per the
WireGuard/AmneziaWG convention:

  Line 1 (interface): private_key  public_key  listen_port  fwmark
  Line 2+ (per peer):  public_key  preshared_key  endpoint  allowed_ips
                       latest_handshake  transfer_rx  transfer_tx
                       persistent_keepalive

We only ever parse this — the private key on line 1 is read here
in-process for the interface's own bookkeeping but is deliberately
dropped before returning (see InterfaceStatus below), never included
in any dict handed back to the API layer.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.core.config import get_settings
from src.docker_control.executor import AgentCommandError, run_awg_command

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PeerStatus:
    public_key: str
    endpoint: str | None
    allowed_ips: str
    last_handshake: datetime | None
    rx_bytes: int
    tx_bytes: int


@dataclass(frozen=True)
class InterfaceStatus:
    interface_up: bool
    public_key: str | None
    listen_port: int | None
    peers: list[PeerStatus] = field(default_factory=list)


def get_interface_status() -> InterfaceStatus:
    """
    Returns the current state of the AWG interface, or
    interface_up=False if the interface doesn't exist yet (e.g. before
    /server/init has ever been called on this node).
    """
    settings = get_settings()

    try:
        raw = run_awg_command(
            ["awg", "show", settings.AWG_INTERFACE, "dump"],
            redact_output=True,  # line 1 contains the server's own private key
        )
    except AgentCommandError as exc:
        logger.info(
            "Interface %s not up or not found (exit=%s) — reporting down",
            settings.AWG_INTERFACE,
            exc.exit_code,
        )
        return InterfaceStatus(interface_up=False, public_key=None, listen_port=None)

    lines = [line for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        logger.warning(
            "awg show dump returned empty output for %s", settings.AWG_INTERFACE
        )
        return InterfaceStatus(interface_up=False, public_key=None, listen_port=None)

    interface_fields = lines[0].split("\t")
    # interface_fields[0] is the private key — intentionally never read
    # into a variable we might accidentally return or log.
    public_key = interface_fields[1] if len(interface_fields) > 1 else None
    listen_port = (
        int(interface_fields[2])
        if len(interface_fields) > 2 and interface_fields[2].isdigit()
        else None
    )

    peers = [_parse_peer_line(line) for line in lines[1:]]

    logger.debug(
        "Interface %s up, %d peer(s)", settings.AWG_INTERFACE, len(peers)
    )
    return InterfaceStatus(
        interface_up=True,
        public_key=public_key,
        listen_port=listen_port,
        peers=peers,
    )


def _parse_peer_line(line: str) -> PeerStatus:
    parts = line.split("\t")
    # public_key, preshared_key, endpoint, allowed_ips, latest_handshake,
    # rx, tx, keepalive
    public_key = parts[0]
    endpoint = parts[2] if len(parts) > 2 and parts[2] != "(none)" else None
    allowed_ips = parts[3] if len(parts) > 3 else ""
    handshake_epoch = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
    rx_bytes = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0
    tx_bytes = int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else 0

    last_handshake = (
        datetime.fromtimestamp(handshake_epoch, tz=timezone.utc)
        if handshake_epoch > 0
        else None
    )

    return PeerStatus(
        public_key=public_key,
        endpoint=endpoint,
        allowed_ips=allowed_ips,
        last_handshake=last_handshake,
        rx_bytes=rx_bytes,
        tx_bytes=tx_bytes,
    )


def get_own_private_key_for_persistence() -> str:
    """
    Returns the server's own private key for INTERNAL use only — to
    rebuild the on-disk config file after a peer change (see
    config_builder.persist_current_peers). This function must never be
    called from an API route handler directly; only from the
    server-management service layer that immediately feeds the result
    into persist_current_peers() and never returns it further up the
    call stack.

    Deliberately separate from get_interface_status(), whose whole
    point is to be safe to return from an API response.
    """
    settings = get_settings()
    raw = run_awg_command(
        ["awg", "show", settings.AWG_INTERFACE, "dump"],
        redact_output=True,
    )
    first_line = raw.strip().splitlines()[0]
    private_key = first_line.split("\t")[0]
    return private_key


def add_peer(
    public_key: str,
    allowed_ips: str,
) -> None:
    settings = get_settings()
    run_awg_command(
        [
            "awg",
            "set",
            settings.AWG_INTERFACE,
            "peer",
            public_key,
            "allowed-ips",
            allowed_ips,
        ]
    )
    logger.info(
        "Added peer %s with allowed-ips=%s to %s",
        public_key,
        allowed_ips,
        settings.AWG_INTERFACE,
    )


def remove_peer(public_key: str) -> None:
    settings = get_settings()
    run_awg_command(
        ["awg", "set", settings.AWG_INTERFACE, "peer", public_key, "remove"]
    )
    logger.info("Removed peer %s from %s", public_key, settings.AWG_INTERFACE)


def update_peer_allowed_ips(public_key: str, allowed_ips: str) -> None:
    settings = get_settings()
    run_awg_command(
        [
            "awg",
            "set",
            settings.AWG_INTERFACE,
            "peer",
            public_key,
            "allowed-ips",
            allowed_ips,
        ]
    )
    logger.info(
        "Updated peer %s allowed-ips=%s on %s",
        public_key,
        allowed_ips,
        settings.AWG_INTERFACE,
    )
