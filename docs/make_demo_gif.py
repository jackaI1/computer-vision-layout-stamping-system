"""Build the animated demo used at the top of the README.

Everything shown is generated: the sheets and the seal come from
``examples/make_sample_sheet.py`` and the placements come from running the real
pipeline over them. No real drawing or seal is involved at any point.

    python docs/make_demo_gif.py

Writes ``docs/demo.gif``.
"""

import os
import subprocess
import sys

import fitz
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
EXAMPLES = os.path.join(ROOT, "examples")
sys.path.insert(0, ROOT)

from stamper import Settings, compute_placements  # noqa: E402
from stamper.engineer_box import detect_engineer_box  # noqa: E402
from stamper.occupancy import analyze_page  # noqa: E402
from stamper.placement import keepout_rects  # noqa: E402

CANVAS_W, CANVAS_H = 1000, 700
BAR_H = 62
BG = (255, 255, 255)
BAR_BG = (24, 28, 34)
BAR_FG = (238, 240, 244)
ACCENT = (86, 178, 255)
RESERVED = (232, 72, 72)
FOUND = (46, 184, 114)


def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render(pdf_path: str, page_no: int, target_w: int):
    doc = fitz.open(pdf_path)
    page = doc[page_no]
    scale = target_w / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img, scale


def overlay_rect(img, rect_pt, scale, colour, label, dashed=False):
    """Draw a translucent highlight over a rectangle given in points."""
    out = img.convert("RGB")
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = [v * scale for v in rect_pt]
    d.rectangle([x0, y0, x1, y1], fill=colour + (46,), outline=colour + (255,), width=5)
    if label:
        tw = int(len(label) * 8.6) + 20
        ly = max(0, y0 - 34)
        d.rectangle([x0, ly, x0 + tw, ly + 30], fill=colour + (235,))
        d.text((x0 + 10, ly + 7), label, font=font(15), fill=(255, 255, 255, 255))
    out = Image.alpha_composite(out.convert("RGBA"), layer).convert("RGB")
    return out


def frame(img, step, caption):
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    area_h = CANVAS_H - BAR_H
    scale = min((CANVAS_W - 32) / img.width, (area_h - 32) / img.height)
    w, h = int(img.width * scale), int(img.height * scale)
    canvas.paste(img.resize((w, h), Image.LANCZOS),
                 ((CANVAS_W - w) // 2, BAR_H + (area_h - h) // 2))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, CANVAS_W, BAR_H], fill=BAR_BG)
    d.text((22, 15), step, font=font(15), fill=ACCENT)
    d.text((22, 36), caption, font=font(15), fill=BAR_FG)
    d.rectangle([0, BAR_H - 2, CANVAS_W, BAR_H], fill=ACCENT)
    return canvas


def controls_frame():
    """A plain list of what the operator can change. Not a screenshot -- the
    point is the range of control, not the widget styling."""
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, CANVAS_W, BAR_H], fill=BAR_BG)
    d.text((22, 15), "OPERATOR CONTROLS", font=font(15), fill=ACCENT)
    d.text((22, 36), "Automatic placement is a starting point, not a verdict",
           font=font(15), fill=BAR_FG)
    d.rectangle([0, BAR_H - 2, CANVAS_W, BAR_H], fill=ACCENT)

    items = [
        ("Click to place", "click anywhere on the page to move the seal there"),
        ("Nudge sliders", "fine positional control once it is roughly right"),
        ("Seal diameter", "1.4 - 3.2 in, or auto-fit to a designated cell"),
        ("Apply to all pages", "push one placement across the whole set"),
        ("Remove per page", "skip a page without losing its computed placement"),
        ("Reserved corner", "width / height fractions and padding, per sheet size"),
        ("Caption text", "edit or clear the line printed under the seal"),
        ("Date format", "font size and colour of the date in the seal's top hole"),
        ("Recompute", "discard every cached placement and search again"),
    ]
    y = BAR_H + 34
    for name, desc in items:
        d.rectangle([44, y + 6, 52, y + 14], fill=ACCENT)
        d.text((68, y), name, font=font(17), fill=(20, 22, 26))
        d.text((300, y + 2), desc, font=font(15), fill=(90, 96, 104))
        y += 58
    return canvas


def main() -> None:
    os.makedirs(DOCS, exist_ok=True)
    print("generating sample sheets...")
    subprocess.run([sys.executable, os.path.join(EXAMPLES, "make_sample_sheet.py")],
                   check=True, cwd=ROOT, stdout=subprocess.DEVNULL)

    settings = Settings()
    frames = []

    # --- cover sheet --------------------------------------------------------
    cover_path = os.path.join(EXAMPLES, "sample_cover.pdf")
    cover_img, sc = render(cover_path, 0, 1500)

    doc = fitz.open(cover_path)
    page = doc[0]
    occ = analyze_page(page, settings)
    ko = keepout_rects(page.rect.width, page.rect.height, settings)[0]
    ebox = detect_engineer_box(page, occ)
    doc.close()

    frames.append((frame(cover_img, "STEP 1",
                         "A cover sheet. Where does the seal go?"), 2600))
    frames.append((frame(overlay_rect(cover_img, ko, sc, RESERVED,
                                      "RESERVED - the city stamps here"),
                         "STEP 2",
                         "The top-right corner is never used automatically"), 3200))
    if ebox is not None:
        frames.append((frame(overlay_rect(cover_img, ebox.box, sc, FOUND,
                                          "DESIGNATED CELL"),
                             "STEP 3",
                             "A labelled ENGINEER STAMP cell is found and takes priority"),
                       3000))

    stamped_cover, sc2 = render(os.path.join(EXAMPLES, "sample_cover_stamped.pdf"), 0, 1500)
    col = stamped_cover.crop((int(stamped_cover.width * 0.74), 0,
                              stamped_cover.width, int(stamped_cover.height * 0.72)))
    frames.append((frame(col, "STEP 4",
                         "Seal centred in the cell, date written into the top hole"), 3200))

    # --- dense notes sheet --------------------------------------------------
    notes_img, _ = render(os.path.join(EXAMPLES, "sample_notes.pdf"), 0, 1500)
    frames.append((frame(notes_img, "HARDER CASE",
                         "A notes sheet: no designated cell and almost no free space"), 2800))

    notes_doc = fitz.open(os.path.join(EXAMPLES, "sample_notes.pdf"))
    p = compute_placements(notes_doc, settings)[0]
    notes_doc.close()
    stamped_notes, _ = render(os.path.join(EXAMPLES, "sample_notes_stamped.pdf"), 0, 1500)
    frames.append((frame(stamped_notes, "RESULT",
                         f"Least-inked spot found - {p.coverage:.2%} ink under the seal"),
                   3200))

    frames.append((controls_frame(), 4200))

    out = os.path.join(DOCS, "demo.gif")
    imgs = [f for f, _ in frames]
    imgs[0].save(out, save_all=True, append_images=imgs[1:],
                 duration=[d for _, d in frames], loop=0, optimize=True)
    print(f"wrote {out} ({os.path.getsize(out):,} bytes, {len(imgs)} frames)")


if __name__ == "__main__":
    main()
