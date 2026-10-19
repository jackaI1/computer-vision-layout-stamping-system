"""Streamlit UI for placing engineering seals on drawing sets.

Workflow
--------
1. Pick a seal (from ``stamps/`` or upload one) and the stamp date.
2. Upload one or many drawing PDFs (select a whole folder's worth at once).
3. Review the auto-suggested placements, ordered worst-first (the seal covering
   the most ink shows up at the top).
4. Click a preview or drag the sliders to move a seal -- previews update in
   real time because each page is rasterised once (cached) and the seal is
   composited in memory, and each card runs in its own fragment so adjusting one
   stamp never reruns the whole app.
5. Download each stamped PDF, or hit "Download all" (top or bottom of the list)
   to save them all individually -- full quality, non-flattened, no ZIP.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
import sys
from io import BytesIO
from pathlib import Path

import fitz
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from stamper import (
    DEFAULT_SETTINGS,
    PLACEMENT_LOGIC_VERSION,
    Settings,
    compute_placements,
    render_stamped_pdf,
    sanitize_placements,
)
from stamper.occupancy import analyze_page, disk_coverage
from stamper.placement import Placement, placement_in_keepout
from stamper.preview import compose_preview, render_base_page
from stamper.stamp_image import StampAsset, load_stamp_from_bytes

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
    _HAS_CLICK = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_CLICK = False

def _app_base_dir() -> Path:
    """Directory for user-facing folders (e.g. ``stamps/``).

    When running from source this is the repository root. In a packaged
    (PyInstaller) build it is the folder containing the executable, so a
    recipient can drop their seal PNG(s) into a ``stamps`` folder beside the app
    — or simply upload one in the sidebar.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _resource_dir() -> Path:
    """Directory holding bundled read-only resources (default seals).

    PyInstaller unpacks bundled data to ``sys._MEIPASS``; from source it is the
    repository root.
    """
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


# Default seals shipped with the program (bundled into the build), plus any the
# user drops into a writable ``stamps`` folder next to the app.
BUNDLED_STAMPS_DIR = _resource_dir() / "stamps"
STAMPS_DIR = _app_base_dir() / "stamps"
try:
    STAMPS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # A read-only install location is fine — seals can still be uploaded in the
    # sidebar; we just can't offer the drop-in folder.
    pass


def _seal_options() -> dict[str, Path]:
    """Map seal name -> path, from the bundled defaults and the user folder.

    A user seal with the same filename overrides a bundled one.
    """
    seals: dict[str, Path] = {}
    for d in (BUNDLED_STAMPS_DIR, STAMPS_DIR):
        if d.exists():
            for p in sorted(d.glob("*.png")):
                seals[p.name] = p
    return seals


st.set_page_config(page_title="Engineering Stamp Placer", layout="wide")


# --------------------------------------------------------------------------- #
# Cached heavy work
# --------------------------------------------------------------------------- #
# Every cached function is keyed on ``fid`` (a short content hash) rather than
# the raw PDF, with the bytes passed as an unhashed ``_pdf_bytes`` argument. That
# avoids re-hashing tens of megabytes on each rerun while still keying the cache
# to the file's content.
@st.cache_resource(show_spinner=False)
def _open_doc(fid: str, _pdf_bytes: bytes):
    doc = fitz.open(stream=_pdf_bytes, filetype="pdf")
    # Owner-locked PDFs (no user password) authenticate with an empty string;
    # without this, page rendering raises "document closed or encrypted". Files
    # that need a real password are rejected up front in main().
    if doc.needs_pass:
        doc.authenticate("")
    return doc


@st.cache_data(show_spinner="Analyzing pages for whitespace…")
def _auto_placements(fid: str, settings_key: tuple, logic_version: int,
                     _pdf_bytes: bytes, _settings: Settings) -> list[dict]:
    # ``settings_key`` + ``logic_version`` form the cache identity; bumping the
    # version invalidates placements made by older logic.
    doc = _open_doc(fid, _pdf_bytes)
    return [p.to_dict() for p in compute_placements(doc, _settings)]


@st.cache_resource(max_entries=48, show_spinner=False)
def _base_image(fid: str, page_index: int, dpi: int, _pdf_bytes: bytes):
    """Rasterise a page once for fast in-memory preview compositing."""
    doc = _open_doc(fid, _pdf_bytes)
    return render_base_page(doc[page_index], dpi)


@st.cache_resource(max_entries=48, show_spinner=False)
def _occupancy(fid: str, page_index: int, settings_key: tuple,
               _pdf_bytes: bytes, _settings: Settings):
    doc = _open_doc(fid, _pdf_bytes)
    return analyze_page(doc[page_index], _settings)


# The stamped PDF is rendered lazily, when a download is actually clicked (see
# ``_make_download_callable``). Streamlit's deferred-download callables run
# outside a script context, so we memoise with a plain bounded dict rather than
# ``st.cache_data``. Keyed on everything that affects the output, so a download
# always reflects the current placements and is only re-rendered when they
# change.
_RENDER_CACHE: dict[tuple, bytes] = {}
_RENDER_ORDER: list[tuple] = []
_RENDER_CACHE_MAX = 32


def _render_stamped(fid: str, placement_sig: tuple, date_str: str,
                    stamp_digest: str, settings_key: tuple,
                    placements: list[Placement], stamp: StampAsset,
                    settings: Settings, pdf_bytes: bytes) -> bytes:
    key = (fid, placement_sig, date_str, stamp_digest, settings_key)
    cached = _RENDER_CACHE.get(key)
    if cached is not None:
        return cached
    data = render_stamped_pdf(pdf_bytes, placements, stamp, date_str, settings)
    _RENDER_CACHE[key] = data
    _RENDER_ORDER.append(key)
    while len(_RENDER_ORDER) > _RENDER_CACHE_MAX:
        _RENDER_CACHE.pop(_RENDER_ORDER.pop(0), None)
    return data


