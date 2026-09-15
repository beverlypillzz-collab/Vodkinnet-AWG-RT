"""
Key generation via the `awg` CLI inside the AmneziaWG container.

Every function here that touches a private key is named explicitly
(generate_keypair, not generate) so it's obvious at every call site
that the return value needs careful handling — never logged, never
persisted to Postgres, only ever passed through to the caller and
(for client keys) into the Redis TTL cache built in
peer_service on the panel side.
"""

import logging
from dataclasses import dataclass

from src.docker_control.executor import run_awg_command

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Keypair:
    private_key: str
    public_key: str

    def __repr__(self) -> str:
        # Prevent accidental leakage via a stray logger.debug(keypair)
        # or an unguarded print() during development.
        return "Keypair(private_key=<redacted>, public_key=" + self.public_key + ")"


def generate_keypair() -> Keypair:
    """
    Generate a fresh WireGuard/AmneziaWG keypair.

    Uses `awg genkey | awg pubkey` semantics but without a real shell
    pipe (see executor.py's no-shell-string policy) — we generate the
    private key, then derive the public key from it via stdin in a
    second exec call.
    """
    private_key = run_awg_command(["awg", "genkey"], redact_output=True).strip()

    public_key = _derive_public_key(private_key)

    logger.info(
        "Generated new keypair, public_key=%s", public_key
    )
    return Keypair(private_key=private_key, public_key=public_key)


def _derive_public_key(private_key: str) -> str:
    """
    `awg pubkey` reads the private key from stdin. docker-py's exec_run
    doesn't give us a simple way to pipe stdin into an exec, so we pass
    the key via an environment variable (not argv, not an interpolated
    shell string) and read it from there inside a small `sh -c`
    wrapper. This avoids both a shell-injection surface and the
    private key showing up in a process listing (`ps aux`) on the
    container, which argv would not protect against.
    """
    output = run_awg_command(
        ["sh", "-c", 'echo "$WG_PRIVKEY" | awg pubkey'],
        redact_output=True,
        environment={"WG_PRIVKEY": private_key},
        redact_environment_keys=True,
    )
    return output.strip()
