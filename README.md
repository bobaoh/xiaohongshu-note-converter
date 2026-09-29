# Xiaohongshu Note Converter

Turn a public Xiaohongshu/RedNote note into a structured Markdown + JSON document in any format you define: a recipe, a summary, a travel guide, a product review, a tutorial, or your own.

**中文使用说明：** [Claude Code 版](HUMAN_INSTRUCTIONS(ClaudeCode).md) · [Codex 版](HUMAN_INSTRUCTIONS(Codex).md)

The design has three layers:

| Layer | Location | Role |
|---|---|---|
| Extraction | `scripts/extract_note.py` | Detects video vs image notes and saves the caption, speech transcript, OCR text, and images. It does not depend on the output format. |
| Rules | `.claude/skills/xhs-note/SKILL.md` | The workflow and cleanup rules shared by every format: source priority, uncertainty markers, and the JSON envelope. |
| Formats | `.claude/skills/xhs-note/formats/*.md` | One file per output format. Add a file to add a format; no code changes needed. |

Speech recognition and OCR run locally. Audio is not sent to a third-party service.

## Requirements

- Windows 10/11
- Python 3.11+
- FFmpeg
- Claude Code (for the skill workflow)
- A public, user-authorized Xiaohongshu/RedNote link

## Setup on Windows

Open PowerShell in this folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
```

The setup installs FFmpeg and the Python packages in `requirements.txt`. The first transcription run downloads the Whisper model selected by `WHISPER_MODEL` (default: `small`).

## Use in Claude Code

Open Claude Code in this folder:

```
/xhs-note http://xhslink.com/o/example                     # pick a format automatically
/xhs-note http://xhslink.com/o/example recipe              # use a defined format
/xhs-note http://xhslink.com/o/example 店名、地址、人均、推荐菜  # describe a one-off format
/xhs-note 把刚才那篇换成 tutorial 格式                        # reuse the extraction
```

Claude extracts the note into `output/<key>/`. If that folder already holds a complete extraction, Claude reuses it. The result is written to `results/<note_id>-<format>.md` and `.json`, then checked with `scripts/validate_result.py`.

Both `output/` and `results/` are git-ignored because they contain other people's posts. Remove `results/` from `.gitignore` if you want to version your results.

## Formats

| Name | Title | For |
|---|---|---|
| `recipe` | 菜谱 | cooking, baking, drinks |
| `summary` | 通用摘要 | any note; the fallback |
| `travel-guide` | 旅行攻略 | itineraries, places, transport |
| `product-review` | 好物测评 | product picks, comparisons, hauls |
| `tutorial` | 教程 | step-by-step how-tos |

### Add your own format

1. Copy `.claude/skills/xhs-note/formats/_TEMPLATE.md` to `formats/<name>.md`.
2. Fill in four things:
   - the frontmatter (`name`, `title`, `description`)
   - the field table (`字段 | 类型 | 必填 | 说明`)
   - a JSON example
   - a Markdown template and any format-specific rules
3. Use it with `/xhs-note <link> <name>`.

You can also describe a format inline. Claude then offers to save it as a new format file for you.

Every result JSON shares one envelope, so results from different formats can be processed the same way:

```json
{
  "format": "recipe",
  "source": {"url": "...", "note_id": "...", "title": "...", "note_type": "video", "published_at": "2026-09-20"},
  "sources_used": ["caption", "ocr"],
  "data": {},
  "uncertain": [],
  "missing": []
}
```

## Run the extractor directly

```powershell
python .\scripts\extract_note.py "http://xhslink.com/o/example" --output .\output\example
```

The extractor writes these files:

- `metadata.json`: note ID, type (`video` or `normal`), title, publish date, and processing status
- `caption.txt`: the author's title, description, and tags
- `transcript.txt`: the timestamped speech transcript (empty for image notes and silent videos)
- `ocr.txt`: deduplicated Chinese/English text from video frames or post images
- `media/`: the note's own images (image notes), or the video, audio, and frames with `--keep-media`

`extract_recipe.py` and `extract_post.py` still work as aliases.

Codex and other agents that read `AGENTS.md` are pointed to the same skill rules automatically. `AGENTS.md` also explains how to use a web chat AI that cannot run commands.

## Access and copyright

Use only public content that you are authorized to access. This package does not bypass login walls, private-note permissions, DRM, paywalls, or anti-bot challenges. Do not provide cookies, session tokens, or credentials to the script or an AI.
