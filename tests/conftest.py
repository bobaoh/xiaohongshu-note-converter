from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic"
LOCAL = FIXTURES / "local"

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))


def _refresh_windows_path() -> None:
    """Pick up FFmpeg installed by winget in shells that started before the installation."""
    if os.name != "nt" or shutil.which("ffmpeg"):
        return
    import winreg

    paths = []
    for hive, key in (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ):
        try:
            with winreg.OpenKey(hive, key) as handle:
                paths.append(os.path.expandvars(winreg.QueryValueEx(handle, "Path")[0]))
        except OSError:
            continue
    os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), *paths])


_refresh_windows_path()


@pytest.fixture(autouse=True)
def isolated_cost_ledger(tmp_path, monkeypatch):
    """Tests must never write to the real ledger in logs/."""
    ledger = tmp_path / "conversions.jsonl"
    monkeypatch.setenv("NOTE_COST_LEDGER", str(ledger))
    monkeypatch.setenv("NOTE_COST_CONTEXT", "test")
    return ledger


@pytest.fixture
def require_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("FFmpeg/ffprobe is not installed")


# --- Synthetic note pages -------------------------------------------------------------
# These mirror the structure of real Xiaohongshu pages with invented IDs, URLs, and names.
# Real pages escape "/" as /, double-escape it inside the JSON-in-JSON mediaV2 field,
# and contain bare `undefined` values; the builder reproduces all three.

NOTE_URL = "https://www.xiaohongshu.com/discovery/item/{note_id}?type={type}&xsec_token=TEST"
CDN = "http://sns-webpic-qc.xhscdn.com/202601010000/abc/notes_pre_post/{file}!h5_1080jpg"
VIDEO_CDN = "http://sns-video-zl.xhscdn.com/stream/1/110/{stream}/{file}_{stream}.mp4?sign=TEST&t=1"
LIVE_CDN = "http://sns-video-zl.xhscdn.com/stream/1/10/19/{file}_19.mp4?sign=TEST&t=1"


def image_entry(file: str, live: bool = False) -> dict:
    entry = {
        "fileId": f"notes_pre_post/{file}",
        "width": 1080,
        "height": 1440,
        "url": CDN.format(file=file),
        "infoList": [
            {"imageScene": "WB_PRV", "url": CDN.format(file=file) + "_prv"},
            {"imageScene": "WB_DFT", "url": CDN.format(file=file)},
        ],
        "livePhoto": live,
        "stream": {},
    }
    if live:
        entry["stream"] = {
            "h264": [{"masterUrl": LIVE_CDN.format(file=file), "backupUrls": [], "audioCodec": "", "audioChannels": 0}],
            "h265": [],
        }
    return entry


def video_stream(stream: int, file: str, codec: str) -> dict:
    return {
        "streamType": stream,
        "videoCodec": codec,
        "audioCodec": "aac",
        "audioChannels": 2,
        "masterUrl": VIDEO_CDN.format(stream=stream, file=file),
        "backupUrls": [VIDEO_CDN.format(stream=stream, file=file).replace("sns-video-zl", "sns-bak-v10")],
    }


def image_note_data(**overrides: object) -> dict:
    data = {
        "noteId": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "type": "normal",
        "title": "做3个焙茶团子",
        "desc": "Q糯不粘牙[大笑R]\n\t\n配方：\n糯米粉 32g\n\t\n#焙茶团子[话题]# #团子[话题]#",
        "time": 1790000000000,
        "user": {"userId": "uuuuuuuuuuuuuuuuuuuuuuuu", "nickName": "测试作者", "avatar": "http://example.invalid/a.jpg"},
        "tagList": [{"name": "焙茶团子"}, {"name": "团子"}],
        "imageList": [image_entry("img01"), image_entry("img02", live=True), image_entry("img03")],
        "extraField": "UNDEFINED_PLACEHOLDER",
    }
    data.update(overrides)
    return data


def video_note_data(**overrides: object) -> dict:
    # H.265 is listed first on purpose: the extractor must still prefer H.264 with audio.
    streams = {"h265": [video_stream(520, "vid01", "hevc")], "h264": [video_stream(259, "vid01", "h264")], "av1": []}
    media_v2 = {"video_id": "1", "stream": {"h264": [{"master_url": VIDEO_CDN.format(stream=259, file="vid01"), "audio_codec": "aac"}]}}
    data = {
        "noteId": "bbbbbbbbbbbbbbbbbbbbbbbb",
        "type": "video",
        "title": "微波炉2分钟糯米皮",
        "desc": "放三天都软糯",
        "time": 1790000000000,
        "user": {"userId": "vvvvvvvvvvvvvvvvvvvvvvvv", "nickName": "视频作者"},
        "tagList": [],
        "imageList": [image_entry("cover")],
        "video": {
            "media": {"videoId": 1, "stream": streams},
            # Real pages store mediaV2 as a JSON string, so its URLs end up double-escaped.
            "mediaV2": json.dumps(media_v2).replace("/", "\\u002F"),
        },
    }
    data.update(overrides)
    return data


