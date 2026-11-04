"""FMEA integrity: catch invalid scoring, broken evidence and stale public reports."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _tool():
    from quality import fmea_report
    return fmea_report


@pytest.fixture
def register(tmp_path):
    (tmp_path / 'quality').mkdir()
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/test_control.py').write_text(
        'def test_control(): pass\ndef test_unrelated(): pass\n')
    (tmp_path / 'control.py').write_text('def protect(): pass\n')
    requirements = {'requirements': [
        {'id': 'REQ-01', 'code': ['control.py::protect'],
         'tests': ['tests/test_control.py::test_control']},
        {'id': 'REQ-02', 'code': ['control.py::protect'],
         'tests': ['tests/test_control.py::test_unrelated']}]}
    (tmp_path / 'quality/requirements.json').write_text(json.dumps(requirements))
    row = {'id': 'FM-01', 'type': 'design', 'step': 'Place seal',
           'failure_mode': 'Covers source text', 'effects': 'Unreadable dimension',
           'causes': 'Wrong coordinate', 'requirements': ['REQ-01', 'REQ-02'],
           'prevention': 'Coordinate transform', 'detection_controls': 'Output inspection',
           'scores': {'severity': 8, 'occurrence': 2, 'detection': 3},
           'rationale': {'severity': 'Critical drawing information could be hidden.',
                         'occurrence': 'Uncommon geometry.',
                         'detection': 'Synthetic checks plus output review.'},
           'actions': [{'id': 'ACT-01', 'description': 'Check exported coordinates',
                        'owner': 'Maintainer', 'status': 'verified_automated',
                        'verification_tests': ['tests/test_control.py::test_control'],
                        'acceptance': 'Exported seal lies within expected bounds.'}]}
    return tmp_path, {'document': 'QMS-FMEA-001', 'revision': 1, 'failure_modes': [row]}


def test_fmea_valid_register_renders_calculated_rpn_and_links(register):
    root, data = register
    tool = _tool()
    assert tool.validate(data, root) == []
    text = tool.render(data, root)
    assert '| 8 | 2 | 3 | 48 |' in text
    assert '[REQ-01](TRACEABILITY_MATRIX.md)' in text
    assert '../tests/test_control.py#L1' in text
    assert 'verified_automated' in text


@pytest.mark.parametrize(('severity', 'rpn', 'expected'), [
    (8, 8, 'Review before issue'), (7, 160, 'Review before issue'),
    (7, 80, 'Planned improvement'), (7, 79, 'Maintain controls')])
def test_fmea_priority_keeps_high_severity_visible(severity, rpn, expected):
    assert _tool().priority(severity, rpn) == expected


@pytest.mark.parametrize('score', [0, 11, True, 2.5, '3', None])
def test_fmea_rejects_noninteger_or_out_of_range_scores(register, score):
    root, data = register
    data['failure_modes'][0]['scores']['severity'] = score
    assert any('severity' in e for e in _tool().validate(data, root))


@pytest.mark.parametrize(('field', 'value', 'message'), [
    ('rationale', {}, 'rationale'), ('actions', [], 'actions'),
    ('requirements', ['REQ-99'], 'unknown requirement'),
    ('failure_mode', '  ', 'failure_mode'), ('type', 'other', 'type')])
def test_fmea_rejects_incomplete_analysis(register, field, value, message):
    root, data = register
    data['failure_modes'][0][field] = value
    assert any(message in e for e in _tool().validate(data, root))


@pytest.mark.parametrize(('field', 'value', 'message'), [
    ('owner', '', 'owner'), ('acceptance', '', 'acceptance'),
    ('status', 'closed', 'status'), ('verification_tests', [], 'verification_tests'),
    ('verification_tests', ['tests/test_control.py::missing'], 'test not found'),
    ('verification_tests', ['tests/test_control.py::test_*'], 'test not found')])
def test_fmea_rejects_unverifiable_actions(register, field, value, message):
    root, data = register
    data['failure_modes'][0]['actions'][0][field] = value
    assert any(message in e for e in _tool().validate(data, root))


def test_fmea_rejects_test_evidence_unrelated_to_linked_requirements(register):
    root, data = register
    data['failure_modes'][0]['requirements'] = ['REQ-02']
    assert any('not linked' in e for e in _tool().validate(data, root))


@pytest.mark.parametrize('duplicate_action', [False, True])
def test_fmea_rejects_duplicate_identifiers(register, duplicate_action):
    root, data = register
    row = data['failure_modes'][0]
    if duplicate_action:
        row['actions'].append(copy.deepcopy(row['actions'][0]))
    else:
        data['failure_modes'].append(copy.deepcopy(row))
    assert any('duplicate' in e for e in _tool().validate(data, root))


@pytest.mark.parametrize('data', [{}, {'document': 'QMS-FMEA-001', 'revision': 1,
                                        'failure_modes': []},
                                 {'document': 'QMS-FMEA-001', 'revision': 1,
                                  'failure_modes': [None]}])
def test_fmea_rejects_empty_or_malformed_register(register, data):
    root, _ = register
    assert _tool().validate(data, root)


def test_fmea_open_actions_remain_open_in_report(register):
    root, data = register
    data['failure_modes'][0]['actions'][0]['status'] = 'open'
    text = _tool().render(data, root)
    assert 'open' in text
    assert '0 verified software actions' in text


def test_fmea_cli_detects_drift_and_invalid_input_without_overwriting(register):
    root, data = register
    source = root / 'quality/fmea.json'
    source.write_text(json.dumps(data))
    command = [sys.executable, str(ROOT / 'quality/fmea_report.py'), '--root', str(root)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = root / 'quality/FMEA_REGISTER.md'
    original = report.read_text()
    result = subprocess.run(command + ['--check'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data['failure_modes'][0]['scores']['occurrence'] = 4
    source.write_text(json.dumps(data))
    result = subprocess.run(command + ['--check'], capture_output=True, text=True)
    assert result.returncode == 1 and 'out of date' in result.stderr
    assert report.read_text() == original
    source.write_text('{bad json')
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1 and 'ERROR' in result.stderr
    assert report.read_text() == original


def test_fmea_repository_register_is_valid_and_report_current():
    tool = _tool()
    data = json.loads((ROOT / 'quality/fmea.json').read_text())
    assert tool.validate(data) == []
    assert (ROOT / 'quality/FMEA_REGISTER.md').read_text() == tool.render(data)
    linked = {r for mode in data['failure_modes'] for r in mode['requirements']}
    requirements = json.loads((ROOT / 'quality/requirements.json').read_text())
    assert linked == {r['id'] for r in requirements['requirements']}


@pytest.mark.parametrize('relative', ['quality/fmea.json', 'quality/fmea_report.py',
                                    'quality/FMEA.md', 'quality/FMEA_REGISTER.md'])
def test_fmea_changes_invalidate_the_iq_oq_fingerprint(tmp_path, relative):
    from quality import oq_report

    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text('before')
    before, _ = oq_report.fingerprint(tmp_path)
    path.write_text('after')
    after, _ = oq_report.fingerprint(tmp_path)
    assert before != after