@st.cache_data(show_spinner=False, max_entries=512)
def _preview(fid: str, page_index: int, cx_pt: float, cy_pt: float, dia_pt: float,
             draw_seal: bool, date_str: str, stamp_digest: str, preview_key: tuple,
             _pdf_bytes: bytes, _stamp: StampAsset, _settings: Settings):
    """Compose (and memoise) one preview image.

    Compositing a preview -- crop, high-quality resize, paste the seal -- costs
    real time per page, and any full app rerun re-runs every review card.
    Memoising on the placement geometry makes those reruns near-instant whenever
    nothing moved.
    """
    base_img, base_scale = _base_image(fid, page_index, _settings.preview_dpi, _pdf_bytes)
    page_w = base_img.width / base_scale
    page_h = base_img.height / base_scale
    placement = Placement(page_index, cx_pt, cy_pt, dia_pt, "preview", 0.0,
                          page_w, page_h)
    return compose_preview(base_img, base_scale, placement, _stamp, date_str,
                           _settings, draw_seal=draw_seal)


def _preview_key(settings: Settings) -> tuple:
    """Settings that change a preview's pixels (cache identity for ``_preview``)."""
    return (settings.preview_dpi, round(settings.preview_zoom, 3),
            settings.preview_target_px, round(settings.date_font_pt, 3),
            settings.date_color, settings.bottom_text, settings.bottom_text_color)


def _file_id(pdf_bytes: bytes, name: str = "") -> str:
    """Stable per-file identity used to key session state, widgets and caches.

    Folds the upload's **name** in with its content so two files that are
    byte-identical but named differently are treated as two separate files (each
    stamped/downloaded under its own name), while a true duplicate (same name AND
    content) still collapses to one. Identical content under different names is
    re-analysed separately — a negligible cost versus losing a distinct file.
    """
    h = hashlib.sha256()
    h.update(name.encode("utf-8", "surrogatepass"))
    h.update(b"\x00")
    h.update(pdf_bytes)
    return h.hexdigest()[:16]


def _placement_sig(placements: list[Placement]) -> tuple:
    return tuple(sorted(
        (p.page_index, round(p.center_x_pt, 1), round(p.center_y_pt, 1),
         round(p.diameter_pt, 1), p.source)
        for p in placements
    ))


# --------------------------------------------------------------------------- #
# Sidebar — seal, date, settings
# --------------------------------------------------------------------------- #
_NAME_SUFFIX_DEFAULT = "_stamped"


@st.cache_data(show_spinner=False)
def _read_seal_bytes(path_str: str, fingerprint: tuple) -> bytes:
    """Read a seal PNG, cached so it isn't re-fetched on every rerun — important
    when the app runs from a network share (the read is otherwise an SMB
    round-trip each interaction). ``fingerprint`` is (mtime_ns, size); including
    it means replacing a same-named seal file on disk invalidates the cache, so a
    swapped seal is never served stale (a real hazard for a legal seal)."""
    return Path(path_str).read_bytes()


def _sidebar() -> tuple[bytes | None, str, str, str, Settings]:
    st.sidebar.header("1. Seal & date")

    seal_map = _seal_options()
    names = list(seal_map)
    options = names + ["Upload a seal…"]
    choice = st.sidebar.selectbox("Seal", options, index=0 if names else len(options) - 1)

    seal_bytes: bytes | None = None
    seal_name = ""
    if choice == "Upload a seal…":
        up = st.sidebar.file_uploader("Seal image (PNG)", type=["png"])
        if up is not None:
            seal_bytes = up.getvalue()
            seal_name = up.name
    else:
        seal_name = choice
        seal_path = seal_map[choice]
        try:
            stt = seal_path.stat()  # one cheap stat vs re-reading the whole PNG
            fingerprint = (stt.st_mtime_ns, stt.st_size)
        except OSError:
            fingerprint = (0, 0)
        seal_bytes = _read_seal_bytes(str(seal_path), fingerprint)

    if seal_bytes is not None:
        st.sidebar.image(seal_bytes, caption=seal_name, width=160)

    date_val = st.sidebar.date_input("Stamp date", value=_dt.date.today())
    date_str = date_val.strftime("%Y-%m-%d")
    st.sidebar.caption(f"Will print **{date_str}** in the seal's top hole.")

    bottom_text = st.sidebar.text_input(
        "Caption under the seal", value=DEFAULT_SETTINGS.bottom_text,
        help="Printed under the circle, auto-sized to the seal's width. "
             "Clear it to print no caption.").strip()

    name_suffix = st.sidebar.text_input(
        "Stamped file name suffix", value=_NAME_SUFFIX_DEFAULT,
        help="Appended to each file name, e.g. drawing.pdf → drawing_stamped.pdf.")

    st.sidebar.header("2. Placement settings")
    s = DEFAULT_SETTINGS
    diameter = st.sidebar.slider("Default seal diameter (in)", 1.0, 3.5,
                                 float(s.stamp_diameter_in), 0.1)
    fit_box = st.sidebar.checkbox("Fit to 'ENGINEER STAMP' box when present", True)
    font_pt = st.sidebar.slider("Date font size (pt)", 6.0, 14.0,
                                float(s.date_font_pt), 0.5)
    date_hex = st.sidebar.color_picker("Date colour", "#000000")
    date_color = tuple(int(date_hex[i:i + 2], 16) / 255 for i in (1, 3, 5))
    zoom_in = st.sidebar.slider("Preview zoom (1 = whole page)", 1.0, 8.0,
                                float(s.preview_zoom), 0.5,
                                help="1 shows the entire page; higher zooms in "
                                     "toward the seal.")
    with st.sidebar.expander("Output"):
        flatten = st.checkbox(
            "Flatten output (rasterise pages)", s.flatten_output,
            help="Bake the stamp in permanently — each page becomes an image. "
                 "Larger file; nothing selectable. Off keeps full vector quality.")
        flatten_dpi = st.slider("Flatten resolution (DPI)", 100, 300,
                                int(s.flatten_dpi), 25, disabled=not flatten)
    with st.sidebar.expander("Advanced"):
        ink = st.slider("Ink sensitivity (lower = stricter)", 100, 240,
                        s.ink_threshold, 5)
        max_clear = st.checkbox(
            "Maximise whitespace around the seal", s.maximize_clearance,
            help="When several spots are equally ink-free, pick the one "
                 "farthest from any drawing instead of the first found.")
        ko_w = st.slider("Top-right keep-out width (page frac)", 0.0, 0.5,
                         float(s.keepout_width_frac), 0.01)
        ko_h = st.slider("Top-right keep-out height (page frac)", 0.0, 0.6,
                         float(s.keepout_height_frac), 0.01)
        ko_pad = st.slider("Keep-out extra padding (in)", 0.0, 3.0,
                           float(s.keepout_pad_in), 0.25)

    m_top, m_bottom, m_left, m_right = _padding_controls()

    settings = s.with_overrides(
        stamp_diameter_in=diameter,
        fit_stamp_to_engineer_box=fit_box,
        date_font_pt=font_pt,
        date_color=date_color,
        bottom_text=bottom_text,
        preview_zoom=zoom_in,
        flatten_output=flatten,
        flatten_dpi=flatten_dpi,
        ink_threshold=ink,
        maximize_clearance=max_clear,
        margin_top_in=m_top,
        margin_bottom_in=m_bottom,
        margin_left_in=m_left,
        margin_right_in=m_right,
        keepout_width_frac=ko_w,
        keepout_height_frac=ko_h,
        keepout_pad_in=ko_pad,
    )
    return seal_bytes, seal_name, date_str, name_suffix, settings


