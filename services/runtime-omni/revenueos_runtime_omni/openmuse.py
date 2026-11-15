"""OpenMuse (spec 3.5) inside the desktop runtime.

Persistent browser: Playwright over the system Chromium, one persistent context per agent,
rooted at the agent's own browser-profile identity (Phase 2, INV-09), all traffic through that
agent's identity-pinned egress session, downloads into the runtime workspace. Every action is
risk-classified and receipted like any other tool call (server=runtime-omni, tool=openmuse.*).

Human takeover console: the desktop already serves VNC (x11vnc on localhost:5900, see the
entrypoint). Takeover pauses the agent — the runtime refuses tool execution with 423 while a
human holds the desk — gives the human the VNC endpoint plus a typing channel (xdotool into the
focused window), and the agent resumes on release. Acceptance 3: attach, type, resume.
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field


class TakenOver(RuntimeError):
    """Raised by the runtime while a human holds the desk."""


@dataclass
class Takeover:
    display: str = ":1"
    vnc_port: int = 5900
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    holder: str | None = None
    since: float | None = None
    typed: int = 0

    def attach(self, holder: str) -> dict:
        with self._lock:
            if self.holder and self.holder != holder:
                raise PermissionError(f"desk already held by {self.holder}")
            self.holder, self.since = holder, self.since or time.time()
        return self.status()

    def require_free(self) -> None:
        if self.holder:
            raise TakenOver(f"human takeover active ({self.holder}); agent paused")

    def type_text(self, holder: str, text: str) -> dict:
        with self._lock:
            if self.holder != holder:
                raise PermissionError("attach before typing")
        if len(text) > 4096:
            raise ValueError("type at most 4096 characters per call")
        subprocess.run(["xdotool", "type", "--delay", "15", "--", text],
                       env={"DISPLAY": self.display, "PATH": "/usr/bin:/bin"}, check=True, timeout=120)
        self.typed += len(text)
        return self.status()

    def key(self, holder: str, key: str) -> dict:
        with self._lock:
            if self.holder != holder:
                raise PermissionError("attach before typing")
        if not key.replace("+", "").replace("_", "").isalnum() or len(key) > 32:
            raise ValueError("key must be an xdotool key name like Return or ctrl+l")
        subprocess.run(["xdotool", "key", "--", key],
                       env={"DISPLAY": self.display, "PATH": "/usr/bin:/bin"}, check=True, timeout=30)
        return self.status()

    def release(self, holder: str) -> dict:
        with self._lock:
            if self.holder and self.holder != holder:
                raise PermissionError(f"desk held by {self.holder}")
            self.holder, self.since = None, None
        return self.status()

    def status(self) -> dict:
        return {"active": self.holder is not None, "holder": self.holder, "since": self.since,
                "typed_chars": self.typed, "vnc": {"host": "localhost", "port": self.vnc_port,
                                                   "note": "tunnel in; VNC is never exposed off-host"}}


# --------------------------------------------------------------------------------------------
@dataclass
class _Session:
    agent_id: str
    task_id: str
    context: object
    page: object
    egress_cm: object
    profile_dir: str


class Browser:
    """One persistent Chromium context per agent. Sync Playwright, serialized by the runtime's
    tool lock (the desktop is shared state anyway)."""

    def __init__(self, db, egress_factory, workdir: str, display: str = ":1",
                 executable: str = "/usr/bin/chromium"):
        self.db, self.egress_factory, self.workdir = db, egress_factory, workdir
        self.display, self.executable = display, executable
        self._pw = None
        self.sessions: dict[str, _Session] = {}

    def _playwright(self):
        if self._pw is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
        return self._pw

    def _profile_dir(self, agent_id: str) -> str:
        row = self.db.one(
            "SELECT profile_path FROM agent_identities WHERE agent_id = $a::uuid AND kind = 'browser_profile' "
            "AND status = 'active' ORDER BY created_at DESC LIMIT 1", a=agent_id)
        if not row or not row.get("profile_path"):
            raise PermissionError(f"agent {agent_id} has no active browser profile identity (INV-09)")
        import os
        # Phase 2 lays the profile out as <profile_path>/{profile.json, user-data}; Chromium's
        # persistent context lives in user-data, which is what makes the browser persistent.
        return os.path.join(row["profile_path"], "user-data")

    def open(self, agent_id: str, task_id: str) -> dict:
        if agent_id in self.sessions:
            return {"status": "ok", "reused": True, "profile": self.sessions[agent_id].profile_dir}
        profile = self._profile_dir(agent_id)
        proxy_url, ca = None, None
        cm = None
        if self.egress_factory is not None:
            cm = self.egress_factory(agent_id, task_id)
            proxy_url, ca = cm.__enter__()
        try:
            kw = {"headless": False, "executable_path": self.executable, "accept_downloads": True,
                  "env": {"DISPLAY": self.display},
                  "ignore_default_args": ["--use-mock-keychain"],
                  "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if proxy_url:
                kw["proxy"] = {"server": proxy_url}
                # The egress CA is trusted via the image's NSS store (see python.Dockerfile:
                # desktop builds load /run/revenueos/keychain/egress-ca-cert into $HOME/.pki at
                # entrypoint), so MITM'd HTTPS verifies properly instead of being ignored.
            ctx = self._playwright().chromium.launch_persistent_context(profile, **kw)
        except Exception:
            if cm is not None:
                cm.__exit__(None, None, None)
            raise
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        self.sessions[agent_id] = _Session(agent_id, task_id, ctx, page, cm, profile)
        return {"status": "ok", "reused": False, "profile": profile}

    def _page(self, agent_id: str):
        s = self.sessions.get(agent_id)
        if s is None:
            raise KeyError("no open browser session for this agent; call open first")
        return s

    def goto(self, agent_id: str, url: str, timeout_ms: int = 30000) -> dict:
        s = self._page(agent_id)
        s.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        return {"url": s.page.url, "title": s.page.title()}

    def fill(self, agent_id: str, selector: str, value: str) -> dict:
        s = self._page(agent_id)
        s.page.fill(selector, value, timeout=15000)
        return {"filled": selector}

    def click(self, agent_id: str, selector: str, timeout_ms: int = 15000) -> dict:
        s = self._page(agent_id)
        s.page.click(selector, timeout=timeout_ms)
        return {"clicked": selector, "url": s.page.url}

    def text(self, agent_id: str, selector: str | None = None) -> dict:
        s = self._page(agent_id)
        content = s.page.inner_text(selector, timeout=15000) if selector else s.page.content()
        return {"text": content[:200000]}

    def download(self, agent_id: str, selector: str, to: str, timeout_ms: int = 60000) -> dict:
        """Click `selector` and save the resulting download under the runtime workspace."""
        import os
        s = self._page(agent_id)
        dest = os.path.normpath(os.path.join(self.workdir, to))
        if not dest.startswith(os.path.normpath(self.workdir) + os.sep):
            raise PermissionError("download target escapes the workspace")
        with s.page.expect_download(timeout=timeout_ms) as dl:
            s.page.click(selector)
        download = dl.value
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        download.save_as(dest)
        return {"saved": dest, "suggested": download.suggested_filename}

    def close(self, agent_id: str) -> dict:
        s = self.sessions.pop(agent_id, None)
        if s is None:
            return {"closed": False}
        try:
            s.context.close()
        finally:
            if s.egress_cm is not None:
                s.egress_cm.__exit__(None, None, None)
        return {"closed": True}


BROWSER_TOOLS = {   # openmuse.browser.<name> -> (method, mutating side effects live in the page)
    "open": ("open", ["task_id"]),
    "goto": ("goto", ["url"]),
    "fill": ("fill", ["selector", "value"]),
    "click": ("click", ["selector"]),
    "text": ("text", []),
    "download": ("download", ["selector", "to"]),
    "close": ("close", []),
}
