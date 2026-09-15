"""
Tests for wg/interface.py, particularly `awg show dump` parsing —
tab-separated field indices are an easy place to introduce a
one-column-off bug that silently reports wrong handshake times.
"""

from src.wg.interface import get_interface_status


FAKE_PRIVATE_KEY = "cGFzc3dvcmQxMjM0NTY3ODkwYWJjZGVmZ2hpams="
FAKE_SERVER_PUBKEY = "c2VydmVycHVia2V5MTIzNDU2Nzg5MGFiY2RlZg=="
FAKE_PEER_PUBKEY = "cGVlcnB1YmtleTEyMzQ1Njc4OTBhYmNkZWZnaGk="


def _dump_line(*fields: str) -> str:
    return "\t".join(fields)


def test_parses_interface_with_no_peers(mock_docker_client, exec_result):
    dump = _dump_line(FAKE_PRIVATE_KEY, FAKE_SERVER_PUBKEY, "55632", "off") + "\n"
    mock_docker_client.exec_run.return_value = exec_result(0, dump.encode())

    status = get_interface_status()

    assert status.interface_up is True
    assert status.public_key == FAKE_SERVER_PUBKEY
    assert status.listen_port == 55632
    assert status.peers == []
    # The private key must never appear anywhere on the returned object.
    assert FAKE_PRIVATE_KEY not in repr(status)


def test_parses_interface_with_one_peer(mock_docker_client, exec_result):
    interface_line = _dump_line(FAKE_PRIVATE_KEY, FAKE_SERVER_PUBKEY, "55632", "off")
    peer_line = _dump_line(
        FAKE_PEER_PUBKEY,
        "(none)",  # preshared key
        "203.0.113.5:41234",  # endpoint
        "10.8.0.7/32",  # allowed ips
        "1757894400",  # latest handshake (unix epoch)
        "184320",  # rx
        "92160",  # tx
        "off",  # persistent keepalive
    )
    dump = interface_line + "\n" + peer_line + "\n"
    mock_docker_client.exec_run.return_value = exec_result(0, dump.encode())

    status = get_interface_status()

    assert len(status.peers) == 1
    peer = status.peers[0]
    assert peer.public_key == FAKE_PEER_PUBKEY
    assert peer.endpoint == "203.0.113.5:41234"
    assert peer.allowed_ips == "10.8.0.7/32"
    assert peer.rx_bytes == 184320
    assert peer.tx_bytes == 92160
    assert peer.last_handshake is not None
    assert peer.last_handshake.timestamp() == 1757894400


def test_peer_never_had_handshake_reports_none(mock_docker_client, exec_result):
    interface_line = _dump_line(FAKE_PRIVATE_KEY, FAKE_SERVER_PUBKEY, "55632", "off")
    peer_line = _dump_line(
        FAKE_PEER_PUBKEY, "(none)", "(none)", "10.8.0.8/32", "0", "0", "0", "off"
    )
    dump = interface_line + "\n" + peer_line + "\n"
    mock_docker_client.exec_run.return_value = exec_result(0, dump.encode())

    status = get_interface_status()

    assert status.peers[0].last_handshake is None
    assert status.peers[0].endpoint is None


def test_interface_down_returns_false_not_exception(mock_docker_client, exec_result):
    mock_docker_client.exec_run.return_value = exec_result(
        1, b"Unable to access interface: No such device\n"
    )

    status = get_interface_status()

    assert status.interface_up is False
    assert status.public_key is None
    assert status.peers == []
