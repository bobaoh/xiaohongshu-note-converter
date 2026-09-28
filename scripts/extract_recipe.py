from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
OUTPUT_FILES = ("caption.txt", "transcript.txt", "ocr.txt", "metadata.json")


@dataclass
class Note:
    resolved_url: str
    note_type: str
    title: str = ""
    desc: str = ""
    tags: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    live_photo_count: int = 0
    video_urls: list[str] = field(default_factory=list)
    source: str = "initial_state"


def fetch_page(url: str) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.geturl(), response.read().decode("utf-8", errors="replace")


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


def image_url(image: dict) -> str | None:
    scenes = {info.get("imageScene"): info.get("url") for info in image.get("infoList") or [] if info.get("url")}
    url = scenes.get("WB_DFT") or scenes.get("H5_DTL") or image.get("urlDefault") or image.get("url")
    return unescape_url(url) if url else None


def clean_desc(desc: str) -> str:
    desc = re.sub(r"\[话题\]#", "", desc)
    desc = re.sub(r"\[[^\[\]\s]{1,8}R\]", "", desc)
    return "\n".join(line.rstrip() for line in desc.replace("\t", "").splitlines()).strip()


def fallback_note(resolved_url: str, page: str) -> Note:
    """Best-effort parsing when the page has no embedded note state."""
    query_type = (parse_qs(urlparse(resolved_url).query).get("type") or ["unknown"])[0]
    decoded = unescape_url(page)
    videos = [
        url
        for url in re.findall(r"https?://[^\"'<>\s]+?\.mp4(?:\?[^\"'<>\s]+)?", decoded)
        if "LIVEPHOTO" not in url.upper() and "/10/19/" not in url
    ]
    videos = sorted(dict.fromkeys(videos), key=lambda url: "_259.mp4" not in url and "h264" not in url.lower())
    note = Note(resolved_url=resolved_url, note_type=query_type, video_urls=videos, source="regex_fallback")
    if note.note_type == "unknown":
        note.note_type = "video" if note.video_urls else "normal"
    return note


def load_note(url: str) -> Note:
    resolved_url, page = fetch_page(url)
    state = parse_state(page)
    data = find_note_data(state) if state else None
    if not data:
        if re.search(r"/(404|login|website-login)\b", urlparse(resolved_url).path):
            raise RuntimeError("The note is unavailable: it was removed, is private, or requires login.")
        return fallback_note(resolved_url, page)

    images = data.get("imageList") or []
    note = Note(
        resolved_url=resolved_url,
        note_type=data.get("type") or "unknown",
        title=data.get("title") or "",
        desc=clean_desc(data.get("desc") or ""),
        tags=[tag.get("name") for tag in data.get("tagList") or [] if tag.get("name")],
        image_urls=[url for url in (image_url(image) for image in images) if url],
        live_photo_count=sum(1 for image in images if image.get("livePhoto")),
        video_urls=video_urls(data.get("video") or {}),
    )
    if note.note_type not in ("video", "normal"):
        note.note_type = "video" if note.video_urls else "normal"
    return note


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


def download_first(urls: list[str], destination: Path, referer: str) -> None:
    errors = []
    for url in urls:
        try:
            download(url, destination, referer)
            return
        except Exception as error:
            errors.append(str(error))
    raise RuntimeError("Could not download the video: " + "; ".join(errors))


def run_ffmpeg(args: list[str]) -> None:
    try:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *args], check=True)
    except FileNotFoundError as error:
        raise RuntimeError("FFmpeg is not installed or is not on PATH.") from error


def probe_streams(video_path: Path) -> dict[str, object]:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(video_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("ffprobe is not installed or is not on PATH.") from error
    info = json.loads(result.stdout)
    types = [stream.get("codec_type") for stream in info.get("streams", [])]
    if "video" not in types:
        raise RuntimeError("The downloaded file is not a valid video.")
    return {"has_audio": "audio" in types, "duration": float((info.get("format") or {}).get("duration") or 0)}


def transcribe(audio_path: Path, output_path: Path) -> dict[str, object]:
    from faster_whisper import WhisperModel

    model_name = os.environ.get("WHISPER_MODEL", "small")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, vad_filter=True, beam_size=5)
    lines = 0
    with output_path.open("w", encoding="utf-8") as output:
        for segment in segments:
            text = segment.text.strip()
            if text:
                output.write(f"[{segment.start:.1f}-{segment.end:.1f}] {text}\n")
                lines += 1
    result: dict[str, object] = {
        "status": "complete",
        "model": model_name,
        "language": info.language,
        "language_probability": info.language_probability,
        "lines": lines,
    }
    if info.language_probability < 0.5 or lines <= 2:
        # Music-only videos make Whisper guess a language and hallucinate short phrases such as "You".
        result["warning"] = "little or no recognizable speech; the transcript is probably noise, so rely on OCR"
    return result


