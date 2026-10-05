"""The interface the xhs-library project (claude/xhs-library) relies on.

xhs-library runs this repository as a separate tool. Its xhs_library/extractor_adapter.py and
tests/test_contract.py use exactly what is checked here; see "Contract with xhs-library" in
AGENTS.md. If one of these tests fails, the change breaks xhs-library: keep the old behavior,
or change both projects together.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ROOT, SYNTHETIC, image_note_data, make_page, note_url, video_note_data

from notekit import default_output_dir, net, pipeline

# Copied from xhs_library/links.py, which locates output/<key> on its own.
NOTE_ID_PATTERN = re.compile(r"\b([0-9a-f]{24})\b")


def xhs_library_link_key(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    segments = [part for part in parsed.path.split("/") if part]
    if host.endswith("xhslink.com") and segments:
        return segments[-1]
    match = NOTE_ID_PATTERN.search(parsed.path)
    if match:
        return match.group(1)
    return re.sub(r"[^0-9A-Za-z_-]", "", segments[-1]) or "note"


#: The commands xhs-library lets Claude run while it uses /note (GENERAL_SKILL_TOOLS in
#: xhs_library/other_links.py): Bash or PowerShell calls that start with one of these.
LIBRARY_ALLOWED_COMMANDS = ("python scripts/extract.py", "python scripts/validate_result.py")


def command_blocks(skill: Path) -> list[list[str]]:
    text = skill.read_text(encoding="utf-8")
    return [block.strip().splitlines() for block in re.findall(r"```(?:powershell|bash|sh)\n(.*?)```", text, re.S)]


def test_note_skill_commands_fit_the_library_allowlist():
    """A block that runs a script must be that one command alone: the library refuses a call
    that mixes in anything else (a PATH refresh, a cd), and then no result gets written."""
    blocks = command_blocks(ROOT / ".claude/skills/note/SKILL.md")
    script_blocks = [block for block in blocks if any(line.strip().startswith("python ") for line in block)]
    assert script_blocks, "the skill should show how to run the extractor and the validator"
    for block in script_blocks:
        assert len(block) == 1 and block[0].strip().startswith(LIBRARY_ALLOWED_COMMANDS), block


def test_scripts_skill_and_formats_are_where_the_library_looks():
    for relative in ("scripts/extract_note.py", "scripts/validate_result.py", ".claude/skills/xhs-note/SKILL.md"):
        assert (ROOT / relative).exists(), relative
    formats = [p.stem for p in (ROOT / ".claude/skills/xhs-note/formats").glob("*.md") if not p.name.startswith("_")]
    assert "recipe" in formats


def test_extract_note_cli_still_offers_output_and_keep_media():
    help_text = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "extract_note.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT, check=True,
    ).stdout
    assert "--output" in help_text and "--keep-media" in help_text


@pytest.mark.parametrize(
    "url",
    [
        "http://xhslink.com/o/7OKVgxAyUiN",
        "https://www.xiaohongshu.com/discovery/item/6ab7ada8000000000200daea?xsec_token=abc",
        "https://www.xiaohongshu.com/explore/6ab27abc0000000031007cc5",
    ],
)
def test_xiaohongshu_output_directory_is_output_slash_link_key(url):
    assert default_output_dir(url) == Path("output") / xhs_library_link_key(url)


@pytest.mark.parametrize("url", ["https://example.com/recipe", "https://www.reddit.com/r/GifRecipes/comments/1pokml7/slug/"])
def test_other_sources_never_land_where_the_library_scans(url):
    """The library's contract test reads every output/*/metadata.json and expects a 24-hex note ID
    and note_type "video" or "normal", so other sources must stay one level deeper."""
    directory = default_output_dir(url)
    assert len(directory.relative_to("output").parts) == 2


@pytest.mark.parametrize(
    ("url", "code", "printed"),
    [
        ("https://www.reddit.com/r/GifRecipes/comments/1pokml7/slug/", 0, str(Path("output/reddit/1pokml7"))),
        ("https://www.reddit.com/r/GifRecipes/", 2, ""),
    ],
)
def test_where_gives_the_library_its_key_or_refuses(url, code, printed):
    """OtherLinksExtractor.key_for runs `extract.py <url> --where` and keeps the path under output/;
    exit code 2 makes the library report the link as unsupported."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "extract.py"), url, "--where"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    assert (result.returncode, result.stdout.strip()) == (code, printed), result.stderr


