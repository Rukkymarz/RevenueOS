"""Shared pytest setup: make workspace packages importable without installation and
expose the database fixtures from dbkit to every test directory."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
for p in ["packages/pycommon", "packages/mcp-common", "packages/contracts/python", "infra/egress",
          "infra/sandbox-supervisor", *(str(d.relative_to(ROOT)) for d in sorted((ROOT / "services").iterdir()) if d.is_dir()),
          *(str(d.relative_to(ROOT)) for d in sorted((ROOT / "mcp").iterdir()) if d.is_dir())]:
    sys.path.insert(0, str(ROOT / p))

from dbkit import db, template_db, world  # noqa: E402,F401  (fixtures)
