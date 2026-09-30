# AGENTS.md

This repository converts public Xiaohongshu/RedNote notes (video or image posts) into structured Markdown + JSON documents. Examples: a recipe, a travel guide, a product review, a tutorial, a summary, or a format the user describes.

## When the user gives a Xiaohongshu link

Trigger this workflow for any `xhslink.com` or `xiaohongshu.com` link, or when the user asks to reformat a note that was already extracted (for example "换成 tutorial 格式").

1. Read `.claude/skills/xhs-note/SKILL.md` in full, then follow its workflow and general rules exactly. It is the single source of truth, shared with Claude Code. Do not work from memory of an earlier read.
2. Output formats live in `.claude/skills/xhs-note/formats/`.
   - The user names a format (`recipe`, `菜谱`, `travel-guide`…): read that file.
   - The user gives no format: read only the frontmatter of each file and pick one, as SKILL.md describes.
   - The user describes fields instead of naming a format: create a `custom:<name>` result, as SKILL.md describes.
3. Finish every conversion with the two steps below. Report the result of both to the user.
   - Write `results/<note_id>-<format>.md` and `results/<note_id>-<format>.json`.
   - Run `python scripts/validate_result.py results/<note_id>-<format>.json` and fix any errors.

## Environment notes for Codex

- **Network is required.** `scripts/extract_note.py` fetches the note page and downloads images or video. The first run also downloads the Whisper model. If the sandbox blocks network access, request approval to run the command with network access; do not try to work around the block.
- **Video notes take 2–4 minutes** because of local transcription. Let the command finish; do not kill it early or rerun it in parallel.
- **Reuse extractions.** If `output/<key>/metadata.json` already has `"status": "complete"`, reuse it instead of downloading again.
- **Images.** For image notes, SKILL.md asks you to look at `output/<key>/media/image-NN.jpg` when steps, maps, or price lists are shown only in pictures. If you cannot view local images, rely on `ocr.txt` and list what could not be checked in the result's `missing` field.
- **FFmpeg on Windows.** If `ffmpeg` is not found right after installation, reload PATH in PowerShell before retrying:
  `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`

## If you cannot run commands

This applies to web chat AIs or agents without a shell, for example when the user uploads this file or links the repository.

1. You cannot extract the note yourself. Ask the user to run the extractor locally:
   `python scripts/extract_note.py "<LINK>" --output output/<key>`
2. Ask them to upload these files:
   - `metadata.json`, `caption.txt`, `ocr.txt`, and `transcript.txt` from `output/<key>/`
   - `.claude/skills/xhs-note/SKILL.md`
   - the chosen format file from `.claude/skills/xhs-note/formats/`
   - any images from `media/` that show steps, maps, or prices
3. Follow SKILL.md as usual. You cannot write files, so reply with exactly two code blocks: first ```markdown, then ```json. The JSON must use the envelope defined in SKILL.md.
4. Tell the user to save them as `results/<note_id>-<format>.md` and `.json`, then run `python scripts/validate_result.py` on the JSON.

## Safety

- Process only public links the user supplied.
- Do not bypass login walls, private-note permissions, CAPTCHAs, or DRM.
- Never ask for, store, or print cookies, session tokens, QR-login data, or passwords.
- If a note is unavailable, report the `error` from `metadata.json` and stop.

## Working on the code

- `scripts/extract_note.py` is the extractor. `scripts/extract_recipe.py` and `scripts/extract_post.py` are aliases; keep them working.
- Adding a format means adding a file to `.claude/skills/xhs-note/formats/` that follows `_TEMPLATE.md`. `validate_result.py` reads each format's `## 字段说明` table, so keep its columns (`字段 | 类型 | 必填 | 说明`) intact.
- `output/`, `results/`, and `tests/fixtures/local/` are git-ignored and hold other people's content. Do not commit them.

## Testing

There are three layers. Run them in this order, and report which ones you ran and their results.

| Layer | Command | When | Time |
|---|---|---|---|
| 1. Offline | `python -m pytest` | After every code or format change. CI also runs it on every push. | ~1 min |
| 2. Cached real notes | `python -m pytest -m local` | Before merging any change to `scripts/extract_note.py` | ~8 min |
| 3. Live regression | `python scripts/regression.py` | Before merging extractor changes, and when Xiaohongshu may have changed its pages | ~8 min, needs network |

- **Layer 1** has two parts:
  - Unit tests for parsing and validation. They use synthetic pages built in `tests/conftest.py`.
  - Media tests. They run FFmpeg, OCR, and Whisper `tiny` on original synthetic media in `tests/fixtures/synthetic/`.
- **Layer 2** reruns the full analysis on real notes cached in `tests/fixtures/local/`. Create the cache once with `python tests/fixtures/fetch_local.py`. Tests for notes that are not cached are skipped, so a skip is not a pass. Say so if the cache is missing.
- **Layer 3** exit code 2 means some links were unavailable, not that the code is broken. Report it; do not change the expectations to make it pass.
- Expectations for layers 2 and 3 live in `tests/fixtures/regression_links.json`. Change an expectation only when the note itself changed, and say why.
- When you fix a bug, add a test that fails without the fix.
- The synthetic media is generated by `tests/fixtures/make_synthetic.py`, which needs Windows for the zh-CN speech voice. Regenerate it only when the fixtures need to change, and commit the output.
