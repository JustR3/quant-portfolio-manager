"""The autouse guard in conftest.py blocks internet sockets in unmarked tests."""

import socket

import pytest


def _family_supported(family) -> bool:
    try:
        socket.socket(family, socket.SOCK_STREAM).close()
        return True
    except OSError:  # e.g. a container with IPv6 disabled
        return False


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6])
@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_unmarked_test_cannot_open_internet_connection(
    family, method, _block_network_in_unmarked_tests
):
    if not _family_supported(family):
        pytest.skip(f"{family.name} sockets unavailable on this host")
    address = ("127.0.0.1", 9) if family == socket.AF_INET else ("::1", 9, 0, 0)
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        with pytest.raises(RuntimeError, match="network access in an unmarked test"):
            getattr(sock, method)(address)
    assert len(_block_network_in_unmarked_tests) == 1
    _block_network_in_unmarked_tests.clear()  # expected; don't fail at teardown


def test_unix_socket_still_works(tmp_path, monkeypatch):
    # Relative path: AF_UNIX paths have a short length limit.
    monkeypatch.chdir(tmp_path)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind("s")
        server.listen(1)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            assert client.connect_ex("s") == 0
            conn, _ = server.accept()
            with conn:
                client.sendall(b"ok")
                assert conn.recv(2) == b"ok"


def test_swallowed_network_error_is_still_recorded(_block_network_in_unmarked_tests):
    """Code that catches the RuntimeError must not hide the attempt from the guard."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.connect(("127.0.0.1", 9))
        except Exception:
            pass
    assert len(_block_network_in_unmarked_tests) == 1
    _block_network_in_unmarked_tests.clear()  # expected; don't fail at teardown


def test_curl_cffi_is_blocked(_block_network_in_unmarked_tests):
    """yfinance goes through curl_cffi, which never touches Python sockets."""
    from curl_cffi import curl

    with pytest.raises(RuntimeError, match="network access in an unmarked test"):
        curl.Curl().perform()
    assert len(_block_network_in_unmarked_tests) == 1
    _block_network_in_unmarked_tests.clear()  # expected; don't fail at teardown
