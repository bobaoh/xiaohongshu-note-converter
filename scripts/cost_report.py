"""Summarize the conversion cost ledger (logs/conversions.jsonl).

    python scripts/cost_report.py                 # summary of every conversion
    python scripts/cost_report.py --expensive     # only the flagged ones, most expensive first
    python scripts/cost_report.py --since 2026-10-01 --context cli
    python scripts/cost_report.py --json          # machine-readable summary

The report answers three questions:
- Which conversions were expensive, and which thresholds did they cross?
- Where does the time go (stage shares), per source?
- How good are the predictions? They are what a future limit on expensive conversions will use;
  when they drift, adjust the factors in cost_policy.toml.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notekit import cost  # noqa: E402

MIN_SECONDS_FOR_RELATIVE_ERROR = 30


def select(records: list[dict], since: str | None, context: str | None) -> list[dict]:
    return [
        r for r in records
        if (not since or str(r.get("time", "")) >= since) and (not context or r.get("context") == context)
    ]


def summarize(records: list[dict]) -> dict:
    complete = [r for r in records if r.get("status") == "complete"]
    expensive = [r for r in records if r.get("expensive")]
    stage_totals: dict[str, float] = defaultdict(float)
    for record in complete:
        for name, seconds in (record.get("stages") or {}).items():
            stage_totals[name] += seconds
    total_stage_seconds = sum(stage_totals.values()) or 1
    by_source: dict[str, list[dict]] = defaultdict(list)
    for record in complete:
        by_source[record.get("source") or "?"].append(record)

    predicted = [r for r in complete if r.get("predicted") and r.get("total_seconds")]
    absolute = [abs(r["total_seconds"] - r["predicted"]["seconds"]) for r in predicted]
    # Relative error only for conversions long enough to matter: a 5 s miss on a 1 s page is 500%.
    errors = [
        abs(r["total_seconds"] - r["predicted"]["seconds"]) / r["total_seconds"]
        for r in predicted
        if r["total_seconds"] >= MIN_SECONDS_FOR_RELATIVE_ERROR
    ]
    return {
        "conversions": len(records),
        "failed": len(records) - len(complete),
        "expensive": len(expensive),
        "flags": dict(Counter(flag for r in records for flag in r.get("flags") or []).most_common()),
        "stage_share": {name: round(seconds / total_stage_seconds, 3) for name, seconds in sorted(stage_totals.items(), key=lambda kv: -kv[1])},
        "by_source": {
            source: {
                "conversions": len(items),
                "median_seconds": round(statistics.median(r.get("total_seconds", 0) for r in items), 1),
                "median_ai_text_tokens": statistics.median((r.get("ai_input") or {}).get("text_tokens_estimate", 0) for r in items),
                "expensive": sum(1 for r in items if r.get("expensive")),
            }
            for source, items in sorted(by_source.items())
        },
        "prediction": {
            "compared": len(predicted),
            "median_abs_seconds": round(statistics.median(absolute), 1) if absolute else None,
            "compared_relative": len(errors),
            "median_error": round(statistics.median(errors), 2) if errors else None,
        },
    }


def most_expensive(records: list[dict], limit: int) -> list[dict]:
    return sorted(records, key=lambda r: (len(r.get("flags") or []), r.get("total_seconds", 0)), reverse=True)[:limit]


def print_report(records: list[dict], summary: dict, only_expensive: bool, limit: int) -> None:
    print(f"{summary['conversions']} conversions, {summary['failed']} failed, {summary['expensive']} flagged expensive")
    if summary["flags"]:
        print("Flags: " + ", ".join(f"{flag} ×{n}" for flag, n in summary["flags"].items()))
    if summary["stage_share"]:
        print("Where the time goes: " + ", ".join(f"{name} {share:.0%}" for name, share in summary["stage_share"].items()))
    for source, info in summary["by_source"].items():
        print(
            f"  {source}: {info['conversions']} complete, median {info['median_seconds']}s, "
            f"median {info['median_ai_text_tokens']:.0f} AI text tokens, {info['expensive']} expensive"
        )
    prediction = summary["prediction"]
    if prediction["compared"]:
        line = f"Prediction: median miss {prediction['median_abs_seconds']}s over {prediction['compared']} conversions"
        if prediction["median_error"] is not None:
            line += (f"; {prediction['median_error']:.0%} median error over the {prediction['compared_relative']} "
                     f"that took {MIN_SECONDS_FOR_RELATIVE_ERROR}s or more")
        print(line)

    shown = [r for r in records if r.get("expensive")] if only_expensive else records
    if not shown:
        return
    print(f"\n{'Most expensive' if only_expensive else 'Conversions'} (up to {limit}):")
    for record in most_expensive(shown, limit):
        flags = ", ".join(
            f"{flag} {over['value']}>{over['limit']}" for flag, over in (record.get("over") or {}).items()
        ) or "-"
        title = (record.get("title") or "")[:30]
        print(f"  {record.get('time', '')[:16]}  {record.get('total_seconds', 0):>6.0f}s  {record.get('status', ''):8}  {flags}")
        print(f"      {record.get('source')}  {title}  {record.get('url')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize the conversion cost ledger.")
    parser.add_argument("--ledger", type=Path, help="Ledger file (default: NOTE_COST_LEDGER or logs/conversions.jsonl)")
    parser.add_argument("--expensive", action="store_true", help="List only flagged conversions")
    parser.add_argument("--since", help="Only conversions at or after this ISO date or time")
    parser.add_argument("--context", help="Only conversions with this context (cli, regression, test, ...)")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Print the summary as JSON")
    args = parser.parse_args(argv)

    records = select(cost.read_ledger(args.ledger), args.since, args.context)
    summary = summarize(records)
    if args.json:
        print(json.dumps({"summary": summary, "expensive": most_expensive([r for r in records if r.get("expensive")], args.limit)},
                         ensure_ascii=False, indent=2))
    elif not records:
        print("No conversions recorded yet.")
    else:
        print_report(records, summary, args.expensive, args.limit)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
