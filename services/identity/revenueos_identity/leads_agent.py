"""Leads agent: signs up for a service with its own identity and completes the emailed
verification unattended (spec 2.6). Runs INSIDE the sandbox with the standard library only.

Its only network path is the sandbox's egress relay: requests go through the identity-pinned
proxy, which also injects the agent's own mail API key for its inbox. The agent never holds that
key or any other secret. Each step is printed as one JSON line for the identity service to write
to the timeline and the audit ledger; the code itself is never printed, only its hash.

usage: python3 -m revenueos_identity.leads_agent --email ADDR --service URL [--mode otp|magic-link]
                                                  [--inbox URL] [--timeout S]
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CODE = re.compile(r"\b(\d{6})\b")
LINK = re.compile(r"(https?://\S+/magic\?token=[A-Za-z0-9_-]+)")


def step(name: str, status: str, **detail) -> None:
    print(json.dumps({"step": name, "status": status, **detail}), flush=True)


def http(method: str, url: str, body: dict | None = None, timeout: float = 20) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"content-type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, OSError, ValueError) as e:   # unreachable / refused / not JSON
        return 0, {"error": type(e).__name__}


def find_verification(inbox: str, since_uids: set, deadline: float) -> dict | None:
    """Poll the agent's own inbox (and spam folder) for the verification message."""
    while time.time() < deadline:
        for listing in (f"{inbox}/mail/inbox?limit=20", f"{inbox}/mail/spam?limit=20"):
            code, body = http("GET", listing)
            if code != 200:
                continue
            for m in body.get("messages", []):
                uid = m.get("uid")
                subject = str(m.get("subject", ""))
                if uid in since_uids or "verification" not in subject.lower():
                    continue
                folder = "" if "inbox" in listing else "?folder=" + urllib.parse.quote(str(body.get("folder", "Junk Mail")))
                c, msg = http("GET", f"{inbox}/mail/messages/{uid}{folder}")
                if c == 200:
                    return msg
        time.sleep(1.0)
    return None


def run(email: str, service: str, inbox: str, mode: str, timeout: float) -> int:
    step("start", "ok", email=email, service=service, mode=mode)
    c, existing = http("GET", f"{inbox}/mail/inbox?limit=50")
    if c != 200:
        step("inbox_access", "failed", http_status=c)
        return 2
    seen = {m.get("uid") for m in existing.get("messages", [])}
    step("inbox_access", "ok", messages=len(seen))

    c, _ = http("POST", f"{service}/signup", {"email": email})
    step("signup", "ok" if c == 202 else "failed", http_status=c)
    if c != 202:
        return 3

    msg = find_verification(inbox, seen, time.time() + timeout)
    if msg is None:
        step("verification_email", "failed", reason="no verification email within timeout")
        return 4
    text = str(msg.get("text") or msg.get("body") or msg.get("html") or "")
    step("verification_email", "ok", subject=str(msg.get("subject", "")))

    if mode == "magic-link":
        m = LINK.search(text)
        if not m:
            step("extract", "failed", reason="no magic link in email")
            return 5
        step("extract", "ok", kind="magic-link", link_sha256=hashlib.sha256(m.group(1).encode()).hexdigest())
        c, body = http("GET", m.group(1))
    else:
        m = CODE.search(text)
        if not m:
            step("extract", "failed", reason="no 6-digit code in email")
            return 5
        step("extract", "ok", kind="otp", code_sha256=hashlib.sha256(m.group(1).encode()).hexdigest())
        c, body = http("POST", f"{service}/verify", {"email": email, "code": m.group(1)})
    ok = c == 200 and body.get("verified") is True
    step("verify", "ok" if ok else "failed", http_status=c)
    c, status = http("GET", f"{service}/status?email={urllib.parse.quote(email)}")
    done = c == 200 and status.get("verified") is True
    step("complete", "ok" if done else "failed")
    return 0 if done else 6


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--service", required=True)
    ap.add_argument("--inbox", default="http://agenticmail:3829/api/agenticmail")
    ap.add_argument("--mode", choices=["otp", "magic-link"], default="otp")
    ap.add_argument("--timeout", type=float, default=60)
    a = ap.parse_args(argv)
    return run(a.email, a.service.rstrip("/"), a.inbox.rstrip("/"), a.mode, a.timeout)


if __name__ == "__main__":
    sys.exit(main())
