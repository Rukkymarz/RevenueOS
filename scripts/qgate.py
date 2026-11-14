"""Q-gate runner (spec 1.9): runs Q1-Q7 and writes a JSON verdict per gate.

Verdicts: PASS, FAIL, DO_NOT_FILE (the gate did not run or produced no evidence),
NOT_APPLICABLE (the gate's subject is built in a later phase; named with that phase).
A gate is never PASS without evidence. Exit code is non-zero on any FAIL or DO_NOT_FILE.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE = int(sys.argv[1]) if len(sys.argv) > 1 else 1

GATES = {
    "Q1": {"name": "schema validation of every payload", "cmd": ["pytest", "-q", "tests/connectivity", "packages/contracts/python/tests"]},
    "Q2": {"name": "unit + integration tests with coverage", "cmd": [
        "pytest", "-q", "tests", "--cov", "--cov-report=json:coverage.json"], "then": ["python", "scripts/coverage_gate.py", "coverage.json"]},
    "Q3": {"name": "EvalForge suites, no regression", "from_phase": 8},
    "Q4": {"name": "GitReins resolution gate", "from_phase": 8},
    "Q5": {"name": "veripipe fail-closed (missing telemetry -> DO_NOT_FILE)", "from_phase": 8},
    "Q6": {"name": "invariant suite INV-01..INV-15", "cmd": ["pytest", "-q", "tests/invariants"]},
    "Q7": {"name": "threat-model tests + secret scan", "cmd": ["pytest", "-q", "tests/threats"]},
}


def run(cmd):
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError as e:
        return None, str(e)
    return r.returncode, (r.stdout + r.stderr)[-4000:]


def main() -> int:
    results = {}
    for gid, g in GATES.items():
        if g.get("from_phase", 0) > PHASE:
            results[gid] = {"name": g["name"], "verdict": "NOT_APPLICABLE", "detail": f"subject lands in Phase {g['from_phase']}"}
            continue
        code, out = run(g["cmd"])
        if code is None:
            results[gid] = {"name": g["name"], "verdict": "DO_NOT_FILE", "detail": out}
            continue
        if code == 0 and "then" in g:
            code, more = run(g["then"])
            out += "\n" + (more or "")
        if code is None:
            verdict = "DO_NOT_FILE"
        elif code == 5:   # pytest: no tests collected -> no evidence
            verdict = "DO_NOT_FILE"
        else:
            verdict = "PASS" if code == 0 else "FAIL"
        results[gid] = {"name": g["name"], "verdict": verdict, "tail": out.strip().splitlines()[-3:]}
    out = ROOT / "docs" / "reviews" / f"phase-{PHASE}-qgates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n")
    for gid, r in results.items():
        print(f"{gid} {r['verdict']:15s} {r['name']}")
    return 1 if any(r["verdict"] in ("FAIL", "DO_NOT_FILE") for r in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
