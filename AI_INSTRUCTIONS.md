# AI Instructions: Xiaohongshu Recipe Extraction

Use this package when the user provides a Xiaohongshu or RedNote recipe/tutorial link, whether it is a video post, an ordinary image post, or an image post with Live Photos.

## Procedure

1. Confirm that the user supplied the link and is authorized to access the content.
2. If terminal execution is available, run the extractor. It detects the note type automatically:
   `python scripts/extract_recipe.py "<LINK>" --output output`
3. Read the files produced under `output/`:
   - `metadata.json`: status, `note_type` (`video` or `normal`), and processing details
   - `caption.txt`: the author's title, description, and tags. Recipes are often written here in full.
   - `transcript.txt`: timestamped speech (video notes with audio only)
   - `ocr.txt`: text from video frames or post images
   - `media/`: post images for visual verification of steps shown in photos
4. Combine the caption, speech, and OCR. Prefer the caption for quantities, and information that is clearly spoken or repeated across frames.
5. Remove duplicate OCR lines and obvious recognition noise, such as packaging text, brand names, and watermarks.
6. Never invent an ingredient, quantity, temperature, or duration. Mark uncertain text as `[不确定]`.
7. Return the result in this format:

```markdown
# 菜谱标题

⏱️ 用时：
🍽️ 份量：

## 配料

### 分组名称
- 配料：用量

## 做法

1. ...

## 小贴士

- ...
```

8. State whether the recipe came from the caption, speech, OCR, or images. Mention missing or uncertain fields.

## Failure handling

- If the page requires login or a challenge, stop and explain that the public media was unavailable.
- If speech is empty or the video has no audio track, rely on the caption and OCR.
- If OCR is too noisy to establish exact quantities, do not guess. Report the reliable title and steps only, and list the missing details.
- Do not request or expose cookies, QR-login data, session tokens, or passwords.
