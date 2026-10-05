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
from notekit import net, source_for  # noqa: E402
from notekit.cost import load_policy  # noqa: E402
from notekit.sources import reddit, web  # noqa: E402
from regression import load_expectations  # noqa: E402

LOCAL = Path(__file__).resolve().parent / "local"


def fetch(expected: dict) -> None:
    source = source_for(expected["url"]).name
    if source == "web":
        fetch_web(expected)
    elif source == "reddit":
        fetch_reddit(expected)
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


def fetch_reddit(expected: dict) -> None:
    """Cache the post feed and the media the Reddit source would read."""
    target = LOCAL / expected["code"]
    target.mkdir(parents=True, exist_ok=True)
    policy = load_policy()
    client = reddit.make_client(policy)
    feed = client.get_feed(reddit.post_feed_url(reddit.post_id_from_url(expected["url"])))
    post = reddit.post_from_feed(feed)
    (target / "feed.xml").write_bytes(feed)
    (target / "source.json").write_text(
        json.dumps({"input_url": expected["url"], "resolved_url": post.permalink, "source": "reddit"}), encoding="utf-8"
    )
    if post.kind in ("gif", "video"):
        how, url = reddit.video_url(post)
        if how == "hls":
            net.download_hls(url, target / "video.mp4", reddit.USER_AGENT)
        else:
            net.download(url, target / f"video{Path(url).suffix}", post.permalink, user_agent=reddit.USER_AGENT)
    else:
        images = target / "images"
        images.mkdir(exist_ok=True)
        work = Path(tempfile.mkdtemp())
        saved = 0
        for urls in reddit.image_candidates(post, policy["reddit"]["max_images"]):
            destination = images / f"image-{saved + 1:02d}.jpg"
            for url in urls:
                outcome = web.save_image(url, post.permalink, work, destination, policy["reddit"]["min_image_side"],
                                         user_agent=reddit.USER_AGENT)
                if outcome != "failed":
                    break
            saved += outcome == "saved"
        shutil.rmtree(work, ignore_errors=True)
    size = sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
    print(f"{expected['code']}: reddit {post.kind}, {len(post.comments)} comments, {size // 1024} KB")


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
