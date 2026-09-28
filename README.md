# Xiaohongshu Recipe Extractor

A standalone workflow for turning a public Xiaohongshu/RedNote note into a structured recipe. It does not require VS Code or a Copilot-specific skill system.

One command handles video notes, ordinary image notes, and image notes with Live Photos. The script reads the note's embedded page data to detect which kind it is.

## Requirements

- Windows 10/11
- Python 3.11+
- FFmpeg
- A public, user-authorized Xiaohongshu/RedNote link

The workflow uses local speech recognition and OCR. Audio is not sent to a third-party transcription service.

## Setup on Windows

Open PowerShell in this folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
```

The setup installs FFmpeg and the Python packages in `requirements.txt`. The first transcription run downloads the Whisper model selected by `WHISPER_MODEL` (default: `small`).

## Extract a recipe

```powershell
python .\scripts\extract_recipe.py "https://www.xiaohongshu.com/..." --output .\output
```

For a short link:

```powershell
python .\scripts\extract_recipe.py "http://xhslink.com/o/example" --output .\output
```

The same command works for image posts. `scripts/extract_post.py` is kept as an alias.

The script writes:

- `output/metadata.json`: note type (`video` or `normal`), title, resolved URL, and processing status
- `output/caption.txt`: the author's title, description, and tags, which often contain the full recipe
- `output/transcript.txt`: timestamped speech transcript (empty for image posts and silent videos)
- `output/ocr.txt`: deduplicated Chinese/English text from video frames or post images
- `output/media/`: the note's own images (image posts), or the video, audio, and frames with `--keep-media`

Then give those files to an AI with the instructions in `AI_INSTRUCTIONS.md`.

## Using another AI

If the AI can run terminal commands, give it this repository and ask:

> Read `AI_INSTRUCTIONS.md`. Run the extractor on this public Xiaohongshu link, then convert the resulting caption, transcript, and OCR into the required recipe format.

If the AI cannot run code or access files, it cannot directly download and process the video. Run the script locally first, then upload `caption.txt`, `transcript.txt`, `ocr.txt`, or screenshots to that AI.

## Access and copyright

Use only public content that you are authorized to access. This package does not bypass login walls, private-note permissions, DRM, paywalls, or anti-bot challenges. Do not provide cookies, session tokens, or credentials to the script or an AI.
