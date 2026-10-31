import json
import re
import urllib.request
from typing import Any

RELEASES_API_URL = "https://api.github.com/repos/Hxueit/Devil-Connection-Sav-Manager/releases/latest"
REQUEST_TIMEOUT_SECONDS = 10


def fetch_latest_release() -> dict[str, Any]:
    request = urllib.request.Request(RELEASES_API_URL, headers={"User-Agent": "Devil-Connection-Sav-Manager"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        release = json.loads(response.read().decode("utf-8"))
    if not isinstance(release, dict) or not release.get("tag_name"):
        raise ValueError("Unexpected GitHub API response")
    return release


def parse_version(version: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3)；无法解析时返回 (0,)"""
    match = re.match(r"v?(\d+(?:\.\d+)*)", version.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else (0,)


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    length = max(len(a), len(b))
    return a + (0,) * (length - len(a)) > b + (0,) * (length - len(b))


def format_release_date(published_at: str) -> str:
    """'2024-01-01T12:00:00Z' -> '2024-01-01 12:00:00'"""
    return (published_at or "").replace("T", " ").rstrip("Z")[:19]
