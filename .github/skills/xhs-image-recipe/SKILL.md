---
name: xhs-image-recipe
description: "Extract recipes and tutorials from public Xiaohongshu or RedNote image posts, including posts with Live Photos. Use when a user provides a non-video 小红书/RedNote post, image note, recipe card, or asks to OCR Chinese or English text from post images. The shared extractor detects video notes automatically too. Requires RapidOCR."
argument-hint: "Provide a public Xiaohongshu or RedNote image-post URL."
user-invocable: true
---

# Xiaohongshu Image-Post Recipe Extraction

Use this skill for ordinary Xiaohongshu/RedNote posts whose content is in the caption and images rather than in video audio. If the link turns out to be a video note, the same extractor handles it; follow the `xhs-video-transcript` skill for the transcript.

## Procedure

1. Confirm the user supplied a public link they are authorized to access.
2. Run the extractor, which detects the note type automatically:
   ```powershell
   python scripts/extract_recipe.py "<PUBLIC_XHS_LINK>" --output <TEMP_DIR>
   ```
   `scripts/extract_post.py` is an alias for the same entry point.
3. Check `metadata.json`. `note_type` should be `normal`. `image_count` counts only the note's own images, and `live_photo_count` counts images with short, silent Live Photo clips, which are not recipe videos.
4. Read `caption.txt` first. Authors often write the full ingredient list and main steps in the description.
5. Read `ocr.txt` (lines tagged `[image-NN|confidence]`). Separate recipe cards from packaging text, brand names, the `小红书` watermark, and UI text.
6. Open images in `media/` when steps are shown rather than written, for example numbered assembly photos. Describe only what is clearly visible.
7. Preserve ingredient names, quantities, temperatures, and durations only when they are written in the caption, legible in an image, or repeated consistently.
8. Never invent missing values. Mark uncertain text as `[不确定]`.
9. Return:
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
10. State which parts came from the caption, image OCR, or visual inspection, and identify missing or uncertain fields.
11. Delete the temporary output directory afterward unless the user asks to keep it.

## Failure handling

- Stop if the page requires login, presents a challenge, or exposes no public images.
- Do not request or expose cookies, QR-login data, session tokens, or passwords.
- The extractor reads images only from the note's `imageList`. If `metadata.json` reports `parser: regex_fallback`, the page had no embedded note data, so verify the images by eye and ignore avatars, logos, or recommendation images.
