from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def timed(metric: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = (time.perf_counter() - start) * 1000
        print(f"METRIC|{metric}|{duration:.2f}ms")


def now_ms() -> int:
    return int(time.time() * 1000)
