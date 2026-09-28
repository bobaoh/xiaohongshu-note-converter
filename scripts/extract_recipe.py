"""Compatibility entry point: the extractor now lives in extract_note.py."""

from extract_note import main

if __name__ == "__main__":
    raise SystemExit(main())
