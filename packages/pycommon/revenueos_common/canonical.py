"""Canonical JSON and argument hashing.

The approval service, the receipt writer, and the database all bind to the
SHA-256 of the canonical form, so a single changed byte in a tool call's
arguments produces a different hash and voids the approval (INV-06).
"""
import hashlib
import json
import math
import re

_SECRETISH = re.compile(r"(secret|token|password|passwd|api[_-]?key|authorization|cookie|private[_-]?key)", re.I)


def _check(obj, path="$"):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        raise ValueError(f"non-finite number at {path} cannot be canonicalized")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise ValueError(f"non-string key at {path}")
            _check(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check(v, f"{path}[{i}]")
    elif not isinstance(obj, (str, int, float, bool)) and obj is not None:
        raise ValueError(f"unsupported type {type(obj).__name__} at {path}")


def canonical_json(obj) -> bytes:
    """Sorted keys, no insignificant whitespace, UTF-8, finite numbers only."""
    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def args_hash(obj) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def redact(obj):
    """Copy of obj with secret-looking keys masked, for human-readable previews and logs."""
    if isinstance(obj, dict):
        return {k: ("[redacted]" if _SECRETISH.search(k) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj
