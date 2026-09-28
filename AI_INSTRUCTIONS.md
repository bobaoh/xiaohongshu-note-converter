# AI Instructions: Xiaohongshu Recipe Extraction

Use this package when the user provides a Xiaohongshu or RedNote recipe/tutorial link, whether it is a video post or an ordinary image post.

## Procedure

1. Confirm that the user supplied the link and is authorized to access the content.
2. If terminal execution is available, inspect the note type. For a video, run:
   `python scripts/extract_recipe.py "<LINK>" --output output`
   For an ordinary image post, run:
   `python scripts/extract_post.py "<LINK>" --output output`
3. Read the files produced under `output/`: `transcript.txt` for speech, `ocr.txt` for image/video text, and `metadata.json` for status.
4. Combine speech and on-screen OCR. Prefer information repeated across frames or clearly spoken.
5. Remove duplicate OCR lines and obvious recognition noise.
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

8. State whether the recipe came from speech, OCR, or both. Mention missing or uncertain fields.

## Failure handling

- If the page requires login or a challenge, stop and explain that the public media was unavailable.
- If speech is empty, rely on OCR and screenshots if available.
- If OCR is too noisy to establish exact quantities, do not guess. Report the reliable title and steps only, and list the missing details.
- Do not request or expose cookies, QR-login data, session tokens, or passwords.
