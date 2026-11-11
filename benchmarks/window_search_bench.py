"""Latency and throughput of the batch page search, with an equivalence check and a regression gate.

It renders the same generated drawings the pipeline benchmark uses (vector,
rotated and scanned-style pages), runs the least-ink seal search on batches of
1, 4 and 16 pages, and times each backend. Every backend must return exactly the
spots of the reference search, or the run fails.

    python -m benchmarks.window_search_bench --output output/window-search/benchmark.json
    python -m benchmarks.window_search_bench --check benchmarks/window_search_thresholds.json \
        --report output/window-search/benchmark.json

``--check`` fails when a backend's median latency for a batch is above the stored
threshold. Thresholds are in ``benchmarks/window_search_thresholds.json``. Each
one is set above the time measured on a CI runner, so it catches a real slowdown
and not ordinary noise. Raise a threshold only with a note in the change log.
"""
from __future__ import annotations

import argparse
import json
import platform
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

import fitz

from benchmarks.drawings import make_drawings
from stamper import window_search as ws
from stamper.config import Settings
from stamper.occupancy import PageOccupancy, analyze_page, find_min_ink_spot

BATCH_SIZES = (1, 4, 16)
REPEATS = 5
DIAMETER_PT = Settings().stamp_diameter_in * 72.0


def representative_pages(directory: Path) -> list[PageOccupancy]:
    """Analysed pages from the fixed drawing corpus (vector, rotated and scanned)."""
    settings = Settings()
    pages = []
    for path in make_drawings(directory):
        with fitz.open(path) as doc:
            pages += [analyze_page(page, settings) for page in doc]
    return pages


def batch_of(pages: list[PageOccupancy], size: int) -> list[PageOccupancy]:
    return [pages[i % len(pages)] for i in range(size)]


def _time_median(fn, repeats: int) -> float:
    fn()  # warm-up: imports, allocation and any kernel compilation are not measured
    samples = []
    for _ in range(repeats):
        start = perf_counter()
        fn()
        samples.append(perf_counter() - start)
    return median(samples)


def available_backends() -> list[str]:
    names = ["numpy"]
    if ws._torch() is not None:
        names.append("torch")
    if ws.cuda_available() and ws.triton is not None:
        names.append("triton")
    return names


def run(pages: list[PageOccupancy], repeats: int = REPEATS,
        batch_sizes: tuple[int, ...] = BATCH_SIZES) -> dict:
    settings = Settings()
    backends = available_backends()
    rows = []
    for size in batch_sizes:
        occs = batch_of(pages, size)
        expected = [find_min_ink_spot(o, DIAMETER_PT, settings) for o in occs]
        for name in backends:
            spots = ws.find_min_ink_spots(occs, DIAMETER_PT, settings, backend=name)
            if spots != expected:
                raise AssertionError(f"backend {name} disagrees with the reference at batch {size}")
            seconds = _time_median(
                lambda: ws.find_min_ink_spots(occs, DIAMETER_PT, settings, backend=name), repeats)
            rows.append({
                "backend": name,
                "batch": size,
                "median_ms": round(seconds * 1000, 3),
                "pages_per_second": round(size / seconds, 1),
            })
    return {
        "diameter_pt": DIAMETER_PT,
        "page_shapes": [list(p.ink.shape) for p in pages],
        "repeats": repeats,
        "machine": platform.platform(),
        "python": platform.python_version(),
        "torch": _torch_version(),
        "cuda": ws.cuda_available(),
        "results": rows,
    }


def _torch_version() -> str | None:
    torch = ws._torch()
    return torch.__version__ if torch is not None else None


def check(report: dict, thresholds: dict) -> list[str]:
    """Return one message per (backend, batch) that is slower than its threshold."""
    problems = []
    limits = thresholds["max_median_ms"]
    for row in report["results"]:
        limit = limits.get(row["backend"], {}).get(str(row["batch"]))
        if limit is None:
            continue
        if row["median_ms"] > limit:
            problems.append(f"{row['backend']} batch {row['batch']}: {row['median_ms']} ms "
                            f"is above the threshold of {limit} ms")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--output", type=Path, help="write the benchmark JSON here")
    ap.add_argument("--repeats", type=int, default=REPEATS)
    ap.add_argument("--check", type=Path, metavar="THRESHOLDS",
                    help="compare --report (or a fresh run) with this threshold file")
    ap.add_argument("--report", type=Path, help="benchmark JSON to check instead of running")
    args = ap.parse_args(argv)
    if args.check:
        thresholds = json.loads(args.check.read_text(encoding="utf-8"))
        if args.report:
            report = json.loads(args.report.read_text(encoding="utf-8"))
        else:
            with tempfile.TemporaryDirectory() as tmp:
                report = run(representative_pages(Path(tmp)), args.repeats)
        problems = check(report, thresholds)
        for row in report["results"]:
            print(f"{row['backend']:>6} batch {row['batch']:>2}: {row['median_ms']:>10.3f} ms, "
                  f"{row['pages_per_second']:>8.1f} pages/s")
        for problem in problems:
            print("REGRESSION:", problem)
        return 1 if problems else 0
    with tempfile.TemporaryDirectory() as tmp:
        report = run(representative_pages(Path(tmp)), args.repeats)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    for row in report["results"]:
        print(f"{row['backend']:>6} batch {row['batch']:>2}: {row['median_ms']:>10.3f} ms, "
              f"{row['pages_per_second']:>8.1f} pages/s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
