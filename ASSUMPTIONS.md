# Design assumptions

These are the judgement calls baked into the tool, derived from the sample sheet
set and seal it was developed against. Check them against your own drawing
standards; most are adjustable in the sidebar or `stamper/config.py`.

## Seal image & date

1. **The tool supports any number of seal PNGs.** Drop each one in `stamps/` and
   it appears in the dropdown. No code change needed.
2. **The seal already includes the signature**, so the tool does *not* add one.
   It adds the **date** and a **caption under the circle** (see item 4a).
3. **Date goes in the upper “top hole”** of the circular seal, centred
   horizontally, at relative position `(0.50, 0.30)` of the seal box, measured
   from the sample seal (inner band lines at ~0.37 and ~0.62 of height). If your
   seals have a different layout, adjust `DATE_REL_X` / `DATE_REL_Y` in
   `config.py`.
4. **Date format `YYYY-MM-DD`, 9 pt, black, Helvetica.** Font size is adjustable
   in the sidebar; colour is in `config.py`.
4a. **Caption under the seal, default “FOR STRUCTURAL ITEMS ONLY”.** Printed as
   real Helvetica text, black, centred under the circle, and **auto‑sized so its
   width matches the seal diameter** (`BOTTOM_TEXT_WIDTH_FRAC = 0.98`). It is a
   **default‑on** option, fully editable in the sidebar; **clear the field to
   print no caption.** Two behaviours to note: (i) for a *short* caption the font is
   **height‑capped** (`BOTTOM_TEXT_MAX_HEIGHT_FRAC = 0.12` of the diameter) so it
   renders narrower than the seal rather than growing to a huge font; (ii) the
   caption sits just *below* the seal, so on a tight “ENGINEER STAMP” cell it may
   overhang the cell's bottom rule by a few points, and on a free‑whitespace
   placement it uses a little of the bottom padding. The overhang is small and
   bounded by the height cap; shorten/clear the caption or reduce the seal
   diameter if a particular cell is very tight. The caption is **not** part of the
   whitespace/keep‑out collision search (only the circular seal is).
5. **White background is knocked out to transparent** (luminance ≥ 240) so the
   seal reads like a real applied stamp and only its ink covers the drawing.

## “ENGINEER STAMP” box detection

6. The label is matched by the literal text `ENGINEER STAMP` (plus a few casings
   / apostrophe variants). It relies on the PDF having **real text**; it will
   not find a label that is part of a rasterised image. The sample PDFs have
   real text, and detection worked on all 10 pages.
7. When found, the seal is **centred in the cell** and sized to `0.86 ×` the
   smaller cell dimension (clamped to the min/max diameter). In the sample this
   reproduced the original placement (~2.2 in seal in the cell).
8. The cell bounds are inferred from the title‑block ruling lines below the
   label. If a title block has an unusual structure, the derived box may be off;
   you can always click/drag‑adjust, and there is a safe fallback size.

## Reserved top‑right whitespace (keep‑out)

9. I interpreted the “whitespace that must be left in the top‑right corner” as
   the large blank box at the **top of the right title‑block column** (above the
   topmost labelled cell in the sample sheet). The keep‑out defaults to the top‑right
   **20 % width × 32 % height** of the sheet, plus **1.5 in** padding. Check that
   these fractions cover your reserved area; they are sliders in the sidebar
   (“Advanced”). The reserved corner is assumed to be the
   **visual top‑right** on every sheet; there is no per‑sheet corner override.
