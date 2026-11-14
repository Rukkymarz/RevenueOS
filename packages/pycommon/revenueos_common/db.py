"""Postgres access through the psql client.

Parameters never touch the SQL text: all values travel in one JSON document
passed as a psql variable and are read back with ->> / ->, so there is no
string interpolation of user data. In SQL, write `$name` for a text value
(cast it, e.g. `$task_id::uuid`) and `#name` for a jsonb value.

Each call runs one psql process: simple and dependency-free, but not fast.
Swap in a pooled driver (psycopg 3) behind this same interface when request
volume needs it; callers do not change.
"""
import json
import os
import re
import subprocess

_PARAM = re.compile(r"(?<![\w$])([$#])([a-z_][a-z0-9_]*)\b")


class DatabaseError(Exception):
    """Raised with the server's error message (e.g. an invariant violation)."""

    @property
    def message(self) -> str:
        text = str(self)
        m = re.search(r"ERROR:\s+(.*)", text)
        return m.group(1).strip() if m else text


class Database:
    def __init__(self, dbname=None, host=None, port=None, user=None, actor="system"):
        self.dbname = dbname or os.environ.get("PGDATABASE", "revenueos")
        self.host = host or os.environ.get("PGHOST", "localhost")
        self.port = str(port or os.environ.get("PGPORT", "5432"))
        self.user = user or os.environ.get("PGUSER", "revenueos_app")
        self.actor = actor

    def with_actor(self, actor: str) -> "Database":
        return Database(self.dbname, self.host, self.port, self.user, actor)

    def _bind(self, sql: str) -> str:
        def sub(m):
            sigil, name = m.groups()
            op = "->>" if sigil == "$" else "->"
            return f"(:'__p'::jsonb {op} '{name}')"
        return _PARAM.sub(sub, sql)

    def _run(self, script: str, params: dict) -> str:
        payload = json.dumps({**params, "__actor": self.actor}, default=str)
        cmd = ["psql", "-h", self.host, "-p", self.port, "-U", self.user, "-d", self.dbname,
               "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-v", f"__p={payload}"]
        r = subprocess.run(cmd, input=script, capture_output=True, text=True)
        if r.returncode != 0:
            raise DatabaseError(r.stderr.strip())
        return r.stdout

    def rows(self, sql: str, **params) -> list[dict]:
        """Run one statement (SELECT, or INSERT/UPDATE ... RETURNING) and return rows as dicts."""
        body = self._bind(sql.strip().rstrip(";"))
        script = (
            "SELECT set_config('revenueos.actor', (:'__p'::jsonb ->> '__actor'), false) \\gset __ignored_\n"
            f"WITH _q AS ({body}) SELECT coalesce(json_agg(_q), '[]'::json) FROM _q;\n"
        )
        out = self._run(script, params).strip()
        return json.loads(out.splitlines()[-1]) if out else []

    def one(self, sql: str, **params):
        rows = self.rows(sql, **params)
        return rows[0] if rows else None

    def scalar(self, sql: str, **params):
        row = self.one(sql, **params)
        return None if row is None else next(iter(row.values()))
