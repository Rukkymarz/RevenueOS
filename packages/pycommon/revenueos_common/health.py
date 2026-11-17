"""Package self-check (spec 1.1) for revenueos-common."""
from . import VERSION
from .canonical import canonical_json


def health() -> dict:
    ok = canonical_json({"b": 1.0, "a": [1e-7, "é"]}).decode() == '{"a":[1e-7,"é"],"b":1}'
    return {"service": "revenueos-common", "status": "ok" if ok else "degraded", "version": VERSION,
            "checks": {"canonical": "ok" if ok else "failed"}}
