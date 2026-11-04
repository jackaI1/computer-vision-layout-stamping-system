#!/usr/bin/env python3
"""Check assessment citations offline; --online rechecks publication identity."""
from __future__ import annotations

import argparse
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PATENT = re.compile(r'(?:US\d{11}A1|CA\d{7}A1|WO\d{10}A1|EP\d{7}A1)')
MENTION = re.compile(r'\b(?:US|CA|WO|EP)\d+[A-Z]\d?\b')
LINK = re.compile(r'\[[^\]]*\]\(([^\s)]+)\)')


class Publication(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name') in {'citation_patent_publication_number', 'DC.title'}:
            self.meta.setdefault(attrs['name'], []).append(attrs.get('content', ''))


def check(root: Path = ROOT, online: bool = False, fetch=None) -> tuple[list[str], int, int]:
    """Return actionable errors and citation counts. Never infer existence from syntax."""
    doc = root / 'docs/commercialization.md'
    text = doc.read_text(encoding='utf-8')
    registry = json.loads((root / 'docs/patents.json').read_text(encoding='utf-8'))
    errors = []
    reviewed = date.fromisoformat(registry['reviewed_on'])
    if reviewed > date.today():
        errors.append('publication review date is in the future')
    entries = registry['patents']
    records = {p['number']: p for p in entries}
    if len(records) != len(entries):
        errors.append('duplicate publication in register')
    numbers = set(MENTION.findall(text))
    if not 6 <= len(numbers) <= 10:
        errors.append('expected 6-10 distinct patent publications')
    if numbers != set(records):
        errors.append('document publications and reviewed register differ')
    paths = set()
    links = LINK.findall(text)
    for target in links:
        url = urlsplit(target)
        if url.scheme or url.netloc or not url.path:
            continue
        resolved = (doc.parent / unquote(url.path)).resolve()
        if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
            errors.append(f'missing or outside-repository citation: {target}')
        paths.add(url.path)
    for number in sorted(numbers):
        p = records.get(number)
        if not PATENT.fullmatch(number) or p is None:
            errors.append(f'invalid or unreviewed publication: {number}')
            continue
        expected = f'https://patents.google.com/patent/{number}/en'
        if p['url'] != expected or expected not in links:
            errors.append(f'publication URL does not match number: {number}')
        if not p['title'].strip() or date.fromisoformat(p['publication_date']) > reviewed:
            errors.append(f'invalid publication metadata: {number}')
        if online:
            try:
                if fetch is None:
                    with urlopen(expected, timeout=20) as response:
                        page = response.read(2_000_000).decode('utf-8')
                else:
                    page = fetch(expected)
                parsed = Publication()
                parsed.feed(page)
                norm = lambda s: ' '.join(s.lower().split())
                if number not in [v.replace(':', '') for v in parsed.meta.get('citation_patent_publication_number', [])]:
                    errors.append(f'publication identity mismatch: {number}')
                if norm(p['title']) not in [norm(t) for t in parsed.meta.get('DC.title', [])]:
                    errors.append(f'publication title mismatch: {number}')
            except Exception as exc:
                errors.append(f'cannot verify {number}: {type(exc).__name__}')
    return errors, len(numbers), len(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--online', action='store_true', help='fetch publication identity and title; fail closed')
    args = parser.parse_args()
    try:
        errors, patents, paths = check(online=args.online)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Invalid assessment/register: {exc}', file=sys.stderr)
        return 1
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    mode = 'live publication metadata' if args.online else 'reviewed publication register'
    print(f'PASS: {patents} patent publications, {paths} repository paths ({mode}).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
