"""Find the least-ink seal position on many pages at once, optionally on a GPU.

:func:`stamper.occupancy.find_min_ink_spot` checks every candidate position on
one page with NumPy. That is correct, but a large batch of drawings is then
processed one page after another. This module runs the same scan over a batch of
pages in one step. The work that dominates is four table lookups per candidate
in each page's integral image (summed-area table), and that is the part that moves
to a Triton GPU kernel. The choice among tied candidates is shared code with the
reference, so every backend returns the same seal position.

Backends (``backend=`` argument):

``"triton"``
    A Triton kernel computes the window sums on the GPU. It needs ``triton`` and
    CUDA. With ``TRITON_INTERPRET=1`` the same kernel runs in Python on the CPU;
    that is slow and used to check the kernel in continuous integration.
``"torch"``
    The same sums with PyTorch tensors on the CPU (or any torch device).
``"numpy"``
    Calls :func:`find_min_ink_spot` once per page. This is the reference.
``"auto"``
    Triton when CUDA is available, otherwise numpy. On a CPU the NumPy reference
    was faster than the PyTorch CPU path in the benchmark, so torch is only used
    when asked for by name.

Pages are grouped by size and scale, because one candidate grid applies to all
pages of the same size. Results come back in the input order.
"""
from __future__ import annotations

import os
from collections.abc import Sequence

import numpy as np

from .config import Settings
from .occupancy import (
    PageOccupancy,
    SearchGrid,
    Spot,
    find_min_ink_spot,
    keepout_blocked,
    search_grid,
)

BACKENDS = ("auto", "triton", "torch", "numpy")
# Sentinel for a candidate that is not allowed. It is larger than any window sum.
BLOCKED = np.int64(2 ** 62)

try:  # Triton is optional. Without it, only the torch and numpy backends run.
    import triton
    import triton.language as tl
except ImportError:  # pragma: no cover - depends on the installed packages
    triton = None
    tl = None


def _torch():
    try:
        import torch
    except ImportError:
        return None
    return torch


def cuda_available() -> bool:
    torch = _torch()
    return bool(torch is not None and torch.cuda.is_available())


def triton_available() -> bool:
    """Triton can run: installed, and either CUDA or the CPU interpreter is on."""
    if triton is None or _torch() is None:
        return False
    return cuda_available() or os.environ.get("TRITON_INTERPRET") == "1"


def resolve_backend(backend: str = "auto") -> str:
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend {backend!r}; choose from {BACKENDS}")
    if backend != "auto":
        return backend
    if triton_available() and cuda_available():
        return "triton"
    return "numpy"


if triton is not None:  # pragma: no branch - the kernel is only defined with Triton

    @triton.jit
    def _min_ink_window_kernel(
        integral_ptr,      # int64, shape (B, H1, W1), C-contiguous
        blocked_ptr,       # int8,  shape (B, n_cand); nonzero = not allowed
        out_ptr,           # int64, shape (B, n_cand)
        H1, W1,            # integral table height and width (H + 1, W + 1)
        n_cand, nx,        # candidates per page and columns of the candidate grid
        y_lo, x_lo, step,  # first candidate row/column and grid step (pixels)
        d,                 # footprint side (pixels)
        blocked_value,     # sentinel written for a blocked candidate
        BLOCK: tl.constexpr,
    ):
        page = tl.program_id(0).to(tl.int64)
        offs = (tl.program_id(1) * BLOCK + tl.arange(0, BLOCK)).to(tl.int64)
        valid = offs < n_cand
        iy = offs // nx
        ix = offs % nx
        y0 = y_lo + iy * step
        x0 = x_lo + ix * step
        base = integral_ptr + page * H1 * W1
        # Summed-area identity: window = I[y0+d, x0+d] - I[y0, x0+d] - I[y0+d, x0] + I[y0, x0]
        a = tl.load(base + (y0 + d) * W1 + (x0 + d), mask=valid, other=0)
        b = tl.load(base + y0 * W1 + (x0 + d), mask=valid, other=0)
        c = tl.load(base + (y0 + d) * W1 + x0, mask=valid, other=0)
        e = tl.load(base + y0 * W1 + x0, mask=valid, other=0)
        keep = tl.load(blocked_ptr + page * n_cand + offs, mask=valid, other=0)
        total = tl.where(keep != 0, blocked_value, a - b - c + e)
        tl.store(out_ptr + page * n_cand + offs, total, mask=valid)


