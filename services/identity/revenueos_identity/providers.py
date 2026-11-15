"""Identity providers (C05). Self-hosted first; hosted fallbacks only when configured.

Self-hosted (primary):
  AgenticMail (named, built from the pinned commit) on Stalwart v0.15.5: per-agent mailbox and
  REST API key; Stalwart's CalDAV gives each mailbox a calendar.
Hosted fallbacks (spec 2.1; proprietary; used only with credentials in the vault and approval):
  AgentMail       POST https://api.agentmail.to/v0/inboxes           (Bearer)
  Browser Use     POST https://api.browser-use.com/api/v2/profiles    (X-Browser-Use-API-Key)
                  POST https://api.browser-use.com/api/v2/sessions
  imAPI           a hosted MCP bridge for IMAP read / SMTP send, reached at a configured URL
Phone carriers (AgenticMail phone transport): 46elks or Twilio. A number is a paid external
resource, so allocation needs carrier credentials and is never automatic.

Secrets are passed in already resolved by the caller (identity service); nothing here reads,
logs or returns them except the values a provider hands back for the vault.
"""
import secrets as pysecrets
from dataclasses import dataclass

import requests

TIMEOUT = 20


class ProviderError(RuntimeError):
    pass


class NotConfigured(ProviderError):
    """Credentials for this provider are not in the vault: the identity stays pending."""


def _check(r: requests.Response, what: str) -> dict:
    if r.status_code >= 300:
        raise ProviderError(f"{what} failed: HTTP {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else {}


def new_password() -> str:
    return pysecrets.token_urlsafe(24)


@dataclass
class Mailbox:
    email: str
    api_key: str
    account_id: str
    password: str
    login: str          # Stalwart principal name: the IMAP/SMTP/CalDAV login


class AgenticMail:
    """AgenticMail REST (`/api/agenticmail`): master key creates accounts; each account gets its
    own agent API key, which the identity service stores in the vault."""

    def __init__(self, base_url: str, master_key: str | None, session: requests.Session | None = None):
        if not master_key:
            raise NotConfigured("AgenticMail master key not in the vault")
        self.base = base_url.rstrip("/") + "/api/agenticmail"
        self.http = session or requests.Session()
        self.headers = {"authorization": f"Bearer {master_key}"}

    def healthy(self) -> bool:
        try:
            return self.http.get(f"{self.base}/health", timeout=TIMEOUT).status_code == 200
        except requests.RequestException:
            return False

    def create_mailbox(self, name: str, domain: str, metadata: dict) -> Mailbox:
        password = new_password()
        body = {"name": name, "domain": domain, "password": password, "role": "custom", "metadata": metadata}
        a = _check(self.http.post(f"{self.base}/accounts", json=body, headers=self.headers, timeout=TIMEOUT),
                   "AgenticMail create account")
        if not a.get("email") or not a.get("apiKey"):
            raise ProviderError("AgenticMail returned no email or API key")
        return Mailbox(email=a["email"], api_key=a["apiKey"], account_id=str(a.get("id", "")), password=password,
                       login=str(a.get("stalwartPrincipal") or a["email"].split("@")[0]))


_DAV = "{DAV:}"
_CALDAV = "{urn:ietf:params:xml:ns:caldav}"


def _propfind(http: requests.Session, url: str, auth, prop_xml: str) -> "ElementTree.Element":
    from xml.etree import ElementTree
    body = f'<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>{prop_xml}</d:prop></d:propfind>'
    r = http.request("PROPFIND", url, auth=auth, data=body, timeout=TIMEOUT, allow_redirects=True,
                     headers={"Depth": "0", "content-type": "application/xml"})
    if r.status_code != 207:
        raise ProviderError(f"CalDAV PROPFIND {url} failed: HTTP {r.status_code}")
    return ElementTree.fromstring(r.content)


def caldav_home(server_url: str, user: str, password: str, session: requests.Session | None = None) -> str:
    """The account's calendar home, found by standard discovery (RFC 6764 well-known URL, then
    current-user-principal, then CalDAV calendar-home-set) with the account's own credentials."""
    from urllib.parse import urljoin
    http, auth, base = session or requests.Session(), (user, password), server_url.rstrip("/") + "/"
    root = _propfind(http, urljoin(base, ".well-known/caldav"), auth, "<d:current-user-principal/>")
    principal = root.find(f".//{_DAV}current-user-principal/{_DAV}href")
    if principal is None or not (principal.text or "").strip():
        raise ProviderError("CalDAV server returned no current-user-principal")
    home = _propfind(http, urljoin(base, principal.text.strip()), auth, "<c:calendar-home-set/>")
    href = home.find(f".//{_CALDAV}calendar-home-set/{_DAV}href")
    if href is None or not (href.text or "").strip():
        raise ProviderError("CalDAV principal has no calendar-home-set")
    return urljoin(base, href.text.strip())


class AgentMailHosted:
    BASE = "https://api.agentmail.to/v0"

    def __init__(self, api_key: str | None, session: requests.Session | None = None):
        if not api_key:
            raise NotConfigured("AgentMail API key not in the vault")
        self.http, self.headers = session or requests.Session(), {"authorization": f"Bearer {api_key}"}

    def create_inbox(self, username: str, display_name: str, client_id: str) -> str:
        body = {"username": username, "display_name": display_name, "client_id": client_id}
        out = _check(self.http.post(f"{self.BASE}/inboxes", json=body, headers=self.headers, timeout=TIMEOUT),
                     "AgentMail create inbox")
        return out["inbox_id"]


class BrowserUseCloud:
    BASE = "https://api.browser-use.com/api/v2"

    def __init__(self, api_key: str | None, session: requests.Session | None = None):
        if not api_key:
            raise NotConfigured("Browser Use Cloud API key not in the vault")
        self.http, self.headers = session or requests.Session(), {"X-Browser-Use-API-Key": api_key}

    def create_profile(self, name: str) -> str:
        return _check(self.http.post(f"{self.BASE}/profiles", json={"name": name[:100]}, headers=self.headers,
                                     timeout=TIMEOUT), "Browser Use create profile")["id"]

    def create_session(self, profile_id: str) -> dict:
        body = {"profileId": profile_id, "keepAlive": False, "persistMemory": False, "enableRecording": False}
        return _check(self.http.post(f"{self.BASE}/sessions", json=body, headers=self.headers, timeout=TIMEOUT),
                      "Browser Use create session")


class ImapiBridge:
    """imAPI: hosted MCP bridge. Only its URL and token are configuration; tools are discovered
    over MCP and governed like any other MCP server (Phase 4 registry, INV-10)."""

    def __init__(self, url: str | None, token: str | None):
        if not url or not token:
            raise NotConfigured("imAPI bridge URL/token not in the vault")
        self.url, self.token = url, token


def phone_provider(name: str | None, credentials: dict | None):
    if not name:
        raise NotConfigured("no phone carrier chosen (46elks or Twilio)")
    if name not in ("46elks", "twilio"):
        raise ProviderError(f"unsupported phone carrier {name!r}")
    if not credentials or not all(credentials.values()):
        raise NotConfigured(f"{name} credentials not in the vault")
    # Allocating a number is a paid external write: it goes through an INV-06 approval and the
    # carrier's own API, never through this provisioning path automatically.
    raise NotConfigured(f"{name} number allocation needs an approved purchase (INV-06)")
