"""Cost tracking, expensive-conversion flags, prediction, and the ledger (notekit.cost)."""

from __future__ import annotations

import copy

import pytest

from notekit import cost


def test_helpers_do_nothing_outside_a_tracked_conversion():
    cost.count("ocr_images", 3)
    with cost.stage("ocr"):
        pass
    cost.predict(video_seconds=100)  # no error, nothing recorded anywhere


def test_tracker_accumulates_stages_and_counts():
    tracker = cost.Tracker()
    with cost.tracking(tracker):
        cost.count("ocr_images", 2)
        cost.count("ocr_images", 3)
        with cost.stage("ocr"):
            pass
        with cost.stage("ocr"):
            pass
    assert tracker.counts == {"ocr_images": 5}
    assert set(tracker.stages) == {"ocr"} and tracker.stages["ocr"] >= 0
    cost.count("ocr_images", 100)
    assert tracker.counts["ocr_images"] == 5, "tracking ends when the context exits"


def test_estimate_tokens_counts_cjk_characters_individually():
    assert cost.estimate_tokens("番茄炒蛋") == 4
    assert cost.estimate_tokens("abcdefgh") == 2
    assert cost.estimate_tokens("番茄 tomato") == 2 + 2
    assert cost.estimate_tokens("") == 0


def write_outputs(directory, caption="", ocr="", transcript=""):
    for name, text in (("caption.txt", caption), ("ocr.txt", ocr), ("transcript.txt", transcript)):
        (directory / name).write_text(text, encoding="utf-8")


def test_cheap_conversion_is_not_flagged(tmp_path):
    write_outputs(tmp_path, caption="番茄炒蛋，很简单。")
    tracker = cost.Tracker()
    summary = cost.summarize(tracker, tmp_path, cost.load_policy(), image_count=2)
    assert summary["expensive"] is False and summary["flags"] == []
    # 7 CJK characters, plus the two full-width punctuation marks counted as other characters.
    assert summary["ai_input"] == {"text_tokens_estimate": 8, "images": 2, "image_tokens_estimate": 3200}


def test_each_threshold_raises_its_own_flag(tmp_path):
    write_outputs(tmp_path, caption="字" * 300)
    policy = copy.deepcopy(cost.load_policy())
    policy["thresholds"].update(ai_text_tokens=100, ocr_items=5, video_seconds=60, download_mb=1, ai_image_tokens=1000)
    tracker = cost.Tracker()
    tracker.counts.update(ocr_frames=4, ocr_images=2, video_seconds=90, bytes_downloaded=3 * 1024 * 1024)
    summary = cost.summarize(tracker, tmp_path, policy, image_count=1)
    assert summary["expensive"] is True
    assert summary["flags"] == ["large_ai_text", "large_download", "long_video", "many_ai_images", "many_ocr_items"]
    assert summary["over"]["many_ocr_items"] == {"value": 6, "limit": 5}


def test_prediction_for_a_video_uses_frames_and_transcription(tmp_path):
    tracker = cost.Tracker()
    with cost.tracking(tracker):
        cost.predict(video_seconds=150)
    # 101 frames (one every 1.5 s, plus the first) at 1.8 s, plus 150 s of audio at 0.4.
    assert tracker.predicted == {"seconds": 241.8, "video_seconds": 150, "ocr_items": 101}
    write_outputs(tmp_path)
    summary = cost.summarize(tracker, tmp_path, cost.load_policy())
    assert summary["predicted"]["expensive"] is True, "241.8 s is over the 180 s total_seconds threshold"


def test_prediction_for_images_and_silent_video():
    tracker = cost.Tracker()
    with cost.tracking(tracker):
        cost.predict(ocr_images=10)
    assert tracker.predicted["seconds"] == 60.0
    with cost.tracking(tracker):
        cost.predict(video_seconds=15, has_audio=False)
    assert tracker.predicted["seconds"] == 11 * 1.8


def test_policy_file_overrides_defaults(tmp_path, monkeypatch):
    policy_file = tmp_path / "policy.toml"
    policy_file.write_text("[thresholds]\ntotal_seconds = 5\n", encoding="utf-8")
    monkeypatch.setenv("NOTE_COST_POLICY", str(policy_file))
    policy = cost.load_policy()
    assert policy["thresholds"]["total_seconds"] == 5
    assert policy["thresholds"]["ocr_seconds"] == cost.DEFAULT_POLICY["thresholds"]["ocr_seconds"]


def test_repository_policy_matches_the_built_in_defaults():
    """cost_policy.toml and DEFAULT_POLICY describe the same values, so neither silently drifts."""
    import tomllib

    with cost.DEFAULT_POLICY_FILE.open("rb") as handle:
        assert tomllib.load(handle) == cost.DEFAULT_POLICY


def test_every_threshold_has_a_flag():
    assert set(cost.DEFAULT_POLICY["thresholds"]) == set(cost.FLAGS)


def test_ledger_round_trip_and_off_switch(isolated_cost_ledger, monkeypatch):
    cost.append_ledger({"url": "https://a", "expensive": True})
    cost.append_ledger({"url": "https://b", "expensive": False})
    records = cost.read_ledger()
    assert [r["url"] for r in records] == ["https://a", "https://b"]
    assert all(r["context"] == "test" and r["time"] for r in records)

    isolated_cost_ledger.write_text(isolated_cost_ledger.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    assert len(cost.read_ledger()) == 2, "a damaged line is skipped, not fatal"

    monkeypatch.setenv("NOTE_COST_LEDGER", "off")
    cost.append_ledger({"url": "https://c"})
    assert cost.ledger_path() is None


@pytest.mark.parametrize("value", ["", None])
def test_ledger_defaults_to_logs(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("NOTE_COST_LEDGER", raising=False)
    else:
        monkeypatch.setenv("NOTE_COST_LEDGER", value)
    assert cost.ledger_path() == cost.DEFAULT_LEDGER
