"""Canonical JSON (RFC 8785) and argument hashing.

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


MAX_SAFE_INT = 2 ** 53 - 1


def _es_number(x) -> str:
    """Serialize a number exactly as ECMAScript Number.prototype.toString does (RFC 8785 sec 3.2.2.3),
    so Python and TypeScript produce byte-identical canonical JSON."""
    if isinstance(x, bool):
        raise TypeError("bool is not a number")
    if isinstance(x, int):
        if abs(x) > MAX_SAFE_INT:
            raise ValueError(f"integer {x} exceeds the IEEE-754 safe range and cannot be canonicalized")
        x = float(x)
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    from decimal import Decimal
    tup = Decimal(repr(abs(x))).normalize().as_tuple()   # shortest round-trip digits
    digits = "".join(map(str, tup.digits)).rstrip("0") or "0"
    k = len(digits)
    n = len(tup.digits) + tup.exponent                   # value = 0.digits * 10^n
    if k <= n <= 21:
        s = digits + "0" * (n - k)
    elif 0 < n <= 21:
        s = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        s = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mant = digits[0] + ("." + digits[1:] if k > 1 else "")
        s = f"{mant}e{'+' if e > 0 else '-'}{abs(e)}"
    return sign + s


def _es_string(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _utf16_key(k: str) -> bytes:
    return k.encode("utf-16-be")


def _encode(obj) -> str:
    if obj is None:
        return "null"
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if isinstance(obj, (int, float)):
        return _es_number(obj)
    if isinstance(obj, str):
        return _es_string(obj)
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_encode(v) for v in obj) + "]"
    if isinstance(obj, dict):
        items = sorted(obj.items(), key=lambda kv: _utf16_key(kv[0]))
        return "{" + ",".join(_es_string(k) + ":" + _encode(v) for k, v in items) + "}"
    raise ValueError(f"unsupported type {type(obj).__name__}")


def canonical_json(obj) -> bytes:
    """RFC 8785 JSON Canonicalization Scheme: sorted keys (UTF-16 order), no insignificant
    whitespace, ECMAScript number formatting, UTF-8. Identical to packages/contracts canonicalize()."""
    _check(obj)
    return _encode(obj).encode("utf-8")


def args_hash(obj) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def redact(obj):
    """Copy of obj with secret-looking keys masked, for human-readable previews and logs."""
    if isinstance(obj, dict):
        return {k: ("[redacted]" if _SECRETISH.search(k) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj
