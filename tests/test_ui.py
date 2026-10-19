"""Real Streamlit review controls with generated in-memory PDFs."""
from streamlit.testing.v1 import AppTest

REVIEW = '''
import app as ui
import streamlit as st
import fitz
from io import BytesIO
from PIL import Image, ImageDraw
from stamper.stamp_image import load_stamp_from_bytes
from stamper.config import Settings
for key in ('placements', 'auto', 'auto_sig', 'removed', 'collapsed'):
    st.session_state.setdefault(key, {})
with fitz.open() as doc:
    doc.new_page(width=400, height=400)
    doc.new_page(width=40, height=40)
    data = doc.tobytes()
image = Image.new('RGB', (80, 80), 'white')
ImageDraw.Draw(image).ellipse((4,4,75,75), outline='blue', width=3)
buf = BytesIO(); image.save(buf, format='PNG')
seal = load_stamp_from_bytes(buf.getvalue())
s = Settings(keepout_width_frac=0, keepout_height_frac=0, keepout_pad_in=0)
ui._prepare_file('synthetic', data, s)
ui._render_file_ui('synthetic.pdf', 'synthetic', data, seal, '2026-10-19', '_stamped', s)
st.session_state['downloaded'] = ui._make_download_callable('synthetic', data, seal, '2026-10-19', s)()
'''


def test_apply_to_all_fits_mixed_page_sizes():
    at = AppTest.from_string(REVIEW, default_timeout=15).run()
    assert not at.exception
    apply = next(b for b in at.button if 'Apply this position' in b.label)
    apply.click().run()
    assert not at.exception
    for p in at.session_state['placements']['synthetic'].values():
        assert p.rect().x0 >= 0 and p.rect().y0 >= 0
        assert p.rect().x1 <= p.page_width_pt and p.rect().y1 <= p.page_height_pt


def test_sidebar_exposes_date_colour_and_keeps_placement_cache_stable():
    at = AppTest.from_string('''
import app as ui
import streamlit as st
*_, settings = ui._sidebar()
st.session_state['settings'] = settings
''').run()
    assert not at.exception
    before = at.session_state['settings']
    colour = next(c for c in at.color_picker if c.label == 'Date colour')
    colour.set_value('#ff0000').run()
    after = at.session_state['settings']
    assert after.date_color == (1, 0, 0)
    assert after.cache_key() == before.cache_key()
    assert after.render_key() != before.render_key()


def test_sidebar_padding_floor_and_caption_setting():
    at = AppTest.from_string('''
import app as ui
import streamlit as st
*_, settings = ui._sidebar()
st.session_state['settings'] = settings
''').run()
    at.slider(key='pad_overall').set_value(.8).run()
    assert at.session_state['settings'].margin_left_in == .8
    next(t for t in at.text_input if t.label == 'Caption under the seal').set_value('SYNTHETIC').run()
    assert at.session_state['settings'].bottom_text == 'SYNTHETIC'


def test_replacing_seal_file_invalidates_cached_bytes(tmp_path):
    import app as ui
    path = tmp_path / 'synthetic.png'
    path.write_bytes(b'first')
    before = path.stat()
    assert ui._read_seal_bytes(str(path), (before.st_mtime_ns, before.st_size)) == b'first'
    path.write_bytes(b'replacement')
    after = path.stat()
    assert ui._read_seal_bytes(str(path), (after.st_mtime_ns, after.st_size)) == b'replacement'


def test_manual_edits_and_removal_reach_live_download(monkeypatch):
    import fitz
    import streamlit as st
    # AppTest supports full script reruns only. Preserve the real rerun and
    # state changes while adapting the fragment scheduling to its test driver.
    rerun = st.rerun
    monkeypatch.setattr(st, 'rerun', lambda **kw: rerun())
    at = AppTest.from_string(REVIEW, default_timeout=15).run()
    assert not at.exception
    at.slider(key='x_synthetic_0').set_value(1.5).run()
    assert not at.exception
    assert at.session_state['placements']['synthetic'][0].center_x_pt == 108
    at.button(key='rm_synthetic_0').click().run()
    assert not at.exception
    with fitz.open(stream=at.session_state['downloaded'], filetype='pdf') as out:
        assert not out[0].get_images()
        assert out[1].get_images()
    at.button(key='unrm_synthetic_0').click().run()
    assert not at.exception
    assert at.session_state['placements']['synthetic'][0].center_x_pt == 108
    at.button(key='resetbtn_synthetic_0').click().run()
    assert not at.exception
    assert at.session_state['placements']['synthetic'][0].source == 'whitespace'


def test_download_sanitizes_late_stale_automatic_placement():
    import fitz
    script = REVIEW[:REVIEW.index("ui._render_file_ui")] + '''
from stamper.placement import Placement
s = Settings()
st.session_state['placements']['synthetic'] = {
    0: Placement(0, 350, 50, 100, 'whitespace', 0, 400, 400)}
st.session_state['downloaded'] = ui._make_download_callable('synthetic', data, seal, '2026-10-19', s)()
'''
    at = AppTest.from_string(script).run()
    assert not at.exception
    with fitz.open(stream=at.session_state['downloaded'], filetype='pdf') as doc:
        assert doc[0].get_image_info()[0]['bbox'][0] < 212


def test_deferred_downloads_keep_the_page_alive_for_bulk_requests():
    at = AppTest.from_string(REVIEW, default_timeout=15).run()
    assert not at.exception
    # This flag is the browser contract: a download must not trigger a rerun
    # that tears down the other deferred downloads in the bulk-click burst.
    assert at.get('download_button')[0].proto.ignore_rerun
