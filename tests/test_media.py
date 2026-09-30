"""Run the real FFmpeg, OCR, and Whisper pipeline on the committed synthetic media.

Whisper defaults to the `tiny` model here so the whole module runs in about a minute.
Assertions use keywords rather than exact text, because recognition output can shift by a
character between model or library versions (for example 微波炉 vs 微波爐).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import SYNTHETIC, image_note_data, make_page, note_url, video_note_data

import extract_note

pytestmark = [pytest.mark.media, pytest.mark.usefixtures("require_ffmpeg")]


@pytest.fixture(scope="module", autouse=True)
def tiny_whisper():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("WHISPER_MODEL", extract_note.os.environ.get("TEST_WHISPER_MODEL", "tiny"))
    yield
    monkeypatch.undo()


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory):
    """Analyze each synthetic video once and share the results across tests."""
    results = {}
    for name in ("speech", "music_only", "silent"):
        work = tmp_path_factory.mktemp(f"{name}-work")
        out = tmp_path_factory.mktemp(f"{name}-out")
        meta = extract_note.analyze_video(SYNTHETIC / f"{name}.mp4", work, out)
        results[name] = {
            "meta": meta,
            "transcript": (out / "transcript.txt").read_text(encoding="utf-8"),
            "ocr": (out / "ocr.txt").read_text(encoding="utf-8"),
        }
    return results


def test_speech_video_is_transcribed(analyzed):
    result = analyzed["speech"]
    transcription = result["meta"]["transcription"]

    assert result["meta"]["video"]["has_audio"] is True
    assert transcription["status"] == "complete"
    assert transcription["language"] == "zh"
    assert "warning" not in transcription, result["transcript"]
    for keyword in ("32", "70", "微波"):
        assert keyword in result["transcript"], result["transcript"]


def test_speech_video_subtitles_are_read(analyzed):
    ocr = analyzed["speech"]["ocr"]
    assert "糯米粉32g" in ocr.replace(" ", "")
    assert "2分钟" in ocr.replace(" ", "")
    assert ocr.startswith("[0.0s|"), "OCR lines should be tagged with the frame time"


def test_music_only_video_warns_and_keeps_subtitles(analyzed):
    result = analyzed["music_only"]
    assert result["meta"]["video"]["has_audio"] is True
    assert "warning" in result["meta"]["transcription"], result["transcript"]
    assert "低筋面粉65g" in result["ocr"].replace(" ", "")


def test_silent_video_skips_transcription(analyzed):
    result = analyzed["silent"]
    assert result["meta"]["video"]["has_audio"] is False
    assert result["meta"]["transcription"]["status"] == "skipped"
    assert result["transcript"] == ""
    assert "LivePhoto" in result["ocr"].replace(" ", "")


def test_transcription_does_not_depend_on_pyav_decoding(tmp_path, monkeypatch):
    """PyAV 19 broke faster-whisper's file decoding; we decode the WAV ourselves instead."""
    import av

    def broken_open(*args, **kwargs):
        raise TypeError("PyAV decoding must not be used")

    monkeypatch.setattr(av, "open", broken_open)
    audio = tmp_path / "audio.wav"
    extract_note.run_ffmpeg(["-y", "-i", str(SYNTHETIC / "speech.mp4"), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)])

    result = extract_note.transcribe(audio, tmp_path / "transcript.txt")

    assert result["status"] == "complete" and result["lines"] >= 1


def test_invalid_video_file_is_rejected(tmp_path):
    fake = tmp_path / "video.mp4"
    fake.write_bytes(b"<html>login required</html>")
    with pytest.raises(Exception):
        extract_note.analyze_video(fake, tmp_path, tmp_path)


def test_image_cards_are_read_in_order(tmp_path):
    cards = sorted(SYNTHETIC.glob("card-*.jpg"))
    meta = extract_note.analyze_images(cards, tmp_path)
    ocr = (tmp_path / "ocr.txt").read_text(encoding="utf-8")
    compact = ocr.replace(" ", "")

    assert meta["image_count"] == 2
    assert meta["transcription"]["status"] == "skipped"
    assert "奶油奶酪135g" in compact
    assert "放入无花果" in compact
    assert ocr.index("[image-01") < ocr.index("[image-02")


# --- Full pipeline through main(), with the network replaced by local fixtures ---------------


def fake_network(monkeypatch, page_data: dict, files: list[Path]) -> None:
    monkeypatch.setattr(extract_note, "fetch_page", lambda url: (note_url(page_data), make_page(page_data)))
    queue = list(files)

    def fake_download(url, destination, referer):
        shutil.copyfile(queue.pop(0), destination)

    monkeypatch.setattr(extract_note, "download", fake_download)


def run_main(tmp_path: Path) -> tuple[dict, Path]:
    out = tmp_path / "out"
    assert extract_note.main(["http://xhslink.com/o/TESTCODE", "--output", str(out)]) == 0
    return json.loads((out / "metadata.json").read_text(encoding="utf-8")), out


def test_main_image_note_end_to_end(tmp_path, monkeypatch):
    data = image_note_data(imageList=image_note_data()["imageList"][:2])
    cards = sorted(SYNTHETIC.glob("card-*.jpg"))
    fake_network(monkeypatch, data, cards)

    meta, out = run_main(tmp_path)

    assert meta["status"] == "complete"
    assert meta["note_type"] == "normal"
    assert meta["author"] == "测试作者"
    assert meta["image_count"] == 2 and meta["live_photo_count"] == 1
    assert sorted(path.name for path in (out / "media").iterdir()) == ["image-01.jpg", "image-02.jpg"]
    assert "作者：测试作者" in (out / "caption.txt").read_text(encoding="utf-8")
    assert "奶油奶酪" in (out / "ocr.txt").read_text(encoding="utf-8")


def test_main_video_note_end_to_end(tmp_path, monkeypatch):
    fake_network(monkeypatch, video_note_data(), [SYNTHETIC / "speech.mp4"])

    meta, out = run_main(tmp_path)

    assert meta["status"] == "complete"
    assert meta["note_type"] == "video"
    assert meta["video"]["has_audio"] is True
    assert meta["transcription"]["status"] == "complete"
    assert "微波" in (out / "transcript.txt").read_text(encoding="utf-8")


def test_main_reports_failures_in_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_note, "fetch_page", lambda url: ("https://www.xiaohongshu.com/404/sec_x", make_page(None)))
    out = tmp_path / "out"

    assert extract_note.main(["http://xhslink.com/o/GONE", "--output", str(out)]) == 1
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert "unavailable" in meta["error"]
