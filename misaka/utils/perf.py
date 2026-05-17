from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger("misaka.perf")


@contextmanager
def perf_timer(label: str, threshold_ms: float = 1.0) -> Generator[None, None, None]:
    """Context manager that logs elapsed time if it exceeds threshold."""
    start = time.perf_counter()
    yield
    elapsed = (time.perf_counter() - start) * 1000
    if elapsed >= threshold_ms:
        logger.debug("[PERF] %s: %.1fms", label, elapsed)
