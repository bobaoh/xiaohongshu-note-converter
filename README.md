# Xiaohongshu Recipe Extractor

A standalone workflow for turning a public Xiaohongshu/RedNote video into a structured recipe. It does not require VS Code or a Copilot-specific skill system.

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

The script writes:

- `output/transcript.txt`: timestamped speech transcript
- `output/ocr.txt`: deduplicated Chinese/English text detected in video frames
- `output/metadata.json`: title, resolved URL, and processing status

Then give those files to an AI with the instructions in `AI_INSTRUCTIONS.md`.

## Using another AI

If the AI can run terminal commands, give it this repository and ask:

> Read `AI_INSTRUCTIONS.md`. Run the extractor on this public Xiaohongshu link, then convert the resulting transcript and OCR into the required recipe format.

If the AI cannot run code or access files, it cannot directly download and process the video. Run the script locally first, then upload `transcript.txt`, `ocr.txt`, or screenshots to that AI.

## Access and copyright

Use only public content that you are authorized to access. This package does not bypass login walls, private-note permissions, DRM, paywalls, or anti-bot challenges. Do not provide cookies, session tokens, or credentials to the script or an AI.
