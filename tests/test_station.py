"""Real decoding, synthetic light challenges, placement and fail-low interface."""
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
import pytest

from stamper import station
from stamper.station_demo import demo_recipe, fixture, lighting, sensitivity_cases

CASES = list(sensitivity_cases())


@pytest.mark.parametrize('name,image,expected', CASES, ids=[c[0] for c in CASES])
def test_lighting_and_contrast_sensitivity(name, image, expected):
    result = station.inspect(image, fixture(False), demo_recipe())
    assert result['plc_pass'] == int(expected), (name, result)
    assert result['status'] == ('PASS' if expected else 'FAIL')
    assert bool(result['reasons']) != expected
    if expected:
        assert result['codes'][0]['decoded'] == [{'format': 'Code128', 'text': 'DEMO-042'}]
        assert result['codes'][1]['decoded'] == [{'format': 'QRCode', 'text': 'DEMO-042:REV-B'}]


def test_reference_normalization_tolerates_different_calibration_light():
    result = station.inspect(lighting(fixture(), gain=.4),
                             lighting(fixture(False), gain=.7), demo_recipe())
    assert result['plc_pass'] == 1


@pytest.mark.parametrize('rotation', [90, 180, 270])
def test_rotated_1d_and_2d_labels_are_actually_read(rotation):
    image = fixture()
    # The 1D ROI is wide: 90-degree bars need a larger inspection region.
    data = asdict(demo_recipe())
    data['codes'] = [{'name': 'label', 'roi': [330, 30, 880, 475],
                      'format': 'Code128', 'text': 'DEMO-042'}]
    image.paste(220, (330, 30, 880, 475))
    label = fixture().crop((380, 55, 809, 205)).rotate(rotation, expand=True)
    image.paste(label, (400, 35))
    assert station.inspect(image, fixture(False), station.Recipe.from_dict(data))['plc_pass'] == 1
    # QR is square and remains inside the existing ROI for any quarter turn.
    image = fixture()
    roi = demo_recipe().codes[1].roi
    image.paste(image.crop(roi).rotate(rotation), roi[:2])
    assert station.inspect(image, fixture(False), demo_recipe())['plc_pass'] == 1


def test_datamatrix_is_supported_with_exact_expected_content():
    data = asdict(demo_recipe())
    data['codes'][1]['format'] = 'DataMatrix'
    result = station.inspect(fixture(format_2d='DataMatrix'), fixture(False),
                             station.Recipe.from_dict(data))
    assert result['plc_pass'] == 1
    assert result['codes'][1]['decoded'][0]['format'] == 'DataMatrix'


def test_matching_payload_in_wrong_format_is_rejected():
    result = station.inspect(fixture(format_2d='DataMatrix'), fixture(False), demo_recipe())
    assert result['plc_pass'] == 0
    assert 'code_mismatch:revision' in result['reasons']


def test_expected_code_outside_its_roi_cannot_rescue_missing_label():
    image = fixture(text_2d=None)
    label = fixture().crop((490, 270, 635, 415))
    image.paste(label, (290, 250))
    result = station.inspect(image, fixture(False), demo_recipe())
    assert result['plc_pass'] == 0
    assert 'code_unreadable:revision' in result['reasons']


def test_extra_wrong_label_in_same_roi_is_rejected():
    import zxingcpp
    image = fixture()
    barcode = zxingcpp.create_barcode('WRONG', zxingcpp.BarcodeFormat.QRCode)
    image.paste(Image.fromarray(np.asarray(barcode.to_image(scale=3))), (680, 270))
    result = station.inspect(image, fixture(False), demo_recipe())
    assert result['plc_pass'] == 0
    assert len(result['codes'][1]['decoded']) == 2


@pytest.mark.parametrize('box,reason', [
    ((130, 140, 170, 180), 'part_area_out_of_range'),
    ((40, 60, 279, 299), 'part_area_out_of_range'),
    ((40, 75, 160, 270), 'part_off_center'),
])
def test_small_oversize_and_shifted_parts_fail_even_with_good_codes(box, reason):
    image = fixture(False)
    ImageDraw.Draw(image).rectangle(box, fill=55)
    result = station.inspect(image, fixture(False), demo_recipe())
    assert result['plc_pass'] == 0
    assert reason in result['reasons']
    assert all(c['matches'] for c in result['codes'])


def test_saturated_glare_on_empty_fixture_is_not_presence_evidence():
    image = fixture(False)
    ImageDraw.Draw(image).rectangle((85, 100, 235, 260), fill=255)
    result = station.inspect(image, fixture(False), demo_recipe())
    assert result['plc_pass'] == 0
    assert 'part_glare' in result['reasons']
    assert result['presence']['changed_fraction'] == 0


