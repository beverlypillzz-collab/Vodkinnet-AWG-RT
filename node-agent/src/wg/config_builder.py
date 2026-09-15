"""
Builds and persists AmneziaWG config files.

Two distinct concerns live here:

1. Server-side persistence: `awg set ... peer ...` (see interface.py)
   changes the running interface immediately but does NOT survive a
   container restart on its own — AmneziaWG reads /opt/amnezia/awg/awg0.conf
   only at `awg-quick up` time. So every peer add/remove/update must
   also be reflected in that file, or a node reboot silently drops
   every client that was added after the container last started.

   We do this the simple, auditable way: keep the on-disk conf file as
   the single source of truth, rewrite it in full on every change, and
   apply the same change to the live interface via `awg set`. This
   avoids partial-update bugs from trying to patch [Peer] blocks with
   sed inside a running container.

2. Client-side config generation: building the .conf a client
   (router) will actually import. This text contains the client's
   PRIVATE key and must be treated as sensitive by every caller —
   see peers.py in the panel for where this gets a Redis TTL instead
   of a Postgres row.
"""

import logging

from src.core.config import get_settings
from src.docker_control.executor import run_awg_command
from src.wg.interface import get_interface_status

logger = logging.getLogger(__name__)

CONFIG_PATH = "/opt/amnezia/awg/awg0.conf"


def render_server_config(
    server_private_key: str,
    listen_port: int,
    awg_params: dict,
    peers: list[dict],
) -> str:
    """
    peers: list of {"public_key": str, "allowed_ips": str}

    awg_params keys map directly to AmneziaWG's [Interface]-level
    obfuscation fields (Jc, Jmin, Jmax, S1, S2, H1-H4). Only include
    keys that are actually set — AmneziaWG treats missing fields as
    "use protocol default", which for a 2.0 node means plain
    WireGuard-compatible behaviour on that field.
    """
    lines = [
        "[Interface]",
        f"PrivateKey = {server_private_key}",
        f"ListenPort = {listen_port}",
    ]
    for key in ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"):
        if key in awg_params:
            lines.append(f"{key} = {awg_params[key]}")

    for peer in peers:
        lines.append("")
        lines.append("[Peer]")
        lines.append(f"PublicKey = {peer['public_key']}")
        lines.append(f"AllowedIPs = {peer['allowed_ips']}")

    return "\n".join(lines) + "\n"


def render_client_config(
    client_private_key: str,
    client_address: str,
    server_public_key: str,
    server_endpoint: str,
    awg_params: dict,
    dns: str = "1.1.1.1",
) -> str:
    """
    Builds the .conf a client router will import. Contains the
    client's private key in plaintext by necessity — this is what the
    client device needs to actually authenticate. Callers must not
    persist the return value anywhere except the short-TTL Redis cache
    described in docs/architecture.md.
    """
    lines = [
        "[Interface]",
        f"PrivateKey = {client_private_key}",
        f"Address = {client_address}",
        f"DNS = {dns}",
    ]
    for key in ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"):
        if key in awg_params:
            lines.append(f"{key} = {awg_params[key]}")

    lines += [
        "",
        "[Peer]",
        f"PublicKey = {server_public_key}",
        f"Endpoint = {server_endpoint}",
        "AllowedIPs = 0.0.0.0/0, ::/0",
        "PersistentKeepalive = 25",
    ]
    return "\n".join(lines) + "\n"


def write_server_config(rendered_config: str) -> None:
    """
    Writes the rendered config into the container at CONFIG_PATH via
    an env-var-passed heredoc (same rationale as keygen.py: avoid
    putting key material in argv or in an interpolated shell string).
    """
    run_awg_command(
        ["sh", "-c", f'cat > {CONFIG_PATH} << "EOF"\n$CONFIG_CONTENT\nEOF'],
        redact_output=True,
        environment={"CONFIG_CONTENT": rendered_config},
        redact_environment_keys=True,
    )
    logger.info("Wrote server config to %s", CONFIG_PATH)


def reload_interface() -> None:
    """
    Re-applies the on-disk config to the live interface via
    `awg syncconf`, which diffs and applies without a full
    down/up cycle (no dropped handshakes for unaffected peers).
    """
    settings = get_settings()
    strip_output = run_awg_command(
        ["awg-quick", "strip", CONFIG_PATH],
        redact_output=True,
    )
    run_awg_command(
        ["sh", "-c", f'echo "$STRIPPED" | awg syncconf {settings.AWG_INTERFACE} /dev/stdin'],
        redact_output=True,
        environment={"STRIPPED": strip_output},
        redact_environment_keys=True,
    )
    logger.info("Reloaded interface %s from %s", settings.AWG_INTERFACE, CONFIG_PATH)


def persist_current_peers(server_private_key: str, listen_port: int, awg_params: dict) -> None:
    """
    Rewrites CONFIG_PATH from the *live* interface state (via `awg show
    dump`) plus the server's own private key, which the caller must
    supply since interface.py deliberately never returns it.

    Call this after every add_peer/remove_peer/update_peer_allowed_ips
    in interface.py so a container restart doesn't lose the change.
    """
    status = get_interface_status()
    peers = [
        {"public_key": p.public_key, "allowed_ips": p.allowed_ips}
        for p in status.peers
    ]
    rendered = render_server_config(
        server_private_key=server_private_key,
        listen_port=listen_port,
        awg_params=awg_params,
        peers=peers,
    )
    write_server_config(rendered)
