"""Per-session egress forwarder (INV-11), host side of the sandbox's only route out.

Each sandbox session gets its own Unix socket. Every connection on it carries one HTTP
request: the forwarder drops any x-revenueos-* header the agent sent, stamps the session's
signed identity, forces `Connection: close` (so a second request cannot ride an already
stamped connection), and passes the request to the Envoy egress proxy. CONNECT tunnels are
refused: an encrypted tunnel cannot be inspected or have secrets injected.
"""
import os
import socket
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from revenueos_common import egress_identity

MAX_HEAD = 64 * 1024


def _deny(conn: socket.socket, reason: str) -> None:
    body = ('{"error":"egress denied","reason":"%s"}' % reason.replace('"', "'")).encode()
    conn.sendall(b"HTTP/1.1 403 Forbidden\r\ncontent-type: application/json\r\ncontent-length: "
                 + str(len(body)).encode() + b"\r\nconnection: close\r\n\r\n" + body)


def rewrite_head(head: bytes, stamp: dict[str, str]) -> bytes | None:
    """Rewrite one request head. None if the request must be refused (CONNECT or malformed)."""
    try:
        text = head.decode("latin-1")
    except UnicodeDecodeError:  # pragma: no cover - latin-1 decodes every byte
        return None
    lines = text.split("\r\n")
    request_line = lines[0].split(" ")
    if len(request_line) != 3 or request_line[0].upper() == "CONNECT" or not request_line[2].startswith("HTTP/1."):
        return None
    kept = [request_line[0] + " " + request_line[1] + " " + request_line[2]]
    for line in lines[1:]:
        if not line:
            continue
        name = line.split(":", 1)[0].strip().lower()
        if name.startswith(egress_identity.HEADER_PREFIX) or name in {"connection", "proxy-connection", "keep-alive"}:
            continue
        kept.append(line)
    kept += [f"{k}: {v}" for k, v in stamp.items()] + ["connection: close"]
    return ("\r\n".join(kept) + "\r\n\r\n").encode("latin-1")


@dataclass
class EgressSession:
    agent_id: str
    task_id: str
    key: str
    upstream: tuple[str, int]
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    on_open: Callable[["EgressSession"], None] | None = None
    on_close: Callable[["EgressSession"], None] | None = None

    def __post_init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="rvos-egress-"))
        os.chmod(self.dir, 0o700)
        self.socket_path = self.dir / "egress.sock"
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(str(self.socket_path))
        self._listener.listen(64)
        self._closed = False
        if self.on_open:
            self.on_open(self)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while not self._closed:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = conn.recv(65536)
                if not chunk or len(buf) > MAX_HEAD:
                    return
                buf += chunk
            head, rest = buf.split(b"\r\n\r\n", 1)
            stamp = egress_identity.sign(self.key, self.session_id, self.agent_id, self.task_id)
            new_head = rewrite_head(head, stamp)
            if new_head is None:
                _deny(conn, "only plain HTTP requests through the proxy are allowed (no CONNECT tunnels)")
                return
            try:
                up = socket.create_connection(self.upstream, timeout=30)
            except OSError:
                _deny(conn, "egress proxy unreachable (fail closed)")
                return
            with up:
                up.sendall(new_head + rest)
                done = threading.Event()

                def client_to_up():
                    try:
                        while data := conn.recv(65536):
                            up.sendall(data)
                    except OSError:
                        pass
                    done.set()

                threading.Thread(target=client_to_up, daemon=True).start()
                try:
                    while data := up.recv(65536):
                        conn.sendall(data)
                except OSError:
                    pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._listener.close()
        finally:
            try:
                self.socket_path.unlink(missing_ok=True)
                self.dir.rmdir()
            except OSError:
                pass
            if self.on_close:
                self.on_close(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
