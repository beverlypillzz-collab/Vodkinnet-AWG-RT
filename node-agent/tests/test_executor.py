"""
Tests for docker_control/executor.py.

Priority is on the security-relevant behaviour: the container name is
never taken from anywhere except Settings, and failures produce clear
exceptions rather than silently swallowing errors.
"""

import pytest

from src.docker_control.executor import (
    AgentCommandError,
    AwgContainerUnavailable,
    container_is_running,
    run_awg_command,
)


def test_run_awg_command_success(mock_docker_client, exec_result):
    mock_docker_client.exec_run.return_value = exec_result(0, b"awg output\n")

    output = run_awg_command(["awg", "show"])

    assert output == "awg output\n"
    mock_docker_client.exec_run.assert_called_once()
    called_cmd = mock_docker_client.exec_run.call_args.args[0]
    assert called_cmd == ["awg", "show"]


def test_run_awg_command_nonzero_exit_raises(mock_docker_client, exec_result):
    mock_docker_client.exec_run.return_value = exec_result(1, b"some error\n")

    with pytest.raises(AgentCommandError) as exc_info:
        run_awg_command(["awg", "show", "nonexistent"])

    assert exc_info.value.exit_code == 1
    assert "some error" in exc_info.value.output


def test_run_awg_command_passes_environment(mock_docker_client, exec_result):
    mock_docker_client.exec_run.return_value = exec_result(0, b"pubkey123\n")

    run_awg_command(
        ["sh", "-c", 'echo "$SECRET" | awg pubkey'],
        environment={"SECRET": "fake-private-key"},
        redact_environment_keys=True,
    )

    call_kwargs = mock_docker_client.exec_run.call_args.kwargs
    assert call_kwargs["environment"] == {"SECRET": "fake-private-key"}


def test_container_not_found_reports_unavailable():
    """
    get_awg_container() must translate a Docker "not found" error into
    AwgContainerUnavailable, not let a raw docker.errors.NotFound
    propagate — the API layer relies on this specific exception type
    to return a clean 503 instead of a 500.
    """
    from unittest.mock import MagicMock, patch

    from docker.errors import NotFound

    with patch("src.docker_control.executor.get_docker_client") as mock_get_client:
        client = MagicMock()
        client.containers.get.side_effect = NotFound("no such container")
        mock_get_client.return_value = client

        with pytest.raises(AwgContainerUnavailable):
            run_awg_command(["awg", "show"])


def test_container_is_running_false_when_unavailable():
    from unittest.mock import MagicMock, patch

    from docker.errors import NotFound

    with patch("src.docker_control.executor.get_docker_client") as mock_get_client:
        client = MagicMock()
        client.containers.get.side_effect = NotFound("no such container")
        mock_get_client.return_value = client

        assert container_is_running() is False


def test_container_is_running_true_when_running(mock_docker_client):
    assert container_is_running() is True
