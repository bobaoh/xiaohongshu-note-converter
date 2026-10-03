"""FFmpeg, speech transcription, and OCR on local files, whatever source they came from."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from . import cost

#: One video frame is OCR'd every this many seconds.
FRAME_INTERVAL_SECONDS = 1.5

# Pinned Hugging Face revisions of the Systran/faster-whisper-* models, so an upstream model
# update cannot silently change transcripts. Update together with requirements.lock.
WHISPER_REVISIONS = {
    "tiny": "d90ca5fe260221311c53c58e660288d3deb8d356",
    "base": "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
    "small": "536b0662742c02347bc0e980a01041f333bce120",
    "medium": "08e178d48790749d25932bbc082711ddcfdfbc4f",
    "large-v3": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
}

MIN_SPEECH_CHARS = 5


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


def load_wav(path: Path):
    """Read the 16 kHz mono PCM WAV written by FFmpeg as float32 samples.

    Passing samples instead of a file path keeps faster-whisper from decoding the file with
    PyAV, whose API changes between releases (PyAV 19 removed an argument that
    faster-whisper 1.2.1 still passes).
    """
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            raise RuntimeError(f"Expected 16 kHz mono 16-bit audio, got {wav.getparams()}")
        frames = wav.readframes(wav.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(audio_path: Path, output_path: Path) -> dict[str, object]:
    from faster_whisper import WhisperModel

    model_name = os.environ.get("WHISPER_MODEL", "small")
    # Other model names or local paths are allowed; they load the latest (unpinned) revision.
    revision = os.environ.get("WHISPER_MODEL_REVISION") or WHISPER_REVISIONS.get(model_name)
    with cost.stage("transcribe"):
        model = WhisperModel(model_name, device="cpu", compute_type="int8", revision=revision)
        segments, info = model.transcribe(load_wav(audio_path), vad_filter=True, beam_size=5)
        texts = []
        with output_path.open("w", encoding="utf-8") as output:
            for segment in segments:  # transcription runs lazily while iterating
                text = segment.text.strip()
                if text:
                    output.write(f"[{segment.start:.1f}-{segment.end:.1f}] {text}\n")
                    texts.append(text)
    result: dict[str, object] = {
        "status": "complete",
        "model": model_name,
        "model_revision": revision,
        "language": info.language,
        "language_probability": info.language_probability,
        "lines": len(texts),
    }
    warning = speech_warning(info.language_probability, texts)
    if warning:
        result["warning"] = warning
    return result


def speech_warning(language_probability: float, texts: list[str]) -> str | None:
    """Flag transcripts that are probably noise.

    Music-only audio makes Whisper guess a language with low confidence and hallucinate short
    phrases such as "You". Judge by the amount of recognized text rather than the number of
    segments: a short real narration can come back as a single long segment.
    """
    chars = sum(len(re.sub(r"[\W_]", "", text)) for text in texts)
    if language_probability < 0.5 or chars < MIN_SPEECH_CHARS:
        return "little or no recognizable speech; the transcript is probably noise, so rely on OCR"
    return None


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
        with cost.stage("ocr"):
            result, _ = self.engine(image)
        for item in result or []:
            text = str(item[1]).strip()
            confidence = float(item[2])
            key = re.sub(r"[^0-9A-Za-z一-鿿]", "", text)
            if confidence >= 0.45 and len(key) >= 2 and key not in self.seen:
                self.seen.add(key)
                self.rows.append(f"[{label}|{confidence:.2f}] {text}")


def analyze_video(video_path: Path, work_dir: Path, output_dir: Path) -> dict[str, object]:
    """Transcribe and OCR a local video file; writes transcript.txt and ocr.txt, returns metadata fields."""
    probe = probe_streams(video_path)
    cost.count("video_seconds", probe["duration"])
    result: dict[str, object] = {"video": probe}

    transcript_path = output_dir / "transcript.txt"
    if probe["has_audio"]:
        audio_path = work_dir / "audio.wav"
        with cost.stage("ffmpeg"):
            run_ffmpeg(["-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio_path)])
        result["transcription"] = transcribe(audio_path, transcript_path)
    else:
        transcript_path.write_text("", encoding="utf-8")
        result["transcription"] = {"status": "skipped", "reason": "video has no audio track"}

    frame_dir = work_dir / "frames"
    frame_dir.mkdir(exist_ok=True)
    with cost.stage("ffmpeg"):
        run_ffmpeg(["-y", "-i", str(video_path), "-vf", f"fps=1/{FRAME_INTERVAL_SECONDS},scale=720:-1", str(frame_dir / "frame-%04d.png")])
    ocr = OcrCollector()
    frames = sorted(frame_dir.glob("*.png"))
    cost.count("ocr_frames", len(frames))
    for frame_path in frames:
        frame_number = int(re.search(r"(\d+)", frame_path.stem).group(1))
        ocr.add(frame_path, f"{(frame_number - 1) * FRAME_INTERVAL_SECONDS:.1f}s")
    (output_dir / "ocr.txt").write_text("\n".join(ocr.rows), encoding="utf-8")
    result["ocr_lines"] = len(ocr.rows)
    return result


def analyze_images(
    image_paths: list[Path], output_dir: Path, no_speech_reason: str = "image note has no speech"
) -> dict[str, object]:
    """OCR local images in order; writes an empty transcript.txt and ocr.txt, returns metadata fields."""
    rows: list[str] = []
    if image_paths:  # loading the OCR model takes about a second; skip it when there is nothing to read
        ocr = OcrCollector()
        cost.count("ocr_images", len(image_paths))
        for index, image_path in enumerate(image_paths, 1):
            ocr.add(image_path, f"image-{index:02d}")
        rows = ocr.rows
    (output_dir / "transcript.txt").write_text("", encoding="utf-8")
    (output_dir / "ocr.txt").write_text("\n".join(rows), encoding="utf-8")
    return {
        "transcription": {"status": "skipped", "reason": no_speech_reason},
        "image_count": len(image_paths),
        "ocr_lines": len(rows),
    }