def make_page(note_data: dict | None) -> str:
    """Render note data the way the mobile page embeds it in window.__INITIAL_STATE__."""
    if note_data is None:
        return "<html><body><p>没有内嵌数据的页面</p></body></html>"
    state = {"global": {}, "noteData": {"data": {"noteData": note_data}}, "UseAbExpStore": {}}
    raw = json.dumps(state, ensure_ascii=False).replace("/", "\\u002F")
    raw = raw.replace('"UNDEFINED_PLACEHOLDER"', "undefined")
    return f"<html><head></head><body><script>window.__INITIAL_STATE__={raw}</script></body></html>"


def note_url(data: dict) -> str:
    return NOTE_URL.format(note_id=data["noteId"], type=data["type"])


# --- Synthetic Reddit feeds ------------------------------------------------------------
# These mirror Reddit's RSS (Atom) feeds with invented IDs, names, and text. In real feeds the
# entry content is HTML escaped into XML, and the HTML itself escapes "&" in URLs, so links are
# escaped twice; the post text and comments sit between <!-- SC_OFF --> and <!-- SC_ON -->.

REDDIT = "https://www.reddit.com"


def reddit_permalink(post_id: str = "t3st01", subreddit: str = "TestKitchen") -> str:
    return f"{REDDIT}/r/{subreddit}/comments/{post_id}/a_test_post/"


def reddit_post_entry(
    post_id: str = "t3st01",
    subreddit: str = "TestKitchen",
    title: str = "Test dumplings & dipping sauce",
    author: str = "test_cook",
    link: str | None = None,
    text_html: str = "",
    thumbnail: str = "",
    published: str = "2026-09-30T08:00:00+00:00",
) -> str:
    import html

    permalink = reddit_permalink(post_id, subreddit)
    link = link or permalink
    body = f'<!-- SC_OFF --><div class="md">{text_html}</div><!-- SC_ON --> ' if text_html else ""
    byline = (
        f'&#32; submitted by &#32; <a href="{REDDIT}/user/{author}"> /u/{author} </a> <br/> '
        f'<span><a href="{html.escape(link)}">[link]</a></span> &#32; <span><a href="{permalink}">[comments]</a></span>'
    )
    if thumbnail:
        content = (
            f'<table> <tr><td> <a href="{permalink}"> <img src="{html.escape(thumbnail)}" alt="{html.escape(title)}" /> </a> '
            f"</td><td> {body}{byline} </td></tr></table>"
        )
        media = f'<media:thumbnail url="{html.escape(thumbnail)}" />'
    else:
        content, media = body + byline, ""
    return (
        f"<entry><author><name>/u/{author}</name><uri>{REDDIT}/user/{author}</uri></author>"
        f'<category term="{subreddit}" label="r/{subreddit}"/><content type="html">{html.escape(content)}</content>'
        f'<id>t3_{post_id}</id>{media}<link href="{permalink}" /><updated>{published}</updated>'
        f"<published>{published}</published><title>{html.escape(title)}</title></entry>"
    )


def reddit_comment_entry(comment_id: str, author: str, text_html: str, post_id: str = "t3st01", subreddit: str = "TestKitchen") -> str:
    import html

    content = f'<!-- SC_OFF --><div class="md">{text_html}</div><!-- SC_ON -->'
    return (
        f"<entry><author><name>/u/{author}</name><uri>{REDDIT}/user/{author}</uri></author>"
        f'<category term="{subreddit}" label="r/{subreddit}"/><content type="html">{html.escape(content)}</content>'
        f'<id>t1_{comment_id}</id><link href="{reddit_permalink(post_id, subreddit)}{comment_id}/" />'
        f"<updated>2026-09-30T09:00:00+00:00</updated><title>/u/{author} on a test post</title></entry>"
    )


def reddit_feed(*entries: str, subreddit: str = "TestKitchen") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:media="http://search.yahoo.com/mrss/">'
        f'<category term="{subreddit}" label="r/{subreddit}"/><updated>2026-10-01T00:00:00+00:00</updated>'
        f"<id>/r/{subreddit}/.rss</id><title>{subreddit}</title>{''.join(entries)}</feed>"
    ).encode("utf-8")


#: A GifRecipes-style post: a GIF, a pinned bot comment, the recipe in the poster's comment,
#: a deleted comment, and replies.
RECIPE_COMMENTS = [
    ("bot001", "AutoModerator", "<p>Please post your recipe in reply to me.</p>"),
    ("op0001", "test_cook", '<p>Source: <a href="https://food.example.com/dumplings">Example Food</a></p> '
                            "<ul> <li>200g flour</li> <li>100ml water</li> </ul> <p>Steam for 8 minutes.</p>"),
    ("del001", "[deleted]", "<p>[deleted]</p>"),
    ("rdr001", "reader_one", "<p>Can I freeze these?</p>"),
    ("op0002", "test_cook", "<p>Yes, freeze them &amp; steam from frozen for 12 minutes.</p>"),
    ("rdr002", "reader_two", '<p>See <a href="/r/TestKitchen/wiki">the wiki</a>.</p>'),
]


@pytest.fixture(autouse=True)
def no_reddit_waits(monkeypatch):
    """Reddit's rate limiter must never sleep in tests; the waits it asked for are recorded."""
    from notekit.sources import reddit

    waits: list[float] = []
    clock = [0.0]

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(reddit, "LIMITER", reddit.RateLimiter(clock=lambda: clock[0], sleep=sleep))
    return waits