@pytest.mark.parametrize('which', ['image', 'empty'])
def test_wrong_frame_size_fails_without_resizing_calibration(which):
    image, empty = fixture(), fixture(False)
    if which == 'image':
        image = image.resize((450, 240))
    else:
        empty = empty.resize((450, 240))
    assert station.inspect(image, empty, demo_recipe()) == station.failed('frame_size_mismatch')


def test_bad_reference_lighting_is_rejected():
    assert station.inspect(fixture(), lighting(fixture(False), gain=.01),
                           demo_recipe())['reasons'] == ['reference_lighting_invalid']


@pytest.mark.parametrize('key,value', [
    ('part_roi', [-1, 0, 40, 40]), ('part_roi', [0, 0, 1000, 40]),
    ('part_roi', [1, 1, 1, 2]), ('part_roi', [0, 0, 2.1, 4]),
    ('background_roi', [40, 60, 280, 300]), ('frame_size', [0, 480]),
    ('frame_size', [20000, 20000]), ('difference_threshold', float('nan')),
    ('difference_threshold', 0), ('min_area', .9), ('max_glare', True),
    ('center_tolerance', float('inf')), ('min_background', 0),
    ('max_background', 256), ('codes', []), ('typo', 123),
])
def test_invalid_recipes_are_rejected(key, value):
    data = asdict(demo_recipe())
    data[key] = value
    with pytest.raises(ValueError):
        station.Recipe.from_dict(data)


@pytest.mark.parametrize('mutation', ['duplicate', 'empty-text', 'bad-format', 'overlap'])
def test_invalid_code_recipes_are_rejected(mutation):
    data = asdict(demo_recipe())
    if mutation == 'duplicate':
        data['codes'][1]['name'] = data['codes'][0]['name']
    elif mutation == 'empty-text':
        data['codes'][0]['text'] = ''
    elif mutation == 'bad-format':
        data['codes'][0]['format'] = 'not-a-format'
    else:
        data['codes'][0]['roi'] = data['part_roi']
    with pytest.raises(ValueError):
        station.Recipe.from_dict(data)


def _inputs(tmp_path):
    recipe, image, empty = [tmp_path / f'{n}.{suffix}' for n, suffix in
                            [('recipe', 'json'), ('image', 'png'), ('empty', 'png')]]
    recipe.write_text(json.dumps(asdict(demo_recipe())))
    fixture().save(image)
    fixture(False).save(empty)
    return ['--recipe', str(recipe), '--image', str(image), '--empty', str(empty)]


def test_cli_pass_then_fail_does_not_reuse_previous_high(tmp_path):
    args = _inputs(tmp_path)
    for present, expected in [(True, 0), (False, 1), (True, 0)]:
        fixture(present).save(tmp_path / 'image.png')
        proc = subprocess.run([sys.executable, '-m', 'stamper.station', *args],
                              text=True, capture_output=True, timeout=30)
        assert proc.returncode == expected, proc.stderr
        result = json.loads(proc.stdout)
        assert result['plc_pass'] == int(present)
        assert result['schema_version'] == 1


@pytest.mark.parametrize('failure', ['missing', 'corrupt-image', 'bad-json', 'decoder'])
def test_cli_processing_errors_emit_fail_low_json(tmp_path, capsys, monkeypatch, failure):
    args = _inputs(tmp_path)
    if failure == 'missing':
        (tmp_path / 'image.png').unlink()
    elif failure == 'corrupt-image':
        (tmp_path / 'image.png').write_bytes(b'not an image')
    elif failure == 'bad-json':
        (tmp_path / 'recipe.json').write_text('{')
    else:
        def broken(*a, **kw):
            raise RuntimeError('decoder unavailable')
        monkeypatch.setattr(station.zxingcpp, 'read_barcodes', broken)
    assert station.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['plc_pass'] == 0
    assert result['status'] == 'FAIL'
    assert result['reasons'][0].startswith('input_or_processing_error:')


def test_demo_writes_reproducible_measured_report(tmp_path):
    from stamper.station_demo import run_demo
    report = run_demo(tmp_path)
    assert report['total'] == report['correct'] == 44
    assert report['false_passes'] == report['false_rejects'] == 0
    assert json.loads((tmp_path / 'sensitivity.json').read_text()) == report
    assert (tmp_path / 'present.png').is_file()
    assert (tmp_path / 'empty.png').is_file()
    assert len(list(tmp_path.glob('*.png'))) == 46