# Per-side page padding, with one "overall minimum" that raises the floor of all
# four sliders. The floor is applied to each side's session value *before* its
# slider is created (you can't write widget state after instantiation), so when
# the overall slider goes up, every side that was below it jumps up to match.
_PAD_SIDES = (("Top", "pad_top"), ("Bottom", "pad_bottom"),
              ("Left", "pad_left"), ("Right", "pad_right"))
_PAD_DEFAULT = 0.4
_PAD_MAX = 3.0


def _padding_controls() -> tuple[float, float, float, float]:
    with st.sidebar.expander("Page padding (keep seal away from edges)"):
        st.session_state.setdefault("pad_overall", _PAD_DEFAULT)
        overall = st.slider(
            "Overall minimum padding (in)", 0.0, _PAD_MAX, step=0.05,
            key="pad_overall",
            help="Raises all four side paddings to at least this value. Lowering "
                 "it again leaves any side you set higher untouched.")
        eff: dict[str, float] = {}
        for label, key in _PAD_SIDES:
            # Lift a side's displayed value up to the floor when the overall is
            # raised. The slider keeps a fixed 0..max range (a *dynamic* min_value
            # makes Streamlit drop values when the floor is later lowered), and the
            # floor is enforced for real via max() below — so a side set above the
            # floor is never lost.
            if st.session_state.get(key, _PAD_DEFAULT) < overall:
                st.session_state[key] = overall
            side = st.slider(f"{label} padding (in)", 0.0, _PAD_MAX, step=0.05,
                             key=key)
            eff[key] = max(side, overall)
    return (eff["pad_top"], eff["pad_bottom"], eff["pad_left"], eff["pad_right"])


# --------------------------------------------------------------------------- #
# Per-file placement state
# --------------------------------------------------------------------------- #
def _sync_file(fid: str, pdf_bytes: bytes, settings: Settings) -> None:
    """(Re)compute auto placements for one file when inputs/logic change.

    Keeps two maps per file: ``auto`` (the suggestion, used for reset and source
    detection) and ``placements`` (the live, possibly-moved values). Stale
    slider widget state is cleared so it re-initialises from the new auto.
    """
    sig = (fid, settings.cache_key(), PLACEMENT_LOGIC_VERSION)
    if st.session_state["auto_sig"].get(fid) == sig:
        return
    auto = _auto_placements(fid, settings.cache_key(),
                            PLACEMENT_LOGIC_VERSION, pdf_bytes, settings)
    auto_map = {d["page_index"]: Placement.from_dict(d) for d in auto}
    st.session_state["auto"][fid] = auto_map
    st.session_state["placements"][fid] = {i: p for i, p in auto_map.items()}
    st.session_state["auto_sig"][fid] = sig
    # Drop stale slider widget state for this file.
    for key in list(st.session_state.keys()):
        if key.endswith(f"_{fid}") or f"_{fid}_" in key:
            st.session_state.pop(key, None)


def _ordered(fid: str) -> list[Placement]:
    pls = list(st.session_state["placements"][fid].values())
    pls.sort(key=lambda p: p.coverage, reverse=True)
    return pls


def _sync_state(src: str, dst: str) -> None:
    """Mirror one widget's value onto another (links a slider and a number box)."""
    st.session_state[dst] = st.session_state[src]


# Diameter fine-tune slider range (inches). Shared so written values can never
# fall outside it (a value below the min makes the slider raise on instantiation).
_DIA_MIN_IN = 0.8
_DIA_MAX_IN = 4.0


