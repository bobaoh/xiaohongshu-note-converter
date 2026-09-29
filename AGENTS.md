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
- `output/` and `results/` are git-ignored and hold other people's content. Do not commit them.
- Regression links used during development:
  - `http://xhslink.com/o/7OKVgxAyUiN`: image note with Live Photos
  - `http://xhslink.com/o/9mo7le3NAf`: video with background music only
  - `http://xhslink.com/o/aV6VUiQGcr`: video with Cantonese narration
  - `http://xhslink.com/o/4wAhGGdelSj`: image note with an empty title field
