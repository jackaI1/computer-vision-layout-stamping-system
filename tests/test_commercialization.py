"""Citation checks must reject plausible but invented evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.check_commercialization import ROOT, check


def _copy(tmp_path):
    shutil.copytree(ROOT / 'docs', tmp_path / 'docs')
    # Retain actual cited files without copying dependencies or private inputs.
    for folder in ('stamper', 'tests', 'quality', 'examples'):
        shutil.copytree(ROOT / folder, tmp_path / folder, ignore=shutil.ignore_patterns('__pycache__'))
    for file in ('README.md', 'LICENSE', 'ASSUMPTIONS.md', 'THIRD_PARTY_NOTICES.md'):
        shutil.copyfile(ROOT / file, tmp_path / file)
    return tmp_path


def test_assessment_citations_and_cli():
    assert check()[0] == []
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/check_commercialization.py')], capture_output=True, text=True, cwd=ROOT.parent)
    assert result.returncode == 0, result.stderr
    assert '7 patent publications' in result.stdout


@pytest.mark.parametrize('before,after', [
    ('../stamper/placement.py', '../stamper/missing.py'),
    ('../stamper/placement.py', '../../outside.py'),
    ('US20070188805A1', 'US20070188805A9'),
    ('US20070188805A1', 'US99999999999A1'),
    ('https://patents.google.com/patent/US20070188805A1/en', 'https://patents.google.com/patent/US20070188805A9/en'),
])
def test_broken_or_invented_citations_fail(tmp_path, before, after):
    root = _copy(tmp_path)
    doc = root / 'docs/commercialization.md'
    doc.write_text(doc.read_text().replace(before, after))
    assert check(root)[0]


def test_duplicate_register_fails(tmp_path):
    root = _copy(tmp_path)
    path = root / 'docs/patents.json'
    data = json.loads(path.read_text())
    data['patents'].append(data['patents'][0])
    path.write_text(json.dumps(data))
    assert 'duplicate publication in register' in check(root)[0]


def test_live_metadata_requires_number_and_title():
    records = json.loads((ROOT / 'docs/patents.json').read_text())['patents']
    pages = {p['url']: f'<meta name="citation_patent_publication_number" content="{p["number"]}"><meta name="DC.title" content="{p["title"]}">' for p in records}
    assert check(online=True, fetch=pages.__getitem__)[0] == []
    assert check(online=True, fetch=lambda url: '<html>not a patent</html>')[0]


def test_network_failure_is_not_a_pass():
    def unavailable(url):
        raise TimeoutError('fixture timeout')
    errors, _, _ = check(online=True, fetch=unavailable)
    assert len(errors) == 7
    assert all('cannot verify' in error for error in errors)
