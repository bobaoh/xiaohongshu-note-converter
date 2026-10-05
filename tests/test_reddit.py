"""Reddit posts (notekit.sources.reddit), using synthetic RSS feeds."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.error import HTTPError

import pytest
from conftest import (
    RECIPE_COMMENTS,
    SYNTHETIC,
    reddit_comment_entry,
    reddit_feed,
    reddit_permalink,
    reddit_post_entry,
)

from notekit import default_output_dir, net, pipeline, source_for
from notekit.sources import reddit

GIF = "https://i.redd.it/testgif001.gif"
IMAGE = "https://i.redd.it/testimg001.jpeg"
PREVIEW = "https://preview.redd.it/testimg001.jpeg?width=640&crop=smart&s=abc"


def recipe_feed(**post) -> bytes:
    post.setdefault("link", GIF)
    return reddit_feed(reddit_post_entry(**post), *(reddit_comment_entry(*comment) for comment in RECIPE_COMMENTS))


class FakeReddit:
    """Stands in for net.fetch: serves feeds and pages by URL and records the requests."""

    def __init__(self, pages: dict[str, tuple[str, bytes]], errors: dict[str, list[int]] | None = None):
        self.pages = pages
        self.errors = errors or {}
        self.requests: list[str] = []

    def __call__(self, url, user_agent=net.MOBILE_USER_AGENT, headers=None):
        self.requests.append(url)
        for prefix, codes in self.errors.items():
            if url.startswith(prefix) and codes:
                code = codes.pop(0)
                raise HTTPError(url, code, "error", {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "20"}, None)
        for prefix, (content_type, body) in self.pages.items():
            if url.startswith(prefix):
                return net.Response(url, content_type, body, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "30"})
        raise HTTPError(url, 404, "not found", {}, None)


def serve(monkeypatch, feed: bytes, post_id: str = "t3st01", **extra_pages) -> FakeReddit:
    pages = {f"https://www.reddit.com/comments/{post_id}/.rss": ("application/atom+xml; charset=UTF-8", feed)}
    pages.update(extra_pages)
    fake = FakeReddit(pages)
    monkeypatch.setattr(net, "fetch", fake)
    return fake


def extract(tmp_path: Path, url: str = None) -> tuple[dict, Path]:
    out = tmp_path / "out"
    metadata = pipeline.extract(url or reddit_permalink(), out)
    return metadata, out


# --- Links -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://www.reddit.com/r/GifRecipes/comments/1pokml7/peppercrusted_beef_tenderloin/", "1pokml7"),
        ("https://old.reddit.com/r/GifRecipes/comments/1pokml7/", "1pokml7"),
        ("https://reddit.com/r/GifRecipes/comments/1pokml7/slug/nufxw0p/?context=3", "1pokml7"),
        ("https://www.reddit.com/comments/1POKML7", "1pokml7"),
        ("https://redd.it/1pokml7", "1pokml7"),
        ("https://www.reddit.com/gallery/1wt8npu", "1wt8npu"),
        ("https://www.reddit.com/user/test_cook/comments/abc123/my_post/", "abc123"),
        ("https://www.reddit.com/r/Cooking/s/AbCdEf123", "s-AbCdEf123"),
    ],
)
def test_reddit_links_are_routed_and_keyed_by_post_id(url, key):
    assert source_for(url).name == "reddit"
    assert default_output_dir(url) == Path("output/reddit") / key


@pytest.mark.parametrize(
    "url",
    ["https://notreddit.com/r/x/comments/abc/", "https://i.redd.it/testimg001.jpeg", "https://v.redd.it/abc123"],
)
def test_other_hosts_are_not_reddit_posts(url):
    """Direct media links have no post (v.redd.it redirects to a video page, not the post)."""
    assert source_for(url).name == "web"


@pytest.mark.parametrize("url", ["https://www.reddit.com/r/Cooking/", "https://www.reddit.com/r/Cooking/top/?t=week", "https://www.reddit.com/"])
def test_subreddit_links_explain_how_to_collect_posts(url):
    with pytest.raises(ValueError, match="discover.py"):
        default_output_dir(url)


def test_extract_cli_rejects_a_subreddit_link_without_fetching(monkeypatch, capsys):
    monkeypatch.setattr(net, "fetch", lambda *a, **k: pytest.fail("must not fetch"))
    assert pipeline.main(["https://www.reddit.com/r/Cooking/"]) == 2
    assert "Not a link to a Reddit post" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("link", "kind"),
    [
        ("", "text"),
        (reddit_permalink(), "text"),
        ("https://i.redd.it/abc.jpeg", "image"),
        ("https://i.imgur.com/abc.png", "image"),
        ("https://i.redd.it/abc.gif", "gif"),
        ("https://i.imgur.com/abc.gifv", "gif"),
        ("https://v.redd.it/abc123", "video"),
        ("https://www.reddit.com/gallery/t3st01", "gallery"),
        ("https://www.reddit.com/r/Other/comments/zzz999/original/", "crosspost"),
        ("https://food.example.com/dumplings", "link"),
        ("https://food.example.com/dumplings.gif", "link"),  # only image hosts serve GIF posts
    ],
)
def test_post_kind(link, kind):
    assert reddit.post_kind(link, "t3st01") == kind


def test_note_id_is_24_hex_and_stable():
    assert reddit.note_id_for("t3st01") == reddit.note_id_for("t3st01")
    assert len(reddit.note_id_for("t3st01")) == 24 and int(reddit.note_id_for("t3st01"), 16) >= 0
    assert reddit.note_id_for("t3st01") != reddit.note_id_for("t3st02")


# --- Parsing -----------------------------------------------------------------------------


def test_html_to_text_keeps_paragraphs_lists_and_link_targets():
    text = reddit.html_to_text(
        '<p>Mix &amp; rest.</p> <ul> <li>200g flour</li> <li>salt</li> </ul> '
        '<p>From <a href="https://food.example.com/x">this site</a>, see <a href="/r/x/wiki">wiki</a> '
        'or <a href="https://a.example.com/y">https://a.example.com/y</a>.</p>'
    )
    assert text == (
        "Mix & rest.\n\n- 200g flour\n- salt\n\n"
        "From this site (https://food.example.com/x), see wiki or https://a.example.com/y."
    )


def test_post_feed_gives_the_post_and_its_comments_in_order():
    post = reddit.post_from_feed(recipe_feed(thumbnail="https://preview.redd.it/testgif001.gif?width=640&crop=smart&s=x"))

    assert (post.post_id, post.subreddit, post.author) == ("t3st01", "TestKitchen", "test_cook")
    assert post.title == "Test dumplings & dipping sauce"
    assert post.published_at == "2026-09-30"
    assert post.link == GIF and post.kind == "gif"
    assert post.thumbnail == "https://preview.redd.it/testgif001.gif?width=640&crop=smart&s=x", "escaped twice in the feed"
    assert [c.comment_id for c in post.comments] == [c[0] for c in RECIPE_COMMENTS]
    assert [c.is_op for c in post.comments] == [False, True, False, False, True, False]
    assert "- 200g flour" in post.comments[1].text
    assert post.score is None and post.num_comments is None, "RSS has no scores"


def test_text_post_body_and_its_images():
    feed = reddit_feed(reddit_post_entry(text_html=f'<p>My notes:</p> <p><a href="{PREVIEW.replace("&", "&amp;")}">{PREVIEW.replace("&", "&amp;")}</a></p>'))
    post = reddit.post_from_feed(feed)
    assert post.kind == "text"
    assert post.text.startswith("My notes:")
    assert post.text_images == [PREVIEW]


def test_a_feed_without_the_post_is_reported():
    subreddit_result = reddit_feed('<entry><id>t5_2rh1w</id><title>Dumplings!</title></entry>')
    with pytest.raises(RuntimeError, match="not found"):
        reddit.post_from_feed(subreddit_result)
    with pytest.raises(RuntimeError, match="readable feed"):
        reddit.post_from_feed(b"<html>blocked</html")


def test_listing_keeps_only_posts_in_rank_order():
    feed = reddit_feed(
        reddit_post_entry("p1", link=GIF), reddit_comment_entry("c1", "x", "<p>hi</p>"), reddit_post_entry("p2", link=IMAGE)
    )
    assert [(p.post_id, p.kind) for p in reddit.posts_from_listing(feed)] == [("p1", "gif"), ("p2", "image")]


def test_select_comments_keeps_every_op_comment_and_limits_the_rest():
    post = reddit.post_from_feed(recipe_feed())
    kept = reddit.select_comments(post, limit=1, skip_authors=["automoderator"])
    assert [c.comment_id for c in kept] == ["op0001", "rdr001", "op0002"]


# --- RSS client --------------------------------------------------------------------------


def test_client_waits_as_reddit_asks_between_requests(monkeypatch, no_reddit_waits):
    feed = recipe_feed()
    serve(monkeypatch, feed)
    client = reddit.RssClient()
    client.post("t3st01")
    client.post("t3st01")
    assert no_reddit_waits == [31.0], "remaining 0 with reset 30 means waiting 31 s before the next request"


def test_client_retries_after_429(monkeypatch, no_reddit_waits):
    fake = FakeReddit({"https://www.reddit.com/comments/": ("application/atom+xml", recipe_feed())},
                      errors={"https://www.reddit.com/comments/": [429, 429]})
    monkeypatch.setattr(net, "fetch", fake)
    assert reddit.RssClient().post("t3st01").post_id == "t3st01"
    assert len(fake.requests) == 3
    assert no_reddit_waits == [21.0, 21.0]


def test_client_gives_up_after_repeated_429(monkeypatch):
    fake = FakeReddit({}, errors={"https://www.reddit.com/": [429] * 10})
    monkeypatch.setattr(net, "fetch", fake)
    with pytest.raises(RuntimeError, match="rate limit"):
        reddit.RssClient(max_attempts=3).post("t3st01")
    assert len(fake.requests) == 3


def test_client_does_not_retry_or_work_around_403(monkeypatch):
    fake = FakeReddit({}, errors={"https://www.reddit.com/": [403, 403]})
    monkeypatch.setattr(net, "fetch", fake)
    with pytest.raises(RuntimeError, match="403.*does not work around"):
        reddit.RssClient().post("t3st01")
    assert len(fake.requests) == 1


def test_a_long_pause_keeps_the_feed_but_stops_the_next_request(monkeypatch):
    feed = recipe_feed()
    monkeypatch.setattr(net, "fetch", lambda *a, **k: net.Response(
        "u", "application/atom+xml", feed, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "600"}))
    client = reddit.RssClient(reddit.RateLimiter(max_wait=60, clock=lambda: 0.0, sleep=lambda s: pytest.fail("slept")))
    assert client.post("t3st01").post_id == "t3st01", "the response already arrived; it must not be thrown away"
    with pytest.raises(RuntimeError, match="wait 601 seconds"):
        client.post("t3st01")


def test_a_login_or_block_page_is_not_parsed_as_a_feed(monkeypatch):
    monkeypatch.setattr(net, "fetch", FakeReddit({"https://www.reddit.com/": ("text/html", b"<html>blocked</html>")}))
    with pytest.raises(RuntimeError, match="web page instead of the feed"):
        reddit.RssClient().post("t3st01")


def test_listing_and_search_urls(monkeypatch):
    fake = FakeReddit({"https://www.reddit.com/": ("application/atom+xml", reddit_feed())})
    monkeypatch.setattr(net, "fetch", fake)
    client = reddit.RssClient()
    client.listing("GifRecipes", "top", "week", 10)
    client.listing("GifRecipes", "hot", "week", 10)
    client.search("dumplings", "Cooking", "top", "month", 5)
    client.search("dumplings", None, "new", "day", 5)
    assert fake.requests == [
        "https://www.reddit.com/r/GifRecipes/top/.rss?limit=10&t=week",
        "https://www.reddit.com/r/GifRecipes/hot/.rss?limit=10",
        "https://www.reddit.com/r/Cooking/search.rss?q=dumplings&sort=top&t=month&limit=5&type=link&restrict_sr=1",
        "https://www.reddit.com/search.rss?q=dumplings&sort=new&t=day&limit=5&type=link",
    ]
    with pytest.raises(ValueError):
        client.listing("GifRecipes", "best")


# --- Extraction (offline) ----------------------------------------------------------------


def test_text_post_extraction(tmp_path, monkeypatch):
    feed = reddit_feed(
        reddit_post_entry(text_html="<p>How do I keep dumplings from sticking?</p>"),
        reddit_comment_entry("rdr001", "reader_one", "<p>Use parchment.</p>"),
        reddit_comment_entry("op0001", "test_cook", "<p>Thanks, that worked.</p>"),
    )
    serve(monkeypatch, feed)
    metadata, out = extract(tmp_path)

    assert metadata["status"] == "complete", metadata.get("error")
    assert metadata["source"] == "reddit"
    assert metadata["note_type"] == "post" and metadata["post_kind"] == "text"
    assert metadata["note_id"] == reddit.note_id_for("t3st01")
    assert metadata["author"] == "u/test_cook" and metadata["subreddit"] == "TestKitchen"
    assert metadata["published_at"] == "2026-09-30"
    assert (metadata["comments_read"], metadata["comments_kept"], metadata["op_comments"]) == (2, 2, 1)
    caption = (out / "caption.txt").read_text(encoding="utf-8")
    assert caption.startswith("标题：Test dumplings & dipping sauce\n作者：u/test_cook\n版块：r/TestKitchen")
    assert "正文：\nHow do I keep dumplings from sticking?" in caption
    comments = (out / "comments.txt").read_text(encoding="utf-8")
    assert "[rdr001] u/reader_one：\nUse parchment." in comments
    assert "[op0001] u/test_cook [楼主]：" in comments
    assert (out / "ocr.txt").read_text(encoding="utf-8") == "" and (out / "transcript.txt").read_text(encoding="utf-8") == ""
    assert metadata["cost"]["ai_input"]["text_tokens_estimate"] > 0
    assert metadata["cost"]["predicted"]["seconds"] == 0


def test_comments_count_toward_the_ai_text_estimate(tmp_path, monkeypatch):
    serve(monkeypatch, recipe_feed(link=reddit_permalink(), text_html="<p>Short.</p>"))
    metadata, out = extract(tmp_path)
    caption_only = pipeline.cost.estimate_tokens((out / "caption.txt").read_text(encoding="utf-8"))
    assert metadata["cost"]["ai_input"]["text_tokens_estimate"] > caption_only


def test_the_post_is_fetched_once_with_an_honest_user_agent(tmp_path, monkeypatch):
    agents = []
    fake = FakeReddit({"https://www.reddit.com/comments/t3st01/.rss": ("application/atom+xml", recipe_feed(link=reddit_permalink()))})
    monkeypatch.setattr(net, "fetch", lambda url, user_agent=None, headers=None: agents.append(user_agent) or fake(url))
    metadata, _ = extract(tmp_path)
    assert metadata["status"] == "complete"
    assert agents == [reddit.USER_AGENT] and "Mozilla" not in reddit.USER_AGENT


def test_link_post_reads_the_linked_page(tmp_path, monkeypatch):
    from test_web import article_page

    article = "https://food.example.com/recipes/fanqie"
    serve(monkeypatch, recipe_feed(link=article), **{article: ("text/html; charset=utf-8", article_page().encode("utf-8"))})
    metadata, out = extract(tmp_path)

    assert metadata["status"] == "complete", metadata.get("error")
    assert metadata["post_kind"] == "link" and metadata["link"] == article
    assert metadata["linked_page"]["status"] == "read"
    assert metadata["linked_page"]["structured_types"] == ["Recipe"]
    caption = (out / "caption.txt").read_text(encoding="utf-8")
    assert f"帖子指向：{article}" in caption
    assert "外部网页" in caption and "番茄炒出汁后倒回鸡蛋" in caption
    assert "网页结构化数据" in caption
    assert json.loads((out / "structured.json").read_text(encoding="utf-8"))[0]["name"] == "家常番茄炒蛋"


def test_a_linked_page_that_fails_does_not_fail_the_post(tmp_path, monkeypatch):
    serve(monkeypatch, recipe_feed(link="https://gone.example.com/x"))
    metadata, _ = extract(tmp_path)
    assert metadata["status"] == "complete"
    assert metadata["linked_page"]["status"] == "failed"


def test_linked_videos_and_disabled_following_are_recorded(tmp_path, monkeypatch):
    serve(monkeypatch, recipe_feed(link="https://www.youtube.com/watch?v=abc"))
    metadata, _ = extract(tmp_path)
    assert metadata["linked_page"]["status"] == "skipped"
    assert metadata["unprocessed_media"] == ["https://www.youtube.com/watch?v=abc"]

    monkeypatch.setenv("NOTE_COST_POLICY", str(write_policy(tmp_path, "follow_links = false")))
    serve(monkeypatch, recipe_feed(link="https://food.example.com/x"))
    metadata, _ = extract(tmp_path)
    assert metadata["linked_page"]["status"].startswith("not followed")


def write_policy(tmp_path: Path, reddit_lines: str) -> Path:
    path = tmp_path / "policy.toml"
    path.write_text(f"[reddit]\n{reddit_lines}\n", encoding="utf-8")
    return path


def test_max_comments_comes_from_the_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTE_COST_POLICY", str(write_policy(tmp_path, "max_comments = 0")))
    serve(monkeypatch, recipe_feed(link=reddit_permalink()))
    metadata, out = extract(tmp_path)
    assert metadata["comments_kept"] == metadata["op_comments"] == 2
    assert "reader_one" not in (out / "comments.txt").read_text(encoding="utf-8")


def test_crosspost_and_removed_text_are_flagged(tmp_path, monkeypatch):
    serve(monkeypatch, recipe_feed(link="https://www.reddit.com/r/Other/comments/zzz999/original/", text_html="<p>[removed]</p>"))
    metadata, out = extract(tmp_path)
    assert metadata["post_kind"] == "crosspost"
    assert "crosspost" in metadata["content_warning"] and "removed" in metadata["content_warning"]
    assert "正文" not in (out / "caption.txt").read_text(encoding="utf-8")


def test_share_links_are_resolved_first(tmp_path, monkeypatch):
    serve(monkeypatch, recipe_feed(link=reddit_permalink()))
    monkeypatch.setattr(net, "redirect_target", lambda url, user_agent: reddit_permalink() + "?share_id=x")
    metadata, _ = extract(tmp_path, "https://www.reddit.com/r/TestKitchen/s/AbCdEf123")
    assert metadata["status"] == "complete" and metadata["post_id"] == "t3st01"


def test_share_link_to_something_else_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(net, "redirect_target", lambda url, user_agent: "https://www.reddit.com/login/")
    metadata, _ = extract(tmp_path, "https://www.reddit.com/r/TestKitchen/s/AbCdEf123")
    assert metadata["status"] == "failed" and "copy the post's own link" in metadata["error"]


def test_blocked_requests_fail_with_the_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(net, "fetch", FakeReddit({}, errors={"https://www.reddit.com/": [403]}))
    metadata, _ = extract(tmp_path)
    assert metadata["status"] == "failed" and "HTTP 403" in metadata["error"]


# --- Extraction with media (FFmpeg, OCR, Whisper tiny) ----------------------------------


def fake_downloads(monkeypatch, files: dict[str, Path | None]) -> list[str]:
    """net.download serves local files by URL; None makes that URL fail."""
    requested = []

    def download(url, destination, referer, user_agent=net.USER_AGENT):
        requested.append(url)
        source = files.get(url)
        if source is None:
            raise RuntimeError("HTTP Error 403")
        shutil.copyfile(source, destination)

    monkeypatch.setattr(net, "download", download)
    return requested


@pytest.mark.media
@pytest.mark.usefixtures("require_ffmpeg")
def test_image_post_falls_back_to_the_preview(tmp_path, monkeypatch):
    serve(monkeypatch, recipe_feed(link=IMAGE, thumbnail=PREVIEW))
    requested = fake_downloads(monkeypatch, {IMAGE: None, PREVIEW: SYNTHETIC / "card-01.jpg"})
    metadata, out = extract(tmp_path)

    assert metadata["status"] == "complete", metadata.get("error")
    assert requested == [IMAGE, PREVIEW]
    assert metadata["image_count"] == 1 and metadata["images_failed"] == 0
    assert "奶油奶酪135g" in (out / "ocr.txt").read_text(encoding="utf-8").replace(" ", "")
    assert metadata["cost"]["predicted"]["ocr_items"] == 1


@pytest.mark.media
@pytest.mark.usefixtures("require_ffmpeg")
def test_gallery_post_reads_the_first_preview_and_says_so(tmp_path, monkeypatch):
    serve(monkeypatch, recipe_feed(link="https://www.reddit.com/gallery/t3st01", thumbnail=PREVIEW))
    fake_downloads(monkeypatch, {PREVIEW: SYNTHETIC / "card-02.jpg"})
    metadata, _ = extract(tmp_path)
    assert metadata["post_kind"] == "gallery" and metadata["image_count"] == 1
    assert "gallery" in metadata["content_warning"]
    assert metadata["unprocessed_media"] == ["https://www.reddit.com/gallery/t3st01"]


@pytest.mark.media
@pytest.mark.usefixtures("require_ffmpeg")
def test_gif_post_is_read_like_a_silent_video(tmp_path, monkeypatch):
    gif = tmp_path / "clip.gif"
    from notekit import media

    media.run_ffmpeg(["-y", "-i", str(SYNTHETIC / "silent.mp4"), "-vf", "fps=4,scale=720:-1", str(gif)])
    serve(monkeypatch, recipe_feed(link=GIF))
    fake_downloads(monkeypatch, {GIF: gif})
    metadata, out = extract(tmp_path)

    assert metadata["status"] == "complete", metadata.get("error")
    assert metadata["note_type"] == "video" and metadata["post_kind"] == "gif"
    assert metadata["video"]["has_audio"] is False
    assert metadata["transcription"]["status"] == "skipped"
    assert "LivePhoto" in (out / "ocr.txt").read_text(encoding="utf-8").replace(" ", "")
    assert metadata["cost"]["predicted"]["video_seconds"] > 0
    assert "Steam for 8 minutes." in (out / "comments.txt").read_text(encoding="utf-8")


@pytest.mark.media
@pytest.mark.usefixtures("require_ffmpeg")
def test_reddit_video_is_saved_from_its_hls_playlist(tmp_path, monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL", "tiny")
    serve(monkeypatch, recipe_feed(link="https://v.redd.it/testvid001"))
    playlists = []

    def download_hls(url, destination, user_agent):
        playlists.append((url, user_agent))
        shutil.copyfile(SYNTHETIC / "speech.mp4", destination)

    monkeypatch.setattr(net, "download_hls", download_hls)
    metadata, out = extract(tmp_path)

    assert metadata["status"] == "complete", metadata.get("error")
    assert playlists == [("https://v.redd.it/testvid001/HLSPlaylist.m3u8", reddit.USER_AGENT)]
    assert metadata["note_type"] == "video" and metadata["video"]["has_audio"] is True
    assert "微波" in (out / "transcript.txt").read_text(encoding="utf-8")
