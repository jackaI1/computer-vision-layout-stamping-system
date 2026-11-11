#!/usr/bin/env python3
"""Requirements management and traceability for the stamp placer.

This is a small, free stand-in for what IBM DOORS does: it imports requirements
from CSV or ReqIF, keeps their IDs stable, links each requirement to the design
element (``code``) and automated tests that verify it, saves baselines and
reports the gaps.

Commands (run from the repository root):

    python quality/rtm.py check                    # DXL-style rules; exit 1 on any FAIL
    python quality/rtm.py coverage [--baseline B]  # coverage matrix as Markdown
    python quality/rtm.py baseline save NAME       # snapshot requirements.json
    python quality/rtm.py diff OLD.json [NEW.json] # changes and gaps between baselines
    python quality/rtm.py import FILE [--write]    # read CSV/ReqIF; --write merges it
    python quality/rtm.py export FILE              # write requirements.json as CSV or ReqIF

``check`` is the gate CI runs. Its rules are written as small named functions
over each requirement, and it prints one PASS or FAIL line per rule, the way a
DOORS DXL script reports on every object in a module.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rtm_import as ri  # noqa: E402
import trace_matrix as tm  # noqa: E402

REQUIREMENTS = tm.REQUIREMENTS
REGISTRY = ROOT / "quality" / "rtm_ids.json"
BASELINES = ROOT / "quality" / "baselines"
TRACKED = ("title", "text", "risk", "code", "tests")


def load(path: Path | None = None) -> list[dict]:
    return tm.load_requirements(path or REQUIREMENTS)


def _load_baseline(name_or_path: str) -> list[dict]:
    path = Path(name_or_path)
    if not path.suffix:
        path = BASELINES / f"{name_or_path}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["requirements"] if isinstance(data, dict) else data


# --- DXL-style rules ----------------------------------------------------------

def _linked_tests(req: dict, result: tm.Result) -> list[str]:
    return result.links.get(req["id"], [])


def _has_broken_reference(req: dict, res: tm.Result) -> bool:
    return any(e.startswith(req["id"] + ":") and ("not found" in e or "matches nothing" in e)
               for e in res.errors)


# Each rule is checked for every requirement. The orphan-test rule looks at the
# test files instead, so it is checked once for the whole set in check().
RULES = [
    ("R1 every requirement names a design element",
     lambda req, res: bool(req.get("code"))),
    ("R2 every requirement has an automated test",
     lambda req, res: bool(_linked_tests(req, res))),
    ("R3 every design element and test pattern resolves",
     lambda req, res: not _has_broken_reference(req, res)),
]


def check(requirements: list[dict], root: Path = ROOT, out=sys.stdout) -> int:
    """Run the rules over every requirement. Return 1 if any rule fails."""
    res = tm.build(root, requirements)
    failures = 0
    for name, rule in RULES:
        bad = [r["id"] for r in requirements if not rule(r, res)]
        failures += bool(bad)
        print(f"{'FAIL' if bad else 'PASS'} {name} ({len(requirements) - len(bad)}/{len(requirements)})",
              file=out)
        for item in bad:
            print(f"     {item}", file=out)
    orphans = [e.split(": ", 1)[1] for e in res.errors if e.startswith("orphan test")]
    failures += bool(orphans)
    total = len(res.tests)
    print(f"{'FAIL' if orphans else 'PASS'} R4 every test belongs to a requirement "
          f"({total - len(orphans)}/{total})", file=out)
    for item in orphans:
        print(f"     {item}", file=out)
    return 1 if failures else 0


# --- coverage matrix and baseline diff -----------------------------------------

def diff(old: list[dict], new: list[dict]) -> dict:
    """Changes between two requirement sets, with the gaps they open."""
    old_by, new_by = {r["id"]: r for r in old}, {r["id"]: r for r in new}
    added = [i for i in new_by if i not in old_by]
    removed = [i for i in old_by if i not in new_by]
    changed = {}
    for i in new_by:
        if i in old_by:
            fields = [f for f in TRACKED if old_by[i].get(f) != new_by[i].get(f)]
            if fields:
                changed[i] = fields
    gaps = [f"{i}: added without an automated test" for i in added if not new_by[i].get("tests")]
    gaps += [f"{i}: text changed but its tests did not, so re-check the test still proves it"
             for i, f in changed.items() if "text" in f and old_by[i].get("tests") == new_by[i].get("tests")]
    gaps += [f"{i}: removed, but its tests are still in the repository"
             for i in removed if old_by[i].get("tests")]
    return {"added": added, "removed": removed, "changed": changed, "gaps": gaps}


def coverage_markdown(requirements: list[dict], baseline: list[dict] | None = None,
                      root: Path = ROOT) -> tuple[str, int]:
    res = tm.build(root, requirements)
    change = {}
    if baseline is not None:
        d = diff(baseline, requirements)
        change = {i: "added" for i in d["added"]}
        change.update({i: "changed: " + ", ".join(f) for i, f in d["changed"].items()})
    rows = ["| ID | Requirement | Design elements | Tests | Status | Since baseline |",
            "| --- | --- | ---: | ---: | --- | --- |"]
    gaps = 0
    for req in requirements:
        errors = [e for e in res.errors if e.startswith(req["id"] + ":")]
        tests = len(_linked_tests(req, res))
        if not req.get("code"):
            status = "UNTRACED"
        elif not tests:
            status = "NO TEST"
        elif errors:
            status = "BROKEN LINK"
        else:
            status = "OK"
        gaps += status != "OK"
        rows.append(f"| {req['id']} | {req['title']} | {len(req.get('code', []))} | {tests} "
                    f"| {status} | {change.get(req['id'], '')} |")
    if baseline is not None:
        for rid in diff(baseline, requirements)["removed"]:
            rows.append(f"| {rid} | (removed since baseline) | | | ORPHANED | removed |")
            gaps += 1
    orphan_tests = [e for e in res.errors if e.startswith("orphan test")]
    gaps += len(orphan_tests)
    summary = (f"**Summary:** {len(requirements)} requirements; {gaps} item(s) with a gap "
               f"(untraced, no test, broken link, orphaned or orphan test).")
    lines = ["# Requirement coverage", "", summary, ""] + rows
    if orphan_tests:
        lines += ["", "Orphan tests:"] + [f"- {e.split(': ', 1)[1]}" for e in orphan_tests]
    return "\n".join(lines) + "\n", gaps


# --- command line --------------------------------------------------------------

def _to_project_record(rec: dict) -> dict:
    return {k: rec[k] for k in ("id", "title", "text", "risk", "code", "tests")}


def cmd_import(args) -> int:
    records = ri.load(Path(args.file))
    current = load()
    existing = {r["id"] for r in current}
    registry = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
    stamped = ri.assign_ids(records, registry, existing)
    by_id = {r["id"]: r for r in current}
    added, updated, kept = [], [], []
    merged = list(current)
    for rec in stamped:
        new = _to_project_record(rec)
        if new["id"] not in by_id:
            merged.append(new)
            added.append(new["id"])
            continue
        old = by_id[new["id"]]
        # The file may omit links; keep the existing design and test links then.
        if not new["code"]:
            new["code"] = old.get("code", [])
        if not new["tests"]:
            new["tests"] = old.get("tests", [])
        if any(old.get(f) != new[f] for f in TRACKED):
            updated.append(new["id"])
            merged[merged.index(old)] = new
        else:
            kept.append(new["id"])
    print(f"{len(stamped)} requirement(s) read from {Path(args.file).name}: "
          f"{len(added)} new, {len(updated)} updated, {len(kept)} unchanged")
    for rec in stamped:
        print(f"  {rec['source_id']} -> {rec['id']}")
    if not args.write:
        print("dry run: nothing written (add --write to merge into quality/requirements.json)")
        return 0
    data = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))
    data["requirements"] = merged
    REQUIREMENTS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REGISTRY.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {REQUIREMENTS.relative_to(ROOT)} and {REGISTRY.relative_to(ROOT)}")
    return 0


def cmd_export(args) -> int:
    out = Path(args.file)
    records = load()
    if out.suffix.lower() == ".csv":
        ri.write_csv(records, out)
    elif out.suffix.lower() == ".reqif":
        ri.write_reqif(records, out)
    else:
        print("use a .csv or .reqif file name", file=sys.stderr)
        return 2
    print(f"wrote {len(records)} requirement(s) to {out}")
    return 0


def cmd_baseline(args) -> int:
    BASELINES.mkdir(parents=True, exist_ok=True)
    path = BASELINES / f"{args.name}.json"
    if path.exists() and not args.force:
        print(f"refusing to overwrite {path.name}; baselines are fixed records (use --force)",
              file=sys.stderr)
        return 2
    path.write_text(json.dumps({"baseline": args.name, "requirements": load()},
                               indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"saved baseline {args.name} with {len(load())} requirement(s) to {path.relative_to(ROOT)}")
    return 0


def cmd_diff(args) -> int:
    old = _load_baseline(args.old)
    new = _load_baseline(args.new) if args.new else load()
    d = diff(old, new)
    print(f"added: {', '.join(d['added']) or 'none'}")
    print(f"removed: {', '.join(d['removed']) or 'none'}")
    for rid, fields in d["changed"].items():
        print(f"changed: {rid} ({', '.join(fields)})")
    for gap in d["gaps"]:
        print(f"GAP {gap}")
    return 1 if d["gaps"] else 0


def cmd_coverage(args) -> int:
    baseline = _load_baseline(args.baseline) if args.baseline else None
    text, gaps = coverage_markdown(load(), baseline)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 1 if gaps and args.fail_on_gap else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="DXL-style rules (CI gate)")
    cov = sub.add_parser("coverage", help="coverage matrix")
    cov.add_argument("--baseline", help="baseline name or JSON path to compare against")
    cov.add_argument("-o", "--output", help="write Markdown here instead of stdout")
    cov.add_argument("--fail-on-gap", action="store_true")
    base = sub.add_parser("baseline", help="baseline snapshots")
    base_sub = base.add_subparsers(dest="action", required=True)
    save = base_sub.add_parser("save")
    save.add_argument("name")
    save.add_argument("--force", action="store_true")
    dif = sub.add_parser("diff", help="changes and gaps between two baselines")
    dif.add_argument("old")
    dif.add_argument("new", nargs="?", help="default: current requirements.json")
    imp = sub.add_parser("import", help="read CSV or ReqIF")
    imp.add_argument("file")
    imp.add_argument("--write", action="store_true")
    exp = sub.add_parser("export", help="write CSV or ReqIF")
    exp.add_argument("file")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return check(load())
    if args.cmd == "coverage":
        return cmd_coverage(args)
    if args.cmd == "baseline":
        return cmd_baseline(args)
    if args.cmd == "diff":
        return cmd_diff(args)
    if args.cmd == "import":
        return cmd_import(args)
    return cmd_export(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ri.RequirementFileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
