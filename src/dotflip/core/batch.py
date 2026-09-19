"""Batch runner with progress and cancellation, shared by CLI and GUI."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .convert import ConversionError, ConvertOptions, convert


@dataclass
class Result:
    source: Path
    output: Path | None
    error: str | None = None
    skipped: bool = False
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and not self.cancelled


def run_batch(
    files,
    opts: ConvertOptions,
    on_progress: Callable[[int, int, Result], None] | None = None,
    cancel: threading.Event | None = None,
    workers: int = 4,
) -> list[Result]:
    """Convert files concurrently. Results are returned in input order."""
    files = [Path(f) for f in files]
    cancel = cancel or threading.Event()
    results: dict[int, Result] = {}

    def work(i: int, src: Path) -> Result:
        if cancel.is_set():
            return Result(src, None, cancelled=True)
        try:
            out = convert(src, opts)
            return Result(src, out, skipped=out is None)
        except ConversionError as e:
            return Result(src, None, error=str(e))
        except Exception as e:  # never let one bad file kill the batch
            return Result(src, None, error=f"{type(e).__name__}: {e}")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(work, i, f): i for i, f in enumerate(files)}
        done = 0
        for fut in as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()
            done += 1
            if on_progress:
                on_progress(done, len(files), results[i])
    return [results[i] for i in range(len(files))]
