"""The Agency roster as served to the Command Center (Addendum A5): config/agents.yaml plus each
agent's companion markdown, read from the repository files baked into the image."""
import os
from pathlib import Path

import yaml


def root() -> Path:
    return Path(os.environ.get("REVENUEOS_CONFIG_DIR", "/src/config")).parent


def load(base: Path | None = None) -> list[dict]:
    base = base or root()
    agents = yaml.safe_load((base / "config" / "agents.yaml").read_text())["agents"]
    out = []
    for a in agents:
        f = base / a["companion"]
        out.append({**a, "markdown": f.read_text() if f.exists() else ""})
    return out
