"""Xiaohongshu / RedNote notes: video notes and image notes (including Live Photos).

The note is read from the page's embedded ``window.__INITIAL_STATE__``. When that is missing,
``fallback_note`` scans the page for video URLs instead.

Output layout: ``output/<key>/`` directly, not ``output/xiaohongshu/<key>/``. The xhs-library
project reads that layout (see AGENTS.md, "Contract with xhs-library"), so it must not change
without a coordinated update there.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import cost, media, net
from . import Job, Source

HOSTS = ("xhslink.com", "xiaohongshu.com", "rednote.com")


@dataclass
class Note:
    resolved_url: str
    note_type: str
    note_id: str = ""
    published_at: str | None = None
    author: str = ""
    author_id: str = ""
    title: str = ""
    desc: str = ""
    tags: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    live_photo_count: int = 0
    video_urls: list[str] = field(default_factory=list)
    #: Length shown on the page, in seconds; used to predict cost before downloading.
    video_duration: float = 0
    #: "initial_state" or "regex_fallback"; written to metadata as "parser".
    parser: str = "initial_state"


def unescape_url(url: str) -> str:
    # Pages embed URLs both as \u002F and, inside JSON-in-JSON fields such as mediaV2, as \\u002F.
    return re.sub(r"\\+(?:u002F|/)", "/", html.unescape(url))


def parse_state(page: str) -> dict | None:
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", page, re.S)
    if not match:
        return None
    try:
        return json.loads(re.sub(r"\bundefined\b", "null", match.group(1)))
    except json.JSONDecodeError:
        return None


def find_note_data(node: object) -> dict | None:
    """Return the first object that looks like a note: it has a type plus images or a video."""
    if isinstance(node, dict):
        if isinstance(node.get("type"), str) and ("imageList" in node or "video" in node) and (
            "title" in node or "desc" in node
        ):
            return node
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = find_note_data(child)
        if found:
            return found
    return None


def stream_urls(streams: dict) -> list[str]:
    """Order video streams: H.264 with audio first, then other codecs, master URLs before backups."""
    entries = []
    for codec in ("h264", "h265", "h266", "av1"):
        for stream in streams.get(codec) or []:
            has_audio = bool(stream.get("audioCodec")) or bool(stream.get("audioChannels"))
            entries.append((not has_audio, codec != "h264", stream))
    entries.sort(key=lambda entry: entry[:2])
    urls = []
    for _, _, stream in entries:
        for url in [stream.get("masterUrl"), *(stream.get("backupUrls") or [])]:
            if url and unescape_url(url) not in urls:
                urls.append(unescape_url(url))
    return urls


def video_urls(video: dict) -> list[str]:
    urls = stream_urls((video.get("media") or {}).get("stream") or {})
    media_v2 = video.get("mediaV2")
    if isinstance(media_v2, str):
        try:
            media_v2 = json.loads(media_v2)
        except json.JSONDecodeError:
            media_v2 = None
    if isinstance(media_v2, dict):
        for stream_list in (media_v2.get("stream") or {}).values():
            for stream in stream_list or []:
                stream.setdefault("masterUrl", stream.get("master_url"))
                stream.setdefault("backupUrls", stream.get("backup_urls"))
                stream.setdefault("audioCodec", stream.get("audio_codec"))
        urls += [url for url in stream_urls(media_v2.get("stream") or {}) if url not in urls]
    return urls


def video_duration(video: dict) -> float:
    """The video length in seconds as the page states it, or 0 when unknown."""
    for value in ((video.get("capa") or {}).get("duration"), ((video.get("media") or {}).get("video") or {}).get("duration")):
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return 0.0


def image_url(image: dict) -> str | None:
    scenes = {info.get("imageScene"): info.get("url") for info in image.get("infoList") or [] if info.get("url")}
    url = scenes.get("WB_DFT") or scenes.get("H5_DTL") or image.get("urlDefault") or image.get("url")
    return unescape_url(url) if url else None


def clean_desc(desc: str) -> str:
    desc = re.sub(r"\[话题\]#", "", desc)
    desc = re.sub(r"\[[^\[\]\s]{1,8}R\]", "", desc)
    return "\n".join(line.rstrip() for line in desc.replace("\t", "").splitlines()).strip()


def published_date(timestamp: object) -> str | None:
    """Convert the note's millisecond timestamp to a local ISO date."""
    if not isinstance(timestamp, (int, float)) or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp / 1000).date().isoformat()


def note_id_from_url(url: str) -> str:
    match = re.search(r"/([0-9a-f]{24})(?:$|[/?#])", urlparse(url).path)
    return match.group(1) if match else ""


def fallback_note(resolved_url: str, page: str) -> Note:
    """Best-effort parsing when the page has no embedded note state."""
    query_type = (parse_qs(urlparse(resolved_url).query).get("type") or ["unknown"])[0]
    decoded = unescape_url(page)
    videos = [
        url
        # Exclude backslashes: inside JSON-in-JSON fields the closing quote is \", not ".
        for url in re.findall(r"https?://[^\"'<>\s\\]+?\.mp4(?:\?[^\"'<>\s\\]+)?", decoded)
        if "LIVEPHOTO" not in url.upper() and "/10/19/" not in url
    ]
    # Prefer H.264 streams, then primary hosts over the sns-bak backup hosts.
    videos = sorted(
        dict.fromkeys(videos),
        key=lambda url: ("_259.mp4" not in url and "h264" not in url.lower(), "sns-bak" in url),
    )
    note = Note(
        resolved_url=resolved_url,
        note_type=query_type,
        note_id=note_id_from_url(resolved_url),
        video_urls=videos,
        parser="regex_fallback",
    )
    if note.note_type == "unknown":
        note.note_type = "video" if note.video_urls else "normal"
    return note