class OcrCollector:
    def __init__(self) -> None:
        import cv2
        from rapidocr_onnxruntime import RapidOCR

        self.cv2 = cv2
        self.engine = RapidOCR()
        self.seen: set[str] = set()
        self.rows: list[str] = []

    def add(self, image_path: Path, label: str) -> None:
        image = self.cv2.imread(str(image_path))
        if image is None:
            return
        result, _ = self.engine(image)
        for item in result or []:
            text = str(item[1]).strip()
            confidence = float(item[2])
            key = re.sub(r"[^0-9A-Za-z一-鿿]", "", text)
            if confidence >= 0.45 and len(key) >= 2 and key not in self.seen:
                self.seen.add(key)
                self.rows.append(f"[{label}|{confidence:.2f}] {text}")


def process_video(note: Note, work_dir: Path, output_dir: Path, metadata: dict) -> None:
    if not note.video_urls:
        raise RuntimeError("This is a video note, but no public video stream was found.")
    video_path = work_dir / "video.mp4"
    download_first(note.video_urls, video_path, note.resolved_url)
    probe = probe_streams(video_path)
    metadata["video"] = probe

    transcript_path = output_dir / "transcript.txt"
    if probe["has_audio"]:
        audio_path = work_dir / "audio.wav"
        run_ffmpeg(["-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio_path)])
        metadata["transcription"] = transcribe(audio_path, transcript_path)
    else:
        transcript_path.write_text("", encoding="utf-8")
        metadata["transcription"] = {"status": "skipped", "reason": "video has no audio track"}

    frame_dir = work_dir / "frames"
    frame_dir.mkdir()
    run_ffmpeg(["-y", "-i", str(video_path), "-vf", "fps=1/1.5,scale=720:-1", str(frame_dir / "frame-%04d.png")])
    ocr = OcrCollector()
    for frame_path in sorted(frame_dir.glob("*.png")):
        frame_number = int(re.search(r"(\d+)", frame_path.stem).group(1))
        ocr.add(frame_path, f"{(frame_number - 1) * 1.5:.1f}s")
    (output_dir / "ocr.txt").write_text("\n".join(ocr.rows), encoding="utf-8")
    metadata["ocr_lines"] = len(ocr.rows)


def process_images(note: Note, output_dir: Path, metadata: dict) -> None:
    if not note.image_urls:
        raise RuntimeError("No public post images were found.")
    media = output_dir / "media"
    media.mkdir(exist_ok=True)
    for stale in media.glob("image-*.jpg"):
        stale.unlink()

    ocr = OcrCollector()
    for index, url in enumerate(note.image_urls, 1):
        image_path = media / f"image-{index:02d}.jpg"
        download(url, image_path, note.resolved_url)
        ocr.add(image_path, f"image-{index:02d}")
    (output_dir / "transcript.txt").write_text("", encoding="utf-8")
    (output_dir / "ocr.txt").write_text("\n".join(ocr.rows), encoding="utf-8")
    metadata["transcription"] = {"status": "skipped", "reason": "image note has no speech"}
    metadata.update({"image_count": len(note.image_urls), "live_photo_count": note.live_photo_count, "ocr_lines": len(ocr.rows)})


def write_caption(note: Note, output_dir: Path) -> None:
    parts = [f"标题：{note.title}" if note.title else "", note.desc, "标签：" + " ".join(f"#{tag}" for tag in note.tags) if note.tags else ""]
    (output_dir / "caption.txt").write_text("\n\n".join(part for part in parts if part), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract the caption, speech, and on-screen or image text from a public Xiaohongshu note. "
        "Video and image notes are detected automatically."
    )
    parser.add_argument("url", help="Public Xiaohongshu, RedNote, or xhslink.com URL")
    parser.add_argument("--output", default="output", help="Directory for caption, transcript, OCR, and metadata")
    parser.add_argument("--keep-media", action="store_true", help="Keep the downloaded video, audio, and frames")
    args = parser.parse_args(argv)

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_FILES:
        (output_dir / name).unlink(missing_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="xhs-recipe-"))
    metadata: dict[str, object] = {"input_url": args.url, "status": "started"}

    try:
        note = load_note(args.url)
        metadata.update(
            {"resolved_url": note.resolved_url, "note_type": note.note_type, "title": note.title, "parser": note.source}
        )
        write_caption(note, output_dir)
        if note.note_type == "video":
            process_video(note, work_dir, output_dir, metadata)
        else:
            process_images(note, output_dir, metadata)
        metadata["status"] = "complete"
    except Exception as error:
        metadata["status"] = "failed"
        metadata["error"] = str(error)
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.keep_media:
            shutil.copytree(work_dir, output_dir / "media", dirs_exist_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)

    print(f"Complete ({note.note_type} note). Read caption.txt, transcript.txt, and ocr.txt in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
