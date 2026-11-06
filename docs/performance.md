# Measuring the drawing-stamping pipeline

I wanted seal-size changes and manual review to reuse work the tool had already
done. I measured the drawing analysis before changing it, then checked the
exported PDFs and seal positions against the original implementation.

## What I measured

The public corpus has three generated PDFs with four large sheets:

| Drawing | Sheets | Size in PDF points (72 points per inch) | Content |
| --- | ---: | --- | --- |
| vector-36x24 | 2 | 2592 × 1728 | Hundreds of vector rectangles; one marked stamp cell |
| rotated-a0 | 1 | 2384 × 3370 before 90° rotation | A0 linework and text |
| scanned-36x24 | 1 | 2592 × 1728 | Embedded grayscale drawing image |

These are synthetic drawings, not customer files. The generator uses a fixed
pattern and omits random PDF identifiers so the inputs can be reproduced.
The normal measurement includes grayscale rendering, ink detection, integral
image construction, box detection, whitespace search, disk coverage and
non-flattened PDF export with a generated DEMO seal. Input generation, file
opening, seal loading and the browser interface are outside the timed loop.
The documents are open in both comparisons, as they are during app review.

The baseline in [benchmarks/reference.py](../benchmarks/reference.py) preserves
the analysis implementation from main at `1ccaffa`. It shares the unchanged
placement/search and PDF writer with production, so the comparison isolates
the analysis changes. It is measurement code, never an app fallback.

## Findings and changes

I used three views of the same workload:

- **cProfile**, Python's function timer, counted calls and cumulative time.
  Across seven original full-pipeline passes it recorded 0.878 seconds total,
  0.541 seconds in integral-image construction (62%), 0.076 seconds in page
  rendering (9%) and 0.075 seconds in export (9%). Nested times overlap and
  should not be added. The cumulative sums inside the integral step consumed
  0.520 seconds on their own.
- **line_profiler** measured individual source lines. In the original analysis,
  about 87% of analysis time was spent building the integral image. Almost all
  of that helper's time was on its chained cumulative-sum line. The before and
  after line reports are saved alongside the function reports below.
- **py-spy** samples a running program's call stack without instrumenting its
  functions. The Linux performance job samples 200 before passes and 200 after
  passes at 100 Hz. It saves Speedscope files, which can be opened at
  <https://www.speedscope.app/>, and a summary of inclusive stack counts.
  Sampling includes Python startup and fixture generation, unlike the timed
  loop, so its percentages are supporting evidence, not a substitute for the
  uninstrumented timings. It attributes native work to the enclosing Python
  call; this run does not resolve individual MuPDF C++ functions.

An integral image is a table of running ink totals that lets the search count
ink in any rectangle without scanning the rectangle again. The old code already
used NumPy arrays rather than Python pixel loops. I changed its two cumulative
sums to write into the final table, visiting rows first, instead of allocating
two extra page-sized arrays. The result stays uint32 and keeps the zero border
and exact integer window counts. On A0 at 72 DPI, this removes two 32-bit
intermediates totalling about 61 MiB, calculated from pixel dimensions.
This is an allocation calculation, not a measured peak-RSS or leak claim.

I also read MuPDF's grayscale pixels through `samples_mv`, a memory view, while
the pixmap is alive, avoiding the copy made by `samples`. The resulting boolean
ink mask owns its memory and remains valid after the pixmap is released.

The app previously analysed a page for automatic placement, then analysed it
again for manual disk-coverage checks. Its full settings cache key also made a
seal-size change repeat the raster work. Both paths now share a byte-bounded
least-recently-used analysis cache, meaning the oldest unused summary is evicted
when space is needed. Its key contains page number, analysis DPI and ink
threshold; seal size, margins and preview settings do not change the ink mask.

Each cache belongs to one open, immutable PDF document, with a 64 MiB allowance.
The app retains at most two such caches, up to 128 MiB of analysis arrays. These
limits do not describe total app memory, including previews and open documents.
Oversized entries are used without retention. Arrays are read-only when shared.
Callers editing a document must call `clear()` after edits and before closing it;
the app's uploaded source documents are immutable. A cache for one document is
rejected by another document's placement pass. No background workers are added.

## Recorded results

These are nine uninstrumented passes on Python 3.12.14, NumPy 2.5.4,
PyMuPDF 1.26.7, macOS ARM64. The JSON files contain every sample and the environment.

| Four-sheet placement and export | Median | Change from original |
| --- | ---: | ---: |
| Original analysis | 123.90 ms | Baseline |
| Optimized, analysis cache disabled | 95.04 ms | 23.3% less time |
| Optimized, warm analysis cache | 34.58 ms | 72.1% less time |

