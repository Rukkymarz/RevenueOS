"""Pure-function units of the NAVA gateway: argument validation, workspace snapshots,
postconditions. No database."""
from pathlib import Path

from revenueos_runtime_os.nava import CallContext, Workspaces, check_postconditions, tree_hash, validate_args

SCHEMA = {"type": "object", "required": ["name"], "additionalProperties": False,
          "properties": {"name": {"type": "string", "maxLength": 8}, "n": {"type": "integer"},
                         "tags": {"type": "array", "items": {"type": "string"}},
                         "kind": {"type": "string", "enum": ["a", "b"]}}}


def test_validate_args():
    assert validate_args(SCHEMA, {"name": "x"}) is None
    assert validate_args(SCHEMA, {"name": "x", "n": 3, "tags": ["t"], "kind": "a"}) is None
    assert "must be an object" in validate_args(SCHEMA, [1])
    assert "missing required" in validate_args(SCHEMA, {})
    assert "unknown argument" in validate_args(SCHEMA, {"name": "x", "zz": 1})
    assert "must be string" in validate_args(SCHEMA, {"name": 3})
    assert "must be integer" in validate_args(SCHEMA, {"name": "x", "n": True})   # bool is not an int here
    assert "array of string" in validate_args(SCHEMA, {"name": "x", "tags": [1]})
    assert "one of" in validate_args(SCHEMA, {"name": "x", "kind": "c"})
    assert "longer than" in validate_args(SCHEMA, {"name": "toolongname"})


def test_tree_hash_and_snapshot_roundtrip(tmp_path):
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    a = ws.path("agent1", "w")
    a.mkdir(parents=True)
    (a / "f.txt").write_text("one")
    (a / "sub").mkdir()
    (a / "sub" / "g.txt").write_text("two")
    h0 = tree_hash(a)
    snap_hash = ws.snapshot("sc1", [ws.resource("agent1", "w")])
    assert ws.current_hash("sc1") == snap_hash
    (a / "f.txt").write_text("CHANGED")
    (a / "new.bin").write_bytes(b"\x00")
    assert ws.current_hash("sc1") != snap_hash
    assert ws.restore("sc1") == snap_hash                 # restore returns the real post-state hash
    assert tree_hash(a) == h0 and not (a / "new.bin").exists()
    ws.discard("sc1")
    assert not ws.has_snapshot("sc1")


def test_snapshot_of_absent_workspace_restores_to_absent(tmp_path):
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    res = ws.resource("agent1", "fresh")
    ws.snapshot("sc2", [res])
    p = ws.path("agent1", "fresh")
    p.mkdir(parents=True)
    (p / "x").write_text("x")
    ws.restore("sc2")
    assert not p.exists()                                  # created by the call -> rolled back to absent


def test_workspace_names_are_plain(tmp_path):
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    for bad in ("", "..", "a/b", "x" * 65):
        try:
            ws.path("agent1", bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def _ctx(ws):
    return CallContext("sc", "agent1", "task1", "auto", None, ws)


def test_postconditions(tmp_path):
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    root = ws.path("agent1", "w")
    root.mkdir(parents=True)
    (root / "out.txt").write_text("hello world")
    ctx, args = _ctx(ws), {"workspace": "w"}
    ok = {"exit_code": 0, "stdout": "built fine"}
    assert check_postconditions([{"exit_code": 0}], ok, ctx, args) is None
    assert "exit code" in check_postconditions([{"exit_code": 0}], {"exit_code": 2}, ctx, args)
    assert check_postconditions([{"stdout_contains": "built"}], ok, ctx, args) is None
    assert "lacks" in check_postconditions([{"stdout_contains": "zzz"}], ok, ctx, args)
    assert check_postconditions([{"file_exists": "out.txt"}], ok, ctx, args) is None
    assert "does not exist" in check_postconditions([{"file_exists": "nope"}], ok, ctx, args)
    assert check_postconditions([{"file_absent": "nope"}], ok, ctx, args) is None
    assert check_postconditions([{"file_contains": ["out.txt", "hello"]}], ok, ctx, args) is None
    assert "lacks" in check_postconditions([{"file_contains": ["out.txt", "bye"]}], ok, ctx, args)
    assert "escapes" in check_postconditions([{"file_exists": "../../etc/passwd"}], ok, ctx, args)
    assert "malformed" in check_postconditions([{"a": 1, "b": 2}], ok, ctx, args)
    assert "unknown postcondition" in check_postconditions([{"net_zero": True}], ok, ctx, args)
    assert "needs a workspace" in check_postconditions([{"file_exists": "x"}], ok, ctx, {})
