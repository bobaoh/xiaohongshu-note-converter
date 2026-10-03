"""scripts/cost_report.py over a synthetic ledger."""

from __future__ import annotations

import json

import cost_report


def record(time, source, seconds, flags=(), status="complete", predicted=None, stages=None, tokens=500, context="cli"):
    return {
        "time": time, "context": context, "url": f"https://{source}/{time}", "source": source, "title": "t",
        "status": status, "total_seconds": seconds, "expensive": bool(flags), "flags": list(flags),
        "over": {flag: {"value": seconds, "limit": 180} for flag in flags},
        "stages": stages or {"ocr": seconds * 0.8, "fetch": seconds * 0.2},
        "ai_input": {"text_tokens_estimate": tokens}, "predicted": predicted,
    }


LEDGER = [
    record("2026-10-01T10:00", "xiaohongshu", 240, flags=["slow", "ocr_heavy"], predicted={"seconds": 200}),
    record("2026-10-02T10:00", "xiaohongshu", 30, predicted={"seconds": 33}),
    record("2026-10-02T11:00", "web", 4, tokens=25000, flags=["large_ai_text"], stages={"fetch": 1, "parse": 3}),
    record("2026-10-03T09:00", "web", 2, status="failed", context="regression"),
]


def write_ledger(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in LEDGER) + "\n", encoding="utf-8")
    return path


def test_summary_counts_flags_stages_sources_and_prediction_error():
    summary = cost_report.summarize(LEDGER)
    assert summary["conversions"] == 4 and summary["failed"] == 1 and summary["expensive"] == 2
    assert summary["flags"] == {"slow": 1, "ocr_heavy": 1, "large_ai_text": 1}
    assert next(iter(summary["stage_share"])) == "ocr", "OCR dominates this ledger"
    assert summary["by_source"]["web"]["conversions"] == 1, "failed conversions are not in the per-source medians"
    assert summary["by_source"]["web"]["median_ai_text_tokens"] == 25000
    # |240-200|/240 = 0.17 and |30-33|/30 = 0.10 -> median 0.13; absolute misses 40 s and 3 s
    assert summary["prediction"] == {"compared": 2, "median_abs_seconds": 21.5, "compared_relative": 2, "median_error": 0.13}


def test_short_conversions_are_left_out_of_the_relative_prediction_error():
    short = [record("2026-10-04T10:00", "web", 1, predicted={"seconds": 6})]
    prediction = cost_report.summarize(short)["prediction"]
    assert prediction == {"compared": 1, "median_abs_seconds": 5, "compared_relative": 0, "median_error": None}


def test_most_expensive_puts_more_flags_first():
    ranked = cost_report.most_expensive(LEDGER, 2)
    assert [r["flags"] for r in ranked] == [["slow", "ocr_heavy"], ["large_ai_text"]]


def test_filters_by_date_and_context():
    assert len(cost_report.select(LEDGER, "2026-10-02", None)) == 3
    assert [r["context"] for r in cost_report.select(LEDGER, None, "regression")] == ["regression"]


def test_cli_text_and_json(tmp_path, capsys):
    path = write_ledger(tmp_path)
    assert cost_report.main(["--ledger", str(path), "--expensive"]) == 0
    out = capsys.readouterr().out
    assert "4 conversions, 1 failed, 2 flagged expensive" in out
    assert "slow 240>180" in out and "Where the time goes: ocr" in out

    assert cost_report.main(["--ledger", str(path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["expensive"] == 2 and len(data["expensive"]) == 2


def test_empty_ledger(tmp_path, capsys):
    assert cost_report.main(["--ledger", str(tmp_path / "none.jsonl")]) == 0
    assert "No conversions recorded yet." in capsys.readouterr().out
