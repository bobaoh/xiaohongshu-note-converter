from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from validate_result import DEFAULT_FORMATS_DIR, field_table, validate

URL = "http://xhslink.com/o/TESTCODE"
GOOD_RESULT = {
    "format": "recipe",
    "source": {
        "url": URL,
        "note_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "title": "做3个焙茶团子",
        "author": "测试作者",
        "note_type": "normal",
        "published_at": "2026-09-26",
    },
    "sources_used": ["caption", "ocr"],
    "data": {
        "title": "焙茶团子",
        "duration": None,
        "servings": "3 个",
        "ingredient_groups": [{"name": "团子皮", "items": [{"name": "糯米粉", "amount": "32g"}]}],
        "method": [{"section": None, "steps": ["混合过筛"]}],
        "variations": [],
        "tips": ["冷冻保存"],
    },
    "uncertain": [],
    "missing": ["总用时"],
}
GOOD_MARKDOWN = f"# 焙茶团子\n\n原作者：测试作者\n\n原链接：[点这里]({URL})\n\n## 配料\n- 糯米粉：32g\n"


def write_result(tmp_path: Path, result: dict, markdown: str | None = GOOD_MARKDOWN) -> Path:
    path = tmp_path / "aaaaaaaaaaaaaaaaaaaaaaaa-recipe.json"
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if markdown is not None:
        path.with_suffix(".md").write_text(markdown, encoding="utf-8")
    return path


def run(tmp_path: Path, result: dict = GOOD_RESULT, markdown: str | None = GOOD_MARKDOWN) -> tuple[list[str], list[str]]:
    return validate(write_result(tmp_path, result, markdown), DEFAULT_FORMATS_DIR)


def mutated(**changes) -> dict:
    result = copy.deepcopy(GOOD_RESULT)
    for dotted, value in changes.items():
        target = result
        *parents, key = dotted.split("__")
        for parent in parents:
            target = target[parent]
        if value is DELETE:
            del target[key]
        else:
            target[key] = value
    return result


DELETE = object()


def test_good_result_passes(tmp_path):
    assert run(tmp_path) == ([], [])


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"source__note_id": ""}, "source.note_id"),
        ({"source__author": DELETE}, "source.author"),
        ({"sources_used": ["caption", "video"]}, "未知来源"),
        ({"missing": DELETE}, "missing"),
        ({"data__method": DELETE}, "必填字段 method"),
        ({"data__ingredient_groups": "糯米粉 32g"}, "data.ingredient_groups 应为 array"),
        ({"format": "travel"}, "找不到格式文件"),
    ],
)
def test_broken_results_are_rejected(tmp_path, changes, message):
    errors, _ = run(tmp_path, mutated(**changes))
    assert any(message in error for error in errors), errors


def test_extra_and_empty_fields_only_warn(tmp_path):
    errors, warnings = run(tmp_path, mutated(data__tips=[], data__calories=300))
    assert errors == []
    assert any("tips" in warning for warning in warnings)
    assert any("calories" in warning for warning in warnings)


def test_unknown_author_must_be_shown_as_unknown(tmp_path):
    result = mutated(source__author=None)
    markdown = GOOD_MARKDOWN.replace("原作者：测试作者", "原作者：未知")
    assert run(tmp_path, result, markdown)[0] == []


@pytest.mark.parametrize(
    ("markdown", "message"),
    [
        (None, "缺少对应的 Markdown"),
        (f"# 焙茶团子\n\n## 配料\n\n原链接：[点这里]({URL})\n", "标题下面必须依次是这两行"),
        (f"# 焙茶团子\n\n原作者：测试作者\n\nInspired by [this]({URL})\n", "标题下面必须依次是这两行"),
        (f"# 焙茶团子\n\n原作者：测试作者\n原链接：[点这里]({URL})\n", "前后都要空一行"),
        (GOOD_MARKDOWN + f"\n原链接：[点这里]({URL})\n", "只能出现一次"),
        (f"焙茶团子\n\n原作者：测试作者\n\n原链接：[点这里]({URL})\n", "第一行必须是 # 标题"),
    ],
)
def test_credit_lines_are_enforced(tmp_path, markdown, message):
    errors, _ = run(tmp_path, markdown=markdown)
    assert any(message in error for error in errors), errors


def test_custom_format_checks_only_the_envelope(tmp_path):
    result = mutated(format="custom:skill-card", data={"audience": "新手"})
    assert run(tmp_path, result)[0] == []
    assert any("data 为空" in error for error in run(tmp_path, mutated(format="custom:x", data={}))[0])


def test_invalid_json_is_reported(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("not json", encoding="utf-8")
    errors, _ = validate(path, DEFAULT_FORMATS_DIR)
    assert "无法读取或解析 JSON" in errors[0]


@pytest.mark.parametrize("format_file", sorted(DEFAULT_FORMATS_DIR.glob("*.md")), ids=lambda path: path.stem)
def test_every_format_file_has_a_parsable_field_table(format_file):
    fields = field_table(format_file.read_text(encoding="utf-8"))
    assert fields, f"{format_file.name} has no parsable 字段说明 table"
    assert any(field["required"] for field in fields)
    assert all(field["type"] in {"string", "number", "boolean", "array", "object"} for field in fields)


@pytest.mark.parametrize("format_file", sorted(DEFAULT_FORMATS_DIR.glob("[!_]*.md")), ids=lambda path: path.stem)
def test_every_format_json_example_matches_its_field_table(format_file, tmp_path):
    """The JSON example in each format file must itself pass validation."""
    text = format_file.read_text(encoding="utf-8")
    example = json.loads(text.split("```json", 1)[1].split("```", 1)[0])
    result = mutated(format=format_file.stem, data=example)
    errors, warnings = run(tmp_path, result)
    assert errors == [], errors
    assert not [warning for warning in warnings if "未定义的字段" in warning], warnings


def test_structured_data_is_an_allowed_source(tmp_path):
    """Web pages can publish schema.org data (structured.json); results may cite it."""
    assert run(tmp_path, mutated(sources_used=["caption", "structured"]))[0] == []


def test_comments_are_an_allowed_source(tmp_path):
    """Reddit posts come with comments.txt; a recipe is often in the poster's own comment."""
    assert run(tmp_path, mutated(sources_used=["caption", "comments"]))[0] == []
