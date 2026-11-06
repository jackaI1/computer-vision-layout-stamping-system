"""Fixed-camera part presence and label checks. No network or hardware output."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
import zxingcpp

FORMATS = {name: getattr(zxingcpp.BarcodeFormat, name)
           for name in ('Code128', 'QRCode', 'DataMatrix')}


def _roi(value, size):
    if (not isinstance(value, (list, tuple)) or len(value) != 4
            or any(type(v) is not int for v in value)):
        raise ValueError('ROIs must contain four integer pixel coordinates')
    x0, y0, x1, y1 = value
    if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
        raise ValueError('ROI is empty or outside the configured frame')
    return tuple(value)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _crop(gray, roi):
    x0, y0, x1, y1 = roi
    return gray[y0:y1, x0:x1]


@dataclass(frozen=True)
class CodeCheck:
    name: str
    roi: tuple[int, int, int, int]
    format: str
    text: str


@dataclass(frozen=True)
class Recipe:
    frame_size: tuple[int, int]
    part_roi: tuple[int, int, int, int]
    background_roi: tuple[int, int, int, int]
    codes: tuple[CodeCheck, ...]
    difference_threshold: float = 0.15
    min_area: float = 0.30
    max_area: float = 0.65
    center_tolerance: float = 0.15
    min_background: float = 30.0
    max_background: float = 250.0
    max_glare: float = 0.10

    @classmethod
    def from_dict(cls, data):
        """Reject bad calibration instead of clipping ROIs or ignoring typos."""
        if not isinstance(data, dict) or set(data) - {f.name for f in fields(cls)}:
            raise ValueError('Unknown recipe fields')
        values = dict(data)
        size = values['frame_size']
        if (len(size) != 2 or any(type(v) is not int or v <= 0 for v in size)
                or size[0] * size[1] > 16_000_000):
            raise ValueError('frame_size must be positive width and height, at most 16 MP')
        values['frame_size'] = tuple(size)
        regions = []
        for key in ('part_roi', 'background_roi'):
            values[key] = _roi(values[key], size)
            regions.append(values[key])
        codes = []
        for item in values['codes']:
            code = CodeCheck(**item)
            if (not isinstance(code.name, str) or not code.name
                    or not isinstance(code.text, str) or not code.text
                    or code.format not in FORMATS):
                raise ValueError('Each code needs a name, expected text and supported format')
            code = CodeCheck(code.name, _roi(code.roi, size), code.format, code.text)
            regions.append(code.roi)
            codes.append(code)
        if not codes or len({c.name for c in codes}) != len(codes):
            raise ValueError('At least one code is required; names must be unique')
        if any(_overlap(a, b) for i, a in enumerate(regions) for b in regions[i + 1:]):
            raise ValueError('Inspection and background regions must not overlap')
        values['codes'] = tuple(codes)
        recipe = cls(**values)
        for name in ('difference_threshold', 'min_area', 'max_area',
                     'center_tolerance', 'max_glare'):
            v = getattr(recipe, name)
            if type(v) not in (int, float) or not math.isfinite(v) or not 0 < v < 1:
                raise ValueError(f'{name} must be between zero and one')
        if recipe.min_area >= recipe.max_area:
            raise ValueError('min_area must be less than max_area')
        for name in ('min_background', 'max_background'):
            v = getattr(recipe, name)
            if type(v) not in (int, float) or not math.isfinite(v):
                raise ValueError(f'{name} must be finite')
        if not 0 < recipe.min_background < recipe.max_background < 255:
            raise ValueError('Background brightness bounds must lie inside 0..255')
        return recipe


def failed(reason):
    return {'schema_version': 1, 'status': 'FAIL', 'plc_pass': 0,
            'reasons': [reason], 'presence': None, 'codes': []}


def inspect(image: Image.Image, empty: Image.Image, recipe: Recipe) -> dict:
    """Return one fresh decision; PASS needs presence AND every expected code.

    ROI coordinates use top-left pixels, right/bottom exclusive. Normalize both
    images by the median brightness of a clear fixture patch. The changed area
    must have the calibrated size and centroid, and limited saturated glare.
    """
    # Validate even recipes constructed directly through the public dataclass.
    recipe = Recipe.from_dict(asdict(recipe))
    if image.size != recipe.frame_size or empty.size != recipe.frame_size:
        return failed('frame_size_mismatch')
    gray = np.asarray(image.convert('L'), dtype=np.float32)
    reference = np.asarray(empty.convert('L'), dtype=np.float32)
    level = float(np.median(_crop(gray, recipe.background_roi)))
    ref_level = float(np.median(_crop(reference, recipe.background_roi)))
    if not recipe.min_background <= ref_level <= recipe.max_background:
        return failed('reference_lighting_invalid')
    if not recipe.min_background <= level <= recipe.max_background:
        return failed('lighting_out_of_range')
    part = _crop(gray, recipe.part_roi)
    ref_part = _crop(reference, recipe.part_roi)
    changed = np.abs(part / level - ref_part / ref_level) >= recipe.difference_threshold
    # Ignore saturated pixels as presence evidence; excessive glare fails below.
    glare = part >= 254
    changed &= ~glare
    area = float(changed.mean())
    glare_fraction = float(glare.mean())
    ys, xs = np.nonzero(changed)
    offset = (max(abs(float(xs.mean()) / max(1, part.shape[1] - 1) - .5),
                  abs(float(ys.mean()) / max(1, part.shape[0] - 1) - .5))
              if len(xs) else 1.0)
    reasons = []
    if glare_fraction > recipe.max_glare:
        reasons.append('part_glare')
    if not recipe.min_area <= area <= recipe.max_area:
        reasons.append('part_area_out_of_range')
    if offset > recipe.center_tolerance:
        reasons.append('part_off_center')
    presence = {'present': not reasons, 'changed_fraction': round(area, 5),
                'center_offset_fraction': round(offset, 5),
                'glare_fraction': round(glare_fraction, 5),
                'background_brightness': round(level, 2)}
    codes = []
    for check in recipe.codes:
        # Read all supported symbologies in this area so a wrong format cannot
        # silently pass just because the expected label is also visible.
        decoded = zxingcpp.read_barcodes(
            np.ascontiguousarray(_crop(gray, check.roi), dtype=np.uint8),
            formats=tuple(FORMATS.values()))
        found = sorted({(b.format.name, b.text) for b in decoded if b.valid})
        matches = found == [(check.format, check.text)]
        codes.append({'name': check.name, 'matches': matches,
                      'decoded': [{'format': f, 'text': t} for f, t in found]})
        if not matches:
            reasons.append(f'code_mismatch:{check.name}' if found else f'code_unreadable:{check.name}')
    return {'schema_version': 1, 'status': 'FAIL' if reasons else 'PASS',
            'plc_pass': int(not reasons), 'reasons': reasons,
            'presence': presence, 'codes': codes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--empty', required=True, type=Path)
    parser.add_argument('--recipe', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        recipe = Recipe.from_dict(json.loads(args.recipe.read_text()))
        with Image.open(args.image) as image, Image.open(args.empty) as empty:
            result = inspect(image, empty, recipe)
        code = 0 if result['plc_pass'] else 1
    except Exception as exc:
        # No previous result can survive an acquisition/configuration/decoder
        # error. An adapter must treat process failure or missing JSON as LOW too.
        result = failed(f'input_or_processing_error:{type(exc).__name__}')
        code = 2
    print(json.dumps(result, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