def _apply_to_all_pages(fid: str, pdf_bytes: bytes, cx: float, cy: float,
                        dia: float, settings: Settings) -> None:
    """Copy one page's seal position/size onto every page in the same file.

    The diameter is shrunk to fit any page too small for it (sets can mix
    orientations/sizes) and the centre is clamped to that page, so the seal never
    hangs off an edge. Coverage is recomputed per page and each page's widget
    state is updated so the sliders/number boxes reflect the new values.

    Writes widget-keyed session state, so it must run *before* any review-card
    widget is instantiated this run — it is invoked from ``_prepare_file`` via the
    deferred ``applyall_pending`` flag, never inline after the sliders exist.
    """
    store = st.session_state["placements"][fid]
    for j, op in list(store.items()):
        # Refit the diameter to the page so a large seal copied onto a smaller
        # page can't run off the sheet; on normal pages this is a no-op. Keep it
        # within the slider's range so the written widget value is always valid.
        pd = min(dia, op.page_width_pt, op.page_height_pt)
        pd = min(max(pd, _DIA_MIN_IN * 72.0), _DIA_MAX_IN * 72.0,
                 op.page_width_pt, op.page_height_pt)
        half = pd / 2.0
        ncx = min(max(cx, half), op.page_width_pt - half)
        ncy = min(max(cy, half), op.page_height_pt - half)
        jocc = _occupancy(fid, j, settings.cache_key(), pdf_bytes, settings)
        jcov = disk_coverage(jocc, ncx, ncy, pd)
        store[j] = Placement(j, ncx, ncy, pd, "manual", jcov,
                             op.page_width_pt, op.page_height_pt)
        st.session_state[f"x_{fid}_{j}"] = st.session_state[f"xn_{fid}_{j}"] = round(ncx / 72.0, 2)
        st.session_state[f"y_{fid}_{j}"] = st.session_state[f"yn_{fid}_{j}"] = round(ncy / 72.0, 2)
        st.session_state[f"d_{fid}_{j}"] = round(pd / 72.0, 2)


