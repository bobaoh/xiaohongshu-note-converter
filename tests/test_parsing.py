from __future__ import annotations

import pytest
from conftest import image_note_data, make_page, note_url, video_note_data

import extract_note
from extract_note import (
    clean_desc,
    note_from_page,
    note_id_from_url,
    published_date,
    speech_warning,
    stream_urls,
    unescape_url,
    write_caption,
)


def test_image_note_uses_only_its_own_images_and_counts_live_photos():
    data = image_note_data()
    note = note_from_page(note_url(data), make_page(data))

    assert note.source == "initial_state"
    assert note.note_type == "normal"
    assert note.note_id == data["noteId"]
    assert len(note.image_urls) == 3
    assert all("_prv" not in url for url in note.image_urls), "should pick WB_DFT, not the preview scene"
    assert note.live_photo_count == 1
    assert note.video_urls == [], "a Live Photo clip must never become the note's video"


def test_image_note_metadata_fields():
    data = image_note_data()
    note = note_from_page(note_url(data), make_page(data))

    assert note.title == "做3个焙茶团子"
    assert note.author == "测试作者"
    assert note.author_id == data["user"]["userId"]
    assert note.published_at == published_date(data["time"])
    assert note.tags == ["焙茶团子", "团子"]
    assert "[大笑R]" not in note.desc and "[话题]" not in note.desc
    assert "#焙茶团子" in note.desc


def test_empty_title_falls_back_to_first_caption_line():
    data = image_note_data(title="", desc="\n人均500 上海2天攻略\n第二行")
    note = note_from_page(note_url(data), make_page(data))
    assert note.title == "人均500 上海2天攻略"


def test_video_note_prefers_h264_with_audio_and_keeps_backups():
    data = video_note_data()
    note = note_from_page(note_url(data), make_page(data))

    assert note.note_type == "video"
    assert note.author == "视频作者"
    assert note.video_urls[0].endswith("_259.mp4?sign=TEST&t=1"), note.video_urls
    assert any("sns-bak-v10" in url for url in note.video_urls), "backup URLs should be kept as fallbacks"
    assert any("_520.mp4" in url for url in note.video_urls), "H.265 stays available after H.264"
    assert all("\\" not in url for url in note.video_urls)


def test_stream_urls_put_streams_without_audio_last():
    streams = {
        "h264": [{"masterUrl": "http://x/silent.mp4", "audioCodec": "", "audioChannels": 0}],
        "h265": [{"masterUrl": "http://x/with-audio.mp4", "audioCodec": "aac"}],
    }
    assert stream_urls(streams) == ["http://x/with-audio.mp4", "http://x/silent.mp4"]


def test_unescape_handles_single_and_double_escaping():
    assert unescape_url("http:\\u002F\\u002Fa.com\\u002Fb.mp4") == "http://a.com/b.mp4"
    assert unescape_url("http:\\\\u002F\\\\u002Fa.com\\\\u002Fb.mp4") == "http://a.com/b.mp4"
    assert unescape_url("http:\\/\\/a.com") == "http://a.com"


def test_page_without_state_uses_regex_fallback_and_skips_live_photos():
    page = (
        '<html><script>var a = "http:\\\\u002F\\\\u002Fsns-video-zl.xhscdn.com\\\\u002Fstream\\\\u002F1\\\\u002F110\\\\u002F259'
        '\\\\u002Fvid_259.mp4?sign=1";'
        ' var b = "http://sns-video-zl.xhscdn.com/stream/1/10/19/live_19.mp4?sign=2";</script></html>'
    )
    note = note_from_page("https://www.xiaohongshu.com/discovery/item/cccccccccccccccccccccccc?type=video", page)

    assert note.source == "regex_fallback"
    assert note.note_type == "video"
    assert note.note_id == "cccccccccccccccccccccccc"
    assert note.video_urls == ["http://sns-video-zl.xhscdn.com/stream/1/110/259/vid_259.mp4?sign=1"]


