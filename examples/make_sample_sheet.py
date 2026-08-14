"""Generate synthetic drawing sets and a synthetic seal, then stamp them.

Real seals are legal signatures and real drawing sets are client property, so
neither is in this repository. This script builds throwaway stand-ins and runs
the full placement pipeline on them, so the tool can be exercised end to end
without either.

Two sheet styles are produced, because they exercise different code paths:

  cover   A cover sheet with a full-height title-block column. The column has a
          large blank box at the top -- the area a municipality stamps, which
          the tool must refuse to use -- and a designated "ENGINEER STAMP" cell
          just below it that partially overlaps the same reserved corner. The
          seal must land in the designated cell and never in the blank box
          above it.

  notes   A dense construction-notes sheet: a grid of detail panels with almost
          no free space and no designated cell. The whitespace search has to
          find the least-inked spot on a crowded page, and reports non-zero ink
          coverage when it does.

Usage:

    python examples/make_sample_sheet.py                # both
    python examples/make_sample_sheet.py --variant cover
    python examples/make_sample_sheet.py --variant notes

Nothing here is derived from any real drawing. All text is invented.
"""

import argparse
import os
import sys

import fitz
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stamper import (  # noqa: E402
    Settings,
    compute_placements,
    load_stamp,
    placement_in_keepout,
    render_stamped_pdf,
)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BLACK = (0.0, 0.0, 0.0)
GREY = (0.45, 0.45, 0.45)

# E-size landscape (36 x 24 in) and D-size landscape (24 x 18 in), the two sheet
# sizes this tool was designed against.
COVER_W, COVER_H = 2592, 1728
NOTES_W, NOTES_H = 1728, 1296


# ---------------------------------------------------------------------------
# Synthetic seal
# ---------------------------------------------------------------------------

def make_seal_png(path: str, size: int = 600) -> None:
    """Draw an obviously synthetic circular seal.

    Mirrors only the geometry the placement code cares about -- a circle with
    two inner band lines, the upper "top hole" being where the date is written.
    It is not modelled on any real professional seal.
    """
    img = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(img)
    pad = 12
    d.ellipse([pad, pad, size - pad, size - pad], outline="black", width=8)
    d.ellipse([pad + 26, pad + 26, size - pad - 26, size - pad - 26],
              outline="black", width=3)
    d.line([pad + 30, int(size * 0.37), size - pad - 30, int(size * 0.37)],
           fill="black", width=4)
    d.line([pad + 30, int(size * 0.62), size - pad - 30, int(size * 0.62)],
           fill="black", width=4)
    d.text((size * 0.5, size * 0.47), "SAMPLE SEAL", fill="black", anchor="mm")
    d.text((size * 0.5, size * 0.55), "NOT A REAL SEAL", fill="black", anchor="mm")
    d.text((size * 0.5, size * 0.72), "SYNTHETIC", fill="black", anchor="mm")
    img.save(path)


# ---------------------------------------------------------------------------
# Shared drawing helpers
# ---------------------------------------------------------------------------

def hatched_box(page, rect: fitz.Rect, spacing: float = 6.0) -> None:
    """A diagonally hatched rectangle, standing in for a wall assembly."""
    page.draw_rect(rect, color=BLACK, width=0.9)
    x = rect.x0 - rect.height
    while x < rect.x1:
        a = fitz.Point(max(x, rect.x0), rect.y1 - max(0.0, rect.x0 - x))
        b = fitz.Point(min(x + rect.height, rect.x1),
                       rect.y0 + max(0.0, (x + rect.height) - rect.x1))
        if a.x < b.x:
            page.draw_line(a, b, color=BLACK, width=0.7)
        x += spacing


def leader_note(page, anchor: fitz.Point, text: str, dx: float, size: float = 4.6) -> None:
    """A short callout with a leader line, the visual staple of a details sheet."""
    end = fitz.Point(anchor.x + dx, anchor.y - 14)
    page.draw_line(anchor, end, color=BLACK, width=0.5)
    tx = end.x + (3 if dx > 0 else -3 - len(text) * size * 0.5)
    page.insert_text((tx, end.y - 2), text, fontsize=size, color=BLACK)


