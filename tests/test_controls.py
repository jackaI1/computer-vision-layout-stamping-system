"""Input controls and the local-only processing boundary."""
import ast
from pathlib import Path

import fitz

import app as ui

ROOT = Path(__file__).resolve().parent.parent
NETWORK_MODULES = {'socket', 'requests', 'urllib', 'urllib3', 'http', 'httpx',
                   'aiohttp', 'ftplib', 'smtplib', 'ssl', 'websockets'}


def _pdf(pages=1, password=None):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=200, height=200)
    if password:
        data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,
                           owner_pw=password, user_pw=password)
    else:
        data = doc.tobytes()
    doc.close()
    return data


def test_readable_pdf_is_accepted():
    assert ui._validate_pdf(_pdf()) == (True, '')


def test_non_pdf_bytes_are_rejected_with_a_reason():
    ok, why = ui._validate_pdf(b'this is not a pdf')
    assert not ok and 'not a readable PDF' in why


def test_password_protected_pdf_is_rejected_with_a_reason():
    ok, why = ui._validate_pdf(_pdf(password='secret'))
    assert not ok and 'password' in why


def test_stamper_package_imports_no_network_modules():
    offenders = []
    for path in sorted((ROOT / 'stamper').glob('*.py')):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                if name.split('.')[0] in NETWORK_MODULES:
                    offenders.append(f'{path.name}: {name}')
    assert not offenders
