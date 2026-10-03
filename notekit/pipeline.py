"""Run a source for a URL and write the output directory, with cost tracking."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import cost
from .sources import SOURCES, Job, source_for

OUTPUT_FILES = ("caption.txt", "transcript.txt", "ocr.txt", "metadata.json", "structured.json")


def default_output_dir(url: str, root: Path | str = "output", source: str | None = None) -> Path:
    """``output/<key>`` for Xiaohongshu (the original layout), ``output/<source>/<key>`` for the rest."""
    chosen = source_for(url, source)
    return Path(root) / chosen.output_subdir / chosen.output_key(url)


def load_complete(output_dir: Path) -> dict | None:
    metadata_path = Path(output_dir) / "metadata.json"
    if not metadata_path.exists():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return metadata if metadata.get("status") == "complete" else None


def extract(url: str, output_dir: Path | str, keep_media: bool = False, source: str | None = None) -> dict:
    """Extract ``url`` into ``output_dir`` and return its metadata (status "complete" or "failed")."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_FILES:
        (output_dir / name).unlink(missing_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="notekit-"))
    metadata: dict[str, object] = {"input_url": url, "status": "started"}
    tracker = cost.Tracker()
    policy = cost.load_policy()

    try:
        chosen = source_for(url, source)
        metadata["source"] = chosen.name
        with cost.tracking(tracker):
            chosen.extract(Job(url=url, output_dir=output_dir, work_dir=work_dir, policy=policy, metadata=metadata))
        metadata["status"] = "complete"
    except Exception as error:
        metadata["status"] = "failed"
        metadata["error"] = str(error)
    finally:
        image_count = len(list((output_dir / "media").glob("image-*.jpg")))
        metadata["cost"] = cost.summarize(tracker, output_dir, policy, image_count)
        (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        if keep_media:
            shutil.copytree(work_dir, output_dir / "media", dirs_exist_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        cost.append_ledger(
            {
                "url": url,
                "source": metadata.get("source"),
                "note_id": metadata.get("note_id"),
                "title": metadata.get("title"),
                "status": metadata["status"],
                "error": metadata.get("error"),
                "output_dir": str(output_dir),
                **metadata["cost"],
            }
        )
    return metadata


def describe_cost(metadata: dict) -> str:
    summary = metadata.get("cost") or {}
    line = f"Cost: {summary.get('total_seconds', 0):.0f}s, about {summary.get('ai_input', {}).get('text_tokens_estimate', 0)} tokens of text for the AI step."
    if summary.get("expensive"):
        details = ", ".join(f"{flag} ({over['value']} > {over['limit']})" for flag, over in summary["over"].items())
        line += f"\nEXPENSIVE conversion: {details}. See cost_policy.toml and scripts/cost_report.py."
    return line


def main(argv: list[str] | None = None, legacy: bool = False) -> int:
    """Command line for scripts/extract.py (``legacy=False``) and scripts/extract_note.py (``legacy=True``).

    The legacy entry point keeps the original behavior that xhs-library relies on: it always
    extracts, into the directory given by --output.
    """
    parser = argparse.ArgumentParser(
        description="Extract the text, speech, and on-screen or image text from a link. "
        f"Sources: {', '.join(s.name for s in SOURCES)} (picked from the URL)."
    )
    parser.add_argument("url", help="A Xiaohongshu/RedNote/xhslink.com link or any http(s) web page")
    parser.add_argument(
        "--output",
        help="Directory for caption, transcript, OCR, and metadata (default: output/<key> for Xiaohongshu, "
        "output/<source>/<key> for other sources)",
    )
    parser.add_argument("--keep-media", action="store_true", help="Keep the downloaded video, audio, and frames")
    parser.add_argument("--source", default="auto", choices=["auto", *(s.name for s in SOURCES)], help="Force a source")
    if not legacy:
        parser.add_argument("--force", action="store_true", help="Extract again even if a complete extraction exists")
        parser.add_argument("--where", action="store_true", help="Only print the default output directory")
    args = parser.parse_args(argv)

    try:
        output_dir = Path(args.output) if args.output else default_output_dir(args.url, source=args.source)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if not legacy:
        if args.where:
            print(output_dir)
            return 0
        existing = load_complete(output_dir)
        if existing and not args.force:
            print(f"Reusing the complete extraction in {output_dir.resolve()} (use --force to extract again).")
            print(describe_cost(existing))
            return 0

    metadata = extract(args.url, output_dir, keep_media=args.keep_media, source=args.source)
    if metadata["status"] != "complete":
        print(f"ERROR: {metadata.get('error')}", file=sys.stderr)
        print(describe_cost(metadata))
        return 1
    print(
        f"Complete ({metadata.get('source')} {metadata.get('note_type')} note). "
        f"Read caption.txt, transcript.txt, and ocr.txt in {Path(output_dir).resolve()}"
    )
    print(describe_cost(metadata))
    return 0
