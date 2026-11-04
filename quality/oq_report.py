#!/usr/bin/env python3
"""Execute the installation pre-checks and the OQ test run; write the record.

Runs the real pytest suite, maps every result to the requirements in
``quality/requirements.json`` (via ``trace_matrix.py``) and writes
``quality/validation/IQ-OQ-EXECUTED.md``. The record names the exact files it
was executed against by SHA-256 so a reader can tell whether it still applies.

Usage:
    python quality/oq_report.py            # execute and rewrite the record
    python quality/oq_report.py --check    # no execution; fail if the record is
                                           # stale, i.e. validated files changed
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata as md
import platform
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_matrix as tm  # noqa: E402

ROOT = tm.ROOT
RECORD = ROOT / "quality" / "validation" / "IQ-OQ-EXECUTED.md"
VALIDATED_GLOBS = ["app.py", "desktop_app.py", "conftest.py", "stamper/*.py", "tests/*.py",
                   "requirements.txt", "requirements-lock.txt", "requirements-dev.txt",
                   "quality/requirements.json", "quality/*.py", "quality/fmea.json",
                   "quality/FMEA.md", "quality/FMEA_REGISTER.md"]
FINGERPRINT_RE = re.compile(r"Combined fingerprint \(SHA-256\): `([0-9a-f]{64})`")


# --- fingerprint -----------------------------------------------------------
def validated_files(root: Path = ROOT) -> list[Path]:
    files: set[Path] = set()
    for pattern in VALIDATED_GLOBS:
        files.update(p for p in root.glob(pattern) if p.is_file())
    return sorted(files)


def fingerprint(root: Path = ROOT) -> tuple[str, list[tuple[str, str]]]:
    rows = [(p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
            for p in validated_files(root)]
    combined = hashlib.sha256("\n".join(f"{h}  {n}" for n, h in rows).encode()).hexdigest()
    return combined, rows


# --- IQ --------------------------------------------------------------------
def locked_packages(lock: Path) -> dict[str, str]:
    pins = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;#]+)", line.strip())
        if m:
            pins[m.group(1)] = m.group(2)
    return pins


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def iq_checks(root: Path = ROOT) -> list[tuple[str, str, bool]]:
    """(check, observed, passed). Python 3.12 is the verified interpreter."""
    checks = [("Python 3.10 or later", platform.python_version(), sys.version_info >= (3, 10))]
    for name, pinned in locked_packages(root / "requirements-lock.txt").items():
        try:
            installed = md.version(name)
        except md.PackageNotFoundError:
            installed = "not installed"
        checks.append((f"{name}=={pinned}", installed, _norm(installed) == _norm(pinned)))
    try:
        sys.path.insert(0, str(root))
        import stamper  # noqa: F401
        checks.append(("`import stamper` succeeds", "ok", True))
    except Exception as exc:  # pragma: no cover - reported in the record
        checks.append(("`import stamper` succeeds", f"{type(exc).__name__}: {exc}", False))
    return checks


# --- OQ --------------------------------------------------------------------
def run_pytest(root: Path = ROOT) -> tuple[int, str, Path]:
    xml = Path(tempfile.mkdtemp(prefix="oq-")) / "junit.xml"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"],
        cwd=root, capture_output=True, text=True)
    return proc.returncode, proc.stdout, xml


def parse_junit(xml: Path) -> dict[str, dict[str, int]]:
    """test function id -> {'passed','failed','skipped'} counts over its cases."""
    out: dict[str, dict[str, int]] = {}
    for case in ET.parse(xml).getroot().iter("testcase"):
        module = case.get("classname", "").split(".")
        file = "/".join(module[:2]) + ".py" if len(module) >= 2 else "?"
        name = re.sub(r"\[.*\]$", "", case.get("name", ""))
        counts = out.setdefault(f"{file}::{name}", {"passed": 0, "failed": 0, "skipped": 0})
        if case.find("failure") is not None or case.find("error") is not None:
            counts["failed"] += 1
        elif case.find("skipped") is not None:
            counts["skipped"] += 1
        else:
            counts["passed"] += 1
    return out


def requirement_status(test_ids: list[str], results: dict[str, dict[str, int]]) -> str:
    if not test_ids or any(t not in results for t in test_ids):
        return "NOT RUN"
    if any(results[t]["failed"] or results[t]["skipped"] for t in test_ids):
        return "FAIL"
    return "PASS"


# --- record ----------------------------------------------------------------
def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def render(iq, trace: tm.Result, results, summary_line: str, rc: int) -> str:
    combined, rows = fingerprint()
    iq_ok = all(ok for *_, ok in iq)
    statuses = {r["id"]: requirement_status(trace.links[r["id"]], results) for r in trace.requirements}
    oq_ok = rc == 0 and all(s == "PASS" for s in statuses.values()) and not trace.errors
    cases = {k: sum(v.values()) for k, v in results.items()}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit = git("rev-parse", "--short", "HEAD") or "unknown"
    dirty = "yes" if git("status", "--porcelain", "--", ".") else "no"
    L = [
        "# IQ/OQ Execution Record", "",
        "| | |", "| --- | --- |",
        "| Document | VAL-REC-001 |",
        "| Protocol executed | [VP-001](VP-001-validation-protocol.md), stages IQ and OQ |",
        "| Status | GENERATED by `python quality/oq_report.py`. Do not edit by hand. |",
        f"| Executed | {now} |",
        "| Executed by | Automated script (no manual steps in IQ/OQ) |",
        f"| Environment | Python {platform.python_version()}, {platform.platform()} |",
        f"| Repository base commit | `{commit}` (uncommitted changes in working tree: {dirty}) |",
        f"| Overall IQ | **{'PASS' if iq_ok else 'FAIL'}** |",
        f"| Overall OQ | **{'PASS' if oq_ok else 'FAIL'}** |", "",
        "> The base commit alone does not identify what was tested when the tree has "
        "uncommitted changes. The fingerprint below does: this record applies to a "
        "source tree only if `python quality/oq_report.py --check` passes on it.", "",
        "## Installation Qualification (IQ) results", "",
        f"{sum(ok for *_, ok in iq)} of {len(iq)} checks passed.", "",
        "| Check | Observed | Result |", "| --- | --- | --- |",
    ]
    L += [f"| {c} | {o} | {'PASS' if ok else 'FAIL'} |" for c, o, ok in iq]
    L += ["", "## Operational Qualification (OQ) results", "",
          f"Command: `python -m pytest -q`. Output summary: `{summary_line}`. "
          f"Total test cases executed: {sum(cases.values())}.", "",
          "### By requirement", "",
          "| Requirement | Title | Risk | Tests linked | Cases | Result |",
          "| --- | --- | --- | ---: | ---: | --- |"]
    for r in trace.requirements:
        ids = trace.links[r["id"]]
        n = sum(cases.get(t, 0) for t in ids)
        L.append(f"| {r['id']} | {r['title']} | {r['risk']} | {len(ids)} | {n} | {statuses[r['id']]} |")
    L += ["", "### By test", "", "| Test | Cases | Passed | Failed | Skipped |",
          "| --- | ---: | ---: | ---: | ---: |"]
    for t in sorted(results):
        c = results[t]
        L.append(f"| `{t}` | {sum(c.values())} | {c['passed']} | {c['failed']} | {c['skipped']} |")
    failed = [t for t in sorted(results) if results[t]["failed"]]
    L += ["", "## Deviations", "",
          ("None raised by the automated run." if oq_ok and iq_ok else
           "The run did not pass. Raise a deviation per SOP-001 section 8 and do not use the tool "
           "for production until it is closed. Failed tests: " + (", ".join(failed) or "see IQ/OQ tables"))]
    if trace.errors:
        L += ["", "Traceability errors: " + "; ".join(trace.errors)]
    L += ["", "## Source fingerprint", "",
          f"Combined fingerprint (SHA-256): `{combined}`", "",
          "| File | SHA-256 |", "| --- | --- |"]
    L += [f"| `{n}` | `{h[:16]}...` |" for n, h in rows]
    L += ["", "## Conclusion and approval", "",
          "The automated checks above are the evidence for IQ and OQ. PQ is not executed here "
          "(it needs representative drawings and an operator; see VP-001 section 7).", "",
          "| Role | Name | Signature | Date |", "| --- | --- | --- | --- |",
          "| Executed by | automated script | n/a | see header |",
          "| Reviewed by | _not reviewed (demonstration)_ | | |",
          "| Approved by | _not approved (demonstration)_ | | |", ""]
    return "\n".join(L)


def check() -> int:
    if not RECORD.exists():
        print("ERROR: no IQ/OQ record; run python quality/oq_report.py", file=sys.stderr)
        return 1
    m = FINGERPRINT_RE.search(RECORD.read_text(encoding="utf-8"))
    current, _ = fingerprint()
    if not m or m.group(1) != current:
        print("ERROR: validated files changed since the IQ/OQ record was executed "
              "(change control: re-execute with python quality/oq_report.py)", file=sys.stderr)
        return 1
    print("IQ/OQ record matches the current source tree.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="verify the record is current; do not run tests")
    args = ap.parse_args(argv)
    if args.check:
        return check()
    trace = tm.build()
    rc, stdout, xml = run_pytest()
    results = parse_junit(xml)
    xml.unlink(missing_ok=True)
    xml.parent.rmdir()
    summary = (stdout.strip().splitlines() or ["(no output)"])[-1].strip("= ")
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    text = render(iq_checks(), trace, results, summary, rc)
    RECORD.write_text(text, encoding="utf-8")
    print(f"wrote {RECORD.relative_to(ROOT)}: {summary}")
    return 0 if "Overall OQ | **PASS**" in text and "Overall IQ | **PASS**" in text else 1


if __name__ == "__main__":
    sys.exit(main())
