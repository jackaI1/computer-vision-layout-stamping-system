"""Profile the batch page search with cProfile and the PyTorch Profiler.

    python -m benchmarks.window_search_profile --backend numpy   # where the reference spends time
    python -m benchmarks.window_search_profile --backend torch   # PyTorch operator table and trace
    python -m benchmarks.window_search_profile --backend triton  # GPU only (CUDA or TRITON_INTERPRET=1)

Output goes to ``output/window-search/`` as text tables plus a Chrome trace file
(``torch-trace.json``, open it at chrome://tracing or in Perfetto). A GPU timeline
for the Triton kernel comes from Nsight Systems; see docs/gpu-search.md for the
command. This script does not start Nsight itself.
"""
from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import tempfile
from pathlib import Path

from benchmarks.window_search_bench import DIAMETER_PT, batch_of, representative_pages
from stamper import window_search as ws
from stamper.config import Settings

OUTPUT = Path("output/window-search")


def profile_numpy(occs, settings, out: Path) -> str:
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(3):
        ws.find_min_ink_spots(occs, DIAMETER_PT, settings, backend="numpy")
    profiler.disable()
    buf = io.StringIO()
    pstats.Stats(profiler, stream=buf).sort_stats("cumulative").print_stats(12)
    out.write_text(buf.getvalue(), encoding="utf-8")
    return out.name


def profile_torch(occs, settings, backend: str, out_dir: Path) -> list[str]:
    from torch.profiler import ProfilerActivity, profile

    activities = [ProfilerActivity.CPU]
    if ws.cuda_available():
        activities.append(ProfilerActivity.CUDA)
    with profile(activities=activities, record_shapes=False) as prof:
        ws.find_min_ink_spots(occs, DIAMETER_PT, settings, backend=backend)
    sort_key = "self_cuda_time_total" if ws.cuda_available() else "self_cpu_time_total"
    table = prof.key_averages().table(sort_by=sort_key, row_limit=12)
    table_path = out_dir / f"{backend}-operators.txt"
    table_path.write_text(table + "\n", encoding="utf-8")
    trace_path = out_dir / f"{backend}-trace.json"
    prof.export_chrome_trace(str(trace_path))
    return [table_path.name, trace_path.name]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", default="numpy", choices=["numpy", "torch", "triton"])
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--output", type=Path, default=OUTPUT)
    args = ap.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    with tempfile.TemporaryDirectory() as tmp:
        occs = batch_of(representative_pages(Path(tmp)), args.batch)
    if args.backend == "numpy":
        written = [profile_numpy(occs, settings, args.output / "numpy-cprofile.txt")]
    else:
        runnable = ws._torch() is not None if args.backend == "torch" else ws.triton_available()
        if not runnable:
            raise SystemExit(f"{args.backend} is not available here (see docs/gpu-search.md)")
        written = profile_torch(occs, settings, args.backend, args.output)
    print("wrote " + ", ".join(str(args.output / name) for name in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
