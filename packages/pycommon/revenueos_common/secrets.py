"""Secret references and stores. Secrets are addressed by reference only:

  keychain://<name>               local 0600 file store (dev machines, bootstrap creds)
  vault://<environment>/<path>/<NAME>   Infisical (self-hosted), project from config

Values are returned to the egress proxy and identity service only, never to
agents, prompts, or logs.
"""
import os
import re
import stat
import threading
import time
from pathlib import Path

import requests

REF = re.compile(r"^(keychain|vault)://([A-Za-z0-9._/-]+)$")


class SecretError(Exception):
    pass


def parse_ref(ref: str):
    m = REF.match(ref or "")
    if not m or ".." in m.group(2):
        raise SecretError(f"invalid secret reference: {ref!r}")
    return m.group(1), m.group(2)


class KeychainStore:
    scheme = "keychain"

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def _path(self, name):
        if "/" in name:
            raise SecretError("keychain names are flat")
        return self.root / name

    def get(self, name):
        p = self._path(name)
        if not p.exists():
            return None
        mode = stat.S_IMODE(p.stat().st_mode)
        if mode & 0o077:
            raise SecretError(f"keychain entry {name} is readable by others (mode {oct(mode)})")
        return p.read_text().rstrip("\n")

    def put(self, name, value):
        p = self._path(name)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(value)
        os.chmod(p, 0o600)


class InfisicalStore:
    """Infisical v4 secrets API with machine-identity (universal auth) login.

    Endpoints (from Infisical source, backend/src/server/routes):
      POST /api/v1/auth/universal-auth/login  {clientId, clientSecret} -> {accessToken}
      GET  /api/v4/secrets/{name}?projectId&environment&secretPath -> {secret: {secretValue}}
      POST /api/v4/secrets/{name}  {projectId, environment, secretPath, secretValue}
    """
    scheme = "vault"

    def __init__(self, base_url, project_id, client_id, client_secret, timeout=10, session=None):
        self.base = base_url.rstrip("/")
        self.project_id = project_id
        self._cid, self._csec = client_id, client_secret
        self.timeout = timeout
        self.http = session or requests.Session()
        self._token, self._exp = None, 0.0
        self._lock = threading.Lock()

    def _auth(self):
        with self._lock:
            if self._token and time.time() < self._exp - 30:
                return self._token
            r = self.http.post(f"{self.base}/api/v1/auth/universal-auth/login",
                               json={"clientId": self._cid, "clientSecret": self._csec}, timeout=self.timeout)
            r.raise_for_status()
            body = r.json()
            self._token = body["accessToken"]
            self._exp = time.time() + int(body.get("expiresIn", 600))
            return self._token

    @staticmethod
    def _split(path):
        parts = path.split("/")
        if len(parts) < 2:
            raise SecretError("vault refs are vault://<environment>/<path>/<NAME>")
        env, name = parts[0], parts[-1]
        secret_path = "/" + "/".join(parts[1:-1]) if len(parts) > 2 else "/"
        return env, secret_path, name

    def get(self, path):
        env, secret_path, name = self._split(path)
        r = self.http.get(f"{self.base}/api/v4/secrets/{name}",
                          params={"projectId": self.project_id, "environment": env, "secretPath": secret_path},
                          headers={"Authorization": f"Bearer {self._auth()}"}, timeout=self.timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()["secret"]["secretValue"]

    def put(self, path, value):
        env, secret_path, name = self._split(path)
        body = {"projectId": self.project_id, "environment": env, "secretPath": secret_path, "secretValue": value}
        h = {"Authorization": f"Bearer {self._auth()}"}
        r = self.http.post(f"{self.base}/api/v4/secrets/{name}", json=body, headers=h, timeout=self.timeout)
        if r.status_code in (400, 409):     # already exists -> update
            r = self.http.patch(f"{self.base}/api/v4/secrets/{name}", json=body, headers=h, timeout=self.timeout)
        r.raise_for_status()


class SecretResolver:
    def __init__(self, *stores):
        self.stores = {s.scheme: s for s in stores}

    def get(self, ref):
        scheme, path = parse_ref(ref)
        store = self.stores.get(scheme)
        if store is None:
            return None
        return store.get(path)

    def put(self, ref, value):
        scheme, path = parse_ref(ref)
        if scheme not in self.stores:
            raise SecretError(f"no store configured for {scheme}://")
        self.stores[scheme].put(path, value)
