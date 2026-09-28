# AI Instructions: Xiaohongshu Note Conversion

This repository's primary workflow is the Claude Code skill in `.claude/skills/xhs-note/`. These notes are for any other AI that can run terminal commands and read files.

## Procedure

1. Read `.claude/skills/xhs-note/SKILL.md` and follow its workflow and general rules exactly. It covers:
   - running `python scripts/extract_note.py "<LINK>" --output output/<key>`
   - which extracted files to read and in what order
   - how to pick an output format
   - the shared JSON envelope
   - uncertainty and source-priority rules
2. Choose an output format from `.claude/skills/xhs-note/formats/`: `recipe`, `summary`, `travel-guide`, `product-review`, or `tutorial`. If the user describes a format that is not listed, design the `data` fields from their description and set `format` to `custom:<name>`.
3. Write `results/<note_id>-<format>.md` and `results/<note_id>-<format>.json`, then run:
   `python scripts/validate_result.py results/<note_id>-<format>.json`
   Fix any reported errors before replying.

## If the AI cannot run code

Run the extractor locally first. Then give the AI four things:
- `caption.txt`, `ocr.txt`, and `transcript.txt`
- `metadata.json`
- `SKILL.md` and the chosen format file from `formats/`
- any images from `media/` that show steps or prices

Ask it to follow `SKILL.md` and reply with one Markdown block and one JSON block.

## Safety

Use only public links the user is authorized to access. Do not bypass login walls, private-note permissions, or anti-bot challenges. Do not request or expose cookies, QR-login data, session tokens, or passwords.