def load_note(url: str) -> Note:
    resolved_url, page = net.fetch_page(url)
    return note_from_page(resolved_url, page)


def note_from_page(resolved_url: str, page: str) -> Note:
    """Parse a fetched note page. Kept separate from fetching so tests can use saved pages."""
    state = parse_state(page)
    data = find_note_data(state) if state else None
    if not data:
        if re.search(r"/(404|login|website-login)\b", urlparse(resolved_url).path):
            raise RuntimeError("The note is unavailable: it was removed, is private, or requires login.")
        return fallback_note(resolved_url, page)

    images = data.get("imageList") or []
    user = data.get("user") or {}
    desc = clean_desc(data.get("desc") or "")
    # Some authors leave the title field empty and put the title on the first line of the description.
    title = data.get("title") or next((line.strip() for line in desc.splitlines() if line.strip()), "")
    video = data.get("video") or {}
    note = Note(
        resolved_url=resolved_url,
        note_type=data.get("type") or "unknown",
        note_id=data.get("noteId") or note_id_from_url(resolved_url),
        published_at=published_date(data.get("time")),
        author=user.get("nickName") or user.get("nickname") or "",
        author_id=user.get("userId") or "",
        title=title,
        desc=desc,
        tags=[tag.get("name") for tag in data.get("tagList") or [] if tag.get("name")],
        image_urls=[url for url in (image_url(image) for image in images) if url],
        live_photo_count=sum(1 for image in images if image.get("livePhoto")),
        video_urls=video_urls(video),
        video_duration=video_duration(video),
    )
    if note.note_type not in ("video", "normal"):
        note.note_type = "video" if note.video_urls else "normal"
    return note


def write_caption(note: Note, output_dir: Path) -> None:
    parts = [
        f"标题：{note.title}" if note.title else "",
        f"作者：{note.author}" if note.author else "",
        note.desc,
        "标签：" + " ".join(f"#{tag}" for tag in note.tags) if note.tags else "",
    ]
    (output_dir / "caption.txt").write_text("\n\n".join(part for part in parts if part), encoding="utf-8")


def process_video(note: Note, work_dir: Path, output_dir: Path, metadata: dict) -> None:
    if not note.video_urls:
        raise RuntimeError("This is a video note, but no public video stream was found.")
    video_path = work_dir / "video.mp4"
    with cost.stage("download"):
        net.download_first(note.video_urls, video_path, note.resolved_url)
    metadata.update(media.analyze_video(video_path, work_dir, output_dir))


def process_images(note: Note, output_dir: Path, metadata: dict) -> None:
    if not note.image_urls:
        raise RuntimeError("No public post images were found.")
    media_dir = output_dir / "media"
    media_dir.mkdir(exist_ok=True)
    for stale in media_dir.glob("image-*.jpg"):
        stale.unlink()

    image_paths = []
    with cost.stage("download"):
        for index, url in enumerate(note.image_urls, 1):
            image_path = media_dir / f"image-{index:02d}.jpg"
            net.download(url, image_path, note.resolved_url)
            image_paths.append(image_path)
    metadata.update(media.analyze_images(image_paths, output_dir))
    metadata["live_photo_count"] = note.live_photo_count


class XiaohongshuSource(Source):
    name = "xiaohongshu"
    output_subdir = ""  # flat output/<key>/, see the module docstring

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == h or host.endswith("." + h) for h in HOSTS)

    def output_key(self, url: str) -> str:
        """xhslink.com/o/<code> gives the short code; a full note URL gives the 24-hex note ID.

        Must match xhs_library.links.link_key, which locates the same directory.
        """
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        segments = [part for part in parsed.path.split("/") if part]
        if host.endswith("xhslink.com") and segments:
            return segments[-1]
        match = re.search(r"\b([0-9a-f]{24})\b", parsed.path)
        if match:
            return match.group(1)
        if segments:
            return re.sub(r"[^0-9A-Za-z_-]", "", segments[-1]) or "note"
        raise ValueError(f"Cannot derive a key from {url}")

    def extract(self, job: Job) -> None:
        with cost.stage("fetch"):
            note = load_note(job.url)
        job.metadata.update(
            {
                "resolved_url": note.resolved_url,
                "note_id": note.note_id,
                "note_type": note.note_type,
                "title": note.title,
                "published_at": note.published_at,
                "author": note.author or None,
                "author_id": note.author_id or None,
                "parser": note.parser,
            }
        )
        write_caption(note, job.output_dir)
        if note.note_type == "video":
            cost.predict(video_seconds=note.video_duration, policy=job.policy)
            process_video(note, job.work_dir, job.output_dir, job.metadata)
        else:
            cost.predict(ocr_images=len(note.image_urls), policy=job.policy)
            process_images(note, job.output_dir, job.metadata)
