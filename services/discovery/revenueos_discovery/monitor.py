"""Turns the sandbox wrapper's syscall traces into `tool_events` rows and quarantines a server
that tried to leave its sandbox (spec 4.5 runtime monitoring, 4.7). Runs in the discovery
service, outside every sandbox."""
from pathlib import Path

from . import registry
from .sandbox_exec import ROOT, analyze


class TraceMonitor:
    def __init__(self, db, ad, root: Path = ROOT):
        self.db, self.ad, self.root = db, ad, Path(root)
        self._reported: dict[str, set] = {}
        self._sizes: dict[str, int] = {}

    def scan(self) -> list[dict]:
        found = []
        for log in sorted(self.root.glob("*/trace/*.log")):
            server = log.parent.parent.name
            try:
                size = log.stat().st_size
                if self._sizes.get(str(log)) == size:
                    continue
                self._sizes[str(log)] = size
                payload = log.with_suffix(".payload").read_text().strip()
                violations = analyze(log.read_text(errors="replace"), payload)
            except OSError:
                continue
            seen = self._reported.setdefault(server, set())
            fresh = [v for v in violations if (v["kind"], v["target"]) not in seen][:50]
            for v in fresh:
                seen.add((v["kind"], v["target"]))
                registry.event(self.db, server, v["kind"], {k: v[k] for k in ("target", "syscall", "errno")})
            if fresh:
                kinds = sorted({v["kind"] for v in fresh})
                registry.mark_unhealthy(self.db, self.ad, server, "quarantined",
                                        {"violations": kinds, "count": len(fresh)}, health="QUARANTINED")
                found += [{"server": server, **v} for v in fresh]
        return found
