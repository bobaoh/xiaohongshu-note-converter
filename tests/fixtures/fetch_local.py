"""Cache the regression notes locally so tests can rerun on the same real media offline.

Downloads each note's page and media into tests/fixtures/local/<code>/. That folder is
git-ignored: the media belongs to its authors and must not be committed to this public
repository. Run once (and again if you want to refresh the cache):

    python tests/fixtures/fetch_local.py            # all regression notes
    python tests/fixtures/fetch_local.py 9mo7le3NAf # one note
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import shutil  # noqa: E402
import tempfile  # noqa: E402

import extract_note  # noqa: E402
from notekit import source_for  # noqa: E402
from notekit.cost import load_policy  # noqa: E402
from notekit.sources import web  # noqa: E402
from regression import load_expectations  # noqa: E402

LOCAL = Path(__file__).resolve().parent / "local"


def fetch(expected: dict) -> None:
    if source_for(expected["url"]).name == "web":
        fetch_web(expected)
    else:
        fetch_xiaohongshu(expected)


def fetch_web(expected: dict) -> None:
    """Cache the page and the images the web source would keep (after size filtering)."""
    target = LOCAL / expected["code"]
    images = target / "images"
    images.mkdir(parents=True, exist_ok=True)
    resolved_url, page_html = web.fetch(expected["url"])
    (target / "page.html").write_text(page_html, encoding="utf-8")
    (target / "source.json").write_text(
        json.dumps({"input_url": expected["url"], "resolved_url": resolved_url, "source": "web"}), encoding="utf-8"
    )
    policy = load_policy()["web"]
    page = web.page_from_html(resolved_url, page_html)
    work = Path(tempfile.mkdtemp())
    saved = 0
    for url, _ in page.images[: policy["max_images"]]:
        destination = images / f"image-{saved + 1:02d}.jpg"
        if web.save_image(url, resolved_url, work, destination, policy["min_image_side"]) == "saved":
            saved += 1
    shutil.rmtree(work, ignore_errors=True)
    print(f"{expected['code']}: web, {len(page.text)} chars, {saved} images")


def fetch_xiaohongshu(expected: dict) -> None:
    target = LOCAL / expected["code"]
    target.mkdir(parents=True, exist_ok=True)
    resolved_url, page = extract_note.fetch_page(expected["url"])
    note = extract_note.note_from_page(resolved_url, page)
    (target / "page.html").write_text(page, encoding="utf-8")
    (target / "source.json").write_text(
        json.dumps({"input_url": expected["url"], "resolved_url": resolved_url, "source": "xiaohongshu"}), encoding="utf-8"
    )

    if note.note_type == "video":
        extract_note.download_first(note.video_urls, target / "video.mp4", resolved_url)
    else:
        images = target / "images"
        images.mkdir(exist_ok=True)
        for index, url in enumerate(note.image_urls, 1):
            extract_note.download(url, images / f"image-{index:02d}.jpg", resolved_url)
    size = sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
    print(f"{expected['code']}: {note.note_type}, {size // 1024} KB")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    codes = sys.argv[1:]
    failed = []
    for expected in load_expectations():
        if codes and expected["code"] not in codes:
            continue
        for attempt in (1, 2, 3):
            try:
                fetch(expected)
                break
            except Exception as error:  # network errors vary; retry, then move on to the next note
                print(f"{expected['code']}: attempt {attempt} failed: {error}")
        else:
            failed.append(expected["code"])
    if failed:
        print(f"Not cached: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
