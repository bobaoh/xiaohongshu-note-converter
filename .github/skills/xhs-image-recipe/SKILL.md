---
name: xhs-image-recipe
description: "Extract recipes and tutorials from public Xiaohongshu or RedNote image posts. Use when a user provides a non-video 小红书/RedNote post, image note, recipe card, or asks to OCR Chinese or English text from post images. Requires the standalone image-post extractor and RapidOCR."
argument-hint: "Provide a public Xiaohongshu or RedNote image-post URL."
user-invocable: true
---

# Xiaohongshu Image-Post Recipe Extraction

Use this skill for ordinary Xiaohongshu/RedNote posts whose content is stored in images rather than video audio.

## Procedure

1. Confirm the user supplied a public link they are authorized to access.
2. Run the standalone image-post extractor:
   ```powershell
   python scripts/extract_post.py "<PUBLIC_XHS_LINK>" --output output
   ```
3. Read `output/ocr.txt` and `output/metadata.json`. Use downloaded images in `output/media/` only when visual verification is needed.
4. Deduplicate OCR lines and separate recipe cards from decorative text, usernames, and interface text.
5. Preserve ingredient names, quantities, temperatures, and durations only when legible or repeated consistently.
6. Never invent missing values. Mark uncertain text as `[不确定]`.
7. Return:
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
8. State that the recipe was extracted from post-image OCR and identify missing or uncertain fields.

## Failure handling

- Stop if the page requires login, presents a challenge, or exposes no public images.
- Do not request or expose cookies, QR-login data, session tokens, or passwords.
- Do not confuse avatars, logos, or unrelated recommendation images with the note's own images.
