#!/usr/bin/env python3
"""Validate the FMEA and generate its requirement/test-linked public register.

Run from the repository root: python quality/fmea_report.py [--check].
Validation resolves exact test IDs without importing or executing test modules.
The full pytest suite, not this generator, establishes whether evidence passes.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from quality import trace_matrix as tm  # noqa: E402


def priority(severity: int, rpn: int) -> str:
    """Project review triggers, not risk acceptance or an industry AP table."""
    if severity >= 8 or rpn >= 160:
        return 'Review before issue'
    return 'Planned improvement' if rpn >= 80 else 'Maintain controls'


def validate(data: dict, root: Path = ROOT) -> list[str]:
    """Return actionable integrity errors; never infer that linked tests passed."""
    errors = []

    def text_fields(obj, fields, where):
        for key in fields:
            if not isinstance(obj.get(key), str) or not obj[key].strip():
                errors.append(f'{where}: {key} must be nonempty text')

    def strings(value, where):
        if not isinstance(value, list) or not value or any(
                not isinstance(v, str) or not v.strip() for v in value):
            errors.append(f'{where} must be a nonempty list of strings')
            return []
        return value

    if not isinstance(data, dict):
        return ['register must be an object']
    if data.get('document') != 'QMS-FMEA-001':
        errors.append('document must be QMS-FMEA-001')
    if type(data.get('revision')) is not int or data['revision'] < 1:
        errors.append('revision must be a positive integer')
    modes = data.get('failure_modes')
    if not isinstance(modes, list) or not modes:
        return errors + ['failure_modes must be a nonempty list']
    requirements = tm.load_requirements(root / 'quality/requirements.json')
    # Resolve each requirement independently: the FMEA need not link every test,
    # and unrelated orphan tests are handled by trace_matrix.py's separate gate.
    trace = tm.build(root, requirements)
    errors.extend(e for e in trace.errors if not e.startswith('orphan test'))
    req_ids = {r['id'] for r in requirements}
    test_ids = {t.id for t in trace.tests}
    mode_ids, action_ids = set(), set()
    for n, mode in enumerate(modes, 1):
        where = f'failure_modes[{n}]'
        if not isinstance(mode, dict):
            errors.append(f'{where}: must be an object')
            continue
        text_fields(mode, ('id', 'step', 'failure_mode', 'effects', 'causes',
                           'prevention', 'detection_controls'), where)
        mid = mode.get('id')
        if not isinstance(mid, str) or not re.fullmatch(r'FM-\d{2,}', mid):
            errors.append(f'{where}: id must have form FM-01')
        elif mid in mode_ids:
            errors.append(f'{where}: duplicate failure mode id {mid}')
        else:
            mode_ids.add(mid)
        if mode.get('type') not in ('design', 'process'):
            errors.append(f'{where}: type must be design or process')
        linked = strings(mode.get('requirements'), f'{where}: requirements')
        for rid in linked:
            if rid not in req_ids:
                errors.append(f'{where}: unknown requirement {rid}')
        allowed = {tid for rid in linked for tid in trace.links.get(rid, [])}
        scores = mode.get('scores')
        if not isinstance(scores, dict):
            errors.append(f'{where}: scores must be an object')
            scores = {}
        rationale = mode.get('rationale')
        if not isinstance(rationale, dict):
            errors.append(f'{where}: rationale must be an object')
            rationale = {}
        for score in ('severity', 'occurrence', 'detection'):
            value = scores.get(score)
            if type(value) is not int or not 1 <= value <= 10:
                errors.append(f'{where}: {score} must be an integer from 1 to 10')
            text_fields(rationale, (score,), f'{where}: rationale')
        if set(scores) - {'severity', 'occurrence', 'detection'}:
            errors.append(f'{where}: scores may contain only severity, occurrence and detection')
        actions = mode.get('actions')
        if not isinstance(actions, list) or not actions:
            errors.append(f'{where}: actions must be a nonempty list')
            continue
        for i, action in enumerate(actions, 1):
            aw = f'{where}: actions[{i}]'
            if not isinstance(action, dict):
                errors.append(f'{aw}: must be an object')
                continue
            text_fields(action, ('id', 'description', 'owner', 'acceptance'), aw)
            aid = action.get('id')
            if not isinstance(aid, str) or not re.fullmatch(r'ACT-\d{2,}', aid):
                errors.append(f'{aw}: id must have form ACT-01')
            elif aid in action_ids:
                errors.append(f'{aw}: duplicate action id {aid}')
            else:
                action_ids.add(aid)
            if action.get('status') not in ('open', 'verified_automated'):
                errors.append(f'{aw}: status must be open or verified_automated')
            for tid in strings(action.get('verification_tests'), f'{aw}: verification_tests'):
                if tid not in test_ids:
                    errors.append(f'{aw}: test not found (exact ID required): {tid}')
                elif tid not in allowed:
                    errors.append(f'{aw}: test not linked to this mode\'s requirements: {tid}')
    return errors


def render(data: dict, root: Path = ROOT) -> str:
    """Render a validated register deterministically, with RPN computed once."""
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', '<br>')

    def test_link(tid):
        path, name = tid.split('::')
        tree = ast.parse((root / path).read_text(encoding='utf-8'))
        line = next(n.lineno for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        return f'[`{tid}`](../{path}#L{line})'

    modes = sorted(data['failure_modes'], key=lambda m: (
        m['scores']['severity'] < 8, -math.prod(m['scores'].values()), m['id']))
    actions = [a for m in modes for a in m['actions']]
    verified = sum(a['status'] == 'verified_automated' for a in actions)
    lines = ['# Seal-stamping design/process FMEA register', '',
             f"Document: {data['document']}, revision {data['revision']}. **GENERATED**; edit `fmea.json`.", '',
             'Method, scoring rubric and limits: [FMEA.md](FMEA.md). '
             'Regenerate with `python quality/fmea_report.py`.', '',
             f'**{len(modes)} failure modes; {verified} verified software actions; '
             f'{len(actions) - verified} open actions.** Scores describe current controls. '
             'No residual reduction or field failure rates are claimed. Software evidence '
             'is limited to synthetic tests; see the [executed IQ/OQ record](validation/IQ-OQ-EXECUTED.md).', '',
             'High-severity modes (S >= 8) appear first, then descending RPN within each group. '
             'Review triggers do not constitute production acceptance.', '',
             '| Mode | Type / step | Failure mode | S | O | D | RPN | Review trigger |',
             '| --- | --- | --- | ---: | ---: | ---: | ---: | --- |']
    for m in modes:
        s, o, d = (m['scores'][k] for k in ('severity', 'occurrence', 'detection'))
        rpn = s * o * d
        lines.append(f"| [{m['id']}](#{m['id'].lower()}) | {cell(m['type'])} / {cell(m['step'])} | "
                     f"{cell(m['failure_mode'])} | {s} | {o} | {d} | {rpn} | {priority(s, rpn)} |")
    for m in modes:
        lines += ['', f"## {m['id']}", '', f"**{m['failure_mode']}** ({m['type']}; {m['step']}).", '',
                  f"- Effect: {m['effects']}", f"- Cause: {m['causes']}",
                  '- Requirements: ' + ', '.join(f'[{rid}](TRACEABILITY_MATRIX.md)' for rid in m['requirements']),
                  f"- Current prevention: {m['prevention']}",
                  f"- Current detection: {m['detection_controls']}", '',
                  '| Score | Current rating | Rationale |', '| --- | ---: | --- |']
        for key in ('severity', 'occurrence', 'detection'):
            lines.append(f"| {key.title()} | {m['scores'][key]} | {cell(m['rationale'][key])} |")
        lines += ['', '| Action | Owner | Status | Acceptance / closure evidence | Verification tests |',
                  '| --- | --- | --- | --- | --- |']
        for a in m['actions']:
            lines.append(f"| {a['id']}: {cell(a['description'])} | {cell(a['owner'])} | {a['status']} | "
                         f"{cell(a['acceptance'])} | " + '<br>'.join(test_link(t) for t in a['verification_tests']) + ' |')
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--check', action='store_true', help='fail for stale report; never write')
    ap.add_argument('--root', type=Path, default=ROOT, help='repository root (default: this checkout)')
    args = ap.parse_args(argv)
    try:
        data = json.loads((args.root / 'quality/fmea.json').read_text(encoding='utf-8'))
        errors = validate(data, args.root)
        if errors:
            for error in errors:
                print('ERROR:', error, file=sys.stderr)
            return 1
        text = render(data, args.root)
        report = args.root / 'quality/FMEA_REGISTER.md'
        if args.check:
            if not report.exists() or report.read_text(encoding='utf-8') != text:
                print('ERROR: FMEA register out of date; run python quality/fmea_report.py', file=sys.stderr)
                return 1
            print('FMEA scores, action evidence and generated report are current.')
        else:
            report.write_text(text, encoding='utf-8')
            print(f"wrote quality/FMEA_REGISTER.md: {len(data['failure_modes'])} failure modes")
    except (OSError, ValueError, KeyError, SyntaxError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
