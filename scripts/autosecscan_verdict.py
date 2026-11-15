"""Turn an AutoSecScan JSON report into a D10 verdict and print every blocking finding.

Blocking = severity high or critical (the triaged severity when present) and not marked a likely
false positive. No report means the scan did not run: DO_NOT_FILE, never PASS.
"""
import json
import subprocess
import sys
from pathlib import Path

BLOCKING = {"high", "critical"}


def findings(node):
    if isinstance(node, dict):
        if "severity" in node and "title" in node:
            yield node
        for v in node.values():
            yield from findings(v)
    elif isinstance(node, list):
        for v in node:
            yield from findings(v)


def severity(f) -> str:
    return str(f.get("ai_severity") or f.get("severity") or "").lower().split(".")[-1]


def main(out_dir: str) -> int:
    reports = sorted(Path(out_dir).glob("scan-*.json"))
    verdict = [sys.executable, str(Path(__file__).with_name("security_verdict.py")), "autosecscan"]
    if not reports:
        return subprocess.call(verdict + ["DO_NOT_FILE", "scanner produced no report"])
    data = json.loads(reports[-1].read_text())
    all_f = list(findings(data))
    block = [f for f in all_f if severity(f) in BLOCKING and f.get("ai_is_real") is not False]
    for f in block:
        print(f"::error title=AutoSecScan {severity(f)}::[{f.get('scanner')}] {f.get('title')} @ {f.get('location')}")
    if block:
        return subprocess.call(verdict + ["FAIL", f"{len(block)} high/critical of {len(all_f)} findings"])
    return subprocess.call(verdict + ["PASS", f"0 high/critical of {len(all_f)} findings"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
