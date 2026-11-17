"""Read-only view of config/components.yaml for services and health checks."""
import os
from functools import lru_cache
from pathlib import Path

import yaml


def _config_dir() -> Path:
    env = os.environ.get("REVENUEOS_CONFIG_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "components.yaml").exists():
            return parent / "config"
    raise FileNotFoundError("config/components.yaml not found; set REVENUEOS_CONFIG_DIR")


@lru_cache(maxsize=1)
def components() -> list[dict]:
    return yaml.safe_load((_config_dir() / "components.yaml").read_text())["components"]


def components_for(component_id: str) -> list[str]:
    return sorted(c["id"] for c in components() if c["component"] == component_id)


def config_loaded() -> bool:
    return len(components()) > 0
