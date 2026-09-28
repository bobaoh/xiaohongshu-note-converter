---
name: xhs-video-transcript
description: "Download videos from user-provided Xiaohongshu/RedNote note links and extract the caption, spoken content, and on-screen text into Chinese or English. Use when a user asks to download a 小红书 or RedNote video, transcribe speech, OCR recipe/tutorial instructions, or turn a video into a written summary. The packaged extractor also detects image notes (including Live Photo notes) automatically. Requires ffmpeg/ffprobe, faster-whisper, and RapidOCR."
argument-hint: "Provide a user-authorized Xiaohongshu or RedNote note URL and the desired output language."
user-invocable: true
---

# Xiaohongshu Video Transcript

Extract the caption, speech, and on-screen text from a Xiaohongshu/RedNote note that the user is authorized to access, then return a readable transcript or structured content such as a recipe.

A share link does not tell you whether the note is a video. Many recipe links are image notes, and some image notes contain Live Photos: 2–4 second silent clips attached to single images. Always let the extractor detect the note type instead of assuming it from the request.

## Scope and safety

- Process only URLs supplied by the user or content they have permission to access.
- Do not bypass login, private-note permissions, paywalls, anti-bot challenges, DRM, or access controls.
- Do not request, store, or expose cookies, session tokens, QR-login data, or personal credentials.
- Treat speech-to-text and OCR as imperfect. Preserve uncertainty rather than inventing missing quantities or steps.
- Keep downloaded media and outputs in a temporary workspace unless the user asks to save them elsewhere.

## Workflow

1. **Check local tools**
   ```powershell
   Get-Command ffmpeg, ffprobe -ErrorAction SilentlyContinue
   python -c "import faster_whisper, rapidocr_onnxruntime; print('ok')"
   ```
   If a shell cannot find FFmpeg right after installation, reload PATH:
   `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`.
   Do not silently install packages or download a large model without consent.

2. **Run the extractor**
   ```powershell
   python scripts/extract_recipe.py "<LINK>" --output <TEMP_DIR>
   ```
   The script resolves `xhslink.com` redirects, reads the note from the page's embedded `window.__INITIAL_STATE__`, and branches on the note type:
   - **Video note** (`type: "video"`): downloads the main stream (H.264 with audio preferred, then H.265, master URL before backups), checks for an audio track with ffprobe, transcribes speech with local faster-whisper when audio exists, and OCRs one frame every 1.5 seconds.
   - **Image note** (`type: "normal"`): downloads only the note's own `imageList` images, skipping recommendation feeds and avatars, then OCRs them. Live Photo clips are counted but never treated as the note's video.

   Add `--keep-media` to retain the video, audio, and frames. `scripts/extract_post.py` is an alias for the same entry point.

3. **Read the outputs** in this order:
   - `metadata.json`: `status`, `note_type`, `title`, `transcription.status`, `video.has_audio`, `image_count`, `ocr_lines`, and `error` on failure.
   - `caption.txt`: the author's title, description, and tags. Recipe posts often put the complete ingredient list here, so read it first.
   - `transcript.txt`: timestamped speech for videos with audio; empty for image notes or silent videos.
   - `ocr.txt`: deduplicated text from video frames (`[12.0s|0.91]`) or post images (`[image-03|0.88]`).
   - `media/`: post images, for visual checks of steps that are shown but not written, such as numbered assembly photos.

4. **Clean and structure the result**
   - Prefer the caption for quantities. Use speech and OCR to fill in steps, and cross-check them against each other.
   - Drop OCR noise: packaging text, brand names, watermarks such as `小红书`, and UI text.
   - Preserve quantities, temperatures, durations, and ingredient names exactly when confidently recognized.
   - Mark unclear words as `[听不清]` (speech) or `[不确定]` (OCR/images); never infer exact measurements.
   - If the transcript uses homophones (for example `糯米分` for `糯米粉`), correct them only when the context makes the meaning certain.
   - Cantonese narration comes out in Traditional Chinese with many homophone errors (for example `熟米澱粉` for `玉米淀粉`). When burned-in subtitles exist, treat the OCR as primary and the transcript as a cross-check.
   - When speech and subtitles disagree on a number (for example steaming for 10 vs 15 minutes), report both instead of choosing one.

5. **Cleanup**
   Delete the temporary output directory after the results have been read, unless the user asks to retain the files.

## Failure handling

- `status: failed` with a login or challenge page: stop and report that the public media was unavailable.
- Video note without a stream URL: report it; do not fabricate a URL or reuse an authenticated browser URL.
- `transcription.status: skipped` on a video: the video has no audio track, so rely on the caption and OCR.
- `transcription.warning` present: the audio is probably background music. Whisper hallucinates short phrases such as `You` on such audio, so ignore the transcript and use the on-screen subtitles in `ocr.txt`.
- Page without embedded note state (`parser: regex_fallback`): results are best-effort, so say so and verify images manually.

## Manual fallback

If the script cannot run, follow the same logic by hand:
1. Fetch the resolved note page without authentication and parse `window.__INITIAL_STATE__` (replace `undefined` with `null` before JSON parsing). The note is at `noteData.data.noteData` on mobile pages.
2. For `type: "video"`, take `video.media.stream.h264[0].masterUrl` (or `backupUrls`). Never take an MP4 from `imageList[].stream`; those are Live Photos.
3. Check `ffprobe -show_entries stream=codec_type` before extracting audio with `ffmpeg -vn -ac 1 -ar 16000 -c:a pcm_s16le`.
4. For `type: "normal"`, download `imageList[].infoList` URLs (scene `WB_DFT` or `H5_DTL`) and read the `desc` field.

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

Always state whether each part came from the caption, speech, OCR, or images, and mention anything that was incomplete, inaccessible, or uncertain.