The cached run starts empty; its first pass took 101.55 ms. The warm figure is
the median of the remaining eight passes, alternating 1.9-inch and 2.0-inch
seals. The original and uncached optimized figures include nine passes. I check
that the final placements, including coordinates, source and coverage, match
exactly. The first optimized cache miss can vary with normal system activity.

[Original timings](performance/before-timing.json),
[optimized timings](performance/after-timing.json),
[cached timings](performance/cached-timing.json),
[original function profile](performance/before-cprofile.txt),
[optimized function profile](performance/after-cprofile.txt),
[original line profile](performance/before-lines.txt) and
[optimized line profile](performance/after-lines.txt) are the recorded evidence.
The [recorded Linux run](https://github.com/jackaI1/computer-vision-layout-stamping-system/actions/runs/42139019655)
passed all checks. Its uninstrumented medians were 202.85 ms before, 155.04 ms
after (23.6% less time) and 45.63 ms with warm analysis reuse (77.5% less time).
Its [saved py-spy summary](performance/py-spy-summary.json) records 4,272 total
samples before and 3,273 after. The integral-image function was present in 2,490
before samples (58.3%) and 1,745 after samples (53.3%). The sampler independently
supports the integral step as the main cost; these inclusive counts include
startup and are not exact stage timings. Both runs completed 200 full passes.

Fresh Linux runs and full sampling profiles are saved by the
[Performance workflow](../.github/workflows/performance.yml).

## Repeat the measurements

From the repository root, with Python 3.12:

```sh
python -m pip install -r requirements-profile.txt
python -m benchmarks.profile_pipeline --baseline --label before --repeats 9
python -m benchmarks.profile_pipeline --label after --repeats 9
python -m benchmarks.profile_pipeline --cache --label cached --repeats 9
python -m benchmarks.compare
python -m benchmarks.profile_pipeline --baseline --label before --mode cprofile --repeats 7
python -m benchmarks.profile_pipeline --label after --mode cprofile --repeats 7
python -m benchmarks.profile_pipeline --baseline --label before --mode lines --repeats 3
python -m benchmarks.profile_pipeline --label after --mode lines --repeats 3
```

Reports and generated drawings go into ignored `output/performance/`.
Use `--dpi 144` on each timing command to try a more expensive raster. A page
may then exceed the cache budget, so warm-cache gains are not guaranteed.
Instrumented runs use separate filenames and are never used for speedup claims.

On Linux, launch py-spy's own child process rather than attaching to another
process:

```sh
py-spy record --rate 100 --format speedscope -o output/performance/before-py-spy.json -- python -m benchmarks.profile_pipeline --baseline --label before --mode sample --repeats 200
py-spy record --rate 100 --format speedscope -o output/performance/after-py-spy.json -- python -m benchmarks.profile_pipeline --label after --mode sample --repeats 200
python -m benchmarks.compare --sampling
```

[py-spy's documentation](https://github.com/benfred/py-spy#when-do-you-need-to-run-as-sudo)
explains why macOS requires administrator access. I use the Linux CI job for
that measurement; no Mac security setting needs to be changed. Each command
exits after its finite workload and leaves no server or browser process.
[line_profiler's API](https://kernprof.readthedocs.io/en/stable/auto/line_profiler.html)
describes the per-line profiler used here.

## Regression checks and limits

`python -m pytest tests/test_performance.py -q` checks exact integral tables,
strided inputs, large counts, cache invalidation, document ownership, eviction,
oversized entries, automatic/manual cache sharing and all four large exported
sheets. It clears the caches before each of three measured passes and requires
the median cold placement-plus-export time to stay below **5 seconds**. This is
a generous shared-runner budget for catching severe regressions, not a promise
of 5 seconds for arbitrary PDFs. Deterministic render-call and equality checks
catch repeat rendering and incorrect results without relying on close timings.

The existing suite still covers rotated coordinates, keep-outs, preview edits,
CAD output and the station checks. CI runs that suite and maintains the existing
traceability and IQ/OQ records; the performance job saves timing/profile artifacts
for 14 days. No strict percentage-speedup gate is used on shared runners.

Real scans, complex fonts, high resolution, many pages, flattening and different
hardware can change the bottleneck. This corpus does not prove speed on every
client drawing. Rendering is smaller than the integral step here, but reusing
analysis still avoids unnecessary render calls during review. Clearance search
remains a visible cost after optimization; I kept its exact tie-breaking behavior
rather than trading away placement quality for another speed figure.