# --------------------------------------------------------------------------- #
# Per-page review card (runs in its own fragment for snappy updates)
# --------------------------------------------------------------------------- #
@st.fragment
def _review_card(fid: str, pdf_bytes: bytes, idx: int, stamp: StampAsset,
                 date_str: str, settings: Settings, layout_gen: str = "") -> None:
    """Render one page's preview and placement controls.

    ``layout_gen`` is a token that changes whenever the set/order of rendered
    files or their collapsed state changes. It is folded into the click
    component's key so that, when the layout shifts (files removed/re-added,
    a file collapsed), the iframe is remounted cleanly instead of being reused in
    a new DOM slot — the vendored streamlit-image-coordinates component only
    re-reports its height on a fresh image load, so a reused iframe handed the
    same cached bytes would otherwise stay collapsed (blank preview) until the
    card is nudged. It stays constant while only dragging a seal, so normal edits
    don't flicker.

    Each edit reruns only this fragment, so moving a seal re-composites just this
    card's cached preview (~0.1 s) and the rest of the page stays put. The edit
    is persisted to ``st.session_state['placements']`` immediately, and the
    download buttons read that live state on click (see
    ``_make_download_callable``), so a download always reflects the latest move
    without re-rendering the whole app on every drag.
    """
    store = st.session_state["placements"][fid]
    auto = st.session_state["auto"][fid][idx]
    pw, ph = auto.page_width_pt, auto.page_height_pt

    kx, ky, kd = f"x_{fid}_{idx}", f"y_{fid}_{idx}", f"d_{fid}_{idx}"
    kxn, kyn = f"xn_{fid}_{idx}", f"yn_{fid}_{idx}"  # number-box mirrors of x/y
    st.session_state.setdefault(kx, round(auto.center_x_pt / 72.0, 2))
    st.session_state.setdefault(ky, round(auto.center_y_pt / 72.0, 2))
    # Round to 2 dp so the value always lands on the diameter slider's 0.01 step
    # grid (an off-grid value is silently snapped on render, desyncing the slider
    # from the stored placement).
    st.session_state.setdefault(kd, round(auto.diameter_pt / 72.0, 2))
    st.session_state.setdefault(kxn, st.session_state[kx])
    st.session_state.setdefault(kyn, st.session_state[ky])

    # Apply a pending "reset to auto" here, *before* the slider widgets exist
    # (widget-keyed session state can't be written once the widget is created).
    if st.session_state.pop(f"reset_{fid}_{idx}", False):
        st.session_state[kx] = st.session_state[kxn] = round(auto.center_x_pt / 72.0, 2)
        st.session_state[ky] = st.session_state[kyn] = round(auto.center_y_pt / 72.0, 2)
        st.session_state[kd] = round(auto.diameter_pt / 72.0, 2)

    # Small pages can need seals below the normal fine-tune range. Clamp before
    # creating widgets, including after diameter changes and apply-to-all.
    dia_max = min(_DIA_MAX_IN, pw / 72.0, ph / 72.0)
    dia_min = min(_DIA_MIN_IN, dia_max / 2)
    st.session_state[kd] = min(max(st.session_state[kd], dia_min), dia_max)
    half_in = st.session_state[kd] / 2
    st.session_state[kx] = st.session_state[kxn] = min(
        max(st.session_state[kx], half_in), pw / 72.0 - half_in)
    st.session_state[ky] = st.session_state[kyn] = min(
        max(st.session_state[ky], half_in), ph / 72.0 - half_in)

    # Current placement is driven entirely by the slider session-state values.
    cx = st.session_state[kx] * 72.0
    cy = st.session_state[ky] * 72.0
    dia = st.session_state[kd] * 72.0
    moved = (abs(cx - auto.center_x_pt) > 0.5 or abs(cy - auto.center_y_pt) > 0.5
             or abs(dia - auto.diameter_pt) > 0.5)
    source = "manual" if moved else auto.source

    occ = _occupancy(fid, idx, settings.cache_key(), pdf_bytes, settings)
    cov = disk_coverage(occ, cx, cy, dia)
    placement = Placement(idx, cx, cy, dia, source, cov, pw, ph)
    store[idx] = placement  # persist for download

    removed_set = st.session_state["removed"].setdefault(fid, set())
    is_removed = idx in removed_set

    cov_pct = cov * 100.0
    flag = "🟢" if cov_pct < 1 else ("🟡" if cov_pct < 8 else "🔴")
    src_label = {"engineer_box": "Engineer-stamp box", "whitespace": "Auto whitespace",
                 "manual": "Manually placed"}.get(source, source)
    in_corner = source == "manual" and placement_in_keepout(placement, settings)

    if is_removed:
        st.markdown(f"#### 🚫 Page {idx + 1} — no stamp")
        st.caption("This page will be left **unstamped**.")
    else:
        st.markdown(f"#### {flag} Page {idx + 1} — {src_label}")
        warn = "  ⛔ **in reserved top-right corner**" if in_corner else ""
        st.caption(f"Covers ~{cov_pct:.1f}% ink · center "
                   f"({cx:.0f}, {cy:.0f}) pt{warn}")

    try:
        preview = _preview(fid, idx, round(cx, 1), round(cy, 1), round(dia, 1),
                           not is_removed, date_str, stamp.digest,
                           _preview_key(settings), pdf_bytes, stamp, settings)
    except Exception:
        # A page that fails to rasterise must not crash the fragment; show a note
        # and still offer the fine-tune controls / download.
        preview = None

    col_img, col_ctl = st.columns([3, 2], gap="medium")

    with col_img:
        if preview is None:
            st.warning("Preview unavailable for this page (it could not be "
                       "rendered). The stamp will still be applied.")
        # Click-to-move only makes sense while the page is being stamped.
        elif _HAS_CLICK and not is_removed:
            st.caption("Click anywhere to move the seal there.")
            # ``use_column_width="always"`` keeps the preview inside its column.
            # A fixed natural-pixel width would overflow the column for *wide*
            # (landscape) previews and the iframe would clip the right edge --
            # exactly where the seal usually sits -- so it looked uncropped.
            click = streamlit_image_coordinates(
                Image.open(BytesIO(preview.png_bytes)),
                key=f"click_{fid}_{idx}_{layout_gen}", use_column_width="always",
            )
            last = f"lastclick_{fid}_{idx}_{layout_gen}"
            if click is not None:
                # Include the event time so a second click on the *same* pixel
                # (e.g. moving the seal away and back) is still registered.
                token = (click["x"], click["y"], click.get("unix_time"))
                if st.session_state.get(last) != token:
                    st.session_state[last] = token
                    # The component reports clicks in *displayed* pixels (the
                    # image is scaled to the column), so rescale to the preview's
                    # natural pixels before mapping to page points.
                    disp_w = click.get("width") or preview.width_px
                    disp_h = click.get("height") or preview.height_px
                    px = click["x"] * preview.width_px / disp_w
                    py = click["y"] * preview.height_px / disp_h
                    nx, ny = preview.pixel_to_point(px, py)
                    half = dia / 2.0
                    st.session_state[kx] = st.session_state[kxn] = round(min(max(nx, half), pw - half) / 72.0, 2)
                    st.session_state[ky] = st.session_state[kyn] = round(min(max(ny, half), ph - half) / 72.0, 2)
                    st.rerun(scope="fragment")
        else:
            st.image(preview.png_bytes, width="stretch")

    with col_ctl:
        if is_removed:
            st.write("**No stamp on this page.**")
            if st.button("➕ Add stamp back", key=f"unrm_{fid}_{idx}",
                         type="primary"):
                removed_set.discard(idx)
                st.rerun(scope="fragment")
        else:
            st.write("**Fine-tune** (drag, or type an exact value)")
            xmax, ymax = round(pw / 72.0, 2), round(ph / 72.0, 2)
            # Horizontal: slider + linked number box (2-decimal precision).
            sx, nx_col = st.columns([3, 2])
            sx.slider("Horizontal (in)", 0.0, xmax, key=kx, step=0.01,
                      on_change=_sync_state, args=(kx, kxn))
            nx_col.number_input("Horizontal exact (in)", 0.0, xmax, key=kxn,
                                step=0.01, format="%.2f", label_visibility="collapsed",
                                on_change=_sync_state, args=(kxn, kx))
            sy, ny_col = st.columns([3, 2])
            sy.slider("Vertical (in)", 0.0, ymax, key=ky, step=0.01,
                      on_change=_sync_state, args=(ky, kyn))
            ny_col.number_input("Vertical exact (in)", 0.0, ymax, key=kyn,
                                step=0.01, format="%.2f", label_visibility="collapsed",
                                on_change=_sync_state, args=(kyn, ky))
            # Range kept wide so it always contains the current value regardless
            # of the default-diameter and min/max settings. Step 0.01 matches the
            # X/Y boxes so every 2-dp value (from reset/apply-to-all) is on-grid.
            st.slider("Diameter (in)", dia_min, dia_max, key=kd, step=0.01)
            if st.button("⇊ Apply this position to every page", key=f"applyall_{fid}_{idx}",
                         help="Set every page in this file to this seal's position and size."):
                # Defer: _apply_to_all_pages writes per-page widget keys, which is
                # illegal once this card's sliders exist. Record the request and
                # full-rerun; it is applied in _prepare_file before any card's
                # widgets are created (mirrors the reset-to-auto pattern above).
                st.session_state["applyall_pending"] = (fid, cx, cy, dia)
                st.rerun()
            c_reset, c_remove = st.columns(2)
            if c_reset.button("↺ Reset to auto", key=f"resetbtn_{fid}_{idx}"):
                # Defer the actual reset to the top of the next fragment run,
                # before the slider widgets are instantiated.
                st.session_state[f"reset_{fid}_{idx}"] = True
                st.rerun(scope="fragment")
            if c_remove.button("🚫 Remove stamp", key=f"rm_{fid}_{idx}",
                               help="Leave this page unstamped."):
                removed_set.add(idx)
                st.rerun(scope="fragment")

    st.divider()


