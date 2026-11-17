"""Pinned egress for the desktop runtime (INV-11). The runtime container has no route out
(internal network); each invocation gets an identity-pinned egress session for its agent and
task, exposed to the tools as a loopback HTTP proxy, with the egress CA for HTTPS."""
import os
import socket
import threading
from contextlib import contextmanager


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _bridge(listener: socket.socket, uds_path: str) -> None:
    while True:
        try:
            client, _ = listener.accept()
        except OSError:
            return   # listener closed: the session is over
        up = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            up.connect(uds_path)
        except OSError:
            client.close()
            continue
        threading.Thread(target=_pipe, args=(client, up), daemon=True).start()
        threading.Thread(target=_pipe, args=(up, client), daemon=True).start()


def session_factory(db, secrets, proxy: tuple[str, int]):
    """callable(agent, task) -> context manager yielding (proxy_url, ca_bundle_path | None)."""
    from revenueos_common import egress_identity
    from revenueos_sandbox.egress import EgressSession
    from revenueos_sandbox.records import egress_hooks
    from revenueos_sandbox.tls import EgressCA

    @contextmanager
    def egress(agent_id: str, task_id: str):
        key = secrets.get(egress_identity.KEY_REF)
        if not key:
            raise RuntimeError("egress identity key unavailable (fail closed)")
        opened, closed = egress_hooks(db)
        with EgressSession(agent_id, task_id or "", key, proxy, on_open=opened, on_close=closed,
                           ca=EgressCA.from_vault(secrets)) as s:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(64)
            threading.Thread(target=_bridge, args=(listener, str(s.socket_path)), daemon=True).start()
            try:
                yield (f"http://127.0.0.1:{listener.getsockname()[1]}", str(s.ca_bundle) if s.ca_bundle else None)
            finally:
                listener.close()
    return egress


def proxy_address() -> tuple[str, int]:
    host, _, port = os.environ.get("EGRESS_PROXY", "envoy:10000").rpartition(":")
    return host, int(port)
