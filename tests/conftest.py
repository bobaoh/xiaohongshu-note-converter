from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic"
LOCAL = FIXTURES / "local"

sys.path.insert(0, str(ROOT / "scripts"))


def _refresh_windows_path() -> None:
    """Pick up FFmpeg installed by winget in shells that started before the installation."""
    if os.name != "nt" or shutil.which("ffmpeg"):
        return
    import winreg

    paths = []
    for hive, key in (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ):
        try:
            with winreg.OpenKey(hive, key) as handle:
                paths.append(os.path.expandvars(winreg.QueryValueEx(handle, "Path")[0]))
        except OSError:
            continue
    os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), *paths])


_refresh_windows_path()


@pytest.fixture
def require_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("FFmpeg/ffprobe is not installed")


# --- Synthetic note pages -------------------------------------------------------------
# These mirror the structure of real Xiaohongshu pages with invented IDs, URLs, and names.
# Real pages escape "/" as /, double-escape it inside the JSON-in-JSON mediaV2 field,
# and contain bare `undefined` values; the builder reproduces all three.

NOTE_URL = "https://www.xiaohongshu.com/discovery/item/{note_id}?type={type}&xsec_token=TEST"
CDN = "http://sns-webpic-qc.xhscdn.com/202601010000/abc/notes_pre_post/{file}!h5_1080jpg"
VIDEO_CDN = "http://sns-video-zl.xhscdn.com/stream/1/110/{stream}/{file}_{stream}.mp4?sign=TEST&t=1"
LIVE_CDN = "http://sns-video-zl.xhscdn.com/stream/1/10/19/{file}_19.mp4?sign=TEST&t=1"


def image_entry(file: str, live: bool = False) -> dict:
    entry = {
        "fileId": f"notes_pre_post/{file}",
        "width": 1080,
        "height": 1440,
        "url": CDN.format(file=file),
        "infoList": [
            {"imageScene": "WB_PRV", "url": CDN.format(file=file) + "_prv"},
            {"imageScene": "WB_DFT", "url": CDN.format(file=file)},
        ],
        "livePhoto": live,
        "stream": {},
    }
    if live:
        entry["stream"] = {
            "h264": [{"masterUrl": LIVE_CDN.format(file=file), "backupUrls": [], "audioCodec": "", "audioChannels": 0}],
            "h265": [],
        }
    return entry


def video_stream(stream: int, file: str, codec: str) -> dict:
    return {
        "streamType": stream,
        "videoCodec": codec,
        "audioCodec": "aac",
        "audioChannels": 2,
        "masterUrl": VIDEO_CDN.format(stream=stream, file=file),
        "backupUrls": [VIDEO_CDN.format(stream=stream, file=file).replace("sns-video-zl", "sns-bak-v10")],
    }


def image_note_data(**overrides: object) -> dict:
    data = {
        "noteId": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "type": "normal",
        "title": "做3个焙茶团子",
        "desc": "Q糯不粘牙[大笑R]\n\t\n配方：\n糯米粉 32g\n\t\n#焙茶团子[话题]# #团子[话题]#",
        "time": 1790000000000,
        "user": {"userId": "uuuuuuuuuuuuuuuuuuuuuuuu", "nickName": "测试作者", "avatar": "http://example.invalid/a.jpg"},
        "tagList": [{"name": "焙茶团子"}, {"name": "团子"}],
        "imageList": [image_entry("img01"), image_entry("img02", live=True), image_entry("img03")],
        "extraField": "UNDEFINED_PLACEHOLDER",
    }
    data.update(overrides)
    return data


def video_note_data(**overrides: object) -> dict:
    # H.265 is listed first on purpose: the extractor must still prefer H.264 with audio.
    streams = {"h265": [video_stream(520, "vid01", "hevc")], "h264": [video_stream(259, "vid01", "h264")], "av1": []}
    media_v2 = {"video_id": "1", "stream": {"h264": [{"master_url": VIDEO_CDN.format(stream=259, file="vid01"), "audio_codec": "aac"}]}}
    data = {
        "noteId": "bbbbbbbbbbbbbbbbbbbbbbbb",
        "type": "video",
        "title": "微波炉2分钟糯米皮",
        "desc": "放三天都软糯",
        "time": 1790000000000,
        "user": {"userId": "vvvvvvvvvvvvvvvvvvvvvvvv", "nickName": "视频作者"},
        "tagList": [],
        "imageList": [image_entry("cover")],
        "video": {
            "media": {"videoId": 1, "stream": streams},
            # Real pages store mediaV2 as a JSON string, so its URLs end up double-escaped.
            "mediaV2": json.dumps(media_v2).replace("/", "\\u002F"),
        },
    }
    data.update(overrides)
    return data


def make_page(note_data: dict | None) -> str:
    """Render note data the way the mobile page embeds it in window.__INITIAL_STATE__."""
    if note_data is None:
        return "<html><body><p>没有内嵌数据的页面</p></body></html>"
    state = {"global": {}, "noteData": {"data": {"noteData": note_data}}, "UseAbExpStore": {}}
    raw = json.dumps(state, ensure_ascii=False).replace("/", "\\u002F")
    raw = raw.replace('"UNDEFINED_PLACEHOLDER"', "undefined")
    return f"<html><head></head><body><script>window.__INITIAL_STATE__={raw}</script></body></html>"


def note_url(data: dict) -> str:
    return NOTE_URL.format(note_id=data["noteId"], type=data["type"])