# --------------------------------------------------------------------------- #
# Per-file section
# --------------------------------------------------------------------------- #
def _prepare_file(fid: str, pdf_bytes: bytes, settings: Settings) -> None:
    """Sync placements for one file and enforce the reserved-corner keep-out.

    Rendering the stamped PDF is deferred to download time (see
    ``_make_download_callable``), so this does no heavy work beyond the cached
    whitespace analysis.
    """
    doc = _open_doc(fid, pdf_bytes)
    _sync_file(fid, pdf_bytes, settings)

    # Guarantee no automatic placement sits in the reserved corner.
    fixed, relocated = sanitize_placements(doc, st.session_state["placements"][fid], settings)
    if relocated:
        st.session_state["placements"][fid] = fixed
        for i in relocated:
            p = fixed[i]
            st.session_state[f"x_{fid}_{i}"] = st.session_state[f"xn_{fid}_{i}"] = round(p.center_x_pt / 72.0, 2)
            st.session_state[f"y_{fid}_{i}"] = st.session_state[f"yn_{fid}_{i}"] = round(p.center_y_pt / 72.0, 2)
            st.session_state[f"d_{fid}_{i}"] = round(p.diameter_pt / 72.0, 2)
            st.session_state["auto"][fid][i] = p

    # Apply a deferred "apply this position to every page" request now — before any
    # of this file's review-card widgets are created, so writing their keyed state
    # is legal (see the applyall button in _review_card).
    pending = st.session_state.get("applyall_pending")
    if pending and pending[0] == fid:
        _, pcx, pcy, pdia = pending
        _apply_to_all_pages(fid, pdf_bytes, pcx, pcy, pdia, settings)
        st.session_state.pop("applyall_pending", None)


def _make_download_callable(fid: str, pdf_bytes: bytes, stamp: StampAsset,
                            date_str: str, settings: Settings):
    """Build the deferred data generator for a file's download button.

    It captures the *live* per-file placement map and removed-page set, so when
    the button is clicked it renders the stamped PDF from the current placements
    — reflecting any seal the operator just moved or removed in a fragment —
    rather than a snapshot from the last full rerun.
    """
    placements_map = st.session_state["placements"][fid]
    removed = st.session_state["removed"].setdefault(fid, set())
    # Key the render cache on the *output*-affecting settings (date, caption,
    # fonts, sizing) so editing the caption refreshes the download without
    # touching the placement cache.
    settings_key = settings.render_key()

    def _generate() -> bytes:
        placements = [p for i, p in placements_map.items() if i not in removed]
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                fixed, _ = sanitize_placements(
                    doc, {p.page_index: p for p in placements}, settings)
            placements = list(fixed.values())
            return _render_stamped(fid, _placement_sig(placements), date_str,
                                   stamp.digest, settings_key, placements, stamp,
                                   settings, pdf_bytes)
        except Exception as exc:
            # The download callable runs outside the script context, so a raised
            # error would just produce a broken/empty file with no explanation.
            # Hand back a one-page PDF stating the failure so the operator can
            # never mistake it for a successfully stamped drawing.
            return _error_pdf(
                "This drawing could not be stamped due to a rendering error:\n"
                f"{type(exc).__name__}: {exc}\n\n"
                "Try turning off 'Flatten output' (or lowering its DPI) and "
                "download again, or re-export the source PDF.")

    return _generate