def _torch_window_sums(I, grid: SearchGrid, blocked, torch, device):
    """Window sums for a batch: ``I`` is an int64 tensor (B, H+1, W+1) on ``device``."""
    ys = torch.as_tensor(grid.ys, dtype=torch.int64, device=device)
    xs = torch.as_tensor(grid.xs, dtype=torch.int64, device=device)
    d = grid.d
    y0, x0 = ys[:, None], xs[None, :]
    y1, x1 = y0 + d, x0 + d
    sums = I[:, y1, x1] - I[:, y0, x1] - I[:, y1, x0] + I[:, y0, x0]
    return torch.where(blocked, torch.as_tensor(BLOCKED, device=device), sums)


def _kernel_window_sums(I, grid: SearchGrid, blocked, torch, device):
    B, H1, W1 = I.shape
    n = grid.xs.size * grid.ys.size
    keep = blocked.reshape(B, n).to(torch.int8).contiguous()
    out = torch.empty((B, n), dtype=torch.int64, device=device)
    block = 1024
    _min_ink_window_kernel[(B, triton.cdiv(n, block))](
        I, keep, out, H1, W1, n, grid.xs.size,
        int(grid.ys[0]), int(grid.xs[0]), grid.step, grid.d, int(BLOCKED),
        BLOCK=block,
    )
    return out.reshape(B, grid.ys.size, grid.xs.size)


def _most_open_batch(I, grid: SearchGrid, eligible, need, torch, device) -> list[int]:
    """Device version of ``occupancy._most_open_candidate``, run for the whole batch at once.

    ``I`` is the int64 integral stack (B, H+1, W+1), ``eligible`` the (B, ny, nx)
    mask of tied candidates and ``need`` a (B,) mask of pages that need a
    tie-break. For each page the binary search finds the largest ink-free square
    that fits on the page, exactly as the reference does, and the first candidate
    (row-major) with the largest square wins. Returns one flat grid index per page,
    or -1 where the reference would return ``None``.
    """
    B, H1, W1 = I.shape
    H, W = H1 - 1, W1 - 1
    bidx, rows, cols = torch.nonzero(eligible & need[:, None, None], as_tuple=True)
    out = [-1] * B
    if bidx.numel() == 0:
        return out
    xs_t = torch.as_tensor(grid.xs, dtype=torch.int64, device=device)
    ys_t = torch.as_tensor(grid.ys, dtype=torch.int64, device=device)
    x, y = xs_t[cols], ys_t[rows]
    d = grid.d
    low = torch.full_like(x, -1)
    high = torch.minimum(torch.minimum(x, y), torch.minimum(W - x - d, H - y - d)) + 1
    while True:
        active = torch.nonzero(high - low > 1, as_tuple=True)[0]
        if active.numel() == 0:
            break
        mid = torch.div(low[active] + high[active], 2, rounding_mode="floor")
        ab, ax, ay = bidx[active], x[active], y[active]
        x0, y0 = ax - mid, ay - mid
        x1, y1 = ax + d + mid, ay + d + mid
        ink = I[ab, y1, x1] - I[ab, y0, x1] - I[ab, y1, x0] + I[ab, y0, x0]
        clear = ink == 0
        low[active[clear]] = mid[clear]
        high[active[~clear]] = mid[~clear]
    # Per page: the largest square, and the first element (row-major) that has it.
    K = low.numel()
    page_best = torch.full((B,), -2, dtype=torch.int64, device=device).scatter_reduce(
        0, bidx, low, reduce="amax")
    position = torch.arange(K, device=device)
    first = torch.full((B,), K, dtype=torch.int64, device=device).scatter_reduce(
        0, bidx, torch.where(low == page_best[bidx], position, K), reduce="amin")
    best_list, first_list = page_best.tolist(), first.tolist()
    flat = (rows * grid.xs.size + cols).tolist()
    for b in range(B):
        if need[b] and best_list[b] >= 0 and first_list[b] < K:
            out[b] = flat[first_list[b]]
    return out


