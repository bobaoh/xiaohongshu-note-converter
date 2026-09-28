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
from pathlib import Path


def fetch_text(url: str) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        resolved_url = response.geturl()
        content = response.read().decode("utf-8", errors="replace")
    return resolved_url, content


def find_video_url(page: str) -> str:
    page = html.unescape(page)
    field_urls = re.findall(r"(?:masterUrl|backupUrls?)\"?\s*:\s*\"([^\"]+)", page)
    candidates = [url.replace(r"\u002F", "/").replace(r"\/", "/") for url in field_urls]
    candidates = [url for url in candidates if ".mp4" in url]
    h264 = [url for url in candidates if "_259.mp4" in url or "h264" in url.lower()]
    if h264:
        return h264[0]
    if candidates:
        return candidates[0]

    decoded = page.replace(r"\u002F", "/").replace(r"\/", "/")
    candidates = re.findall(r"https?://[^\"'<>\s]+?\.mp4(?:\?[^\"'<>\s]+)?", decoded)
    if candidates:
        return candidates[0]
    raise RuntimeError("No public MP4 video URL was found in the page.")


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    if destination.stat().st_size == 0:
        raise RuntimeError("The downloaded video is empty.")


def run_ffmpeg(args: list[str]) -> None:
    try:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *args], check=True)
    except FileNotFoundError as error:
        raise RuntimeError("FFmpeg is not installed or is not on PATH.") from error


def transcribe(audio_path: Path, output_path: Path) -> dict[str, object]:
    from faster_whisper import WhisperModel

    model_name = os.environ.get("WHISPER_MODEL", "small")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, vad_filter=True, beam_size=5)
    with output_path.open("w", encoding="utf-8") as output:
        for segment in segments:
            text = segment.text.strip()
            if text:
                output.write(f"[{segment.start:.1f}-{segment.end:.1f}] {text}\n")
    return {"model": model_name, "language": info.language, "language_probability": info.language_probability}


def ocr_frames(video_path: Path, work_dir: Path, output_path: Path) -> int:
    import cv2
    from rapidocr_onnxruntime import RapidOCR

    frame_dir = work_dir / "frames"
    frame_dir.mkdir()
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "fps=1/1.5,scale=720:-1",
            str(frame_dir / "frame-%04d.png"),
        ]
    )

    engine = RapidOCR()
    seen: set[str] = set()
    rows: list[str] = []
    for frame_path in sorted(frame_dir.glob("*.png")):
        image = cv2.imread(str(frame_path))
        if image is None:
            continue
        result, _ = engine(image)
        if not result:
            continue
        frame_number = int(re.search(r"(\d+)", frame_path.stem).group(1))
        timestamp = (frame_number - 1) * 1.5
        for item in result:
            text = str(item[1]).strip()
            confidence = float(item[2])
            key = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", text)
            if confidence >= 0.45 and len(key) >= 2 and key not in seen:
                seen.add(key)
                rows.append(f"[{timestamp:.1f}s|{confidence:.2f}] {text}")

    output_path.write_text("\n".join(rows), encoding="utf-8")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract speech and on-screen text from a public Xiaohongshu video.")
    parser.add_argument("url", help="Public Xiaohongshu, RedNote, or xhslink.com URL")
    parser.add_argument("--output", default="output", help="Directory for transcript and OCR output")
    parser.add_argument("--keep-media", action="store_true", help="Keep downloaded video, audio, and frames")
    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="xhs-recipe-"))
    metadata: dict[str, object] = {"input_url": args.url, "status": "started"}

    try:
        resolved_url, page = fetch_text(args.url)
        video_url = find_video_url(page)
        metadata["resolved_url"] = resolved_url
        metadata["status"] = "video_found"
        metadata["video_url_found"] = True
        (work_dir / "video.mp4").write_bytes(b"")
        download(video_url, work_dir / "video.mp4")

        run_ffmpeg(
            [
                "-y",
                "-i",
                str(work_dir / "video.mp4"),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(work_dir / "audio.wav"),
            ]
        )
        metadata["transcription"] = transcribe(work_dir / "audio.wav", output_dir / "transcript.txt")
        metadata["ocr_lines"] = ocr_frames(work_dir / "video.mp4", work_dir, output_dir / "ocr.txt")
        metadata["status"] = "complete"
    except Exception as error:
        metadata["status"] = "failed"
        metadata["error"] = str(error)
        (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        if args.keep_media:
            retained = output_dir / "media"
            shutil.copytree(work_dir, retained, dirs_exist_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)

    (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Complete. Read {output_dir / 'transcript.txt'} and {output_dir / 'ocr.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