NOTE_TEXT = [
    "SHEATHING MEMBRANE", "VAPOUR BARRIER", "BATT INSULATION",
    "INTERIOR BOARD", "CONT. FLASHING", "BEARING PLATE",
    "ANCHOR AT 1200 O.C.", "RIGID INSULATION", "WEEPING TILE",
    "DAMPPROOFING", "GRANULAR FILL", "CONT. SILL PLATE",
]


def detail_panel(page, rect: fitz.Rect, tag: str, title: str, seed: int = 0) -> None:
    """One bubble-tagged detail.

    Deliberately busy: a real notes sheet leaves almost no free space, and the
    whitespace search is only interesting when it has to work for it.
    """
    page.draw_rect(rect, color=BLACK, width=1.0)

    body = fitz.Rect(rect.x0 + 12, rect.y0 + 12, rect.x1 - 12, rect.y1 - 46)

    # Vertical wall assembly plus a footing block at its base.
    wall = fitz.Rect(body.x0 + body.width * 0.36, body.y0,
                     body.x0 + body.width * 0.50, body.y0 + body.height * 0.74)
    hatched_box(page, wall, spacing=4.0)
    footing = fitz.Rect(wall.x0 - 22, wall.y1, wall.x1 + 22, wall.y1 + 26)
    hatched_box(page, footing, spacing=5.0)

    # Floor / plate lines running off the assembly, both sides.
    for frac in (0.16, 0.34, 0.52, 0.70):
        y = body.y0 + body.height * frac
        page.draw_line(fitz.Point(wall.x1, y), fitz.Point(body.x1 - 4, y),
                       color=BLACK, width=0.8)
        page.draw_line(fitz.Point(body.x0 + 4, y + 4), fitz.Point(wall.x0, y + 4),
                       color=BLACK, width=0.6)
        # second, lighter line to read as a floor build-up
        page.draw_line(fitz.Point(wall.x1, y + 3), fitz.Point(body.x1 - 30, y + 3),
                       color=GREY, width=0.4)

    # Callouts on both sides.
    for i, frac in enumerate((0.11, 0.28, 0.45, 0.62, 0.79)):
        leader_note(page, fitz.Point(wall.x1, body.y0 + body.height * frac),
                    NOTE_TEXT[(seed + i) % len(NOTE_TEXT)], 40)
    for i, frac in enumerate((0.20, 0.40, 0.60, 0.80)):
        leader_note(page, fitz.Point(wall.x0, body.y0 + body.height * frac),
                    NOTE_TEXT[(seed + i + 5) % len(NOTE_TEXT)], -34)

    # A dimension string down the left edge.
    dim_x = body.x0 + 3
    page.draw_line(fitz.Point(dim_x, body.y0), fitz.Point(dim_x, body.y1),
                   color=BLACK, width=0.4)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = body.y0 + body.height * frac
        page.draw_line(fitz.Point(dim_x - 3, y), fitz.Point(dim_x + 3, y),
                       color=BLACK, width=0.4)

    # A dense block of specification text filling the remaining corner.
    tx = body.x0 + body.width * 0.56
    ty = body.y0 + body.height * 0.80
    for i in range(7):
        page.insert_text((tx, ty + i * 6.4),
                         f"{i + 1}. {NOTE_TEXT[(seed + i * 3) % len(NOTE_TEXT)]} PER NOTE",
                         fontsize=4.2, color=BLACK)

    # Bubble tag and title along the bottom rule.
    cy = rect.y1 - 26
    page.draw_circle(fitz.Point(rect.x0 + 32, cy), 14, color=BLACK, width=1.2)
    page.insert_text((rect.x0 + 25, cy + 4), tag, fontsize=8, color=BLACK)
    page.insert_text((rect.x0 + 54, cy + 4), title, fontsize=8, color=BLACK)
    page.insert_text((rect.x1 - 74, cy + 4), "SCALE: N.T.S.", fontsize=5.5, color=BLACK)


