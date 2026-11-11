"""Requirements import (CSV and ReqIF), stable IDs, DXL-style checks and baseline diffs."""
import io
import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'quality'))

import rtm  # noqa: E402
import rtm_import as ri  # noqa: E402

SAMPLE_CSV = ROOT / 'examples' / 'requirements' / 'sample_requirements.csv'
SAMPLE_REQIF = ROOT / 'examples' / 'requirements' / 'sample_requirements.reqif'


def _repo(tmp_path, requirements):
    """A small fake repository with one code file, one test file and a requirements file."""
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'quality').mkdir()
    (tmp_path / 'mod.py').write_text('def real_fn():\n    pass\n')
    (tmp_path / 'tests' / 'test_a.py').write_text(textwrap.dedent('''
        def test_one(): pass
        def test_two(): pass
    '''))
    return tmp_path


def _req(rid, tests=('tests/test_a.py::test_one',), code=('mod.py::real_fn',), text='The thing.'):
    return {'id': rid, 'title': rid, 'text': text, 'risk': 'Low', 'code': list(code), 'tests': list(tests)}


# --- CSV and ReqIF ----------------------------------------------------------

def test_csv_and_reqif_samples_read_the_same_three_requirements():
    csv_records = ri.read_csv(SAMPLE_CSV)
    assert [r['id'] for r in csv_records] == ['SYS-101', 'SYS-102', 'SYS-103']
    assert ri.read_reqif(SAMPLE_REQIF) == csv_records


def test_reqif_round_trip_keeps_every_field(tmp_path):
    records = [{'id': 'A-1', 'title': 'Title', 'text': 'Text with, commas & <tags>', 'risk': 'High',
                'code': ['mod.py::real_fn', 'mod.py'], 'tests': ['tests/test_a.py::test_*']}]
    out = tmp_path / 'x.reqif'
    ri.write_reqif(records, out)
    assert ri.read_reqif(out) == records


def test_csv_round_trip_and_optional_links(tmp_path):
    records = [{'id': 'B-1', 'title': 'T', 'text': 'x', 'risk': 'Low', 'code': [], 'tests': []}]
    out = tmp_path / 'x.csv'
    ri.write_csv(records, out)
    assert ri.read_csv(out) == records


def test_csv_missing_column_is_rejected(tmp_path):
    bad = tmp_path / 'bad.csv'
    bad.write_text('id,title,text\nX,t,x\n', encoding='utf-8')
    with pytest.raises(ri.RequirementFileError, match="missing column"):
        ri.read_csv(bad)


def test_blank_required_field_and_duplicate_ids_are_rejected(tmp_path):
    blank = tmp_path / 'blank.csv'
    blank.write_text('id,title,text,risk\nX,t,,High\n', encoding='utf-8')
    with pytest.raises(ri.RequirementFileError, match="missing 'text'"):
        ri.read_csv(blank)
    dup = tmp_path / 'dup.csv'
    dup.write_text('id,title,text,risk\nX,t,x,High\nX,u,y,Low\n', encoding='utf-8')
    with pytest.raises(ri.RequirementFileError, match="duplicate source id X"):
        ri.read_csv(dup)


def test_reqif_wrong_root_and_unknown_extension_are_rejected(tmp_path):
    xml = tmp_path / 'other.reqif'
    xml.write_text('<html/>', encoding='utf-8')
    with pytest.raises(ri.RequirementFileError, match="not a ReqIF"):
        ri.read_reqif(xml)
    with pytest.raises(ri.RequirementFileError, match="unsupported"):
        ri.load(tmp_path / 'notes.txt')


# --- stable IDs ---------------------------------------------------------------

def test_stable_ids_are_kept_and_retired_numbers_are_never_reused():
    registry = {}
    existing = {'REQ-01', 'REQ-28'}
    first = ri.assign_ids(ri.read_csv(SAMPLE_CSV), registry, existing)
    assert [r['id'] for r in first] == ['REQ-29', 'REQ-30', 'REQ-31']
    assert all(r['source_id'] == s for r, s in zip(first, ['SYS-101', 'SYS-102', 'SYS-103']))
    # Importing the same file again keeps the same IDs.
    again = ri.assign_ids(ri.read_csv(SAMPLE_CSV), registry, existing)
    assert [r['id'] for r in again] == ['REQ-29', 'REQ-30', 'REQ-31']
    # A source key that is already a project ID keeps it.
    same = ri.assign_ids([{'id': 'REQ-01', 'title': 't', 'text': 'x', 'risk': 'Low',
                           'code': [], 'tests': []}], registry, existing)
    assert same[0]['id'] == 'REQ-01'
    # Dropping SYS-101 retires REQ-29: a new requirement gets the next free number.
    registry_after = dict(registry)
    newer = ri.assign_ids([{'id': 'SYS-900', 'title': 't', 'text': 'x', 'risk': 'Low',
                            'code': [], 'tests': []}], registry_after, existing)
    assert newer[0]['id'] == 'REQ-32'


def test_numbered_ignores_non_numeric_ids():
    assert ri.numbered({'REQ-07', 'REQ-EARTHWORK-01', 'other'}) == 7
    assert ri.numbered(set()) == 0


# --- DXL-style check --------------------------------------------------------------

def test_repository_requirements_pass_every_rule():
    out = io.StringIO()
    assert rtm.check(rtm.load(), ROOT, out=out) == 0, out.getvalue()
    assert 'FAIL' not in out.getvalue()


def test_check_fails_and_names_a_requirement_without_a_test(tmp_path):
    root = _repo(tmp_path, [])
    reqs = [_req('REQ-A'), _req('REQ-B', tests=())]
    out = io.StringIO()
    assert rtm.check(reqs, root, out=out) == 1
    text = out.getvalue()
    assert 'FAIL R2 every requirement has an automated test (1/2)' in text
    assert '     REQ-B' in text