def _device_spots(integrals: np.ndarray, grid: SearchGrid, blocked: np.ndarray, backend: str,
                  device: str | None, settings: Settings) -> list[Spot | None]:
    """Run the whole batch on one device; only the small per-page answers come back."""
    torch = _torch()
    dev = device or ("cuda" if cuda_available() else "cpu")
    I = torch.as_tensor(integrals, dtype=torch.int64, device=dev).contiguous()
    keep = torch.as_tensor(blocked, device=dev)
    if backend == "triton":
        sums = _kernel_window_sums(I, grid, keep, torch, dev)
    else:
        sums = _torch_window_sums(I, grid, keep, torch, dev)
    B = sums.shape[0]
    flat = sums.reshape(B, -1)
    arg = torch.argmin(flat, dim=1)                     # first minimum, as np.argmin
    best = flat.gather(1, arg[:, None]).squeeze(1)
    eligible = flat == best[:, None]
    counts = eligible.sum(dim=1)
    best_list, arg_list = best.tolist(), arg.tolist()
    # A page needs the clearance tie-break when it has an allowed best and several ties.
    # A blank page (best == 0) is exactly the case where every position ties.
    need = (best < BLOCKED) & (counts > 1)
    if not settings.maximize_clearance:
        need = torch.zeros_like(need)
    winners = _most_open_batch(I, grid, eligible.reshape(B, grid.ys.size, grid.xs.size),
                               need, torch, dev)
    d = grid.d
    out: list[Spot | None] = []
    for b in range(B):
        if best_list[b] >= int(BLOCKED):
            out.append(None)
            continue
        choice = winners[b] if winners[b] >= 0 else arg_list[b]
        iy, ix = divmod(choice, grid.xs.size)
        best_x0 = grid.xs[ix]
        best_y0 = grid.ys[iy]
        out.append(Spot(
            (best_x0 + d / 2.0) / grid.scale,
            (best_y0 + d / 2.0) / grid.scale,
            float(best_list[b]) / float(d * d),
        ))
    return out


def find_min_ink_spots(
    occs: Sequence[PageOccupancy],
    diameter_pt: float,
    settings: Settings,
    keepouts: Sequence[list[tuple[float, float, float, float]] | None] | None = None,
    bounds_pt: tuple[float, float, float, float] | None = None,
    backend: str = "auto",
    device: str | None = None,
) -> list[Spot | None]:
    """Least-ink seal spot for every page in ``occs``.

    ``keepouts`` gives one keep-out list per page (or ``None``). ``bounds_pt``
    applies to every page. The result has the same meaning as calling
    :func:`find_min_ink_spot` on each page.
    """
    backend = resolve_backend(backend)
    if keepouts is None:
        keepouts = [None] * len(occs)
    if len(keepouts) != len(occs):
        raise ValueError("keepouts must have one entry per page")
    results: list[Spot | None] = [None] * len(occs)
    if backend == "numpy":
        for i, occ in enumerate(occs):
            results[i] = find_min_ink_spot(occ, diameter_pt, settings, keepouts[i], bounds_pt)
        return results

    groups: dict[tuple, list[int]] = {}
    for i, occ in enumerate(occs):
        groups.setdefault((occ.ink.shape, occ.scale), []).append(i)
    for indices in groups.values():
        grid = search_grid(occs[indices[0]], diameter_pt, settings, bounds_pt)
        if grid is None:
            continue
        integrals = np.stack([occs[i].integral for i in indices]).astype(np.int64)
        empty = np.zeros((grid.ys.size, grid.xs.size), dtype=bool)
        blocked = np.stack([
            empty if (mask := keepout_blocked(grid, diameter_pt, keepouts[i])) is None else mask
            for i in indices
        ])
        spots = _device_spots(integrals, grid, blocked, backend, device, settings)
        for i, spot in zip(indices, spots):
            results[i] = spot
    return results
