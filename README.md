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
- Python 3.11 to 3.14 (tested in CI)
- FFmpeg
- Claude Code (for the skill workflow)
- A public, user-authorized Xiaohongshu/RedNote link

## Setup on Windows

Open PowerShell in this folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
```

The setup installs FFmpeg and the Python packages at the exact versions in `requirements.lock`. The first transcription run downloads the Whisper model selected by `WHISPER_MODEL` (default: `small`).

## Tested versions

| Component | How it is pinned | Tested |
|---|---|---|
| Python packages, including indirect dependencies | `requirements.lock`, used as a pip constraints file. `requirements.txt` keeps the allowed ranges. | CI on every push |
| Newest allowed packages | Not pinned: an early warning only | Weekly `latest dependencies` workflow |
| Whisper model files | `WHISPER_REVISIONS` in `scripts/extract_note.py` (Hugging Face commit IDs) | CI (tiny), local tests (small) |
| Python | 3.11 to 3.14 | CI: 3.11 and 3.14 on Ubuntu, 3.14 on Windows |
| FFmpeg | Not pinned; only basic, long-stable options are used | CI: Ubuntu's FFmpeg 6.1 and Chocolatey's build on Windows. Locally: 9.0. |

A few packages resolve differently by Python version, so the lock pins each variant with an environment marker:

- `rapidocr-onnxruntime` 1.3 and later only support Python below 3.13, so Python 3.13 and 3.14 use 1.2.3.
- `av` 19 and `numpy` 2.5 need Python 3.12 or later, so Python 3.11 uses `av` 18.1 and `numpy` 2.4.

CI tests every one of these variants.

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
  "source": {"url": "...", "note_id": "...", "title": "...", "author": "...", "note_type": "video", "published_at": "2026-09-20"},
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

## Testing

```powershell
python -m pip install -r requirements-dev.txt -c requirements.lock
python -m pytest                          # offline: unit tests + synthetic media (~1 min), also run by CI
python tests/fixtures/fetch_local.py      # once: cache the real regression notes locally
python -m pytest -m local                 # offline: rerun on the cached real notes (~8 min)
python scripts/regression.py              # online: extract the regression notes live (~8 min)
```

The synthetic test media in `tests/fixtures/synthetic/` is original content generated by `tests/fixtures/make_synthetic.py`. Real notes are cached only in the git-ignored `tests/fixtures/local/`, because they belong to their authors. See the Testing section of `AGENTS.md` for when to run each layer.

## Access and copyright

Use only public content that you are authorized to access. This package does not bypass login walls, private-note permissions, DRM, paywalls, or anti-bot challenges. Do not provide cookies, session tokens, or credentials to the script or an AI.