def spec_table(page, rect: fitz.Rect, title: str, rows: int = 8) -> None:
    """A small ruled table, the other staple of a cover sheet."""
    page.draw_rect(rect, color=BLACK, width=1.0)
    page.insert_text((rect.x0 + 8, rect.y0 + 16), title, fontsize=8, color=BLACK)
    page.draw_line(fitz.Point(rect.x0, rect.y0 + 24),
                   fitz.Point(rect.x1, rect.y0 + 24), color=BLACK, width=0.9)
    # Rules are drawn at >= 0.8 pt deliberately. The occupancy analysis runs at
    # 72 DPI by default, where a 0.4 pt hairline antialiases to a grey above the
    # ink threshold and is not seen at all -- real CAD linework is heavier, and
    # a sample drawn too lightly would let the seal land inside a table.
    step = (rect.height - 24) / rows
    for i in range(1, rows):
        y = rect.y0 + 24 + step * i
        page.draw_line(fitz.Point(rect.x0, y), fitz.Point(rect.x1, y),
                       color=BLACK, width=0.8)
    for frac in (0.46, 0.62, 0.80):
        x = rect.x0 + rect.width * frac
        page.draw_line(fitz.Point(x, rect.y0 + 24), fitz.Point(x, rect.y1),
                       color=BLACK, width=0.8)
    mid = rect.x0 + rect.width * 0.62
    for i in range(rows):
        y = rect.y0 + 24 + step * i + step * 0.68
        page.insert_text((rect.x0 + 6, y), f"ITEM {i + 1:02d} SPECIFICATION",
                         fontsize=5, color=BLACK)
        page.insert_text((rect.x0 + rect.width * 0.47 + 4, y), f"{100 + i * 37}",
                         fontsize=5, color=BLACK)
        page.insert_text((mid + 4, y), "CONFORMS", fontsize=5, color=BLACK)
        page.insert_text((rect.x0 + rect.width * 0.81 + 4, y), f"{i + 1}.{i + 2}",
                         fontsize=5, color=BLACK)


# ---------------------------------------------------------------------------
# Variant 1 -- cover sheet
# ---------------------------------------------------------------------------

