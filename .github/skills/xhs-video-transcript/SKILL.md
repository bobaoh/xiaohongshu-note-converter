---
name: xhs-video-transcript
description: "Download videos from user-provided Xiaohongshu/RedNote note links and extract spoken content or on-screen text into Chinese or English. Use when a user asks to download a 小红书 or RedNote video, transcribe speech, OCR recipe/tutorial instructions, or turn a video into a written summary. Requires ffmpeg, faster-whisper, and Tesseract OCR for video text."
argument-hint: "Provide a user-authorized Xiaohongshu or RedNote note URL and the desired output language."
user-invocable: true
---

# Xiaohongshu Video Transcript

Extract speech and on-screen text from a Xiaohongshu/RedNote video that the user is authorized to access, then return a readable transcript or structured content such as a recipe.

## Scope and safety

- Process only URLs supplied by the user or content they have permission to access.
- Do not bypass login, private-note permissions, paywalls, anti-bot challenges, DRM, or access controls.
- Do not request, store, or expose cookies, session tokens, QR-login data, or personal credentials.
- Treat speech-to-text as an imperfect transcription. Preserve uncertainty rather than inventing missing quantities or steps.
- Keep downloaded media and transcripts in a temporary workspace unless the user asks to save them elsewhere.

## Workflow

1. **Resolve the note URL**
   - Follow `xhslink.com` redirects to the canonical Xiaohongshu/RedNote note URL.
   - Fetch the publicly available page with the web-page fetch tool or a non-authenticated HTTP request.
   - Inspect the returned HTML and embedded state for a video URL. Common sources include `video`, `masterUrl`, `h264Url`, `backupUrls`, or `media` fields.
   - Prefer the highest-quality directly available MP4 URL. Do not fabricate a URL or use an authenticated URL copied from a private browser session.
   - If the page only exposes a login wall, challenge, or inaccessible media, stop and report that the video could not be accessed.

2. **Check local tools**
   ```powershell
   Get-Command ffmpeg -ErrorAction SilentlyContinue
   python -c "import faster_whisper; print('faster-whisper available')"
   ```
   Also verify OCR support:
   ```powershell
   Get-Command tesseract -ErrorAction SilentlyContinue
   tesseract --list-langs
   python -c "import pytesseract; print('pytesseract available')"
   ```
   The language list should include `eng` and `chi_sim`. If either OCR language is missing, report it before continuing. Do not silently install packages or download a large model without consent.

3. **Download the video**
   Use a temporary directory and an explicit output path. For a direct public media URL:
   ```powershell
   $work = Join-Path $env:TEMP ('xhs-transcript-' + [guid]::NewGuid())
   New-Item -ItemType Directory -Path $work | Out-Null
   curl.exe -L --fail --retry 2 --output (Join-Path $work 'video.mp4') '<DIRECT_VIDEO_URL>'
   ```
   Check that the file exists and has non-zero size before continuing. Never print URLs containing tokens or cookies.

4. **Extract audio with ffmpeg**
   ```powershell
   ffmpeg -y -i (Join-Path $work 'video.mp4') -vn -ac 1 -ar 16000 -c:a pcm_s16le (Join-Path $work 'audio.wav')
   ```
   Use mono, 16 kHz PCM audio for predictable speech recognition. If ffmpeg reports that the file is not a valid media file, stop and report the download failure.

5. **Transcribe speech**
   Run the local `faster-whisper` API without sending audio to a third-party service:
   ```powershell
   @'
   from faster_whisper import WhisperModel
   import os, sys

   audio_path = sys.argv[1]
   output_path = sys.argv[2]
   model = WhisperModel(os.environ.get("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
   segments, info = model.transcribe(audio_path, language="zh", vad_filter=True)
   with open(output_path, "w", encoding="utf-8") as f:
       for segment in segments:
           text = segment.text.strip()
           if text:
               f.write(f"[{segment.start:.1f}-{segment.end:.1f}] {text}\n")
   print(f"language={info.language} probability={info.language_probability:.3f}")
   '@ | Set-Content -Encoding UTF8 (Join-Path $work 'transcribe.py')
   python (Join-Path $work 'transcribe.py') (Join-Path $work 'audio.wav') (Join-Path $work 'transcript.txt')
   ```
   Use `medium` or `large-v3` only when the user asks for higher accuracy and local resources permit it. If the audio is not Chinese, detect the language and rerun without forcing `language="zh"`.

6. **OCR on-screen text when speech is absent or incomplete**
   - Create representative frames or a contact sheet with FFmpeg, for example one frame every 2 seconds.
   - Run Tesseract with both Chinese and English models:
   ```powershell
   tesseract.exe $frame $outputBase -l chi_sim+eng --psm 6
   ```
   - For Python, configure the executable and user language-data directory explicitly when needed:
   ```python
   import pytesseract
   pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
   text = pytesseract.image_to_string(image, lang="chi_sim+eng", config="--psm 6")
   ```
   - Deduplicate repeated text across frames and retain quantities, temperatures, and times only when the OCR is clear.
   - Try `--psm 11` for sparse overlay text and crop the text region before OCR when the full frame contains distracting imagery.

7. **Clean and structure the result**
   - Read the timestamped transcript and remove obvious filler or duplicated fragments.
   - Preserve quantities, temperatures, durations, and ingredient names exactly when confidently recognized.
   - For recipes, format as: title, time/servings, ingredients grouped by component, method, and tips.
   - Mark unclear words as `[听不清]` or ask for the relevant video segment; never infer exact measurements.
   - State that the recipe or claims were extracted from speech and may need verification.

8. **Cleanup**
   Delete the temporary directory after the transcript has been read unless the user asks to retain the files:
   ```powershell
   Remove-Item -LiteralPath $work -Recurse -Force
   ```

## Output formats

For a general video, return a concise transcript followed by a summary.

For a recipe, use this shape:

```markdown
# 菜谱标题

⏱️ 用时：
🍽️ 份量：

## 配料
- ...

## 做法
1. ...

## 小贴士
- ...
```

Always mention when the transcript was incomplete, the video was inaccessible, or any ingredient/step was uncertain.