def run_extract_note(tmp_path, monkeypatch, data, files, *flags) -> tuple[dict, Path]:
    monkeypatch.setattr(net, "fetch_page", lambda url: (note_url(data), make_page(data)))
    queue = list(files)
    monkeypatch.setattr(net, "download", lambda url, destination, referer: shutil.copyfile(queue.pop(0), destination))
    out = tmp_path / "out"
    import extract_note

    assert extract_note.main(["http://xhslink.com/o/TESTCODE", "--output", str(out), *flags]) == 0
    return json.loads((out / "metadata.json").read_text(encoding="utf-8")), out


@pytest.mark.media
@pytest.mark.usefixtures("require_ffmpeg")
def test_image_note_has_the_fields_and_files_the_library_reads(tmp_path, monkeypatch):
    data = image_note_data(imageList=image_note_data()["imageList"][:2])
    metadata, out = run_extract_note(tmp_path, monkeypatch, data, sorted(SYNTHETIC.glob("card-*.jpg")))

    assert metadata["status"] == "complete"
    assert len(metadata["note_id"]) == 24
    assert metadata["note_type"] == "normal"
    for key in ("title", "author", "published_at", "live_photo_count"):
        assert key in metadata, key
    for name in ("caption.txt", "ocr.txt", "transcript.txt"):
        assert (out / name).exists(), name
    assert sorted(p.name for p in (out / "media").glob("image-*.jpg")) == ["image-01.jpg", "image-02.jpg"]


@pytest.mark.media
@pytest.mark.usefixtures("require_ffmpeg")
def test_video_note_with_keep_media_leaves_video_audio_and_frames(tmp_path, monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL", "tiny")
    metadata, out = run_extract_note(tmp_path, monkeypatch, video_note_data(), [SYNTHETIC / "speech.mp4"], "--keep-media")

    assert metadata["status"] == "complete" and metadata["note_type"] == "video"
    assert (out / "media" / "video.mp4").exists()
    assert (out / "media" / "audio.wav").exists()
    assert list((out / "media" / "frames").glob("*.png"))


def test_failed_extraction_reports_its_error_in_metadata(tmp_path, monkeypatch):
    """The library shows metadata["error"] when extraction fails."""
    monkeypatch.setattr(net, "fetch_page", lambda url: ("https://www.xiaohongshu.com/404/sec_x", make_page(None)))
    out = tmp_path / "out"
    import extract_note

    assert extract_note.main(["http://xhslink.com/o/GONE", "--output", str(out)]) == 1
    assert "unavailable" in json.loads((out / "metadata.json").read_text(encoding="utf-8"))["error"]


def test_web_results_pass_the_same_validator(tmp_path):
    """Results for any source use the same envelope, so the library's validation keeps working."""
    from validate_result import DEFAULT_FORMATS_DIR, validate

    url = "https://example.com/recipe"
    result = {
        "format": "summary",
        "source": {"url": url, "note_id": "0123456789abcdef01234567", "title": "番茄炒蛋", "author": None,
                   "note_type": "article", "published_at": None},
        "sources_used": ["caption"],
        "data": {"title": "番茄炒蛋", "category": "美食", "one_line": "做法", "key_points": ["番茄切块"]},
        "uncertain": [],
        "missing": [],
    }
    path = tmp_path / "0123456789abcdef01234567-summary.json"
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    path.with_suffix(".md").write_text(f"# 番茄炒蛋\n\n原作者：未知\n\n原链接：[点这里]({url})\n\n正文\n", encoding="utf-8")
    assert validate(path, DEFAULT_FORMATS_DIR) == ([], [])
