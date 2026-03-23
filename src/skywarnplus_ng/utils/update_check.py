"""
GitHub release check for advisory "update available" notices (no auto-update).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# GitHub asks API clients to send a User-Agent
USER_AGENT = "SkywarnPlus-NG-UpdateCheck/1.0"


def normalize_release_version(tag_name: str) -> str:
    """Strip leading 'v' from tag like v1.2.3."""
    t = (tag_name or "").strip()
    if t.lower().startswith("v") and len(t) > 1 and (t[1].isdigit() or t[1] == "."):
        return t[1:]
    return t


def compare_versions(installed: str, remote: str) -> bool:
    """Return True if remote is strictly newer than installed."""
    try:
        from packaging.version import Version

        return Version(remote) > Version(installed)
    except Exception:
        # Fallback: naive dot-split numeric compare
        def parts(s: str) -> Tuple[int, ...]:
            out: list[int] = []
            for chunk in re.split(r"[^\d]+", s):
                if chunk.isdigit():
                    out.append(int(chunk))
            return tuple(out) if out else (0,)

        return parts(remote) > parts(installed)


async def fetch_latest_release(
    session: aiohttp.ClientSession,
    github_repo: str,
    timeout_seconds: float = 20.0,
) -> Dict[str, Any]:
    """
    Call GitHub releases/latest API.

    Returns dict with keys: tag_name, html_url, published_at (or raises aiohttp.ClientError).
    """
    owner, _, repo = github_repo.partition("/")
    if not owner or not repo:
        raise ValueError(f"Invalid github_repo: {github_repo!r} (expected owner/repo)")
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with session.get(url, headers=headers, timeout=timeout) as resp:
        if resp.status == 404:
            raise FileNotFoundError("No releases or repo not found")
        resp.raise_for_status()
        data = await resp.json()
    return {
        "tag_name": data.get("tag_name") or "",
        "html_url": data.get("html_url") or "",
        "published_at": data.get("published_at") or "",
    }


def read_cache(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read update check cache %s: %s", path, exc)
        return None


def write_cache(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, indent=2)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def cache_is_fresh(cached: Dict[str, Any], interval_hours: int) -> bool:
    raw = cached.get("checked_at")
    if not raw:
        return False
    try:
        checked = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    now = datetime.now(timezone.utc)
    delta_hours = (now - checked).total_seconds() / 3600.0
    return delta_hours < interval_hours


def build_cache_payload(
    *,
    installed_version: str,
    remote_tag: str,
    remote_version: str,
    html_url: str,
    published_at: str,
    error: Optional[str],
) -> Dict[str, Any]:
    update_available = False
    if not error and remote_version:
        try:
            update_available = compare_versions(installed_version, remote_version)
        except Exception:
            update_available = False
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "installed_version": installed_version,
        "remote_tag": remote_tag,
        "remote_version": remote_version,
        "html_url": html_url,
        "published_at": published_at,
        "error": error,
        "update_available": update_available,
    }
