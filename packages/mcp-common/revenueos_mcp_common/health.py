"""Package self-check (spec 1.1) for revenueos-mcp-common."""
from .server import RISK_CLASSES, TOOL_NAME


def health() -> dict:
    ok = TOOL_NAME.match("probe_echo") is not None and TOOL_NAME.match("a.b") is None and len(RISK_CLASSES) == 4
    return {"service": "revenueos-mcp-common", "status": "ok" if ok else "degraded", "version": "0.1.0",
            "checks": {"tool_names": "ok" if ok else "failed"}}