def test_regex_fallback_does_not_keep_the_backslash_before_an_escaped_quote():
    # Inside mediaV2, real pages quote URLs as \"...\", so a naive match ends in "\".
    page = '<html><script>x = "{\\"master_url\\":\\"http:\\u002F\\u002Fsns-video-zl.xhscdn.com\\u002Fa_259.mp4?sign=1&t=2\\",\\"b\\":1}"</script></html>'
    note = note_from_page("https://www.xiaohongshu.com/discovery/item/cccccccccccccccccccccccc?type=video", page)
    assert note.video_urls == ["http://sns-video-zl.xhscdn.com/a_259.mp4?sign=1&t=2"]


def test_regex_fallback_prefers_primary_host_over_backup():
    page = (
        '<html><script>a = "http://sns-bak-v10.xhscdn.com/stream/1/110/259/v_259.mp4";'
        ' b = "http://sns-video-zl.xhscdn.com/stream/1/110/259/v_259.mp4?sign=1";</script></html>'
    )
    note = note_from_page("https://www.xiaohongshu.com/discovery/item/cccccccccccccccccccccccc?type=video", page)
    assert note.video_urls[0].startswith("http://sns-video-zl.")


def test_unavailable_note_raises_a_clear_error():
    with pytest.raises(RuntimeError, match="unavailable"):
        note_from_page("https://www.xiaohongshu.com/404/sec_abc?source=x", make_page(None))


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.xiaohongshu.com/discovery/item/6ab7ada8000000000200daea?type=normal", "6ab7ada8000000000200daea"),
        ("https://www.xiaohongshu.com/explore/6ab7ada8000000000200daea", "6ab7ada8000000000200daea"),
        ("https://www.xiaohongshu.com/404/sec_abc", ""),
    ],
)
def test_note_id_from_url(url, expected):
    assert note_id_from_url(url) == expected


def test_published_date_rejects_missing_values():
    assert published_date(None) is None
    assert published_date(0) is None
    assert published_date("1790000000000") is None
    assert len(published_date(1790000000000)) == 10


def test_clean_desc_strips_topic_markers_and_emoji_codes():
    assert clean_desc("好吃[派对R]\t\n#团子[话题]# ") == "好吃\n#团子"


@pytest.mark.parametrize(
    ("probability", "texts", "warns"),
    [
        (0.43, ["You"], True),  # music-only video: Whisper hallucinated "You"
        (0.29, [], True),  # nothing recognized
        (0.98, ["嗯"], True),  # confident language, but almost no text
        (0.99, ["今天作被查团子 糯米粉32克 牛奶70克", "放進微波爐 高火加熱2分鐘"], False),  # short real narration, 2 segments
        (0.98, ["一"] * 40, False),
    ],
)
def test_speech_warning(probability, texts, warns):
    assert (speech_warning(probability, texts) is not None) is warns


def write_wav(path, rate=16000, channels=1, samples=(0, 16384, -32768)):
    import struct
    import wave

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(struct.pack("<h", value) for value in samples) * channels)


def test_whisper_revisions_are_pinned_commit_ids():
    import re

    for model in ("tiny", "small"):  # the test default and the production default
        assert model in extract_note.WHISPER_REVISIONS
    for model, revision in extract_note.WHISPER_REVISIONS.items():
        assert re.fullmatch(r"[0-9a-f]{40}", revision), f"{model}: {revision!r} is not a commit ID"


def test_load_wav_returns_float_samples(tmp_path):
    write_wav(tmp_path / "a.wav")
    samples = extract_note.load_wav(tmp_path / "a.wav")
    assert samples.dtype.name == "float32"
    assert samples.tolist() == [0.0, 0.5, -1.0]


def test_load_wav_rejects_unexpected_formats(tmp_path):
    write_wav(tmp_path / "stereo.wav", rate=44100, channels=2)
    with pytest.raises(RuntimeError, match="16 kHz mono"):
        extract_note.load_wav(tmp_path / "stereo.wav")


def test_write_caption_includes_title_author_and_tags(tmp_path):
    data = image_note_data()
    note = note_from_page(note_url(data), make_page(data))
    write_caption(note, tmp_path)
    caption = (tmp_path / "caption.txt").read_text(encoding="utf-8")

    assert caption.startswith("标题：做3个焙茶团子\n\n作者：测试作者")
    assert caption.rstrip().endswith("标签：#焙茶团子 #团子")


def test_aliases_expose_the_same_entry_point():
    import extract_post
    import extract_recipe

    assert extract_recipe.main is extract_note.main
    assert extract_post.main is extract_note.main
