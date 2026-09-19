"""Merge the N processes Explorer launches for an N-file selection into one batch.

The first process to bind the loopback port becomes the leader; later ones hand their
file to it and exit. The leader waits for a short quiet period, then returns everything.
"""
from __future__ import annotations

import socket

PORT = 47613
QUIET_SECONDS = 0.6


def collect(items: list[str]) -> list[str] | None:
    """items are "key\\tpath" strings. Returns all items if this process is the leader, else None."""
    srv = socket.socket()
    try:
        srv.bind(("127.0.0.1", PORT))
    except OSError:
        for _ in range(20):  # leader may be mid-shutdown; retry briefly
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=2) as c:
                    c.sendall(("\n".join(items) + "\n").encode("utf-8"))
                return None
            except OSError:
                import time

                time.sleep(0.1)
        return items  # could not reach a leader; just do our own
    srv.listen(64)
    srv.settimeout(QUIET_SECONDS)
    got = list(items)
    try:
        while True:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                break
            with conn:
                conn.settimeout(2)
                buf = b""
                try:
                    while chunk := conn.recv(65536):
                        buf += chunk
                except OSError:
                    pass
                got.extend(line for line in buf.decode("utf-8", "replace").splitlines() if line)
    finally:
        srv.close()
    return got
