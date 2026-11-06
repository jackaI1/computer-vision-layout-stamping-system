"""Generate a repeatable labelled fixture and measure lighting sensitivity."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import zxingcpp

from .station import Recipe, inspect


def demo_recipe():
    return Recipe.from_dict({
        'frame_size': [900, 480], 'part_roi': [40, 60, 280, 300],
        'background_roi': [40, 340, 280, 440],
        'codes': [
            {'name': 'drawing', 'roi': [330, 30, 880, 230],
             'format': 'Code128', 'text': 'DEMO-042'},
            {'name': 'revision', 'roi': [420, 245, 780, 475],
             'format': 'QRCode', 'text': 'DEMO-042:REV-B'}]})


def fixture(present=True, text_1d='DEMO-042', text_2d='DEMO-042:REV-B',
            format_2d='QRCode'):
    """All content is invented: a fixture for a labelled drawing/seal carrier."""
    yy, xx = np.mgrid[:480, :900]
    texture = 220 + 3 * np.sin(xx / 27) + 2 * np.cos(yy / 19)
    image = Image.fromarray(texture.astype(np.uint8))
    if present:
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((85, 100, 235, 260), radius=15, fill=55)
        draw.ellipse((140, 160, 180, 200), fill=220)
    for text, fmt, location, scale in (
        (text_1d, 'Code128', (380, 55), 3),
        (text_2d, format_2d, (490, 270), 5)):
        if text is not None:
            barcode = zxingcpp.create_barcode(text, getattr(zxingcpp.BarcodeFormat, fmt))
            image.paste(Image.fromarray(np.asarray(barcode.to_image(scale=scale))), location)
    return image


def lighting(image, gain=1.0, contrast=1.0, glare=0, noise=0.0):
    data = np.asarray(image, dtype=np.float32)
    data = (220 + contrast * (data - 220)) * gain
    if noise:
        data += np.random.default_rng(42).normal(0, noise, data.shape)
    image = Image.fromarray(np.clip(data, 0, 255).astype(np.uint8))
    if glare:
        # Specular reflection crossing the part; at radius 65 it hides too much.
        ImageDraw.Draw(image).ellipse((110 - glare, 130 - glare,
                                      110 + glare, 130 + glare), fill=255)
    return image


def sensitivity_cases():
    # Both a populated fixture and its empty control at every setting.
    for gain in (0.25, 0.5, 1.0):
        for contrast in (0.35, 0.6, 1.0):
            for glare in (0, 15):
                for present in (False, True):
                    name = f'gain-{gain}_contrast-{contrast}_glare-{glare}_part-{int(present)}'
                    yield name, lighting(fixture(present), gain, contrast, glare, noise=1), present
    # Deliberately unusable conditions must fail, including when labels decode.
    yield 'too-dark', lighting(fixture(), gain=.04), False
    yield 'severe-glare', lighting(fixture(), glare=65), False
    yield 'overexposed', lighting(fixture(), gain=3), False
    yield 'lost-contrast', lighting(fixture(), contrast=.05), False
    yield 'wrong-drawing', fixture(text_1d='DEMO-099'), False
    yield 'wrong-revision', fixture(text_2d='DEMO-042:REV-A'), False
    yield 'missing-1d', fixture(text_1d=None), False
    yield 'missing-2d', fixture(text_2d=None), False


def run_demo(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    recipe = demo_recipe()
    empty = fixture(False)
    empty.save(output / 'empty.png')
    fixture().save(output / 'present.png')
    (output / 'recipe.json').write_text(json.dumps(asdict(recipe), indent=2) + '\n')
    rows = []
    for name, image, expected in sensitivity_cases():
        result = inspect(image, empty, recipe)
        image.save(output / f'{name}.png')
        rows.append({'case': name, 'expected_pass': expected,
                     'correct': bool(result['plc_pass']) == expected, **result})
    report = {'total': len(rows), 'correct': sum(r['correct'] for r in rows),
              'false_passes': sum(r['plc_pass'] and not r['expected_pass'] for r in rows),
              'false_rejects': sum(not r['plc_pass'] and r['expected_pass'] for r in rows),
              'cases': rows}
    (output / 'sensitivity.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('output/station'))
    args = parser.parse_args(argv)
    report = run_demo(args.output_dir)
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}))
    return 0 if report['correct'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
