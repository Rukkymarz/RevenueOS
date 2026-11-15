"""Contract round trip, Python side (runs between the TS ts1 and ts2 steps).

Valid fixtures and the TypeScript output must both validate with the generated
pydantic models and survive a dump/re-validate cycle unchanged; invalid
fixtures must be rejected. Output goes to out/py for the ts2 step.
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from revenueos_contracts import models

PKG = Path(__file__).resolve().parents[2]
FIXTURES = PKG / "fixtures"
CASES = [(d.name, f) for d in sorted(FIXTURES.iterdir()) for f in sorted((d / "valid").iterdir())]
BAD = [(d.name, f) for d in sorted(FIXTURES.iterdir()) for f in sorted((d / "invalid").iterdir())]


def model(name):
    m = getattr(models, name, None)
    assert m is not None, f"generated models lack {name}"
    return m


def dump(obj):
    return json.loads(obj.model_dump_json(exclude_unset=True, by_alias=True))


@pytest.mark.parametrize("name,path", CASES, ids=lambda x: x if isinstance(x, str) else x.name)
def test_valid_fixture_and_ts_output_round_trip(name, path):
    original = json.loads(path.read_text())
    m = model(name)
    from_fixture = dump(m.model_validate(original))
    ts_out = PKG / "out" / "ts" / name / path.name
    assert ts_out.exists(), "run the TypeScript ts1 step first"
    from_ts = dump(m.model_validate(json.loads(ts_out.read_text())))
    assert from_ts == from_fixture, f"{name}/{path.name}: TS output differs after Python validation"
    assert dump(m.model_validate(from_ts)) == from_ts
    out = PKG / "out" / "py" / name
    out.mkdir(parents=True, exist_ok=True)
    (out / path.name).write_text(json.dumps(from_ts, sort_keys=True))


@pytest.mark.parametrize("name,path", BAD, ids=lambda x: x if isinstance(x, str) else x.name)
def test_invalid_fixture_rejected_at_boundary(name, path):
    with pytest.raises(ValidationError):
        model(name).model_validate(json.loads(path.read_text()))
