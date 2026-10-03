"""The original extractor entry point, kept for compatibility.

xhs-library and older instructions run ``python scripts/extract_note.py <url> --output <dir>
[--keep-media]``. It now runs the shared pipeline in ``notekit`` (so it accepts any supported
link) with the original behavior: it always extracts, into --output. New code should use
``scripts/extract.py``.

The names below are re-exported so code and tests written against the single-file extractor
keep working; the implementations live in ``notekit``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notekit import pipeline  # noqa: E402
from notekit.media import (  # noqa: E402,F401
    FRAME_INTERVAL_SECONDS,
    MIN_SPEECH_CHARS,
    WHISPER_REVISIONS,
    OcrCollector,
    analyze_images,
    analyze_video,
    load_wav,
    probe_streams,
    run_ffmpeg,
    speech_warning,
    transcribe,
)
from notekit.net import USER_AGENT, download, download_first, fetch_page  # noqa: E402,F401
from notekit.pipeline import OUTPUT_FILES, extract  # noqa: E402,F401
from notekit.sources.xiaohongshu import (  # noqa: E402,F401
    Note,
    clean_desc,
    fallback_note,
    find_note_data,
    image_url,
    load_note,
    note_from_page,
    note_id_from_url,
    parse_state,
    process_images,
    process_video,
    published_date,
    stream_urls,
    unescape_url,
    video_urls,
    write_caption,
)


def main(argv: list[str] | None = None) -> int:
    return pipeline.main(argv, legacy=True)


if __name__ == "__main__":
    raise SystemExit(main())
