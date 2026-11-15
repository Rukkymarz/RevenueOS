"""Secret scan over emitted telemetry (spec 2.4): OTel traces, service logs, any text output.

Fails if any live secret value (every file in the keychain dir, plus extra files given with
--secret-file) or any leak pattern from the repo scan appears in the scanned files. Scanning
nothing is not a pass: with no trace file present the verdict is DO_NOT_FILE (INV-05).

usage: scan_traces.py --keychain DIR [--secret-file F ...] [--require F ...] PATH [PATH ...]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "threats"))
from test_secret_hygiene import PATTERNS  # noqa: E402  (one pattern list for repo and traces)

MIN_LEN = 8


def secret_values(keychain: Path, extra: list[Path]) -> dict[str, str]:
    out = {}
    for f in [*sorted(p for p in keychain.iterdir() if p.is_file()), *extra]:
        v = f.read_text().strip()
        if f.name == "api-principals" or len(v) < MIN_LEN:
            continue   # digests only, or too short to match meaningfully
        out[f.name] = v
    return out


def scan(paths: list[Path], secrets: dict[str, str]) -> list[str]:
    findings = []
    for p in paths:
        for f in ([p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file())):
            text = f.read_text(errors="replace")
            for name, value in secrets.items():
                if value in text:
                    findings.append(f"{f}: value of keychain secret '{name}'")
            for label, rx in PATTERNS.items():
                if rx.search(text):
                    findings.append(f"{f}: {label}")
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keychain", type=Path, required=True)
    ap.add_argument("--secret-file", type=Path, action="append", default=[])
    ap.add_argument("--require", type=Path, action="append", default=[], help="file that must exist and be non-empty")
    ap.add_argument("paths", type=Path, nargs="+")
    a = ap.parse_args(argv)
    missing = [str(r) for r in a.require if not r.is_file() or r.stat().st_size == 0]
    if missing:
        print(json.dumps({"verdict": "DO_NOT_FILE", "reason": f"nothing to scan: {missing}"}))
        return 1
    findings = scan([p for p in a.paths if p.exists()], secret_values(a.keychain, a.secret_file))
    print(json.dumps({"verdict": "FAIL" if findings else "PASS", "findings": findings}))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
