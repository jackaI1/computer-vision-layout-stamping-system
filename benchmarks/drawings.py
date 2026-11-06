"""A fixed corpus of large vector, rotated and scanned-style drawing PDFs."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageDraw


def make_drawings(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, width, height, pages in [
        ("vector-36x24", 2592, 1728, 2),
        ("rotated-a0", 2384, 3370, 1),
        ("scanned-36x24", 2592, 1728, 1),
    ]:
        with fitz.open() as doc:
            for number in range(pages):
                page = doc.new_page(width=width, height=height)
                if name.startswith("scanned"):
                    image = Image.new("L", (width, height), 255)
                    draw = ImageDraw.Draw(image)
                    for y in range(60, height - 240, 45):
                        draw.line((60, y, width * .70, y + 20), fill=80, width=2)
                    draw.rectangle((width - 620, height - 220, width - 40, height - 40), outline=0, width=3)
                    raw = BytesIO()
                    image.save(raw, format="PNG")
                    page.insert_image(page.rect, stream=raw.getvalue())
                else:
                    shape = page.new_shape()
                    for y in range(60, height - 280, 36):
                        for x in range(60, int(width * .70), 90):
                            shape.draw_rect(fitz.Rect(x, y, x + 65, y + 20))
                    shape.draw_rect(fitz.Rect(width - 620, height - 240, width - 40, height - 40))
                    shape.finish(color=(.15, .15, .15), width=.8)
                    shape.commit()
                    page.insert_text((width - 600, height - 210), "ENGINEER STAMP" if number else "SYNTHETIC DRAWING", fontsize=14)
                page.insert_text((60, height - 30), f"SYNTHETIC PERFORMANCE FIXTURE {number + 1}")
                if name.startswith("rotated"):
                    page.set_rotation(90)
            path = directory / f"{name}.pdf"
            doc.save(path, deflate=True, no_new_id=True)
            paths.append(path)
    return paths


def make_seal():
    """A demonstration image, never a professional seal."""
    from stamper.stamp_image import load_stamp_from_bytes
    image = Image.new("RGBA", (160, 160), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((5, 5, 155, 155), outline="blue", width=4)
    draw.text((45, 70), "DEMO", fill="blue")
    raw = BytesIO()
    image.save(raw, format="PNG")
    return load_stamp_from_bytes(raw.getvalue())
