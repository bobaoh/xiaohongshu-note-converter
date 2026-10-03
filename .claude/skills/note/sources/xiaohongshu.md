# 来源：小红书 / RedNote（`source: xiaohongshu`）

- **帖子类型**：`note_type` 为 `video`（视频帖）或 `normal`（图文帖）。
- **输出目录**：`output/<短码或 note_id>/`（不在 `output/xiaohongshu/` 下，因为 xhs-library 读这个位置）。
- **素材**：`caption.txt` 是作者写的标题、正文、标签；图文帖的图片在 `media/image-NN.jpg`；视频帖有 `transcript.txt` 和逐帧 `ocr.txt`。

## 已知问题

**语音转写**
- `transcription.warning` 存在：音轨基本是背景音乐，Whisper 容易幻觉出 "You" 之类的短句。忽略转写，以字幕 OCR 为准。
- 粤语配音：转写结果是繁体，同音错字很多（如"熟米澱粉"其实是"玉米淀粉"）。以字幕为准，转写只用来交叉核对。

**OCR 噪音**
- `小红书` 水印、作者用户名会出现在几乎每一帧里，去掉。

**Live Photo**
- `live_photo_count` 是图文帖中 2–4 秒的无声动图，不是教程视频，不要当作视频内容。

**标题**
- 有的作者把标题写在正文第一行、标题字段留空；`title` 已经自动取了正文第一行。

**广告与合作**
- 正文出现"合作""广告""赞助"，或 @ 了品牌官方账号时，如实注明。

**成本**
- 视频帖最贵：每 1.5 秒截一帧做 OCR（约 1.8 秒/帧），2 分钟的视频 OCR 就要 2–3 分钟。`ocr_heavy`、`long_video` 多半来自这里。
