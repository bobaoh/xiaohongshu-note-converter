"""Sources: one module per kind of link.

Every source turns a URL into the same output directory, so everything after extraction
(the note skill, formats, validation, the cost ledger) works the same for all of them:

- ``metadata.json``: ``status``, ``source``, ``note_id``, ``note_type``, ``title``, ``author``,
  ``published_at``, ``input_url``, ``resolved_url``, plus anything source-specific
- ``caption.txt``: the author's own text (post caption, article body)
- ``ocr.txt``: text read from images or video frames
- ``transcript.txt``: speech, if any (empty otherwise)
- ``comments.txt``: comments by readers and the author, for sources that have them
- ``media/image-NN.jpg``: images the formatting step may look at

To add a source:

1. Create ``sources/<name>.py`` with a ``Source`` subclass. Implement ``matches``, ``output_key``,
   and ``extract``; report cost with ``cost.stage``, ``cost.count``, and ``cost.predict``.
2. Register it in ``SOURCES`` below, before ``WebSource``, which accepts any http(s) link.
3. Add tests (see tests/test_web.py) and a regression link in tests/fixtures/regression_links.json.
4. Describe what the formatting step should know about it in
   ``.claude/skills/note/sources/<name>.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Job:
    """One extraction run, handed to ``Source.extract``."""

    url: str
    output_dir: Path
    work_dir: Path
    policy: dict
    metadata: dict = field(default_factory=dict)


class Source:
    #: Short name, stored as metadata["source"] and used for the output subdirectory.
    name = ""
    #: Subdirectory of output/ for this source. Xiaohongshu keeps the original flat layout.
    output_subdir = ""

    def matches(self, url: str) -> bool:
        raise NotImplementedError

    def output_key(self, url: str) -> str:
        """Directory name under the output root, derived from the URL alone (before fetching)."""
        raise NotImplementedError

    def extract(self, job: Job) -> None:
        """Fetch the link and write caption.txt, ocr.txt, transcript.txt, media/, and metadata fields."""
        raise NotImplementedError


def _sources() -> list[Source]:
    from .reddit import RedditSource
    from .web import WebSource
    from .xiaohongshu import XiaohongshuSource

    return [XiaohongshuSource(), RedditSource(), WebSource()]


SOURCES: list[Source] = _sources()


def source_for(url: str, name: str | None = None) -> Source:
    """The source for ``url``: the named one, or the first registered source that matches."""
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"Not an http(s) link: {url}")
    if name and name != "auto":
        for source in SOURCES:
            if source.name == name:
                return source
        raise ValueError(f"Unknown source {name!r}; available: {', '.join(s.name for s in SOURCES)}")
    for source in SOURCES:
        if source.matches(url):
            return source
    raise ValueError(f"No source handles {url}")
