"""
Docker exec wrapper for running `awg`/`awg-quick` commands inside the
AmneziaWG container from the agent's own process.

SECURITY NOTE — read before touching this file:

The agent has access to /var/run/docker.sock, which is equivalent to
root on the host. To keep that power narrowly scoped:

1. The target container name comes ONLY from Settings.AWG_CONTAINER_NAME
   (set once at deploy time via env var). It is never accepted as a
   parameter from an API caller. If you find yourself wanting to add a
   `container_name` argument to any function in this file so the panel
   can specify it — don't. That turns a scoped agent into an
   unrestricted docker-exec-as-a-service, which defeats the entire
   point of running agent and AWG in separate containers.

2. Commands are passed as argument lists (never a shell string), so
   there is no shell interpolation and no injection surface even if a
   caller-supplied value (e.g. a public key) ends up as one argument.

3. Every exec is logged at DEBUG with the command and exit code. Output
   is logged at DEBUG too, EXCEPT for any command building or printing
   a private key (see wg/config_builder.py) — those call sites must
   redact before logging, not this wrapper, since this wrapper has no
   way to know which output is sensitive.
"""

import logging

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class AgentCommandError(Exception):
    """Raised when a command inside the AWG container fails."""

    def __init__(self, command: list[str], exit_code: int, output: str):
        self.command = command
        self.exit_code = exit_code
        self.output = output
        super().__init__(
            f"Command {command!r} exited {exit_code}: {output.strip()}"
        )


class AwgContainerUnavailable(Exception):
    """Raised when the AWG container cannot be found or is not running."""


_client: docker.DockerClient | None = None


def get_docker_client() -> docker.DockerClient:
    global _client
    if _client is None:
        settings = get_settings()
        logger.debug(
            "Initialising Docker client against %s", settings.DOCKER_SOCKET
        )
        _client = docker.DockerClient(base_url=settings.DOCKER_SOCKET)
    return _client


def get_awg_container() -> Container:
    """
    Resolve the fixed AWG container by name. Raises
    AwgContainerUnavailable if it doesn't exist or isn't running —
    callers (the /server/status route in particular) should turn that
    into a clear 'node offline' signal for the panel rather than a
    raw 500.
    """
    settings = get_settings()
    client = get_docker_client()

    try:
        container = client.containers.get(settings.AWG_CONTAINER_NAME)
    except NotFound as exc:
        logger.error(
            "AWG container %r not found on this host",
            settings.AWG_CONTAINER_NAME,
        )
        raise AwgContainerUnavailable(
            f"Container {settings.AWG_CONTAINER_NAME!r} not found"
        ) from exc

    if container.status != "running":
        logger.error(
            "AWG container %r exists but is not running (status=%s)",
            settings.AWG_CONTAINER_NAME,
            container.status,
        )
        raise AwgContainerUnavailable(
            f"Container {settings.AWG_CONTAINER_NAME!r} is "
            f"{container.status}, not running"
        )

    return container


def run_awg_command(
    cmd: list[str],
    *,
    redact_output: bool = False,
    environment: dict[str, str] | None = None,
    redact_environment_keys: bool = False,
) -> str:
    """
    Execute `cmd` inside the AWG container and return stdout+stderr
    combined as a string.

    Set redact_output=True for any command whose output could contain
    a private key (e.g. `awg genkey`) so it never lands in a DEBUG log
    line by accident.

    `environment` lets callers pass sensitive values (e.g. a private
    key) into the exec without putting them in argv, where they'd be
    visible via `ps aux` inside the container and would show up
    verbatim in this function's own debug log of `cmd`. Set
    redact_environment_keys=True to log which *keys* were passed
    without logging their values.
    """
    settings = get_settings()
    container = get_awg_container()

    if environment and redact_environment_keys:
        logger.debug(
            "Executing in %s: %s (env keys: %s, values redacted)",
            settings.AWG_CONTAINER_NAME,
            cmd,
            list(environment.keys()),
        )
    else:
        logger.debug("Executing in %s: %s", settings.AWG_CONTAINER_NAME, cmd)

    result = container.exec_run(
        cmd,
        demux=False,
        tty=False,
        environment=environment,
    )

    output = result.output.decode("utf-8", errors="replace")
    exit_code = result.exit_code

    if redact_output:
        logger.debug(
            "Command exited %s (output redacted — may contain key material)",
            exit_code,
        )
    else:
        logger.debug("Command exited %s, output: %s", exit_code, output.strip())

    if exit_code != 0:
        # Safe to include output in the exception even when
        # redact_output=True — exceptions here are caught by the API
        # layer and turned into a generic 500, never returned to the
        # panel verbatim. If that ever changes, revisit this.
        raise AgentCommandError(cmd, exit_code, output)

    return output


def container_is_running() -> bool:
    """
    Cheap health check used by GET /health — must never raise, since
    /health is the one endpoint operators hit first when something is
    wrong and it needs to degrade gracefully rather than 500.

    Covers three distinct failure modes we've actually seen while
    testing this locally:
      - the named container doesn't exist / isn't running
        (AwgContainerUnavailable, raised by get_awg_container)
      - the Docker daemon is reachable but returned an API-level error
        (docker.errors.APIError)
      - the Docker socket itself isn't reachable at all — wrong mount,
        daemon not running, permissions — which docker-py raises as a
        bare DockerException from the client constructor, not as
        APIError. This is the case a misconfigured docker-compose.yml
        on a fresh node will actually hit, so it must be covered here
        too rather than assumed away.
    """
    try:
        get_awg_container()
        return True
    except AwgContainerUnavailable:
        return False
    except (APIError, DockerException):
        logger.exception(
            "Docker error while checking container health "
            "(daemon unreachable or socket misconfigured?)"
        )
        return False
