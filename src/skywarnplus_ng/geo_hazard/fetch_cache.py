"""Short-TTL cache for geo-hazard HTTP responses (poll, dashboard, health)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")

DEFAULT_TTL_SECONDS = 120.0
HEALTH_REUSE_MAX_AGE_SECONDS = 120.0


class GeoFetchCache:
    """Process-wide cache with in-flight request deduplication."""

    _shared: Optional["GeoFetchCache"] = None

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[datetime, Any]] = {}
        self._in_flight: dict[str, asyncio.Task[Any]] = {}

    @classmethod
    def shared(cls) -> "GeoFetchCache":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def get_fresh(self, key: str) -> Optional[Any]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        age = (datetime.now(timezone.utc) - stored_at).total_seconds()
        if age > self.ttl_seconds:
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._evict_expired()
        self._entries[key] = (datetime.now(timezone.utc), value)

    def _evict_expired(self) -> None:
        """Drop stale entries so the process-wide cache cannot grow unbounded."""
        now = datetime.now(timezone.utc)
        expired = [
            key
            for key, (stored_at, _) in self._entries.items()
            if (now - stored_at).total_seconds() > self.ttl_seconds
        ]
        for key in expired:
            del self._entries[key]

    async def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Awaitable[Optional[T]]],
    ) -> Optional[T]:
        cached = self.get_fresh(key)
        if cached is not None:
            return cached

        if key in self._in_flight:
            try:
                return await self._in_flight[key]
            except Exception:
                return None

        task = asyncio.create_task(fetch_fn())
        self._in_flight[key] = task
        try:
            result = await task
        finally:
            self._in_flight.pop(key, None)

        if result is not None:
            self.set(key, result)
        return result
