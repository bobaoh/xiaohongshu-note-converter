"""Track what each conversion costs, flag expensive ones, and keep a ledger.

A conversion has two costs:

- Extraction, measured here: wall time per stage (fetch, download, transcription, OCR), bytes
  downloaded, video length, and how many frames and images went through OCR.
- The AI step that formats the extracted material, estimated from what the AI has to read: the
  text in caption.txt, ocr.txt, and transcript.txt, plus the images it may look at.

Before the heavy work starts, sources call ``predict`` with what they already know (video length,
image count), so the ledger can compare predicted and actual cost. That comparison is what a future
limit on expensive conversions will be based on.

Thresholds and estimate factors live in ``cost_policy.toml``. Every conversion, including failed
ones, is appended to the ledger (``logs/conversions.jsonl``); ``scripts/cost_report.py`` summarizes it.

Code anywhere in the package reports through the module-level helpers (``count``, ``stage``,
``predict``). They do nothing when no conversion is being tracked, so the media and network
functions also work on their own.
"""

from __future__ import annotations

import contextvars
import copy
import json
import os
import re
import time
import tomllib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_FILE = ROOT / "cost_policy.toml"
DEFAULT_LEDGER = ROOT / "logs" / "conversions.jsonl"

#: Used when cost_policy.toml is missing a value. Keep in sync with cost_policy.toml.
DEFAULT_POLICY = {
    "thresholds": {
        "total_seconds": 180,
        "ocr_seconds": 120,
        "transcribe_seconds": 120,
        "video_seconds": 300,
        "ocr_items": 120,
        "download_mb": 100,
        "ai_text_tokens": 20000,
        "ai_image_tokens": 30000,
    },
    "estimates": {
        "seconds_per_ocr_frame": 1.8,
        "seconds_per_ocr_image": 6.0,
        "transcribe_seconds_per_audio_second": 0.4,
        "tokens_per_image": 1600,
    },
    "web": {
        "max_images": 8,
        "min_image_side": 200,
        "thin_text_chars": 200,
    },
}

#: Flag name for each threshold.
FLAGS = {
    "total_seconds": "slow",
    "ocr_seconds": "ocr_heavy",
    "transcribe_seconds": "transcription_heavy",
    "video_seconds": "long_video",
    "ocr_items": "many_ocr_items",
    "download_mb": "large_download",
    "ai_text_tokens": "large_ai_text",
    "ai_image_tokens": "many_ai_images",
}

_current: contextvars.ContextVar[Tracker | None] = contextvars.ContextVar("notekit_cost", default=None)


class Tracker:
    """Collects the cost of one conversion."""

    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.stages: dict[str, float] = {}
        self.counts: dict[str, float] = {}
        self.predicted: dict | None = None

    @contextmanager
    def stage(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = round(self.stages.get(name, 0.0) + time.perf_counter() - start, 2)

    def count(self, name: str, amount: float = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + amount

    def elapsed(self) -> float:
        return round(time.perf_counter() - self.started, 2)


@contextmanager
def tracking(tracker: Tracker):
    token = _current.set(tracker)
    try:
        yield tracker
    finally:
        _current.reset(token)


def count(name: str, amount: float = 1) -> None:
    tracker = _current.get()
    if tracker is not None:
        tracker.count(name, amount)


@contextmanager
def stage(name: str):
    tracker = _current.get()
    if tracker is None:
        yield
        return
    with tracker.stage(name):
        yield


def load_policy(path: Path | str | None = None) -> dict:
    """Read cost_policy.toml (or NOTE_COST_POLICY), filling gaps from DEFAULT_POLICY."""
    policy = copy.deepcopy(DEFAULT_POLICY)
    path = Path(path or os.environ.get("NOTE_COST_POLICY") or DEFAULT_POLICY_FILE)
    if path.exists():
        with path.open("rb") as handle:
            loaded = tomllib.load(handle)
        for section, values in loaded.items():
            policy.setdefault(section, {}).update(values)
    return policy


def predict(*, video_seconds: float = 0, has_audio: bool = True, ocr_images: int = 0, policy: dict | None = None) -> None:
    """Record the expected extraction cost before the heavy work starts."""
    tracker = _current.get()
    if tracker is None:
        return
    from .media import FRAME_INTERVAL_SECONDS

    estimates = (policy or load_policy())["estimates"]
    frames = int(video_seconds / FRAME_INTERVAL_SECONDS) + (1 if video_seconds else 0)
    seconds = frames * estimates["seconds_per_ocr_frame"] + ocr_images * estimates["seconds_per_ocr_image"]
    if has_audio:
        seconds += video_seconds * estimates["transcribe_seconds_per_audio_second"]
    tracker.predicted = {
        "seconds": round(seconds, 1),
        "video_seconds": round(video_seconds, 1),
        "ocr_items": frames + ocr_images,
    }


_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")


def estimate_tokens(text: str) -> int:
    """Rough token count: about one token per CJK character and per four other characters."""
    cjk = len(_CJK.findall(text))
    other = len(re.sub(r"\s", "", text)) - cjk
    return cjk + (other + 3) // 4


def summarize(tracker: Tracker, output_dir: Path, policy: dict, image_count: int = 0) -> dict:
    """The cost block written to metadata.json and the ledger."""
    texts = [
        (output_dir / name).read_text(encoding="utf-8")
        for name in ("caption.txt", "ocr.txt", "transcript.txt")
        if (output_dir / name).exists()
    ]
    text_tokens = sum(estimate_tokens(text) for text in texts)
    counts = {name: round(value, 2) for name, value in sorted(tracker.counts.items())}
    measured = {
        "total_seconds": tracker.elapsed(),
        "ocr_seconds": tracker.stages.get("ocr", 0.0),
        "transcribe_seconds": tracker.stages.get("transcribe", 0.0),
        "video_seconds": counts.get("video_seconds", 0),
        "ocr_items": counts.get("ocr_frames", 0) + counts.get("ocr_images", 0),
        "download_mb": round(counts.get("bytes_downloaded", 0) / 1024 / 1024, 2),
        "ai_text_tokens": text_tokens,
        "ai_image_tokens": image_count * policy["estimates"]["tokens_per_image"],
    }
    over = {
        FLAGS[name]: {"value": measured[name], "limit": limit}
        for name, limit in policy["thresholds"].items()
        if name in FLAGS and measured.get(name, 0) > limit
    }
    summary = {
        "expensive": bool(over),
        "flags": sorted(over),
        "over": over,
        "total_seconds": measured["total_seconds"],
        "stages": dict(sorted(tracker.stages.items())),
        "counts": counts,
        "ai_input": {
            "text_tokens_estimate": text_tokens,
            "images": image_count,
            "image_tokens_estimate": measured["ai_image_tokens"],
        },
        "predicted": tracker.predicted,
    }
    if tracker.predicted:
        limit = policy["thresholds"]["total_seconds"]
        summary["predicted"] = {**tracker.predicted, "expensive": tracker.predicted["seconds"] > limit}
    return summary


def ledger_path() -> Path | None:
    """Where the ledger goes: NOTE_COST_LEDGER, or logs/conversions.jsonl. "off" disables it."""
    value = os.environ.get("NOTE_COST_LEDGER")
    if value and value.lower() == "off":
        return None
    return Path(value) if value else DEFAULT_LEDGER


def append_ledger(record: dict) -> None:
    path = ledger_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "context": os.environ.get("NOTE_COST_CONTEXT", "cli"), **record},
        ensure_ascii=False,
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_ledger(path: Path | None = None) -> list[dict]:
    path = path or ledger_path() or DEFAULT_LEDGER
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records
