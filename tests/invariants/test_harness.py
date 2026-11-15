"""Spec 1.9: exactly fifteen invariant files, one per INV, each with a real attack body.
A file passes only if it has at least one test whose body asserts or expects a rejection,
and no test is a tautology such as `assert True`."""
import ast
import re
from pathlib import Path

HERE = Path(__file__).parent
FILES = sorted(HERE.glob("test_inv[0-9][0-9]_*.py"))


def _is_trivial(node: ast.Assert) -> bool:
    return isinstance(node.test, ast.Constant) and bool(node.test.value)


def _real_assertions(fn: ast.FunctionDef) -> int:
    n = 0
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert) and not _is_trivial(node):
            n += 1
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in ("pytest.raises", "db.rejects") or name.endswith(".rejects"):
                n += 1
    return n


def test_exactly_fifteen_invariant_files_one_per_inv():
    numbers = [int(re.match(r"test_inv(\d\d)_", f.name).group(1)) for f in FILES]
    assert sorted(numbers) == list(range(1, 16)), f"invariant files present: {numbers}"


def test_every_invariant_file_contains_real_attacks():
    for f in FILES:
        tree = ast.parse(f.read_text())
        tests = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        assert tests, f"{f.name} has no tests"
        for fn in tests:
            assert _real_assertions(fn) > 0, f"{f.name}::{fn.name} has no real assertion"
            assert not any(isinstance(n, ast.Assert) and _is_trivial(n) for n in ast.walk(fn)), \
                f"{f.name}::{fn.name} contains a tautological assert"
