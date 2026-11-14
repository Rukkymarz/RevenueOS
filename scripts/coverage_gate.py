"""Q2 coverage gate: >= 80% line coverage per service/package, >= 90% for services/qc.
Reads coverage.json (pytest --cov ... --cov-report=json). Exits non-zero naming every miss."""
import json
import sys
from collections import defaultdict

THRESHOLDS = {"services/qc": 90.0}
DEFAULT = 80.0


def unit(path: str) -> str:
    parts = path.split("/")
    if parts[0] in ("services", "mcp") or (parts[0] == "infra" and len(parts) > 1):
        return "/".join(parts[:2])
    if parts[0] == "packages":
        return "/".join(parts[:2])
    return parts[0]


def main(report="coverage.json") -> int:
    data = json.load(open(report))
    covered, total = defaultdict(int), defaultdict(int)
    for path, f in data["files"].items():
        u = unit(path)
        covered[u] += f["summary"]["covered_lines"]
        total[u] += f["summary"]["num_statements"]
    failed = []
    for u in sorted(total):
        pct = 100.0 * covered[u] / total[u] if total[u] else 100.0
        need = THRESHOLDS.get(u, DEFAULT)
        print(f"{u:40s} {pct:6.1f}%  (need {need:.0f}%)")
        if pct < need:
            failed.append(u)
    if failed:
        print("coverage below threshold: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
