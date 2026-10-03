"""Turn a link into note materials: caption/main text, transcript, OCR text, images, and metadata.

The package is split so new kinds of links can be added without touching the rest:

- ``net``: HTTP fetching and downloads
- ``media``: FFmpeg, speech transcription, and OCR, independent of where the media came from
- ``cost``: per-conversion cost tracking, expensive-conversion flags, and the cost ledger
- ``sources``: one module per kind of link (``xiaohongshu``, ``web``); see ``sources/__init__.py``
- ``pipeline``: runs a source for a URL and writes the output directory
"""

from .pipeline import default_output_dir, extract, main
from .sources import source_for

__all__ = ["default_output_dir", "extract", "main", "source_for"]
