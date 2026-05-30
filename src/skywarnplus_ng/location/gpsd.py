"""Read GPS fixes from a local gpsd instance."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GpsFix:
    """A single GPS fix from gpsd."""

    latitude: float
    longitude: float
    mode: int
    accuracy_m: Optional[float]
    fix_time: datetime


def _parse_gpsd_time(raw: Any) -> datetime:
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def poll_gpsd_fix(
    host: str = "127.0.0.1",
    port: int = 2947,
    timeout: float = 5.0,
) -> Optional[GpsFix]:
    """
    Request a one-shot fix from gpsd over its JSON interface.

    Returns None if gpsd is unreachable or no fix is available.
    """
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        logger.debug("Unable to connect to gpsd at %s:%s: %s", host, port, exc)
        return None

    try:
        writer.write(b'?WATCH={"enable":true,"json":true};\n')
        await writer.drain()
        writer.write(b"?POLL;\n")
        await writer.drain()

        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if not line:
                break
            try:
                payload = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if payload.get("class") != "POLL":
                continue
            return _fix_from_poll(payload)
        return None
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


def _fix_from_poll(payload: dict[str, Any]) -> Optional[GpsFix]:
    mode = int(payload.get("mode") or 0)
    if mode < 2:
        return None

    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None or lon is None:
        return None

    accuracy = payload.get("eph")
    if accuracy is None:
        accuracy = payload.get("epy")

    try:
        return GpsFix(
            latitude=float(lat),
            longitude=float(lon),
            mode=mode,
            accuracy_m=float(accuracy) if accuracy is not None else None,
            fix_time=_parse_gpsd_time(payload.get("time")),
        )
    except (TypeError, ValueError):
        return None
