"""Identity pinning for egress (INV-11).

The sandbox supervisor's forwarder is the only thing that can put an agent's traffic on the
network. It stamps every request with the session, agent and task it belongs to, plus a
timestamp and an HMAC over all four. egress-authz recomputes the HMAC and checks the session
row, so an agent can never claim to be another agent or task: it never holds the key, and any
x-revenueos-* header it sends is stripped by the forwarder before signing.
"""
import hashlib
import hmac
import time

HEADER_PREFIX = "x-revenueos-"
KEY_REF = "keychain://egress-identity-hmac"
MAX_AGE_S = 300


def _message(session: str, agent: str, task: str, ts: str) -> bytes:
    return "|".join((session, agent, task, ts)).encode()


def sign(key: str, session: str, agent: str, task: str, ts: int | None = None) -> dict[str, str]:
    """Headers the forwarder adds to a request."""
    stamp = str(int(time.time()) if ts is None else ts)
    mac = hmac.new(key.encode(), _message(session, agent, task, stamp), hashlib.sha256).hexdigest()
    return {f"{HEADER_PREFIX}session": session, f"{HEADER_PREFIX}agent": agent,
            f"{HEADER_PREFIX}task": task, f"{HEADER_PREFIX}ts": stamp, f"{HEADER_PREFIX}sig": mac}


def verify(key: str, session: str, agent: str, task: str, ts: str, sig: str,
           now: float | None = None, max_age_s: int = MAX_AGE_S) -> str | None:
    """None when the stamp is authentic and fresh, otherwise the reason it is not."""
    if not (session and agent and ts and sig):
        return "request is not identity-pinned (no signed session stamp)"
    if not ts.isdigit():
        return "malformed identity timestamp"
    age = (time.time() if now is None else now) - int(ts)
    if age > max_age_s or age < -30:
        return "identity stamp expired"
    want = hmac.new(key.encode(), _message(session, agent, task, ts), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, sig):
        return "identity signature invalid"
    return None
