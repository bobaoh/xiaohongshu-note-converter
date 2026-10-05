"""Live regression: extract the known test links (Xiaohongshu, web pages, Reddit) and check the results.

Run this before merging changes to the extractor. It needs network access and takes
several minutes because two of the notes are videos, and Reddit allows about one request
per minute.

    python scripts/regression.py            # all notes
    python scripts/regression.py 9mo7le3NAf # one note

Exit codes: 0 all passed, 1 at least one check failed, 2 no failures but some links
were unavailable (the note was removed, went private, or the network failed).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notekit import pipeline  # noqa: E402

EXPECTATIONS_FILE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "regression_links.json"
UNAVAILABLE_MARKERS = (
    "unavailable", "timed out", "urlopen error", "getaddrinfo", "connection", "http error 4", "http error 5",
    "(http 4", "(http 5", "rate limit", "was not found",  # Reddit's messages
)


def load_expectations() -> list[dict]:
    return json.loads(EXPECTATIONS_FILE.read_text(encoding="utf-8"))


def check_expectations(expected: dict, metadata: dict, output_dir: Path) -> list[str]:
    """Compare one extraction against its expectations; return human-readable failures."""
    failures = []

    def read(name: str) -> str:
        path = output_dir / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    for key in ("source", "note_type", "post_kind", "author", "title", "image_count", "live_photo_count"):
        if key in expected and metadata.get(key) != expected[key]:
            failures.append(f"{key}: expected {expected[key]!r}, got {metadata.get(key)!r}")
    if "has_audio" in expected and (metadata.get("video") or {}).get("has_audio") != expected["has_audio"]:
        failures.append(f"has_audio: expected {expected['has_audio']}, got {(metadata.get('video') or {}).get('has_audio')}")

    if "min_text_chars" in expected and (metadata.get("text_chars") or 0) < expected["min_text_chars"]:
        failures.append(f"text_chars: expected >= {expected['min_text_chars']}, got {metadata.get('text_chars')}")
    missing_types = set(expected.get("structured_types", [])) - set(metadata.get("structured_types") or [])
    if missing_types:
        failures.append(f"structured_types: missing {sorted(missing_types)}, got {metadata.get('structured_types')}")

    transcription = metadata.get("transcription") or {}
    if "speech_warning" in expected and ("warning" in transcription) != expected["speech_warning"]:
        failures.append(f"speech_warning: expected {expected['speech_warning']}, transcription={transcription}")
    if "min_transcript_lines" in expected and (transcription.get("lines") or 0) < expected["min_transcript_lines"]:
        failures.append(f"transcript lines: expected >= {expected['min_transcript_lines']}, got {transcription.get('lines')}")

    for file_name, key in (
        ("caption.txt", "caption_contains"),
        ("ocr.txt", "ocr_contains"),
        ("transcript.txt", "transcript_contains"),
        ("comments.txt", "comments_contains"),
    ):
        text = read(file_name).replace(" ", "")
        for needle in expected.get(key, []):
            if needle.replace(" ", "") not in text:
                failures.append(f"{file_name} does not contain {needle!r}")
    for needle in expected.get("comments_exclude", []):
        if needle in read("comments.txt"):
            failures.append(f"comments.txt should not contain {needle!r}")
    return failures


def run_one(expected: dict, keep: Path | None) -> tuple[str, list[str]]:
    output_dir = (keep / expected["code"]) if keep else Path(tempfile.mkdtemp(prefix=f"note-regression-{expected['code']}-"))
    try:
        metadata = pipeline.extract(expected["url"], output_dir)
        if metadata["status"] != "complete":
            error = str(metadata.get("error", ""))
            status = "UNAVAILABLE" if any(marker in error.lower() for marker in UNAVAILABLE_MARKERS) else "FAIL"
            return status, [f"extraction failed: {error}"]
        failures = check_expectations(expected, metadata, output_dir)
        return ("FAIL" if failures else "PASS"), failures
    finally:
        if not keep:
            shutil.rmtree(output_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the live extraction regression.")
    parser.add_argument("codes", nargs="*", help="Short codes to run (default: all)")
    parser.add_argument("--keep", type=Path, help="Keep outputs in this directory instead of a temp directory")
    args = parser.parse_args(argv)
    os.environ.setdefault("NOTE_COST_CONTEXT", "regression")

    expectations = [item for item in load_expectations() if not args.codes or item["code"] in args.codes]
    statuses = []
    for expected in expectations:
        print(f"--- {expected['code']}: {expected['covers']}", flush=True)
        status, failures = run_one(expected, args.keep)
        statuses.append(status)
        print(f"{status} {expected['code']}")
        for failure in failures:
            print(f"    {failure}")

    print(f"\n{statuses.count('PASS')} passed, {statuses.count('FAIL')} failed, {statuses.count('UNAVAILABLE')} unavailable")
    if "FAIL" in statuses:
        return 1
    return 2 if "UNAVAILABLE" in statuses else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
