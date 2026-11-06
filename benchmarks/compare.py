"""Compare uninstrumented runs and verify that optimization kept placements."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compare(directory: Path) -> str:
    reports = [json.loads((directory / f'{label}-timing.json').read_text())
               for label in ('before', 'after', 'cached')]
    before, after, cached = reports
    for report in reports:
        if report['mode'] != 'timing':
            raise ValueError('Only uninstrumented timing runs can be compared')
        if report['placements'] != before['placements']:
            raise ValueError('Placement coordinates or coverage changed')
    cold_gain = 100 * (1 - after['median_seconds'] / before['median_seconds'])
    warm_gain = 100 * (1 - cached['warm_median_seconds'] / before['median_seconds'])
    return (f'Four-sheet placement and export, identical placements:\n'
            f"Before: {before['median_seconds']:.6f}s median\n"
            f"After (no cache): {after['median_seconds']:.6f}s median ({cold_gain:.1f}% less time)\n"
            f"After (warm analysis cache): {cached['warm_median_seconds']:.6f}s median ({warm_gain:.1f}% less time)\n")


def sampling_summary(directory: Path):
    summary = {}
    for label in ('before', 'after'):
        data = json.loads((directory / f'{label}-py-spy.json').read_text())
        frames = data['shared']['frames']
        counts = {}
        total = 0
        for profile in data['profiles']:
            for sample in profile['samples']:
                total += 1
                # Inclusive stack presence, not additive stage wall time.
                for name in {frames[i]['name'] for i in sample}:
                    if name in ('analyze_page', 'integral_image', '_integral_image',
                                '_most_open_candidate', 'render_stamped_pdf'):
                        counts[name] = counts.get(name, 0) + 1
        if total == 0:
            raise ValueError('py-spy did not record any samples')
        summary[label] = {'total_samples': total, 'inclusive_samples': counts}
    (directory / 'py-spy-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, nargs='?', default=Path('output/performance'))
    parser.add_argument('--sampling', action='store_true')
    args = parser.parse_args()
    print(compare(args.directory))
    if args.sampling:
        print(json.dumps(sampling_summary(args.directory), indent=2))
