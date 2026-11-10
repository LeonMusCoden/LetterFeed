"""Tests for the IMAP connection timeout."""

import imaplib
import socket
import threading
import time

import pytest


def test_imap_connection_actually_times_out():
    """A server that accepts but never answers must not block the thread forever."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def accept_and_stall():
        connection, _ = server.accept()
        time.sleep(5)
        connection.close()

    threading.Thread(target=accept_and_stall, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(OSError):
        imaplib.IMAP4_SSL("127.0.0.1", port, timeout=1)
    elapsed = time.monotonic() - started
    server.close()
    assert elapsed < 3
