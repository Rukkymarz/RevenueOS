"""Isolated browser profiles (INV-09). Each agent gets its own profile directory under the
profile root: a private Chromium user-data dir (independent cookies, local storage, cache) and
a fingerprint seed the Phase 3 runtimes apply at launch. Profiles are never shared, never a
human's, and rotate by creating a new profile and retiring the old one."""
import json
import os
import random
import uuid
from pathlib import Path

LOCALES = ["en-US", "en-GB", "en-CA", "en-AU"]
TIMEZONES = ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "Europe/London"]
VIEWPORTS = [(1366, 768), (1440, 900), (1536, 864), (1920, 1080), (1280, 800)]


def fingerprint(seed: int) -> dict:
    rng = random.Random(seed)
    w, h = rng.choice(VIEWPORTS)
    return {"seed": seed, "locale": rng.choice(LOCALES), "timezone": rng.choice(TIMEZONES),
            "viewport": {"width": w, "height": h}, "device_scale_factor": rng.choice([1, 1, 1.25, 2]),
            "hardware_concurrency": rng.choice([4, 8, 12, 16])}


def create_profile(root: Path | str, agent_id: str) -> Path:
    """Create root/<agent>/<profile> (0700) with an empty user-data dir and a fingerprint."""
    agent_dir = Path(root) / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = agent_dir / str(uuid.uuid4())
    path.mkdir(mode=0o700)
    (path / "user-data").mkdir(mode=0o700)
    seed = int.from_bytes(os.urandom(8), "big")
    (path / "profile.json").write_text(json.dumps({"agent_id": agent_id, "fingerprint": fingerprint(seed),
                                                   "user_data_dir": "user-data"}, indent=2))
    os.chmod(path / "profile.json", 0o600)
    return path
