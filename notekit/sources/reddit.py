"""Reddit posts: text, image, GIF, video, gallery, and link posts, with their comments.

Reddit blocks scripts from its JSON endpoints and web pages unless they sign in to the official
API. Its public RSS (Atom) feeds stay open, so ``RssClient`` reads those and identifies itself
with ``USER_AGENT``. The feeds are heavily rate-limited (often one request per 10-60 seconds):
the client waits as long as Reddit's ``x-ratelimit-reset`` header says and retries after HTTP
429. It does not work around a 403 or any other block.

One post feed (``/comments/<id>/.rss``) gives the title, author, subreddit, time, the post text
(as HTML), what the post links to (an i.redd.it image or GIF, a v.redd.it video, a gallery, or an
outside page), a preview image, and about 40 comments in Reddit's default order, each reply right
after the comment it answers. It does not give scores, comment counts, comment nesting, or the
images of a gallery after the first one.

Media: images are OCR'd. GIFs and v.redd.it videos (an HLS stream, saved with FFmpeg) go through
the same video analysis as Xiaohongshu videos. For link posts, the linked page's main text is read
with the web source (``[reddit] follow_links``); its images are not.

Output: ``output/reddit/<post id>/``. Comments go to ``comments.txt``, apart from the post in
``caption.txt``. ``note_id`` is the first 24 hex digits of the SHA-1 of ``reddit:<post id>``.

Official API: ``make_client`` is the one place that picks a client. A client for Reddit's OAuth
API (scores, every gallery image, more comments) only has to implement ``RedditClient``; this
source and scripts/discover.py would work unchanged. See docs/reddit.md.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse

from .. import cost, media, net
from . import Job, Source, web

#: Reddit asks scripts to identify themselves instead of posing as a browser.
USER_AGENT = "python:notekit:0.1 (personal note converter)"
BASE_URL = "https://www.reddit.com"
SORTS = ("hot", "new", "top", "rising", "controversial")
TIMES = ("hour", "day", "week", "month", "year", "all")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
IMAGE_HOSTS = ("i.redd.it", "preview.redd.it", "i.imgur.com")
NO_SPEECH = "this Reddit post has no video"
GONE_TEXTS = ("[deleted]", "[removed]")
NOT_A_POST = "Not a link to a Reddit post: {url}. To collect posts from a subreddit, run scripts/discover.py."

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA_RSS = "{http://search.yahoo.com/mrss/}"


@dataclass
class Comment:
    comment_id: str
    author: str
    text: str
    is_op: bool = False


@dataclass
class Post:
    post_id: str
    subreddit: str
    title: str
    author: str
    permalink: str
    published_at: str | None = None
    #: The post's own text, as plain text with links written out.
    text: str = ""
    #: What the post points to: an image, GIF, video, gallery, or outside page; for text posts,
    #: the post itself.
    link: str = ""
    thumbnail: str = ""
    #: Images linked inside the post text.
    text_images: list[str] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    #: Not in RSS; an API client fills these.
    score: int | None = None
    num_comments: int | None = None

    @property
    def kind(self) -> str:
        return post_kind(self.link, self.post_id)


class RedditClient(Protocol):
    """What the source and discovery need from Reddit."""

    name: str

    def post(self, post_id: str) -> Post:
        """One post with its comments."""

    def listing(self, subreddit: str, sort: str = "top", time: str = "day", limit: int = 25) -> list[Post]:
        """A subreddit's posts in the order Reddit ranks them (without comments)."""

    def search(
        self, query: str, subreddit: str | None = None, sort: str = "top", time: str = "week", limit: int = 25
    ) -> list[Post]:
        """Posts matching ``query``, in one subreddit or across Reddit (without comments)."""

    def resolve_share_link(self, url: str) -> str:
        """The post ID behind an app share link (``/r/<sub>/s/<code>``)."""


# --- Links --------------------------------------------------------------------------------


def is_reddit_host(host: str) -> bool:
    host = host.lower()
    return host == "reddit.com" or host.endswith(".reddit.com") or host == "redd.it"


