"""Shared test setup.

- Makes shared fixtures importable as ``fixtures.*`` from any test directory.
- Guards the default suite against network I/O: any connection or name lookup outside
  loopback fails the test (global constitution article 18). ``live`` tests are exempt.
"""

import ipaddress
import socket
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))

_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo


def _is_loopback(host: object) -> bool:
    if host is None or host in _LOOPBACK_NAMES:
        return True
    if isinstance(host, bytes):
        host = host.decode()
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _check(sock: socket.socket, address: Any) -> None:
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address[0]):
        raise AssertionError(f"default test suite attempted network access to {address!r}")


def _connect(self: socket.socket, address: Any) -> None:
    _check(self, address)
    _real_connect(self, address)


def _connect_ex(self: socket.socket, address: Any) -> int:
    _check(self, address)
    return _real_connect_ex(self, address)


def _getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    if not _is_loopback(host):
        raise AssertionError(f"default test suite attempted a DNS lookup of {host!r}")
    return _real_getaddrinfo(host, *args, **kwargs)


@pytest.fixture(autouse=True)
def _no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setattr(socket.socket, "connect", _connect)
        monkeypatch.setattr(socket.socket, "connect_ex", _connect_ex)
        monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)
    yield
