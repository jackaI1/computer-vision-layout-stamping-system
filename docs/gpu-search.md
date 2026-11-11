# Batch page search and the Triton kernel: design notes

## What is searched

For each page, the stamper looks for the seal position with the least ink under it.
The page is turned into an ink mask (a yes/no grid of dark pixels). An integral image
(a table of running ink totals, also called a summed-area table) makes the ink under
any square a four-lookup sum. The reference search, `find_min_ink_spot` in
`stamper/occupancy.py`, checks every candidate grid position with that sum. Ties are
broken by clearance: the seal goes to the candidate with the largest ink-free square
that still fits on the page.

## Profile first

Profile of the reference on the generated drawing batch (16 pages, cProfile, this Mac):

- `_most_open_candidate` (clearance tie-break) took about 75% of the time;
- the window sums (`_window_sums`) took about 20%.

So a GPU port of the window sums alone can only save about a fifth of the time. The
batch search therefore moves the tie-break to the device as well, and runs the binary
search for all pages in one loop.

## Design

`stamper/window_search.py`:

- `find_min_ink_spots(occs, diameter_pt, settings, keepouts, bounds_pt, backend)`
  groups pages by size and scale, computes the candidate grid and keep-out masks on
  the host, and runs the scan on one device.
- Backends: `triton` (a Triton kernel for the window sums), `torch` (the same sums
  with PyTorch tensors), `numpy` (calls the reference per page), and `auto` (Triton
  when CUDA is available, otherwise numpy). `torch` is never chosen automatically on a
  CPU, because the CPU benchmark was slower than NumPy.
- The tie-break `_most_open_batch` follows the reference binary search line by line.
  "First candidate in row-major order" is kept by `torch.argmax`/`scatter_reduce`
  semantics, which return the first maximum.
- Only the small per-page answers (coordinates and coverage) come back to the host.

The shared pieces (`search_grid`, `keepout_blocked`, `spot_from_sums`) live in
`stamper/occupancy.py`, so the reference and the batch path use one definition.

## Verifying the kernel without a GPU

Triton has no macOS build, and GitHub's free runners have no GPU. The
`window-search.yml` workflow sets `TRITON_INTERPRET=1`, which runs the kernel in
Python on the CPU, and `WINDOW_SEARCH_REQUIRE_TRITON=1`, which turns a missing Triton
into a failure rather than a skipped test. The same tests then compare every backend
with the reference.

## Benchmark and gate

`benchmarks/window_search_bench.py` renders the drawing corpus used by the pipeline
benchmark, analyses its pages, and times each backend on batches of 1, 4 and 16 pages.
Every backend must match the reference before it is timed. The gate (`--check`)
compares each median latency with `benchmarks/window_search_thresholds.json`.

## Profiling commands

```sh
python -m benchmarks.window_search_profile --backend numpy   # cProfile table of the reference
python -m benchmarks.window_search_profile --backend torch   # PyTorch Profiler table and Chrome trace
```

On a Linux or Windows machine with an NVIDIA GPU (install the CUDA build of PyTorch
first), profile the Triton path with Nsight Systems:

```sh
nsys profile -t cuda -o window-search python -m benchmarks.window_search_profile --backend triton
```

Open `window-search.nsys-rep` in Nsight Systems to see each kernel launch and its
time on the GPU. This has not been run yet; no NVIDIA GPU was available for it.

## Not done yet

- The app does not call the batch search; the single-page path is unchanged.
- GPU latency and throughput are not measured. CI measures only the CPU backends.
- The Triton kernel has only been run in the interpreter, not on a GPU.