def test_check_fails_on_untraced_requirement_and_broken_references(tmp_path):
    root = _repo(tmp_path, [])
    reqs = [_req('REQ-C', code=()), _req('REQ-D', code=('mod.py::missing_fn',)),
            _req('REQ-E', tests=('tests/test_a.py::test_gone',))]
    out = io.StringIO()
    assert rtm.check(reqs, root, out=out) == 1
    text = out.getvalue()
    assert 'FAIL R1 every requirement names a design element (2/3)' in text
    assert 'FAIL R3 every design element and test pattern resolves (1/3)' in text
    assert '     REQ-D' in text and '     REQ-E' in text


def test_check_fails_on_orphan_test(tmp_path):
    root = _repo(tmp_path, [])
    out = io.StringIO()
    assert rtm.check([_req('REQ-F', tests=('tests/test_a.py::test_one',))], root, out=out) == 1
    assert 'FAIL R4 every test belongs to a requirement' in out.getvalue()
    assert 'tests/test_a.py::test_two' in out.getvalue()


# --- coverage matrix and baselines ------------------------------------------------

def test_coverage_matrix_flags_each_kind_of_gap(tmp_path):
    root = _repo(tmp_path, [])
    current = [_req('REQ-OK'), _req('REQ-NOTEST', tests=()), _req('REQ-NOCODE', code=())]
    text, gaps = rtm.coverage_markdown(current, None, root)
    assert '| REQ-OK | REQ-OK | 1 | 1 | OK |' in text
    assert '| REQ-NOTEST | REQ-NOTEST | 1 | 0 | NO TEST |' in text
    assert '| REQ-NOCODE | REQ-NOCODE | 0 | 1 | UNTRACED |' in text
    # test_two is not linked to any requirement, so it is an orphan test.
    assert 'tests/test_a.py::test_two' in text
    assert gaps == 3


def test_diff_reports_added_removed_changed_and_the_gaps_they_open():
    old = [_req('REQ-1'), _req('REQ-2'), _req('REQ-3', tests=('tests/test_a.py::test_two',))]
    new = [
        _req('REQ-1', text='Changed wording.'),              # text changed, tests unchanged
        _req('REQ-3', tests=('tests/test_a.py::test_two',)),  # unchanged
        _req('REQ-4', tests=()),                             # added, no test yet
    ]
    d = rtm.diff(old, new)
    assert d['added'] == ['REQ-4']
    assert d['removed'] == ['REQ-2']
    assert d['changed'] == {'REQ-1': ['text']}
    assert any('REQ-4: added without an automated test' in g for g in d['gaps'])
    assert any('REQ-1: text changed' in g for g in d['gaps'])
    assert any('REQ-2: removed, but its tests' in g for g in d['gaps'])


def test_baseline_save_refuses_to_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(rtm, 'BASELINES', tmp_path / 'baselines')
    monkeypatch.setattr(rtm, 'ROOT', tmp_path)
    assert rtm.main(['baseline', 'save', 'B9']) == 0
    assert rtm.main(['baseline', 'save', 'B9']) == 2
    assert rtm.main(['baseline', 'save', 'B9', '--force']) == 0
    saved = json.loads((tmp_path / 'baselines' / 'B9.json').read_text())
    assert saved['baseline'] == 'B9' and len(saved['requirements']) == len(rtm.load())


def test_import_merges_new_requirements_and_keeps_existing_links(tmp_path, monkeypatch):
    reqs = tmp_path / 'requirements.json'
    reqs.write_text(json.dumps({'document': 'x', 'requirements': [
        _req('REQ-01', tests=('tests/test_a.py::test_one',))]}))
    registry = tmp_path / 'rtm_ids.json'
    monkeypatch.setattr(rtm, 'REQUIREMENTS', reqs)
    monkeypatch.setattr(rtm, 'REGISTRY', registry)
    monkeypatch.setattr(rtm, 'ROOT', tmp_path)
    source = tmp_path / 'in.csv'
    source.write_text(
        'id,title,text,risk,code,tests\n'
        'REQ-01,Same thing,The thing.,Low,,\n'
        'SYS-7,New thing,A new rule.,High,mod.py::real_fn,\n',
        encoding='utf-8')
    assert rtm.main(['import', str(source)]) == 0          # dry run
    assert json.loads(reqs.read_text())['requirements'] == [
        _req('REQ-01', tests=('tests/test_a.py::test_one',))]  # nothing written
    assert not registry.exists()
    assert rtm.main(['import', str(source), '--write']) == 0
    merged = json.loads(reqs.read_text())['requirements']
    by_id = {r['id']: r for r in merged}
    assert by_id['REQ-01']['tests'] == ['tests/test_a.py::test_one']   # link kept
    assert by_id['REQ-02']['title'] == 'New thing'                       # new, stable ID
    assert json.loads(registry.read_text())['ids'] == {'REQ-01': 'REQ-01', 'SYS-7': 'REQ-02'}


def test_export_writes_csv_and_reqif(tmp_path, monkeypatch):
    reqs = tmp_path / 'requirements.json'
    reqs.write_text(json.dumps({'requirements': [_req('REQ-1')]}))
    monkeypatch.setattr(rtm, 'REQUIREMENTS', reqs)
    assert rtm.main(['export', str(tmp_path / 'out.csv')]) == 0
    assert rtm.main(['export', str(tmp_path / 'out.reqif')]) == 0
    assert ri.read_csv(tmp_path / 'out.csv') == ri.read_reqif(tmp_path / 'out.reqif')
    assert rtm.main(['export', str(tmp_path / 'out.xlsx')]) == 2