def post_id_from_url(url: str) -> str | None:
    """The base-36 post ID in a post, comment, gallery, or redd.it short link."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    segments = [part for part in parsed.path.split("/") if part]
    if host == "redd.it" and segments:
        return segments[0].lower() if re.fullmatch(r"[0-9a-zA-Z]+", segments[0]) else None
    if not is_reddit_host(host):
        return None
    match = re.search(r"/(?:comments|gallery)/([0-9a-z]+)(?:/|$)", parsed.path, re.I)
    return match.group(1).lower() if match else None


def share_code(url: str) -> str | None:
    """The code of an app share link such as reddit.com/r/Cooking/s/AbC123."""
    match = re.match(r"^/r/[^/]+/s/([0-9A-Za-z]+)", urlparse(url).path)
    return match.group(1) if match and is_reddit_host(urlparse(url).hostname or "") else None


def post_feed_url(post_id: str) -> str:
    return f"{BASE_URL}/comments/{post_id}/.rss"


def note_id_for(post_id: str) -> str:
    return hashlib.sha1(f"reddit:{post_id}".encode("utf-8")).hexdigest()[:24]


def post_kind(link: str, post_id: str = "") -> str:
    """text, image, gif, video, gallery, crosspost, or link (an outside page)."""
    parsed = urlparse(link)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if not link:
        return "text"
    if host == "v.redd.it":
        return "video"
    if is_reddit_host(host):
        if "/gallery/" in path:
            return "gallery"
        linked = post_id_from_url(link)
        return "crosspost" if linked and post_id and linked != post_id else "text"
    if host in IMAGE_HOSTS and path.endswith((".gif", ".gifv")):
        return "gif"
    if path.endswith(IMAGE_EXTENSIONS):
        return "image"
    return "link"


# --- Feed parsing -------------------------------------------------------------------------


class _TextParser(HTMLParser):
    """Reddit's rendered Markdown to plain text: paragraphs, list items, and link targets kept."""

    BLOCKS = {"p", "div", "ul", "ol", "blockquote", "pre", "table", "tr", "hr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCKS:
            self.parts.append("\n")
        elif tag == "a":
            self.links.append((dict(attrs).get("href") or "", len(self.parts)))

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.links:
            href, start = self.links.pop()
            label = "".join(self.parts[start:]).strip()
            if href.startswith("http") and label and label != href:
                self.parts.append(f" ({href})")
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(fragment: str) -> str:
    parser = _TextParser()
    parser.feed(fragment)
    parser.close()
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _markdown_html(content: str) -> str:
    """The rendered Markdown inside an entry: the post text or the comment."""
    match = re.search(r"<!-- SC_OFF -->(.*?)<!-- SC_ON -->", content, re.S)
    return match.group(1) if match else ""


def _linked_images(fragment: str) -> list[str]:
    images: list[str] = []
    for url in re.findall(r"<(?:a[^>]+href|img[^>]+src)=\"([^\"]+)\"", fragment):
        url = html.unescape(url)
        parsed = urlparse(url)
        if (parsed.hostname or "").lower() in IMAGE_HOSTS and parsed.path.lower().endswith(IMAGE_EXTENSIONS):
            if url not in images:
                images.append(url)
    return images


def _author(entry: ET.Element) -> str:
    name = (entry.findtext(f"{ATOM}author/{ATOM}name") or "").strip()
    return re.sub(r"^/?u/", "", name)


def _entries(feed_xml: bytes | str) -> list[ET.Element]:
    try:
        root = ET.fromstring(feed_xml)
    except ET.ParseError as error:
        raise RuntimeError(f"Reddit did not return a readable feed ({error}).") from error
    return root.findall(f"{ATOM}entry")


def post_from_entry(entry: ET.Element) -> Post:
    content = entry.findtext(f"{ATOM}content") or ""
    body = _markdown_html(content)
    link = re.search(r"<a href=\"([^\"]+)\">\[link\]</a>", content)
    thumbnail = entry.find(f"{MEDIA_RSS}thumbnail")
    image = re.search(r"<img src=\"([^\"]+)\"", content)
    category = entry.find(f"{ATOM}category")
    link_element = entry.find(f"{ATOM}link")
    permalink = (link_element.get("href") if link_element is not None else "") or ""
    published = entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated")
    return Post(
        post_id=(entry.findtext(f"{ATOM}id") or "").removeprefix("t3_"),
        subreddit=category.get("term", "") if category is not None else "",
        title=html.unescape(entry.findtext(f"{ATOM}title") or "").strip(),
        author=_author(entry),
        permalink=permalink,
        published_at=published[:10] if published else None,
        text=html_to_text(body),
        link=html.unescape(link.group(1)) if link else "",
        thumbnail=(thumbnail.get("url") if thumbnail is not None else "") or (html.unescape(image.group(1)) if image else ""),
        text_images=_linked_images(body),
    )


def post_from_feed(feed_xml: bytes | str) -> Post:
    """A post feed: the post first, then its comments in Reddit's default order."""
    entries = _entries(feed_xml)
    if not entries or not (entries[0].findtext(f"{ATOM}id") or "").startswith("t3_"):
        raise RuntimeError("The Reddit post was not found. It may have been deleted, or the subreddit may be private.")
    post = post_from_entry(entries[0])
    for entry in entries[1:]:
        comment_id = entry.findtext(f"{ATOM}id") or ""
        if not comment_id.startswith("t1_"):
            continue
        author = _author(entry)
        post.comments.append(
            Comment(
                comment_id=comment_id.removeprefix("t1_"),
                author=author,
                text=html_to_text(_markdown_html(entry.findtext(f"{ATOM}content") or "")),
                is_op=bool(author) and author == post.author,
            )
        )
    return post


def posts_from_listing(feed_xml: bytes | str) -> list[Post]:
    """A subreddit or search feed: posts in ranked order."""
    return [post_from_entry(entry) for entry in _entries(feed_xml) if (entry.findtext(f"{ATOM}id") or "").startswith("t3_")]


# --- RSS client ---------------------------------------------------------------------------


class RateLimiter:
    """Spaces requests the way Reddit's rate-limit headers ask. One per process by default."""

    def __init__(self, min_interval: float = 2.0, max_wait: float = 120.0, clock=time.monotonic, sleep=time.sleep) -> None:
        self.min_interval = min_interval
        self.max_wait = max_wait
        self.clock = clock
        self.sleep = sleep
        self.next_allowed = 0.0

    def wait(self) -> None:
        """Sleep until the next request is allowed. Raises instead if Reddit asked for too long a pause."""
        delay = self.next_allowed - self.clock()
        if delay > self.max_wait:
            raise RuntimeError(f"Reddit's rate limit asks to wait {delay:.0f} seconds; try again later.")
        if delay > 0:
            with cost.stage("rate_limit_wait"):
                self.sleep(delay)

    def update(self, headers: dict[str, str], limited: bool = False) -> None:
        """Schedule the next request from the headers of the last response."""
        try:
            remaining = float(headers.get("x-ratelimit-remaining", "1"))
            reset = float(headers.get("x-ratelimit-reset", "0"))
        except ValueError:
            remaining, reset = 1.0, 0.0
        wait = self.min_interval
        if limited or remaining < 1:
            wait = max(wait, reset + 1 if reset else 30.0)
        self.next_allowed = self.clock() + wait


LIMITER = RateLimiter()


def describe_http_error(code: int) -> str:
    if code == 404:
        return "Reddit says the post or subreddit does not exist (HTTP 404)."
    if code == 403:
        return (
            "Reddit refused the request (HTTP 403). The subreddit may be private or quarantined, or Reddit is "
            "blocking automated access; this tool does not work around that."
        )
    if code == 429:
        return "Reddit kept refusing requests because of its rate limit (HTTP 429); try again in a few minutes."
    return f"Reddit returned HTTP {code}."


class RssClient:
    name = "rss"

    def __init__(self, limiter: RateLimiter | None = None, max_attempts: int = 4) -> None:
        self.limiter = limiter or LIMITER
        self.max_attempts = max_attempts

    def get_feed(self, url: str) -> bytes:
        """A feed's raw XML, waiting and retrying as Reddit's rate limit asks."""
        for attempt in range(1, self.max_attempts + 1):
            self.limiter.wait()
            try:
                response = net.fetch(url, user_agent=USER_AGENT, headers={"Accept": "application/atom+xml"})
            except HTTPError as error:
                headers = {key.lower(): value for key, value in (error.headers or {}).items()}
                if error.code == 429:
                    self.limiter.update(headers, limited=True)
                    if attempt < self.max_attempts:
                        continue
                else:
                    self.limiter.update(headers)
                raise RuntimeError(describe_http_error(error.code)) from error
            self.limiter.update(response.headers)
            if "xml" not in response.content_type.lower():
                raise RuntimeError(
                    "Reddit returned a web page instead of the feed; it may be asking for a login or blocking "
                    "automated access."
                )
            return response.body
        raise RuntimeError(describe_http_error(429))

    def post(self, post_id: str) -> Post:
        return post_from_feed(self.get_feed(post_feed_url(post_id)))

    def listing(self, subreddit: str, sort: str = "top", time: str = "day", limit: int = 25) -> list[Post]:
        if sort not in SORTS or time not in TIMES:
            raise ValueError(f"sort must be one of {SORTS} and time one of {TIMES}")
        query = {"limit": limit, **({"t": time} if sort in ("top", "controversial") else {})}
        return posts_from_listing(self.get_feed(f"{BASE_URL}/r/{subreddit}/{sort}/.rss?{urlencode(query)}"))

    def search(
        self, query: str, subreddit: str | None = None, sort: str = "top", time: str = "week", limit: int = 25
    ) -> list[Post]:
        if sort not in ("relevance", "hot", "top", "new", "comments") or time not in TIMES:
            raise ValueError(f"search sort must be relevance, hot, top, new, or comments, and time one of {TIMES}")
        # type=link: without it, a search across Reddit returns matching subreddits instead of posts.
        params = {"q": query, "sort": sort, "t": time, "limit": limit, "type": "link"}
        if subreddit:
            params["restrict_sr"] = 1
            return posts_from_listing(self.get_feed(f"{BASE_URL}/r/{subreddit}/search.rss?{urlencode(params)}"))
        return posts_from_listing(self.get_feed(f"{BASE_URL}/search.rss?{urlencode(params)}"))

    def resolve_share_link(self, url: str) -> str:
        self.limiter.wait()
        target = net.redirect_target(url, USER_AGENT)
        self.limiter.update({})
        post_id = post_id_from_url(target or "")
        if not post_id:
            raise RuntimeError(f"The share link {url} did not lead to a Reddit post. Open it and copy the post's own link.")
        return post_id


def make_client(policy: dict | None = None) -> RedditClient:
    """The Reddit client to use. Only RSS exists today.

    When an official API client is added, return it here when its credentials are configured
    (see docs/reddit.md); nothing else needs to change.
    """
    settings = (policy or {}).get("reddit", {})
    LIMITER.min_interval = float(settings.get("min_request_seconds", LIMITER.min_interval))
    return RssClient()


# --- Extraction ---------------------------------------------------------------------------


def select_comments(post: Post, limit: int, skip_authors: list[str]) -> list[Comment]:
    """Every comment by the poster, plus the first ``limit`` comments by others, in feed order.

    The poster's comments are always kept: in many subreddits (r/GifRecipes, for example) the
    recipe itself is a comment by the poster.
    """
    skip = {name.lower() for name in skip_authors}
    kept: list[Comment] = []
    others = 0
    for comment in post.comments:
        if comment.author.lower() in skip or not comment.text or comment.text in GONE_TEXTS:
            continue
        if comment.is_op:
            kept.append(comment)
        elif others < limit:
            kept.append(comment)
            others += 1
    return kept


KIND_LABELS = {
    "text": "文字帖",
    "image": "图片帖（图片文字在 ocr.txt）",
    "gif": "GIF 动图（画面文字在 ocr.txt）",
    "video": "视频帖（语音在 transcript.txt，画面文字在 ocr.txt）",
    "gallery": "多图帖（RSS 只提供第一张图的预览）",
    "crosspost": "转帖",
    "link": "链接帖（指向外部网页）",
}


def write_caption(post: Post, output_dir: Path, linked_page: web.WebPage | None = None) -> None:
    header = [
        f"标题：{post.title}",
        f"作者：u/{post.author}" if post.author else "",
        f"版块：r/{post.subreddit}" if post.subreddit else "",
        f"发布时间：{post.published_at}" if post.published_at else "",
        f"帖子类型：{KIND_LABELS.get(post.kind, post.kind)}",
        f"帖子指向：{post.link}" if post.kind in ("link", "crosspost") else "",
    ]
    parts = ["\n".join(line for line in header if line)]
    if post.text and post.text not in GONE_TEXTS:
        parts.append(f"正文：\n{post.text}")
    if linked_page is not None:
        page_parts = [
            f"外部网页（{linked_page.url}，只读了正文，没有处理其中的图片）：",
            f"网页标题：{linked_page.title}" if linked_page.title else "",
            f"网页作者：{linked_page.author}" if linked_page.author else "",
            linked_page.text,
        ]
        summary = web.structured_summary(linked_page.structured)
        if summary:
            page_parts.append(f"网页结构化数据（schema.org）：\n{summary}")
        parts.append("\n".join(part for part in page_parts if part))
    (output_dir / "caption.txt").write_text("\n\n".join(parts), encoding="utf-8")


def write_comments(comments: list[Comment], output_dir: Path, total: int) -> None:
    if not comments:
        (output_dir / "comments.txt").write_text("", encoding="utf-8")
        return
    header = (
        f"评论（共读到 {total} 条，这里保留楼主的全部评论和其他人的前几条；按 Reddit 默认排序，"
        "回复紧跟在被回复的评论后面。RSS 不提供点赞数和楼层关系。[楼主] 是发帖人自己的评论。）"
    )
    blocks = [
        f"[{comment.comment_id}] u/{comment.author}{' [楼主]' if comment.is_op else ''}：\n{comment.text}"
        for comment in comments
    ]
    (output_dir / "comments.txt").write_text("\n\n".join([header, *blocks]), encoding="utf-8")


def read_linked_page(url: str) -> tuple[web.WebPage | None, dict]:
    """The outside page a link post points to: its main text only. Failures are recorded, not raised."""
    host = (urlparse(url).hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in web.VIDEO_HOSTS):
        return None, {"url": url, "status": "skipped", "reason": "video site; videos from other sites are not processed"}
    try:
        final_url, page_html = web.fetch(url)
        page = web.page_from_html(final_url, page_html)
    except Exception as error:
        return None, {"url": url, "status": "failed", "error": str(error)}
    return page, {
        "url": final_url,
        "status": "read",
        "title": page.title,
        "text_chars": len(page.text),
        "structured_types": sorted({kind for node in page.structured for kind in web.types_of(node) if kind}),
    }


def video_url(post: Post) -> tuple[str, str]:
    """Where to download a GIF or video post, and how: ("hls", playlist) or ("file", url)."""
    if post.kind == "video":
        video_id = urlparse(post.link).path.strip("/").split("/")[0]
        return "hls", f"https://v.redd.it/{video_id}/HLSPlaylist.m3u8"
    if post.link.lower().endswith(".gifv"):  # imgur serves the MP4 behind its .gifv pages
        return "file", post.link[: -len(".gifv")] + ".mp4"
    return "file", post.link


def process_video(post: Post, job: Job) -> None:
    how, url = video_url(post)
    suffix = ".mp4" if how == "hls" or url.lower().endswith(".mp4") else ".gif"
    video_path = job.work_dir / f"video{suffix}"
    with cost.stage("download"):
        if how == "hls":
            net.download_hls(url, video_path, USER_AGENT)
        else:
            net.download(url, video_path, post.permalink, user_agent=USER_AGENT)
    probe = media.probe_streams(video_path)
    cost.predict(video_seconds=probe["duration"], has_audio=probe["has_audio"], policy=job.policy)
    job.metadata.update(media.analyze_video(video_path, job.work_dir, job.output_dir))


def image_candidates(post: Post, max_images: int) -> list[list[str]]:
    """The images to save, each as the URLs to try in order."""
    if post.kind == "image":
        return [[post.link, post.thumbnail] if post.thumbnail else [post.link]]  # the preview is the fallback
    if post.kind == "gallery":
        return [[post.thumbnail]] if post.thumbnail else []
    return [[url] for url in post.text_images[:max_images]]


def process_images(candidates: list[list[str]], post: Post, job: Job, settings: dict) -> None:
    media_dir = job.output_dir / "media"
    media_dir.mkdir(exist_ok=True)
    for stale in media_dir.glob("image-*.jpg"):
        stale.unlink()
    image_paths: list[Path] = []
    outcomes: list[str] = []
    with cost.stage("download"):
        for urls in candidates:
            destination = media_dir / f"image-{len(image_paths) + 1:02d}.jpg"
            for url in urls:
                outcome = web.save_image(
                    url, post.permalink, job.work_dir, destination, settings.get("min_image_side", 200), user_agent=USER_AGENT
                )
                if outcome != "failed":
                    break
            outcomes.append(outcome)
            if outcome == "saved":
                image_paths.append(destination)
    job.metadata["images_failed"] = outcomes.count("failed")
    cost.predict(ocr_images=len(image_paths), policy=job.policy)
    job.metadata.update(media.analyze_images(image_paths, job.output_dir, NO_SPEECH))


class RedditSource(Source):
    name = "reddit"
    output_subdir = "reddit"

    def matches(self, url: str) -> bool:
        return is_reddit_host(urlparse(url).hostname or "")

    def output_key(self, url: str) -> str:
        post_id = post_id_from_url(url)
        if post_id:
            return post_id
        code = share_code(url)
        if code:
            return f"s-{code}"
        raise ValueError(NOT_A_POST.format(url=url))

    def extract(self, job: Job) -> None:
        settings = job.policy.get("reddit", {})
        client = make_client(job.policy)
        with cost.stage("fetch"):
            post_id = post_id_from_url(job.url)
            if not post_id:
                if not share_code(job.url):
                    raise RuntimeError(NOT_A_POST.format(url=job.url))
                post_id = client.resolve_share_link(job.url)
            post = client.post(post_id)

        kind = post.kind
        comments = select_comments(post, settings.get("max_comments", 20), settings.get("skip_authors", ["AutoModerator"]))
        job.metadata.update(
            {
                "resolved_url": post.permalink,
                "canonical_url": f"{BASE_URL}/comments/{post.post_id}/",
                "note_id": note_id_for(post.post_id),
                "note_type": "video" if kind in ("gif", "video") else "post",
                "post_kind": kind,
                "post_id": post.post_id,
                "subreddit": post.subreddit,
                "title": post.title,
                "published_at": post.published_at,
                "author": f"u/{post.author}" if post.author else None,
                "link": post.link if kind != "text" else None,
                "client": client.name,
                "parser": "reddit_rss",
                "comments_read": len(post.comments),
                "comments_kept": len(comments),
                "op_comments": sum(1 for comment in comments if comment.is_op),
                "unprocessed_media": [],
            }
        )
        if post.score is not None:
            job.metadata["score"] = post.score
        if post.num_comments is not None:
            job.metadata["num_comments"] = post.num_comments
        warnings = []
        if post.text in GONE_TEXTS:
            warnings.append(f"the post text was {post.text[1:-1]}; only the title, media, and comments remain")
        if kind == "gallery":
            warnings.append("gallery post: RSS only gives a cropped preview of the first image; the other images were not read")
            job.metadata["unprocessed_media"].append(post.link)
        if kind == "crosspost":
            warnings.append("crosspost: the original post was not read; extract its own link for its media and comments")

        linked_page = None
        if kind == "link":
            if settings.get("follow_links", True):
                with cost.stage("linked_page"):
                    linked_page, outcome = read_linked_page(post.link)
                job.metadata["linked_page"] = outcome
                if outcome["status"] == "skipped":
                    job.metadata["unprocessed_media"].append(post.link)
            else:
                job.metadata["linked_page"] = {"url": post.link, "status": "not followed ([reddit] follow_links = false)"}
        if warnings:
            job.metadata["content_warning"] = "; ".join(warnings)

        write_caption(post, job.output_dir, linked_page)
        write_comments(comments, job.output_dir, len(post.comments))
        if linked_page is not None and linked_page.structured:
            (job.output_dir / "structured.json").write_text(
                json.dumps(linked_page.structured, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        if kind in ("gif", "video"):
            process_video(post, job)
        else:
            process_images(image_candidates(post, settings.get("max_images", 8)), post, job, settings)
