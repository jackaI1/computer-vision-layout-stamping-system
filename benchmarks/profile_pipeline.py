"""Profile placement and PDF export; generate/open inputs outside the measured loop.

Run with python -m benchmarks.profile_pipeline --help.
"""
from __future__ import annotations

import argparse
import cProfile
from contextlib import ExitStack
import json
import hashlib
import platform
import pstats
from statistics import median
from time import perf_counter
from pathlib import Path

import fitz
import numpy as np

from benchmarks.drawings import make_drawings, make_seal
from benchmarks import reference
from stamper import occupancy, placement
from stamper.config import Settings
from stamper.pdf_writer import render_stamped_pdf


def run_corpus(documents, settings, caches=None, baseline=False, sources=None, stamp=None):
    if baseline:
        result = [reference.compute_placements(doc, settings) for doc in documents]
    else:
        result = [placement.compute_placements(doc, settings, analysis_cache=cache)
                  for doc, cache in zip(documents, caches or [None] * len(documents))]
    if sources is not None:
        for source, placements in zip(sources, result):
            render_stamped_pdf(source, placements, stamp, "2026-11-05", settings)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output/performance"))
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--dpi", type=int, default=72)
    parser.add_argument("--label", default="before")
    parser.add_argument("--mode", choices=["timing", "cprofile", "lines", "sample"], default="timing")
    parser.add_argument("--baseline", action="store_true", help="Run the preserved pre-optimization analysis")
    parser.add_argument("--cache", action="store_true", help="Reuse page analysis across seal-size changes")
    args = parser.parse_args()
    if args.repeats < 1 or args.dpi < 1:
        parser.error("repeats and dpi must be positive")
    if args.baseline and args.cache:
        parser.error("baseline does not have an analysis cache")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    paths = make_drawings(args.output_dir / "drawings")
    prefix = args.output_dir / f"{args.label}-{args.mode}"
    with ExitStack() as stack:
        docs = [stack.enter_context(fitz.open(path)) for path in paths]
        caches = [occupancy.PageAnalysisCache(doc) for doc in docs] if args.cache else None
        sources = [path.read_bytes() for path in paths]
        stamp = make_seal()
        settings = Settings(analysis_dpi=args.dpi)
        # Warm imports/native libraries; explicitly empty the analysis caches.
        run_corpus(docs, settings, caches, args.baseline, sources, stamp)
        if caches:
            for cache in caches:
                cache.clear()

        def workload():
            samples = []
            for i in range(args.repeats):
                start = perf_counter()
                result = run_corpus(docs, settings.with_overrides(stamp_diameter_in=1.9 + (i % 2) * .1), caches, args.baseline, sources, stamp)
                samples.append(perf_counter() - start)
            return samples, result

        if args.mode == "cprofile":
            profiler = cProfile.Profile()
            samples, result = profiler.runcall(workload)
            profiler.dump_stats(str(prefix) + ".pstats")
            with open(str(prefix) + "-cprofile.txt", "w") as stream:
                pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(30)
        elif args.mode == "lines":
            from line_profiler import LineProfiler
            profiler = LineProfiler(occupancy.analyze_page, occupancy._integral_image,
                                    occupancy._most_open_candidate, placement.place_one_page,
                                    reference.analyze_page, reference.integral_image)
            samples, result = profiler.runcall(workload)
            with open(str(prefix) + "-lines.txt", "w") as stream:
                from io import StringIO
                text = StringIO()
                profiler.print_stats(stream=text)
                stream.write(text.getvalue().replace(str(Path(__file__).resolve().parents[1]), "<repo>"))
        else:
            samples, result = workload()
        report = {
            "label": args.label, "mode": args.mode, "analysis_dpi": args.dpi,
            "scope": "placement and non-flattened PDF export; fixture generation/open excluded",
            "cache": args.cache, "baseline_revision": "1ccaffa" if args.baseline else None, "repeats": args.repeats,
            "python": platform.python_version(), "platform": platform.platform(),
            "numpy": np.__version__, "pymupdf": fitz.VersionBind,
            "corpus": [{"name": p.name, "sha256": hashlib.sha256(source).hexdigest(), "pages": len(d), "dimensions_pt": [list(page.rect) for page in d]}
                       for p, d, source in zip(paths, docs, sources)],
            "seconds": samples, "median_seconds": median(samples),
            "first_seconds": samples[0],
            "warm_median_seconds": median(samples[1:]) if len(samples) > 1 else None,
            "placements": [[p.to_dict() for p in placements] for placements in result],
        }
        prefix.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        if caches:
            for cache in caches:
                cache.clear()
        print(json.dumps({k: report[k] for k in ["label", "mode", "cache", "median_seconds", "first_seconds", "warm_median_seconds"]}))


if __name__ == "__main__":
    main()
