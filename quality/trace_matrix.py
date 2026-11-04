#!/usr/bin/env python3
"""Regenerate the requirements traceability matrix (requirements -> code -> tests).

The only hand-maintained input is ``quality/requirements.json``. Each requirement
lists code references (``path::symbol``) and test-name patterns
(``tests/<file>::<test function>``, ``*`` allowed). This script reads the test
files with ``ast`` (it never imports or runs them), resolves the patterns to real
test names and writes ``quality/TRACEABILITY_MATRIX.md``.

It fails (exit 1) when the traceability is broken:
  * a requirement has no test;
  * a test pattern matches no test, or a code reference does not exist;
  * a test is not linked to any requirement ("orphan test").

Usage:
    python quality/trace_matrix.py            # rewrite the matrix
    python quality/trace_matrix.py --check    # fail if the matrix on disk is stale
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "quality" / "requirements.json"
MATRIX = ROOT / "quality" / "TRACEABILITY_MATRIX.md"


@dataclass(frozen=True)
class TestFn:
    id: str        # "tests/test_x.py::test_name"
    cases: int     # 1, or the number of parametrized cases


@dataclass
class Result:
    requirements: list[dict]
    tests: list[TestFn]
    links: dict[str, list[str]]            # requirement id -> test ids
    errors: list[str] = field(default_factory=list)


def load_requirements(path: Path = REQUIREMENTS) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [r["id"] for r in data["requirements"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate requirement id in " + str(path))
    return data["requirements"]


def _case_count(fn: ast.FunctionDef) -> int:
    """Number of cases a literal ``pytest.mark.parametrize`` list expands to."""
    total = 1
    for dec in fn.decorator_list:
        call = dec if isinstance(dec, ast.Call) else None
        if call is None or not isinstance(call.func, ast.Attribute):
            continue
        if call.func.attr != "parametrize" or len(call.args) < 2:
            continue
        values = call.args[1]
        if isinstance(values, (ast.List, ast.Tuple)):
            total *= len(values.elts)
    return total


def collect_tests(root: Path = ROOT) -> list[TestFn]:
    found = []
    for path in sorted((root / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                found.append(TestFn(f"tests/{path.name}::{node.name}", _case_count(node)))
    return found


def symbol_exists(root: Path, ref: str) -> bool:
    """``path`` must exist; ``path.py::Name`` or ``::Class.method`` must be defined."""
    rel, _, symbol = ref.partition("::")
    path = root / rel
    if not path.is_file():
        return False
    if not symbol:
        return True
    if path.suffix != ".py":
        return False
    scope = ast.parse(path.read_text(encoding="utf-8")).body
    for part in symbol.split("."):
        nxt = None
        for node in scope:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == part:
                nxt = node
            elif isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == part for t in node.targets):
                nxt = node
            if nxt is not None:
                break
        if nxt is None:
            return False
        scope = getattr(nxt, "body", [])
    return True


def build(root: Path = ROOT, requirements: list[dict] | None = None) -> Result:
    requirements = load_requirements(root / "quality" / "requirements.json") \
        if requirements is None else requirements
    tests = collect_tests(root)
    result = Result(requirements, tests, {})
    linked: set[str] = set()
    for req in requirements:
        matched: list[str] = []
        for pattern in req.get("tests", []):
            hits = [t.id for t in tests if fnmatch.fnmatchcase(t.id, pattern)]
            if not hits:
                result.errors.append(f"{req['id']}: test pattern matches nothing: {pattern}")
            matched += [h for h in hits if h not in matched]
        if not matched:
            result.errors.append(f"{req['id']}: no test is linked to this requirement")
        for ref in req.get("code", []):
            if not symbol_exists(root, ref):
                result.errors.append(f"{req['id']}: code reference not found: {ref}")
        result.links[req["id"]] = matched
        linked.update(matched)
    for t in tests:
        if t.id not in linked:
            result.errors.append(f"orphan test, linked to no requirement: {t.id}")
    return result


def _short(test_id: str) -> str:
    return test_id.split("::", 1)[1]


def render(result: Result) -> str:
    by_id = {t.id: t for t in result.tests}
    total_cases = sum(t.cases for t in result.tests)
    lines = [
        "# Requirements Traceability Matrix",
        "",
        "| | |",
        "| --- | --- |",
        "| Document | QMS-RTM-001 |",
        "| System | Engineering Stamp Placer (computer-vision-layout-stamping-system) |",
        "| Status | GENERATED. Do not edit by hand. |",
        "",
        "> Generated by `python quality/trace_matrix.py` from "
        "[`requirements.json`](requirements.json) and the test names in `tests/`. "
        "CI fails if this file is out of date, a requirement has no test, or a test "
        "is linked to no requirement.",
        "",
        f"**Summary:** {len(result.requirements)} requirements, "
        f"{len(result.tests)} test functions ({total_cases} test cases once "
        "parametrized tests are expanded), "
        f"{len(result.errors)} traceability errors.",
        "",
        "## Requirements to code to tests",
        "",
        "| ID | Requirement | Risk | Code | Verifying tests (cases) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for req in result.requirements:
        code = "<br>".join(f"`{c}`" for c in req.get("code", []))
        tests = "<br>".join(
            f"`{_short(t)}`" + (f" ({by_id[t].cases})" if by_id[t].cases > 1 else "")
            for t in result.links[req["id"]])
        text = req["text"].replace("|", "\\|")
        lines.append(f"| {req['id']} | **{req['title']}.** {text} | {req['risk']} | {code} | {tests} |")
    lines += ["", "## Tests to requirements (reverse view)", "",
              "| Test file | Test | Cases | Requirements |", "| --- | --- | ---: | --- |"]
    reverse: dict[str, list[str]] = {t.id: [] for t in result.tests}
    for rid, ids in result.links.items():
        for tid in ids:
            reverse[tid].append(rid)
    for t in result.tests:
        file, name = t.id.split("::", 1)
        reqs = ", ".join(reverse[t.id]) or "**NONE (orphan)**"
        lines.append(f"| `{file}` | `{name}` | {t.cases} | {reqs} |")
    if result.errors:
        lines += ["", "## Traceability errors", ""] + [f"- {e}" for e in result.errors]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="do not write; fail if the matrix on disk is out of date")
    args = ap.parse_args(argv)
    result = build()
    text = render(result)
    for err in result.errors:
        print("ERROR:", err, file=sys.stderr)
    if args.check:
        current = MATRIX.read_text(encoding="utf-8") if MATRIX.exists() else ""
        if current != text:
            print("ERROR: quality/TRACEABILITY_MATRIX.md is out of date; "
                  "run python quality/trace_matrix.py", file=sys.stderr)
            return 1
    else:
        MATRIX.write_text(text, encoding="utf-8")
        print(f"wrote {MATRIX.relative_to(ROOT)}: {len(result.requirements)} requirements, "
              f"{len(result.tests)} tests")
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
