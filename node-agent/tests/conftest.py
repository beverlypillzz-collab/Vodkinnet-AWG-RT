"""
Shared test fixtures.

We mock the Docker client entirely rather than spinning up a real
amnezia-awg2 container in CI — the agent's job is to build correct
commands and handle their (mocked) results correctly, not to
re-test AmneziaWG itself.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# Settings requires these env vars to be present at import time.
# Set safe test values before any src.* module is imported.
os.environ.setdefault("AGENT_TOKEN", "test-token-" + "x" * 32)
os.environ.setdefault("AWG_CONTAINER_NAME", "test-amnezia-awg2")
os.environ.setdefault("AWG_LISTEN_PORT", "55632")
os.environ.setdefault("LOG_LEVEL", "DEBUG")


@pytest.fixture
def mock_docker_client():
    """
    Patches docker_control.executor.get_docker_client() to return a
    MagicMock whose .containers.get() returns a fake running
    container. Individual tests configure exec_run() return values
    per-case.
    """
    with patch("src.docker_control.executor.get_docker_client") as mock_get_client:
        client = MagicMock()
        container = MagicMock()
        container.status = "running"
        client.containers.get.return_value = container
        mock_get_client.return_value = client
        yield container


@pytest.fixture
def exec_result():
    """Factory for a fake docker-py ExecResult-like object."""

    def _make(exit_code: int, output: bytes):
        result = MagicMock()
        result.exit_code = exit_code
        result.output = output
        return result

    return _make
