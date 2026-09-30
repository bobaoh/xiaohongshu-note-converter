"""Rerun the full analysis on real notes cached in tests/fixtures/local (offline, slow).

These cover cases the synthetic media cannot: real background music, Cantonese narration,
and real page structures. The cache is not committed; create it with
`python tests/fixtures/fetch_local.py`. Tests for notes that are not cached are skipped.

    python -m pytest -m "local and not slow"   # pages only, under a second
    python -m pytest -m local                  # also OCR and transcription, several minutes

Whisper uses the production default (`small`) unless TEST_WHISPER_MODEL is set, so the
results match what users get. Expect 2-4 minutes per video.
"""

from __future__ import annotations

import json
import os

import pytest
from conftest import LOCAL

import extract_note
from regression import check_expectations, load_expectations

pytestmark = [pytest.mark.local, pytest.mark.usefixtures("require_ffmpeg")]


PAGE_KEYS = ("note_type", "author", "title", "image_count", "live_photo_count", "caption_contains")


def load_cached_note(code: str):
    cache = LOCAL / code
    if not (cache / "page.html").exists():
        pytest.skip(f"{code} is not cached; run tests/fixtures/fetch_local.py")
    source = json.loads((cache / "source.json").read_text(encoding="utf-8"))
    note = extract_note.note_from_page(source["resolved_url"], (cache / "page.html").read_text(encoding="utf-8"))
    return cache, note


def page_metadata(note) -> dict:
    return {
        "note_type": note.note_type,
        "title": note.title,
        "author": note.author,
        "image_count": len(note.image_urls) if note.note_type == "normal" else None,
        "live_photo_count": note.live_photo_count,
    }


@pytest.mark.parametrize("expected", load_expectations(), ids=lambda item: item["code"])
def test_cached_page(expected, tmp_path):
    """Fast: parse the cached page only. Run after any change to page parsing."""
    _, note = load_cached_note(expected["code"])
    extract_note.write_caption(note, tmp_path)
    page_expected = {key: value for key, value in expected.items() if key in PAGE_KEYS}
    failures = check_expectations(page_expected, page_metadata(note), tmp_path)
    assert not failures, "\n".join(failures)


@pytest.mark.slow
@pytest.mark.parametrize("expected", load_expectations(), ids=lambda item: item["code"])
def test_cached_media(expected, tmp_path, monkeypatch):
    """Slow: rerun OCR and transcription on the cached media. Run after media or dependency changes."""
    cache, note = load_cached_note(expected["code"])
    monkeypatch.setenv("WHISPER_MODEL", os.environ.get("TEST_WHISPER_MODEL", "small"))
    extract_note.write_caption(note, tmp_path)
    metadata = page_metadata(note)
    if note.note_type == "video":
        work = tmp_path / "work"
        work.mkdir()
        metadata.update(extract_note.analyze_video(cache / "video.mp4", work, tmp_path))
    else:
        images = sorted((cache / "images").glob("image-*.jpg"))
        assert len(images) == len(note.image_urls), "cached images do not match the cached page; refetch"
        metadata.update(extract_note.analyze_images(images, tmp_path))

    failures = check_expectations(expected, metadata, tmp_path)
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("expected", load_expectations(), ids=lambda item: item["code"])
def test_regex_fallback_agrees_with_page_state(expected):
    """If the embedded state ever disappears, the fallback must still pick the same main video."""
    cache = LOCAL / expected["code"]
    if not (cache / "page.html").exists():
        pytest.skip(f"{expected['code']} is not cached; run tests/fixtures/fetch_local.py")
    source = json.loads((cache / "source.json").read_text(encoding="utf-8"))
    page = (cache / "page.html").read_text(encoding="utf-8")

    from_state = extract_note.note_from_page(source["resolved_url"], page)
    from_regex = extract_note.fallback_note(source["resolved_url"], page)

    assert from_regex.note_type == from_state.note_type
    if from_state.note_type == "video":
        assert from_regex.video_urls[0].split("?")[0] == from_state.video_urls[0].split("?")[0]
        assert all(not url.endswith("\\") for url in from_regex.video_urls)
    else:
        assert from_regex.video_urls == [], "Live Photo clips must not be picked up as the note video"
