"""The quality-system scripts: traceability generation and OQ record helpers."""
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'quality'))

import oq_report  # noqa: E402
import trace_matrix as tm  # noqa: E402


def _tree(tmp_path, tests, code='def real_fn():\n    pass\n\nclass C:\n    def m(self):\n        pass\n'):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'quality').mkdir()
    (tmp_path / 'tests' / 'test_a.py').write_text(textwrap.dedent(tests))
    (tmp_path / 'mod.py').write_text(code)
    return tmp_path


def _req(rid, tests, code=('mod.py::real_fn',)):
    return {'id': rid, 'title': rid, 'text': 'x', 'risk': 'Low', 'code': list(code), 'tests': tests}


TESTS = '''
import pytest
def test_one(): pass
@pytest.mark.parametrize('a', [1, 2, 3])
@pytest.mark.parametrize('b', [1, 2])
def test_two(a, b): pass
def helper(): pass
'''


def test_collect_tests_expands_parametrize_and_ignores_helpers(tmp_path):
    found = {t.id: t.cases for t in tm.collect_tests(_tree(tmp_path, TESTS))}
    assert found == {'tests/test_a.py::test_one': 1, 'tests/test_a.py::test_two': 6}


def test_patterns_link_tests_and_complete_traceability_has_no_errors(tmp_path):
    root = _tree(tmp_path, TESTS)
    result = tm.build(root, [_req('R1', ['tests/test_a.py::test_*'])])
    assert result.errors == []
    assert result.links['R1'] == ['tests/test_a.py::test_one', 'tests/test_a.py::test_two']
    assert 'R1' in tm.render(result)


def test_broken_traceability_is_reported(tmp_path):
    root = _tree(tmp_path, TESTS)
    reqs = [_req('R1', ['tests/test_a.py::test_one'], code=['mod.py::missing_fn']),
            _req('R2', ['tests/test_a.py::nothing_matches_*'])]
    errors = ' | '.join(tm.build(root, reqs).errors)
    assert 'R1: code reference not found: mod.py::missing_fn' in errors
    assert 'R2: test pattern matches nothing' in errors
    assert 'R2: no test is linked' in errors
    assert 'orphan test, linked to no requirement: tests/test_a.py::test_two' in errors


def test_symbol_lookup_handles_classes_methods_and_plain_files(tmp_path):
    root = _tree(tmp_path, TESTS)
    (root / 'plain.txt').write_text('x')
    assert tm.symbol_exists(root, 'mod.py::C.m')
    assert not tm.symbol_exists(root, 'mod.py::C.nope')
    assert tm.symbol_exists(root, 'plain.txt')
    assert not tm.symbol_exists(root, 'gone.py::real_fn')


def test_repository_traceability_is_complete_and_matrix_is_current():
    result = tm.build()
    assert result.errors == []
    assert tm.MATRIX.read_text(encoding='utf-8') == tm.render(result)
    assert len(json.loads(tm.REQUIREMENTS.read_text(encoding='utf-8'))['requirements']) >= 1


def test_junit_results_are_grouped_per_test_function(tmp_path):
    xml = tmp_path / 'j.xml'
    xml.write_text('''<testsuites><testsuite>
      <testcase classname="tests.test_a" name="test_two[1-1]"/>
      <testcase classname="tests.test_a" name="test_two[2-1]"><failure/></testcase>
      <testcase classname="tests.test_a" name="test_one"/>
    </testsuite></testsuites>''')
    got = oq_report.parse_junit(xml)
    assert got['tests/test_a.py::test_two'] == {'passed': 1, 'failed': 1, 'skipped': 0}
    assert got['tests/test_a.py::test_one']['passed'] == 1


def test_requirement_status_fails_on_any_failed_skipped_or_missing_test():
    ok = {'passed': 2, 'failed': 0, 'skipped': 0}
    results = {'a': ok, 'b': {'passed': 1, 'failed': 1, 'skipped': 0}, 'c': {'passed': 0, 'failed': 0, 'skipped': 1}}
    assert oq_report.requirement_status(['a'], results) == 'PASS'
    assert oq_report.requirement_status(['a', 'b'], results) == 'FAIL'
    assert oq_report.requirement_status(['c'], results) == 'FAIL'
    assert oq_report.requirement_status(['a', 'zzz'], results) == 'NOT RUN'
    assert oq_report.requirement_status([], results) == 'NOT RUN'


def test_lock_file_parser_and_fingerprint_detect_changes(tmp_path):
    lock = tmp_path / 'lock.txt'
    lock.write_text('# comment\nnumpy==2.5.4\nPyMuPDF==1.26.7  # pin\n\n')
    assert oq_report.locked_packages(lock) == {'numpy': '2.5.4', 'PyMuPDF': '1.26.7'}
    (tmp_path / 'app.py').write_text('a = 1\n')
    before, _ = oq_report.fingerprint(tmp_path)
    (tmp_path / 'app.py').write_text('a = 2\n')
    after, _ = oq_report.fingerprint(tmp_path)
    assert before != after
