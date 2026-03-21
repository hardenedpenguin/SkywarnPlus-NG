"""
Simple in-memory sliding-window rate limiting for HTTP handlers.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


class SlidingWindowRateLimiter:
    """Allow at most max_calls per key within window_seconds (monotonic clock)."""

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.max_calls = max_calls
        self.window = float(window_seconds)
        self._buckets: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> Tuple[bool, Optional[float]]:
        """
        Record one attempt for key.

        Returns:
            (allowed, retry_after_seconds) — retry_after is set when not allowed.
        """
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets[key]
            cutoff = now - self.window
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            if len(bucket) >= self.max_calls:
                retry_after = self.window - (now - bucket[0])
                return False, max(retry_after, 0.0)
            bucket.append(now)
            return True, None