def build_cover(doc) -> None:
    page = doc.new_page(width=COVER_W, height=COVER_H)
    page.draw_rect(fitz.Rect(36, 36, COVER_W - 36, COVER_H - 36), color=BLACK, width=2)

    col_x = COVER_W - 576          # full-height title-block column
    page.insert_text((60, 74), "SYNTHETIC COVER SHEET - NOT A REAL DRAWING",
                     fontsize=15, color=BLACK)

    # --- left: legend columns of hatched assemblies -------------------------
    for c in range(2):
        x0 = 60 + c * 300
        page.insert_text((x0, 112), "ASSEMBLY LEGEND", fontsize=8, color=BLACK)
        for r in range(6):
            y0 = 126 + r * 250
            hatched_box(page, fitz.Rect(x0, y0, x0 + 92, y0 + 210))
            page.insert_text((x0 + 100, y0 + 14), f"TYPE W{c * 6 + r + 1}",
                             fontsize=7, color=BLACK)
            for k in range(6):
                page.insert_text((x0 + 100, y0 + 32 + k * 13),
                                 "GENERIC ASSEMBLY NOTE LINE", fontsize=4.6, color=BLACK)

    # --- middle: calculation tables ----------------------------------------
    for c in range(2):
        for r in range(3):
            spec_table(page, fitz.Rect(680 + c * 330, 130 + r * 300,
                                       680 + c * 330 + 290, 130 + r * 300 + 250),
                       f"AREA CALCULATIONS {c * 3 + r + 1}")
    spec_table(page, fitz.Rect(680, 1040, 1300, 1560), "PERFORMANCE MATRIX", rows=16)

    # --- right-centre: a schematic key plan ---------------------------------
    kp = fitz.Rect(1360, 130, col_x - 40, 900)
    page.draw_rect(kp, color=BLACK, width=1.2)
    page.insert_text((kp.x0 + 10, kp.y0 + 20), "KEY PLAN  (N.T.S.)", fontsize=9, color=BLACK)
    for i in range(5):
        y = kp.y0 + 90 + i * 150
        page.draw_line(fitz.Point(kp.x0 + 20, y), fitz.Point(kp.x1 - 20, y),
                       color=GREY, width=1.0)
        page.insert_text((kp.x0 + 26, y - 6), f"STREET {chr(65 + i)}", fontsize=6, color=GREY)
    for i in range(4):
        x = kp.x0 + 120 + i * 130
        page.draw_line(fitz.Point(x, kp.y0 + 60), fitz.Point(x, kp.y1 - 40),
                       color=GREY, width=1.0)
    for i in range(6):
        bx = kp.x0 + 60 + (i % 3) * 190
        by = kp.y0 + 130 + (i // 3) * 300
        page.draw_rect(fitz.Rect(bx, by, bx + 150, by + 110), color=BLACK, width=0.8)
        page.insert_text((bx + 12, by + 60), f"BLOCK {i + 1}", fontsize=7, color=BLACK)

    # --- the title-block column --------------------------------------------
    page.draw_rect(fitz.Rect(col_x, 60, COVER_W - 60, COVER_H - 60),
                   color=BLACK, width=2)

    # (1) The municipal stamp box: deliberately large and completely blank.
    #     It is the emptiest region on the sheet, so a naive least-ink search
    #     would choose it. It sits inside the reserved top-right corner and
    #     must be refused.
    page.draw_rect(fitz.Rect(col_x, 60, COVER_W - 60, 520), color=BLACK, width=2)

    # (2) Project identity cells.
    page.draw_rect(fitz.Rect(col_x, 520, COVER_W - 60, 610), color=BLACK, width=2)
    page.insert_text((col_x + 150, 560), "BLOCK 1", fontsize=26, color=BLACK)
    page.insert_text((col_x + 60, 590), "UNITS T-01 to T-12", fontsize=16, color=BLACK)
    page.draw_rect(fitz.Rect(col_x, 610, COVER_W - 60, 655), color=BLACK, width=2)
    page.insert_text((col_x + 150, 642), "6.00m LOTS", fontsize=15, color=BLACK)

    # (3) The designated engineer stamp cell. It starts at y=655 and so overlaps
    #     the bottom of the default reserved corner -- which is exactly why an
    #     explicitly designated cell is exempt from the keep-out.
    page.draw_rect(fitz.Rect(col_x, 655, COVER_W - 60, 1010), color=BLACK, width=2)
    page.insert_text((col_x + 12, 676), "ENGINEER STAMP", fontsize=11, color=BLACK)

    # (4) Consultant / issuance cells below.
    for i, label in enumerate(("MUNICIPALITY", "DEVELOPER", "DESIGNER")):
        y0 = 1010 + i * 200
        page.draw_rect(fitz.Rect(col_x, y0, COVER_W - 60, y0 + 200), color=BLACK, width=2)
        page.insert_text((col_x + 12, y0 + 22), label, fontsize=8, color=BLACK)
    page.draw_rect(fitz.Rect(col_x, 1610, COVER_W - 60, COVER_H - 60), color=BLACK, width=2)
    page.insert_text((col_x + 12, 1636), "TITLE SHEET", fontsize=11, color=BLACK)
    page.insert_text((COVER_W - 150, 1660), "A0.1", fontsize=18, color=BLACK)


# ---------------------------------------------------------------------------
# Variant 2 -- dense construction notes
# ---------------------------------------------------------------------------

def build_notes(doc) -> None:
    page = doc.new_page(width=NOTES_W, height=NOTES_H)
    page.draw_rect(fitz.Rect(24, 24, NOTES_W - 24, NOTES_H - 24), color=BLACK, width=2)
    page.insert_text((40, 52), "SYNTHETIC CONSTRUCTION NOTES - NOT A REAL DRAWING",
                     fontsize=11, color=BLACK)

    tags = ["FB1", "GE1", "GE2", "GE3", "X1", "X2", "X3", "EW", "CN1"]
    titles = ["FOUNDATION WALL SECTION", "SECTION AT UPPER LEVEL",
              "SECTION AT UPPER LEVEL", "SECTION AT LOFT FLOOR",
              "SECTION AT FOOTING", "SECTION AT FOOTING",
              "SECTION AT STAIR OPENING", "TYPICAL WALL CONTINUITY",
              "GENERIC DETAIL"]

    cols, rows = 3, 3
    m, gap = 32, 12
    grid_w = NOTES_W - 2 * m
    grid_h = NOTES_H - 2 * m - 34
    cw = (grid_w - gap * (cols - 1)) / cols
    ch = (grid_h - gap * (rows - 1)) / rows

    for i in range(cols * rows):
        r, c = divmod(i, cols)
        x0 = m + c * (cw + gap)
        y0 = m + 34 + r * (ch + gap)
        cell = fitz.Rect(x0, y0, x0 + cw, y0 + ch)
        if r == rows - 1 and c == cols - 1:
            # Bottom-right cell carries the compliance table and title block
            # instead of a detail, matching how these sheets are laid out.
            split = cell.y0 + cell.height * 0.52
            spec_table(page, fitz.Rect(cell.x0, cell.y0, cell.x1, split - 8),
                       "COMPLIANCE PACKAGE", rows=11)

            page.draw_rect(fitz.Rect(cell.x0, split, cell.x1, cell.y1),
                           color=BLACK, width=1.5)
            tb_h = cell.y1 - split
            for k in range(1, 4):
                y = split + k * (tb_h / 4)
                page.draw_line(fitz.Point(cell.x0, y), fitz.Point(cell.x1, y),
                               color=BLACK, width=0.8)
            page.insert_text((cell.x0 + 10, split + 18), "SAMPLE DESIGN CO.",
                             fontsize=8, color=BLACK)
            page.insert_text((cell.x0 + 10, split + tb_h / 4 + 18), "SYNTHETIC PROJECT",
                             fontsize=7, color=BLACK)
            page.insert_text((cell.x0 + 10, split + tb_h / 2 + 18), "CONSTRUCTION NOTES",
                             fontsize=7, color=BLACK)
            page.insert_text((cell.x1 - 60, cell.y1 - 12), "CN1", fontsize=13, color=BLACK)
            continue
        detail_panel(page, cell, tags[i], titles[i], seed=i * 2)


# ---------------------------------------------------------------------------

BUILDERS = {"cover": build_cover, "notes": build_notes}


def run(variant: str, seal_path: str) -> None:
    doc = fitz.open()
    BUILDERS[variant](doc)
    sheet_path = os.path.join(OUT_DIR, f"sample_{variant}.pdf")
    doc.save(sheet_path)
    source_bytes = doc.tobytes()

    settings = Settings()
    placements = compute_placements(doc, settings)

    print(f"--- {variant} " + "-" * (56 - len(variant)))
    print(f"  sheet: {sheet_path}")
    for p in sorted(placements, key=lambda q: q.page_index):
        flag = "  <-- IN RESERVED CORNER" if placement_in_keepout(p, settings) else ""
        print(f"  page {p.page_index + 1}: source={p.source:<12} "
              f"centre=({p.center_x_pt:7.1f}, {p.center_y_pt:7.1f}) pt  "
              f"dia={p.diameter_pt:6.1f} pt  ink={p.coverage:6.2%}{flag}")

    stamp = load_stamp(seal_path)
    stamped = render_stamped_pdf(source_bytes, placements, stamp, "2026-01-01", settings)
    out_path = os.path.join(OUT_DIR, f"sample_{variant}_stamped.pdf")
    with open(out_path, "wb") as fh:
        fh.write(stamped)
    doc.close()
    print(f"  stamped: {out_path} ({len(stamped):,} bytes)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant", choices=["cover", "notes", "both"], default="both")
    args = ap.parse_args()

    seal_path = os.path.join(OUT_DIR, "sample_seal.png")
    make_seal_png(seal_path)
    print(f"seal: {seal_path}\n")

    for v in (["cover", "notes"] if args.variant == "both" else [args.variant]):
        run(v, seal_path)
        print()

    print("Expected: the cover sheet's seal lands in the designated ENGINEER")
    print("STAMP cell, never in the blank municipal box above it. The notes")
    print("sheet has no designated cell, so the whitespace search picks the")
    print("least-inked spot and reports the ink it could not avoid.")


if __name__ == "__main__":
    main()