def _error_pdf(message: str) -> bytes:
    """A minimal, valid one-page PDF carrying an error message."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(54, 54, page.rect.width - 54, page.rect.height - 54),
                        message, fontsize=12, fontname="helv")
    out = BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


# Each page preview is a separate streamlit-image-coordinates iframe — a real
# browsing context. A large drawing set (e.g. 184 pages) rendered all at once is
# hundreds of iframes and tens of MB of images, which makes the browser (and the
# whole machine) crawl. So big files start collapsed and expanded files render
# only a window of pages at a time. Output is unaffected — every page is still
# stamped and downloaded regardless of what is previewed.
_AUTO_COLLAPSE_PAGES = 12
_PREVIEW_PAGE_SIZE = 8


def _render_file_ui(name: str, fid: str, pdf_bytes: bytes, stamp: StampAsset,
                    date_str: str, name_suffix: str, settings: Settings,
                    layout_gen: str = "") -> None:
    # Strip characters that are illegal in Windows filenames so the suggested
    # save name is always valid.
    safe_suffix = re.sub(r'[\\/:*?"<>|]', "", name_suffix)
    stamped_name = Path(name).stem + safe_suffix + ".pdf"
    st.download_button(
        f"⬇️ Download “{stamped_name}”",
        data=_make_download_callable(fid, pdf_bytes, stamp, date_str, settings),
        file_name=stamped_name,
        mime="application/pdf", key=f"dl_{fid}", type="primary", on_click="ignore",
    )

    n_pages = len(st.session_state["placements"][fid])
    # Large files start collapsed so opening a 100+ page set doesn't render
    # hundreds of preview iframes at once (the user expands the one(s) they want).
    collapsed = st.session_state["collapsed"].get(fid, n_pages > _AUTO_COLLAPSE_PAGES)
    if st.button("▸ Show page previews" if collapsed else "▾ Minimise page previews",
                 key=f"collapse_{fid}",
                 help="Hide/show this file's per-page previews (does not affect output)."):
        st.session_state["collapsed"][fid] = not collapsed
        st.rerun()
    if collapsed:
        st.caption(f"{n_pages} page(s) — previews hidden for speed. "
                   "Click **Show page previews** to review (all pages are stamped either way).")
        return

    cards = _ordered(fid)  # worst-coverage first
    # Paginate so only a small window of heavy preview iframes is live at once.
    if len(cards) > _PREVIEW_PAGE_SIZE:
        n_win = (len(cards) + _PREVIEW_PAGE_SIZE - 1) // _PREVIEW_PAGE_SIZE

        def _winlabel(i: int) -> str:
            a = i * _PREVIEW_PAGE_SIZE + 1
            b = min((i + 1) * _PREVIEW_PAGE_SIZE, len(cards))
            return f"Showing {a}–{b} of {len(cards)} (worst coverage first)"

        win = st.selectbox(
            "Preview window", list(range(n_win)), format_func=_winlabel,
            key=f"pvwin_{fid}",
            help="Only this group of pages is rendered, to keep the app fast on large "
                 "sets. Every page is still stamped and included in the download.")
        win = win or 0
        cards = cards[win * _PREVIEW_PAGE_SIZE:(win + 1) * _PREVIEW_PAGE_SIZE]

    for placement in cards:
        # A stable per-card container key ties each card's DOM identity (and its
        # preview iframe) to (fid, page) rather than to loop position, so removing
        # or re-adding files doesn't strand a card's component in a reused slot.
        with st.container(key=f"card_{fid}_{placement.page_index}"):
            _review_card(fid, pdf_bytes, placement.page_index, stamp, date_str,
                         settings, layout_gen)


def _download_all_widget(n: int, key: str) -> None:
    """Flag every stamped PDF for an individual, full-quality download (no ZIP).

    The actual downloads are fired by ``_run_download_all``; this just records
    that the user asked for them so they happen after every per-file download
    button has rendered.
    """
    if st.button(f"⬇️ Download all {n} stamped PDFs", key=key, type="primary",
                 help="Saves each stamped PDF separately at full quality (no "
                      "ZIP), back-to-back. Your browser may ask permission to "
                      "download several files at once."):
        st.session_state["dl_all_go"] = True


def _run_download_all() -> None:
    """Fire every file's download in one back-to-back burst -- no per-file rerun.

    Each per-file ``st.download_button`` renders its (current) stamped PDF on
    demand. We click them all in a single synchronous burst from a tiny iframe,
    so every download fires before Streamlit can rerun and tear the iframe down.
    This keeps "download all" as fast as clicking each button by hand, with no
    ZIP and no quality loss.
    """
    if not st.session_state.pop("dl_all_go", False):
        return
    # Use components.html (renders arbitrary HTML/JS in an iframe across all
    # supported Streamlit versions) rather than st.iframe, which only accepts an
    # HTML string on very recent versions and would silently no-op on older ones.
    components.html(
        """
        <script>
        (async () => {
          const pdoc = window.parent.document;
          let btns = [];
          for (let t = 0; t < 40; t++) {
            btns = pdoc.querySelectorAll('[data-testid="stDownloadButton"] button');
            if (btns.length) break;
            await new Promise(r => setTimeout(r, 25));
          }
          // One synchronous pass: all downloads fire in the same tick.
          btns.forEach(b => b.click());
        })();
        </script>
        """,
        height=1,
    )


def _validate_pdf(data: bytes) -> tuple[bool, str]:
    """Open-test an uploaded file so a corrupt/encrypted/empty PDF is skipped with
    a clear message instead of crashing the whole batch with a raw traceback."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return False, "it is not a readable PDF."
    try:
        if doc.needs_pass and not doc.authenticate(""):
            return False, "it is password-protected (remove the password and re-upload)."
        if doc.page_count == 0:
            return False, "it has no pages."
    except Exception:
        return False, "it could not be read."
    finally:
        doc.close()
    return True, ""


