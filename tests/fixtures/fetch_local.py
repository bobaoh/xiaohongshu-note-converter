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

import extract_note  # noqa: E402
from regression import load_expectations  # noqa: E402

LOCAL = Path(__file__).resolve().parent / "local"


def fetch(expected: dict) -> None:
    target = LOCAL / expected["code"]
    target.mkdir(parents=True, exist_ok=True)
    resolved_url, page = extract_note.fetch_page(expected["url"])
    note = extract_note.note_from_page(resolved_url, page)
    (target / "page.html").write_text(page, encoding="utf-8")
    (target / "source.json").write_text(json.dumps({"input_url": expected["url"], "resolved_url": resolved_url}), encoding="utf-8")

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
