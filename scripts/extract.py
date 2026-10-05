"""Extract any supported link (Xiaohongshu, a Reddit post, or an ordinary web page) into an output directory.

    python scripts/extract.py <url>            # writes to the default directory, reusing a complete one
    python scripts/extract.py <url> --where    # only print that directory
    python scripts/extract.py <url> --force    # extract again

The output and the cost block in metadata.json are described in notekit/sources/__init__.py
and notekit/cost.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notekit.pipeline import main  # noqa: E402

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