10. The keep‑out only blocks the **automatic whitespace search**. A designated
    “ENGINEER STAMP” cell is **exempt**: it is an explicit “stamp here” and, in
    example 1, the cell legitimately overlaps the default keep‑out rectangle, so
    exempting it is required to honour your instruction. A manual click can still
    place a seal anywhere (you're in control), but the UI shows a clear **warning**
    if a manual placement is left inside the reserved corner.
10a. **The corner is enforced in three layers** so a stale Streamlit cache can
    never sneak a seal into it: search‑time exclusion, a `PLACEMENT_LOGIC_VERSION`
    folded into cache/session keys, and an uncached *sanitize* pass that runs
    before every preview/download and relocates any auto‑placement found in the
    corner. Without all three layers a stale cached placement can survive a plain
    "Rerun". There is also a **“♻️ Recompute from scratch”** button as a manual
    reset.
11. **Page rotation is handled.** The whole pipeline works in *display* space
    (the visually‑upright page), so analysis, previews, keep‑out and placement
    all use the orientation you see. Seals and dates are rotated back to upright
    on insert. Synthetic regression tests cover 0°, 90°, 180° and 270°, including
    non-zero page origins.

## Sizing, scoring & search

12. **Default free‑whitespace seal size = 1.9 in** diameter (typical seal is
    ~1.75 in). Adjustable.
13. **“Covers the most → least” ordering** uses the fraction of ink under the
    circular seal footprint. Designated‑box and clean‑whitespace placements
    score ~0 %, so they sort to the bottom (least likely to need attention).
14. **Ink threshold = 180/255.** Faint/very light linework below this contrast
    is treated as whitespace. Raise it in the sidebar if you want the search to
    avoid lighter linework too.
15. Whitespace is scored over a **square** footprint for speed during the search;
    the final reported coverage uses the exact **circle**. The square is a slight
    over‑estimate, which is conservative (errs toward more clearance).
15a. **Ties for least ink are broken by clearance.** On a sparse sheet many
    footprints are completely ink‑free, so the minimum is not unique. When that
    happens the tool picks the most isolated candidate: the centre around which
    the largest ink-free **square** fits entirely on the page. An exact binary
    search over integer pixel padding scores each square in O(1) using the same
    summed-area table (no distance-transform dependency). Because
    the squares are bounded by the page edges, the seal is centred in open space
    rather than hugging a margin. This only re‑orders among already‑equal
    (least‑ink) spots; it never trades ink coverage for clearance. Disable via
    **“Maximise whitespace around the seal”** in the sidebar (Advanced).

## Output / quality

16. **Not flattened, full quality.** Seals are embedded as overlay image objects
    at their native resolution (verified: the seal lands as a 2067×2063
    lossless/FlateDecode image), the date as real selectable text, and existing
    vector + raster content is untouched. The PDF is saved with object‑stream
    de‑duplication + lossless deflate only (no rasterisation/recompression of
    your content).
17. The download filename is `<original>_stamped.pdf`.

## Scope notes

18. Designed and tested on **E‑size landscape sheets (36 × 24 in, 2592 × 1728 pt)**
    with real‑text PDFs. Other sizes should work (everything is relative), but
    scanned/image‑only PDFs will skip the “ENGINEER STAMP” text detection and
    fall back to whitespace search.
19. The “move” interaction uses click‑to‑place plus sliders. If the
    `streamlit-image-coordinates` component is unavailable, the UI falls back to
    sliders only (click‑to‑move disabled).
20. **Previews are a fast approximation.** The on‑screen preview composites the
    seal and a PIL‑rendered date onto a cached page raster, so the date font is
    not the exact PDF Helvetica and the image is rasterised. The **downloaded
    PDF** is the source of truth: real, crisp, non‑flattened seal image + real
    text date. Always trust the PDF over the preview for final appearance.
21. **Multiple files** are de-duplicated by name and content (a repeated
    identical upload is processed once; different filenames remain distinct).
    Each file's settings come from the single shared
    sidebar; there is no per‑file override. A true OS “folder picker” isn't
    available to browsers; multi‑select the files instead.
21a. **“Download all” saves each PDF individually, not as a ZIP.** A sandboxed
    web app can't write into a real folder on disk (the File System Access API
    is blocked in Streamlit's component iframe), so the button downloads the
    files individually instead. It clicks every per‑file download button in one
    back‑to‑back burst, reusing the data Streamlit already loaded for those
    buttons, so it is as fast as the individual downloads and works for large
    drawing sets. Re‑encoding every PDF into one inline payload, or downloading
    one‑per‑rerun, is far slower. Each file is the exact byte stream the single
    download produces, with no ZIP, recompression or quality loss, which matters
    for sealed drawings issued as records. The browser may
    show a one‑time “download multiple files?” permission prompt. The button
    appears at both the top and bottom of the review list.
21b. **Removing a stamp is per‑page and non‑destructive.** “Remove stamp” marks
    a page to be left unstamped (it is excluded from the output and its preview
    redraws without the seal) while keeping the computed placement so “Add stamp
    back” restores it exactly. Removal is the operator's deliberate choice and is
    remembered across setting changes (but cleared by “Recompute from scratch”).
22. **Default preview shows the whole page.** Increase *Preview zoom* to focus
    on the seal; this affects only previews, never the output.
23. **No guessed coverage on analysis failures.** Unreadable pages cause a clear
    file error. Small sheets shrink the seal to avoid the reserved corner; a
    fully reserved sheet is refused until the keep-out settings are reduced.
