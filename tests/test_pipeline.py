"""The extraction pipeline end to end, with the network replaced by local fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import SYNTHETIC

from notekit import cost, net, pipeline

PAGE_URL = "https://food.example.com/recipes/tuanzi"
TEXT = "焙茶团子的做法很简单。" * 30


def article(images: str = "") -> bytes:
    return f"""<html><head><title>焙茶团子</title><meta name="author" content="测试作者">
<meta property="article:published_time" content="2026-09-01"></head><body>
<nav>首页 登录 注册</nav><article><h1>焙茶团子</h1><p>{TEXT}</p>{images}<p>做好以后冷冻保存。</p></article>
<footer>版权所有</footer></body></html>""".encode("utf-8")


def fake_web(monkeypatch, body: bytes, files: dict[str, Path] | None = None, content_type="text/html; charset=utf-8"):
    calls = {"fetch": 0, "download": []}

    def fake_fetch(url, user_agent=None, headers=None):
        calls["fetch"] += 1
        cost.count("bytes_downloaded", len(body))
        return net.Response(PAGE_URL, content_type, body)

    def fake_download(url, destination, referer):
        calls["download"].append(url)
        if url not in (files or {}):
            raise RuntimeError(f"404 {url}")
        shutil.copyfile(files[url], destination)

    monkeypatch.setattr(net, "fetch", fake_fetch)
    monkeypatch.setattr(net, "download", fake_download)
    return calls


def test_web_page_without_images_needs_no_ocr(tmp_path, monkeypatch, isolated_cost_ledger):
    fake_web(monkeypatch, article())
    metadata = pipeline.extract(PAGE_URL, tmp_path / "out")
    out = tmp_path / "out"

    assert metadata["status"] == "complete", metadata.get("error")
    assert metadata["source"] == "web" and metadata["note_type"] == "article"
    assert len(metadata["note_id"]) == 24
    assert metadata["author"] == "测试作者" and metadata["published_at"] == "2026-09-01"
    assert metadata["image_count"] == 0 and metadata["ocr_lines"] == 0
    caption = (out / "caption.txt").read_text(encoding="utf-8")
    assert caption.startswith("标题：焙茶团子\n作者：测试作者")
    assert "焙茶团子的做法很简单" in caption and "登录" not in caption
    assert (out / "ocr.txt").read_text(encoding="utf-8") == ""
    assert (out / "transcript.txt").read_text(encoding="utf-8") == ""

    assert metadata["cost"]["expensive"] is False
    assert metadata["cost"]["ai_input"]["text_tokens_estimate"] > 300
    assert set(metadata["cost"]["stages"]) >= {"fetch", "parse"}
    ledger = cost.read_ledger()
    assert len(ledger) == 1 and ledger[0]["status"] == "complete" and ledger[0]["source"] == "web"


def test_unreadable_page_fails_clearly_and_is_still_logged(tmp_path, monkeypatch):
    fake_web(monkeypatch, b"<html><body><div id='app'></div><script src='app.js'></script></body></html>")
    metadata = pipeline.extract(PAGE_URL, tmp_path / "out")

    assert metadata["status"] == "failed"
    assert "JavaScript" in metadata["error"]
    assert json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))["status"] == "failed"
    assert [r["status"] for r in cost.read_ledger()] == ["failed"]


def test_short_page_gets_a_content_warning(tmp_path, monkeypatch):
    fake_web(monkeypatch, b"<html><head><title>t</title></head><body><article><p>" + "短文。".encode() * 20 + b"</p></article></body></html>")
    metadata = pipeline.extract(PAGE_URL, tmp_path / "out")
    assert metadata["status"] == "complete"
    assert "JavaScript" in metadata["content_warning"]


def test_cli_where_reuse_and_force(tmp_path, monkeypatch, capsys):
    calls = fake_web(monkeypatch, article())
    monkeypatch.chdir(tmp_path)

    assert pipeline.main([PAGE_URL, "--where"]) == 0
    where = Path(capsys.readouterr().out.strip())
    assert where.parent == Path("output/web")

    assert pipeline.main([PAGE_URL]) == 0
    assert (tmp_path / where / "metadata.json").exists() and calls["fetch"] == 1
    assert "Cost:" in capsys.readouterr().out

    assert pipeline.main([PAGE_URL]) == 0
    assert calls["fetch"] == 1, "a complete extraction is reused"
    assert "Reusing" in capsys.readouterr().out

    assert pipeline.main([PAGE_URL, "--force"]) == 0
    assert calls["fetch"] == 2


def test_legacy_cli_always_extracts_into_output(tmp_path, monkeypatch):
    """scripts/extract_note.py behaves as before: no reuse, writes where --output says."""
    calls = fake_web(monkeypatch, article())
    for _ in range(2):
        assert pipeline.main([PAGE_URL, "--output", str(tmp_path / "x")], legacy=True) == 0
    assert calls["fetch"] == 2
    assert json.loads((tmp_path / "x" / "metadata.json").read_text(encoding="utf-8"))["status"] == "complete"


def test_cli_reports_expensive_conversions(tmp_path, monkeypatch, capsys):
    policy = tmp_path / "policy.toml"
    policy.write_text("[thresholds]\nai_text_tokens = 10\n", encoding="utf-8")
    monkeypatch.setenv("NOTE_COST_POLICY", str(policy))
    fake_web(monkeypatch, article())
    assert pipeline.main([PAGE_URL, "--output", str(tmp_path / "x")]) == 0
    out = capsys.readouterr().out
    assert "EXPENSIVE conversion: large_ai_text" in out
    assert cost.read_ledger()[-1]["flags"] == ["large_ai_text"]


@pytest.mark.media
@pytest.mark.usefixtures("require_ffmpeg")
def test_web_page_images_are_downloaded_converted_and_read(tmp_path, monkeypatch):
    from PIL import Image

    icon = tmp_path / "icon.png"
    Image.new("RGB", (40, 40), "red").save(icon)
    images = (
        '<img src="/img/step1.png" width="800" height="600" alt="馅料">'
        '<img src="/img/icon.png" width="400" height="400" alt="小图标">'
        '<img src="https://cdn.example.com/step2.jpg" width="800" height="600" alt="组装">'
        '<img src="/img/missing.jpg" width="800" height="600" alt="坏链接">'
    )
    files = {
        "https://food.example.com/img/step1.png": SYNTHETIC / "card-01.jpg",
        "https://food.example.com/img/icon.png": icon,
        "https://cdn.example.com/step2.jpg": SYNTHETIC / "card-02.jpg",
    }
    fake_web(monkeypatch, article(images), files)

    metadata = pipeline.extract(PAGE_URL, tmp_path / "out")
    out = tmp_path / "out"

    assert metadata["status"] == "complete", metadata.get("error")
    assert metadata["images_found"] == 4
    assert metadata["image_count"] == 2, "the 40 px icon and the broken link are dropped"
    assert metadata["images_small"] == 1 and metadata["images_failed"] == 1
    assert sorted(p.name for p in (out / "media").iterdir()) == ["image-01.jpg", "image-02.jpg"]
    with Image.open(out / "media" / "image-01.jpg") as saved:
        assert saved.format == "JPEG"
    caption = (out / "caption.txt").read_text(encoding="utf-8")
    assert "[图 image-01：馅料]" in caption and "[图 image-02：组装]" in caption and "[图：坏链接]" in caption
    ocr = (out / "ocr.txt").read_text(encoding="utf-8").replace(" ", "")
    assert "奶油奶酪135g" in ocr and "放入无花果" in ocr
    assert metadata["cost"]["counts"]["ocr_images"] == 2
    assert metadata["cost"]["predicted"]["ocr_items"] == 2, "predicted after downloading, before OCR"


@pytest.mark.media
@pytest.mark.usefixtures("require_ffmpeg")
def test_web_images_are_capped_by_the_policy(tmp_path, monkeypatch):
    policy = tmp_path / "policy.toml"
    policy.write_text("[web]\nmax_images = 1\n", encoding="utf-8")
    monkeypatch.setenv("NOTE_COST_POLICY", str(policy))
    images = '<img src="/a.jpg" width="800" height="600"><img src="/b.jpg" width="800" height="600">'
    files = {"https://food.example.com/a.jpg": SYNTHETIC / "card-01.jpg", "https://food.example.com/b.jpg": SYNTHETIC / "card-02.jpg"}
    calls = fake_web(monkeypatch, article(images), files)

    metadata = pipeline.extract(PAGE_URL, tmp_path / "out")
    assert metadata["image_count"] == 1 and metadata["images_skipped"] == 1
    assert calls["download"] == ["https://food.example.com/a.jpg"], "skipped images are not even downloaded"
