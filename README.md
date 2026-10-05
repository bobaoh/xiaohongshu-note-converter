# Note Converter

Turn a link into a structured Markdown + JSON document in any format you define: a recipe, a summary, a travel guide, a product review, a tutorial, or your own. Supported links:

- Xiaohongshu / RedNote notes: video and image posts
- Reddit posts: text, image, GIF, video, gallery, and link posts, with their comments
- any ordinary web page: articles, blogs, recipe sites, documentation

For Reddit there is also a tool that lists the popular posts of chosen topics, so you can turn them into notes. See [Reddit](#reddit).

Every conversion records what it cost, and expensive ones are flagged.

**中文使用说明：** [Claude Code 版](HUMAN_INSTRUCTIONS(ClaudeCode).md) · [Codex 版](HUMAN_INSTRUCTIONS(Codex).md)

The design has four layers:

| Layer | Location | Role |
|---|---|---|
| Extraction | `notekit/` and `scripts/extract.py` | One module per kind of link in `notekit/sources/`. Each saves the same files: the text, speech transcript, OCR text, images, and metadata. It does not depend on the output format. |
| Source notes | `.claude/skills/note/sources/*.md` | What the formatting step should know about each kind of link. |
| Rules | `.claude/skills/note/SKILL.md` | The workflow and cleanup rules shared by every source and format: source priority, uncertainty markers, cost handling, and the JSON envelope. |
| Formats | `.claude/skills/xhs-note/formats/*.md` | One file per output format, shared by all sources. Add a file to add a format; no code changes needed. |

Speech recognition and OCR run locally. Audio and images are not sent to a third-party service.

## Requirements

- Windows 10/11
- Python 3.11 to 3.14 (tested in CI)
- FFmpeg
- Claude Code (for the skill workflow)
- A public, user-authorized link

## Setup on Windows

Open PowerShell in this folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
```

The setup installs FFmpeg and the Python packages at the exact versions in `requirements.lock`. The first transcription run downloads the Whisper model selected by `WHISPER_MODEL` (default: `small`).

## Use in Claude Code

Open Claude Code in this folder:

```
/note https://example.com/some-recipe                    # any web page; pick a format automatically
/note http://xhslink.com/o/example recipe                # a Xiaohongshu note in a defined format
/note https://www.reddit.com/r/GifRecipes/comments/<id>/ # a Reddit post, with the recipe from the poster's comment
/note https://example.com/travel 店名、地址、人均、推荐菜    # describe a one-off format
/note 把刚才那篇换成 tutorial 格式                          # reuse the extraction
```

Claude extracts the link, reusing a complete extraction when there is one:

- Xiaohongshu notes go to `output/<key>/`.
- Reddit posts go to `output/reddit/<post id>/`.
- Web pages go to `output/web/<id>/`.

The result is written to `results/<note_id>-<format>.md` and `.json`, then checked with `scripts/validate_result.py`. Claude also tells you when the conversion was expensive.

`/xhs-note` is the original Xiaohongshu-only skill. It still works, and the xhs-library project depends on it; use `/note` for new work.

`output/`, `results/`, and `logs/` are git-ignored because they contain other people's content and your own history. Remove `results/` from `.gitignore` if you want to version your results.

## Formats

| Name | Title | For |
|---|---|---|
| `recipe` | 菜谱 | cooking, baking, drinks |
| `summary` | 通用摘要 | any note or article; the fallback |
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
3. Use it with `/note <link> <name>`.

You can also describe a format inline. Claude then offers to save it as a new format file for you.

Every result JSON shares one envelope, so results from different sources and formats can be processed the same way:

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

## Conversion cost

Every conversion records its cost in `metadata.json` under `cost`, and appends a line to `logs/conversions.jsonl`, including failed conversions. The record contains:

- time per stage
- download size
- video length
- how many frames and images went through OCR
- an estimate of how much text and how many images the AI formatting step has to read
- a prediction made before the expensive work starts

A conversion is flagged as expensive when it crosses a threshold in `cost_policy.toml`:

| Flag | Meaning | Default limit |
|---|---|---|
| `slow` | Total extraction time | 180 s |
| `ocr_heavy` | OCR time | 120 s |
| `transcription_heavy` | Transcription time | 120 s |
| `long_video` | Video length | 300 s |
| `many_ocr_items` | Video frames + images OCR'd | 120 |
| `large_download` | Downloaded data | 100 MB |
| `large_ai_text` | Text the AI step reads | 20,000 tokens |
| `many_ai_images` | Images the AI step may view | 30,000 tokens |

```powershell
python .\scripts\cost_report.py              # flags, where the time goes, cost per source, prediction error
python .\scripts\cost_report.py --expensive  # only the flagged conversions
```

Flagging only marks conversions; nothing is refused yet. A limit on expensive conversions can be built on the recorded predictions. For web pages, `[web] max_images` already caps how many images go through OCR.

Typical costs on a Windows laptop:

| Kind of link | Typical cost |
|---|---|
| Web page | 1–8 s |
| Reddit text post | a few seconds, plus up to a minute waiting for Reddit's rate limit |
| Reddit GIF recipe (2 min, 64 MB) | about 2.5 min, nearly all of it OCR of the frames; plus the rate-limit wait |
| Xiaohongshu image note | about 30 s |
| 2-minute Xiaohongshu video | about 3 min; OCR of video frames is about 85% of that |

## Run the extractor directly

```powershell
python .\scripts\extract.py "https://example.com/article"           # prints the output directory and the cost
python .\scripts\extract.py "http://xhslink.com/o/example" --where  # only print where it would go
python .\scripts\extract.py "https://example.com/article" --force   # extract again
```

The extractor writes these files:

- `metadata.json`:
  - `source`, `note_id`, `note_type` (`video`, `normal`, or `article`), title, author, publish date
  - processing status and `cost`
  - source-specific fields; see `.claude/skills/note/sources/`
- `caption.txt`: the author's own text: a post's caption, or a web page's main text with image markers
- `transcript.txt`: the timestamped speech transcript (empty when there is no speech)
- `comments.txt`: comments, for sources that have them (Reddit); the poster's own comments are marked [楼主]
- `ocr.txt`: deduplicated Chinese/English text from video frames or images
- `structured.json`: schema.org data a web page publishes, such as recipe ingredients (only when present)
- `media/`: the images, or the video, audio, and frames with `--keep-media`

`scripts/extract_note.py` is the original command (`--output <dir> [--keep-media]`), kept unchanged for the xhs-library project. `extract_recipe.py` and `extract_post.py` are aliases.

### Add a kind of link

See the docstring of `notekit/sources/__init__.py` and "Adding a source" in `AGENTS.md`. In short:

1. Write a `Source` subclass.
2. Register it.
3. Report its cost.
4. Add tests and a regression link.

Codex and other agents that read `AGENTS.md` are pointed to the same skill rules automatically. `AGENTS.md` also explains how to use a web chat AI that cannot run commands.

## Reddit

Reddit posts are read through Reddit's public RSS feeds, without signing in. Reddit allows about one request per minute, so expect waits. The feeds have no scores, and galleries only show their first image. An official API client can be added later without changing anything else; see [docs/reddit.md](docs/reddit.md).

To find popular posts on topics you choose, edit `reddit_topics.toml` and run:

```powershell
python .\scripts\discover.py             # list what each topic would pick; changes nothing
python .\scripts\discover.py --extract   # also extract the picked posts, then use /note <link> on them
```

Turning popular posts into notes automatically on a schedule is designed in [docs/reddit.md](docs/reddit.md) but not built yet.

## Tested versions

| Component | How it is pinned | Tested |
|---|---|---|
| Python packages, including indirect dependencies | `requirements.lock`, used as a pip constraints file. `requirements.txt` keeps the allowed ranges. | CI on every push |
| Newest allowed packages | Not pinned: an early warning only | Weekly `latest dependencies` workflow |
| Whisper model files | `WHISPER_REVISIONS` in `notekit/media.py` (Hugging Face commit IDs) | CI (tiny), local tests (small) |
| Python | 3.11 to 3.14 | CI: 3.11 and 3.14 on Ubuntu, 3.14 on Windows |
| FFmpeg | Not pinned; only basic, long-stable options are used | CI: Ubuntu's FFmpeg 6.1 and Chocolatey's build on Windows. Locally: 9.0. |

A few packages resolve differently by Python version, so the lock pins each variant with an environment marker:

- `rapidocr-onnxruntime` 1.3 and later only support Python below 3.13, so Python 3.13 and 3.14 use 1.2.3.
- `av` 19 and `numpy` 2.5 need Python 3.12 or later, so Python 3.11 uses `av` 18.1 and `numpy` 2.4.

CI tests every one of these variants.

## Testing

```powershell
python -m pip install -r requirements-dev.txt -c requirements.lock
python -m pytest                          # offline: unit tests + synthetic media (~2 min), also run by CI
python tests/fixtures/fetch_local.py      # once: cache the real regression notes and pages locally
python -m pytest -m "local and not slow"  # offline: parse the cached real pages (< 1 s)
python -m pytest -m local                 # offline: also rerun OCR and transcription on them (7-11 min)
python scripts/regression.py              # online: extract the regression links live (~8 min)
```

- **Synthetic media**: `tests/fixtures/synthetic/` holds original content generated by `tests/fixtures/make_synthetic.py`.
- **Real notes and pages**: cached only in the git-ignored `tests/fixtures/local/`, because they belong to their authors.
- **xhs-library**: `tests/test_contract_xhs_library.py` checks the interface the xhs-library project relies on.

See the Testing section of `AGENTS.md` for when to run each layer.

## Access and copyright

Use only public content that you are authorized to access. This package does not bypass login walls, private-note permissions, DRM, paywalls, or anti-bot challenges. Do not provide cookies, session tokens, or credentials to the script or an AI.
