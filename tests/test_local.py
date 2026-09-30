"""Rerun the full analysis on real notes cached in tests/fixtures/local (offline, slow).

These cover cases the synthetic media cannot: real background music, Cantonese narration,
and real page structures. The cache is not committed; create it with
`python tests/fixtures/fetch_local.py`. Tests for notes that are not cached are skipped.

    python -m pytest -m local

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


@pytest.mark.parametrize("expected", load_expectations(), ids=lambda item: item["code"])
def test_cached_note(expected, tmp_path, monkeypatch):
    cache = LOCAL / expected["code"]
    if not (cache / "page.html").exists():
        pytest.skip(f"{expected['code']} is not cached; run tests/fixtures/fetch_local.py")
    monkeypatch.setenv("WHISPER_MODEL", os.environ.get("TEST_WHISPER_MODEL", "small"))

    source = json.loads((cache / "source.json").read_text(encoding="utf-8"))
    note = extract_note.note_from_page(source["resolved_url"], (cache / "page.html").read_text(encoding="utf-8"))
    extract_note.write_caption(note, tmp_path)
    metadata = {
        "note_type": note.note_type,
        "title": note.title,
        "author": note.author,
        "live_photo_count": note.live_photo_count,
    }
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
