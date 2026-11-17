"""Record a security scanner verdict (D10, Addendum H). A scan that did not run is DO_NOT_FILE,
never PASS; DO_NOT_FILE and FAIL exit non-zero so the check blocks merge.

usage: security_verdict.py <scanner> <PASS|FAIL|DO_NOT_FILE|NOT_APPLICABLE> <reason>
"""
import json
import sys
from pathlib import Path

scanner, verdict, reason = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])
assert verdict in ("PASS", "FAIL", "DO_NOT_FILE", "NOT_APPLICABLE"), verdict
out = Path(".security") / f"{scanner}.verdict.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"scanner": scanner, "verdict": verdict, "reason": reason}, indent=2) + "\n")
print(f"{scanner}: {verdict} - {reason}")
sys.exit(1 if verdict in ("FAIL", "DO_NOT_FILE") else 0)
