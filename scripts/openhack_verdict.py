"""D10 verdict for an OpenHack report. PASS only for a completed scan with no high/critical
finding; an unfinished, failed, missing or malformed scan is DO_NOT_FILE, never PASS."""
import json
import subprocess
import sys
from pathlib import Path

VERDICT = [sys.executable, str(Path(__file__).with_name("security_verdict.py")), "openhack"]


def main(path: str) -> int:
    p = Path(path)
    if not p.is_file():
        return subprocess.call(VERDICT + ["DO_NOT_FILE", "no report produced"])
    try:
        data = json.loads(p.read_text())
    except ValueError:
        return subprocess.call(VERDICT + ["DO_NOT_FILE", "report is not JSON"])
    findings = data.get("findings")
    if not isinstance(findings, list):
        return subprocess.call(VERDICT + ["DO_NOT_FILE", "unrecognized report shape"])
    high = [f for f in findings if str(f.get("severity", "")).lower() in ("high", "critical")]
    for f in high:
        print(f"::error title=OpenHack {f.get('severity')}::{f.get('category')} @ {f.get('file_path')}")
    if high:   # a confirmed finding blocks even if the scan stopped early
        return subprocess.call(VERDICT + ["FAIL", f"{len(high)} high/critical of {len(findings)}"])
    if data.get("status") != "completed":
        return subprocess.call(VERDICT + ["DO_NOT_FILE", f"scan did not complete (status {data.get('status')!r})"])
    tokens = (data.get("cost") or {}).get("total_tokens") or 0
    if tokens <= 0:   # every step "completed" without one model call: the scan never looked at anything
        for e in [t for t in data.get("trace", []) if "error" in str(t).lower()][-10:]:
            print(f"::warning title=OpenHack trace::{str(e)[:400]}")
        return subprocess.call(VERDICT + ["DO_NOT_FILE", "scan made no model calls (0 tokens): nothing was analysed"])
    return subprocess.call(VERDICT + ["PASS", f"completed; 0 high/critical of {len(findings)}"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
