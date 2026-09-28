from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_FORMATS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "xhs-note" / "formats"
SOURCE_KEYS = ("url", "note_id", "title", "note_type")
ALLOWED_SOURCES = {"caption", "ocr", "transcript", "images"}
TYPE_CHECKS = {
    "string": lambda value: isinstance(value, str),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "array": lambda value: isinstance(value, list),
    "object": lambda value: isinstance(value, dict),
}
REQUIRED_MARKS = {"是", "必填", "yes", "y", "true"}


def frontmatter_name(text: str) -> str | None:
    match = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    if not match:
        return None
    name = re.search(r"^name:\s*(\S+)", match.group(1), re.M)
    return name.group(1).strip("\"'") if name else None


def find_format_file(format_name: str, formats_dir: Path) -> Path | None:
    for path in sorted(formats_dir.glob("*.md")):
        if path.stem == format_name or frontmatter_name(path.read_text(encoding="utf-8")) == format_name:
            return path
    return None


def field_table(text: str) -> list[dict[str, object]]:
    """Parse the `## 字段说明` table into [{name, type, required}]."""
    section = re.search(r"^##\s*字段说明\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not section:
        return []
    rows = [line.strip() for line in section.group(1).splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        return []
    header = [cell.strip() for cell in rows[0].strip("|").split("|")]
    try:
        name_col, type_col, required_col = header.index("字段"), header.index("类型"), header.index("必填")
    except ValueError:
        return []
    fields = []
    for row in rows[2:]:
        cells = [cell.strip().strip("`") for cell in row.strip("|").split("|")]
        if len(cells) <= max(name_col, type_col, required_col) or not cells[name_col]:
            continue
        fields.append(
            {
                "name": cells[name_col],
                "type": cells[type_col].lower(),
                "required": cells[required_col].lower() in REQUIRED_MARKS,
            }
        )
    return fields


def is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def validate(result_path: Path, formats_dir: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"无法读取或解析 JSON：{error}"], warnings
    if not isinstance(result, dict):
        return ["JSON 顶层必须是对象"], warnings

    markdown_path = result_path.with_suffix(".md")
    if not markdown_path.exists() or not markdown_path.read_text(encoding="utf-8").strip():
        errors.append(f"缺少对应的 Markdown 文件或文件为空：{markdown_path.name}")

    format_name = result.get("format")
    if not isinstance(format_name, str) or not format_name:
        errors.append("外壳字段 format 缺失或不是字符串")
    source = result.get("source")
    if not isinstance(source, dict):
        errors.append("外壳字段 source 缺失或不是对象")
    else:
        for key in SOURCE_KEYS:
            if is_empty(source.get(key)):
                errors.append(f"source.{key} 缺失或为空")
    sources_used = result.get("sources_used")
    if not isinstance(sources_used, list) or not sources_used:
        errors.append("外壳字段 sources_used 缺失或为空数组")
    else:
        unknown = [item for item in sources_used if item not in ALLOWED_SOURCES]
        if unknown:
            errors.append(f"sources_used 含未知来源 {unknown}，只允许 {sorted(ALLOWED_SOURCES)}")
    for key in ("uncertain", "missing"):
        if not isinstance(result.get(key), list):
            errors.append(f"外壳字段 {key} 缺失或不是数组（没有内容时写 []）")
    data = result.get("data")
    if not isinstance(data, dict):
        errors.append("外壳字段 data 缺失或不是对象")
        return errors, warnings

    if not isinstance(format_name, str) or format_name.startswith("custom:"):
        if not data:
            errors.append("data 为空对象")
        return errors, warnings

    format_file = find_format_file(format_name, formats_dir)
    if not format_file:
        errors.append(f"找不到格式文件 {format_name}（在 {formats_dir}）；临时格式请把 format 写成 custom:<名称>")
        return errors, warnings

    fields = field_table(format_file.read_text(encoding="utf-8"))
    if not fields:
        warnings.append(f"{format_file.name} 没有可解析的字段说明表，只检查了外壳")
    for spec in fields:
        name = spec["name"]
        if name not in data:
            if spec["required"]:
                errors.append(f"data 缺少必填字段 {name}")
            continue
        value = data[name]
        check = TYPE_CHECKS.get(spec["type"])
        if value is not None and check and not check(value):
            errors.append(f"data.{name} 应为 {spec['type']}，实际是 {type(value).__name__}")
        if spec["required"] and is_empty(value):
            warnings.append(f"必填字段 data.{name} 为空；如果素材里确实没有，请确认已记入 missing")
    known = {spec["name"] for spec in fields}
    extra = [key for key in data if fields and key not in known]
    if extra:
        warnings.append(f"data 含格式未定义的字段 {extra}")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an xhs-note result JSON against its format definition.")
    parser.add_argument("result", help="Path to results/<note_id>-<format>.json")
    parser.add_argument("--formats-dir", default=str(DEFAULT_FORMATS_DIR), help="Directory containing format .md files")
    args = parser.parse_args(argv)

    errors, warnings = validate(Path(args.result), Path(args.formats_dir))
    for message in errors:
        print(f"ERROR: {message}")
    for message in warnings:
        print(f"WARNING: {message}")
    if errors:
        print(f"校验失败：{len(errors)} 个错误，{len(warnings)} 个警告")
        return 1
    print(f"校验通过（{len(warnings)} 个警告）")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