def _gc_session_state(live_fids: set[str]) -> None:
    """Drop per-file maps and per-card widget keys for files no longer uploaded,
    so a long session that cycles through many drawing sets doesn't grow without
    bound. Entries for still-uploaded files are kept, so deselecting then
    re-selecting a file in the picker preserves its edits."""
    maps = ("placements", "auto", "auto_sig", "removed", "collapsed")
    dead: set[str] = set()
    for m in maps:
        dead |= set(st.session_state.get(m, {}).keys()) - live_fids
    if not dead:
        return
    for m in maps:
        d = st.session_state.get(m)
        if isinstance(d, dict):
            for fid in dead:
                d.pop(fid, None)
    for fid in dead:
        for k in [k for k in list(st.session_state.keys())
                  if f"_{fid}_" in k or k.endswith(f"_{fid}")]:
            st.session_state.pop(k, None)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("📐 Engineering Stamp Placer")
    st.write("Stamp every page of one or many drawing sets, skipping the "
             "reserved top-right whitespace and minimising coverage.")

    for key in ("placements", "auto", "auto_sig", "removed", "collapsed"):
        st.session_state.setdefault(key, {})

    seal_bytes, seal_name, date_str, name_suffix, settings = _sidebar()
    if seal_bytes is None:
        st.info("Pick or upload a seal in the sidebar to begin.")
        return
    try:
        # seal_bytes already holds the chosen seal's content (cached read); build
        # the asset from it directly — load_stamp_from_bytes is itself cached by
        # content, and this avoids another disk/SMB read + stat on every rerun.
        stamp = load_stamp_from_bytes(seal_bytes)
    except Exception as exc:
        st.error(f"Could not read the seal image: {exc}")
        return

    st.header("3. Upload drawing PDFs")
    ups = st.file_uploader("Drawing sets (PDF) — select multiple at once",
                           type=["pdf"], accept_multiple_files=True)
    if not ups:
        st.info("Upload one or more PDFs to see suggested stamp placements.")
        return

    if st.button("♻️ Recompute everything from scratch",
                 help="Clear all caches and manual moves, then recompute."):
        st.cache_data.clear()
        st.cache_resource.clear()
        for key in list(st.session_state.keys()):
            st.session_state.pop(key, None)
        st.rerun()

    # De-duplicate identical uploads by content and validate each PDF so one bad
    # file can't crash the batch. Then disambiguate duplicate display names so
    # same-named-but-different files stay distinct in the picker, headings and
    # saved filenames.
    deduped: list[tuple[str, str, bytes]] = []
    seen: set[str] = set()
    for up in ups:
        b = up.getvalue()
        fid = _file_id(b, up.name)
        if fid in seen:
            continue
        ok, why = _validate_pdf(b)
        if not ok:
            st.error(f"“{up.name}” was skipped: {why}")
            continue
        seen.add(fid)
        deduped.append((up.name, fid, b))

    if not deduped:
        st.info("No readable PDFs to stamp.")
        return

    name_counts: dict[str, int] = {}
    for n, _, _ in deduped:
        name_counts[n] = name_counts.get(n, 0) + 1
    files: list[tuple[str, str, bytes]] = []
    for n, fid, b in deduped:
        disp = n if name_counts[n] == 1 else f"{Path(n).stem} ({fid[:6]}){Path(n).suffix}"
        files.append((disp, fid, b))

    # Reclaim session state for files removed from the uploader (entries for any
    # still-uploaded file are kept so deselect-then-reselect preserves edits).
    _gc_session_state({fid for _, fid, _ in files})

    # Choose which uploaded files to stamp (all by default). Keyed by content id so
    # duplicate display names cannot collapse into a single option.
    if len(files) > 1:
        label_by_fid = {fid: disp for disp, fid, _ in files}
        all_fids = [fid for _, fid, _ in files]
        chosen = st.multiselect(
            "Files to stamp", all_fids, default=all_fids,
            format_func=lambda f: label_by_fid[f],
            help="All selected by default — deselect any you don't want to stamp.")
        files = [f for f in files if f[1] in chosen]
        if not files:
            st.info("Select at least one file to stamp.")
            return

    # Sync placements for every selected file (rendering is deferred to download).
    ready_files = []
    for name, fid, pdf_bytes in files:
        try:
            _prepare_file(fid, pdf_bytes, settings)
        except ValueError as exc:
            st.error(f"“{name}” was skipped: {exc}")
            continue
        ready_files.append((name, fid, pdf_bytes))
    files = ready_files
    if not files:
        return

    # Drop a deferred apply-to-all whose file is no longer selected, so it can't
    # fire later against a re-selected file.
    pending = st.session_state.get("applyall_pending")
    if pending and pending[0] not in {fid for _, fid, _ in files}:
        st.session_state.pop("applyall_pending", None)

    # Token that changes when the rendered layout changes (files added/removed or
    # a file collapsed) but not while merely dragging a seal — folded into each
    # preview component's key so its iframe remounts cleanly on a layout shift
    # (otherwise a reused iframe can stay blank).
    # Use the SAME effective collapsed default as _render_file_ui (large files
    # auto-collapse) so the token actually changes when a file is expanded —
    # otherwise expanding one file can leave another file's previews blank.
    layout_gen = hashlib.sha1(
        repr([(fid, st.session_state["collapsed"].get(
                  fid, len(st.session_state["placements"].get(fid, {})) > _AUTO_COLLAPSE_PAGES))
              for _, fid, _ in files]).encode()).hexdigest()[:8]

    st.header(f"4. Review placements — {len(files)} file(s)")

    if len(files) > 1:
        _download_all_widget(len(files), key="dl_all_top")

    for name, fid, pdf_bytes in files:
        with st.container(border=True, key=f"file_{fid}"):
            st.subheader(f"📄 {name}")
            _render_file_ui(name, fid, pdf_bytes, stamp, date_str, name_suffix,
                            settings, layout_gen)

    # Cross-file warning for manual placements left in the reserved corner
    # (skip pages whose stamp was removed -- they go out unstamped anyway).
    bad = []
    for name, fid, _ in files:
        removed = st.session_state["removed"].get(fid, set())
        for i, p in st.session_state["placements"].get(fid, {}).items():
            if (i not in removed and p.source == "manual"
                    and placement_in_keepout(p, settings)):
                bad.append(f"{name} p{i + 1}")
    if bad:
        st.error("Manually placed seal(s) are inside the reserved top-right "
                 f"corner: {', '.join(bad)}. Move them before sending out.")

    if len(files) > 1:
        st.divider()
        _download_all_widget(len(files), key="dl_all_bottom")

    # Fire "download all" (one synchronous burst). Runs after the per-file
    # download buttons exist in the DOM so the iframe can find them.
    _run_download_all()


if __name__ == "__main__":
    main()
