"""HTTP fetching and downloads shared by every source.

Sources call these through the module (``net.fetch_page(...)``), so tests can replace them
with ``monkeypatch.setattr(notekit.net, ...)`` and run the whole pipeline offline.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError

from . import cost

MOBILE_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
# Kept for code written against the single-source extractor.
USER_AGENT = MOBILE_USER_AGENT
MAX_PAGE_BYTES = 15 * 1024 * 1024


@dataclass
class Response:
    url: str
    content_type: str
    body: bytes


def fetch(url: str, user_agent: str = MOBILE_USER_AGENT, headers: dict[str, str] | None = None) -> Response:
    """GET a page. Returns the final URL after redirects, the Content-Type header, and the body."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, **(headers or {})})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(MAX_PAGE_BYTES + 1)
        if len(body) > MAX_PAGE_BYTES:
            raise RuntimeError(f"The page is larger than {MAX_PAGE_BYTES // 1024 // 1024} MB.")
        cost.count("bytes_downloaded", len(body))
        return Response(response.geturl(), response.headers.get("Content-Type", ""), body)


def fetch_page(url: str) -> tuple[str, str]:
    """Fetch a page as text with the mobile user agent (what Xiaohongshu share links expect)."""
    response = fetch(url)
    return response.url, response.body.decode("utf-8", errors="replace")


def download(url: str, destination: Path, referer: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": referer})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    except (HTTPError, URLError):
        subprocess.run(
            ["curl.exe" if os.name == "nt" else "curl", "-sS", "-L", "--fail", "--retry", "2",
             "-A", USER_AGENT, "-e", referer, "-o", str(destination), url],
            check=True,
        )
    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError(f"The downloaded file {destination.name} is empty.")
    cost.count("bytes_downloaded", destination.stat().st_size)


def download_first(urls: list[str], destination: Path, referer: str) -> None:
    errors = []
    for url in urls:
        try:
            download(url, destination, referer)
            return
        except Exception as error:
            errors.append(str(error))
    raise RuntimeError("Could not download the video: " + "; ".join(errors))
