# 来源：普通网页（`source: web`）

所有不属于其他来源的 http(s) 链接都走这里：新闻、博客、菜谱网站、文档、百科。

- **帖子类型**：`note_type` 为 `article`。
- **输出目录**：`output/web/<id>/`，`id` 和 `note_id` 由去掉追踪参数后的网址算出，同一篇文章的不同分享链接会落到同一个目录。
- **正文**：`caption.txt` 的"正文："部分是 trafilatura 提取的网页主体，导航、侧栏、页脚、评论都已去掉，保留了标题层级、列表和表格（Markdown）。
- **图片位置**：正文里的 `[图 image-03：说明]` 表示这里有一张已下载的图（`media/image-03.jpg`，OCR 结果在 `ocr.txt` 的 `[image-03|…]` 行）；`[图：说明]` 表示图片太小（图标、缩略图）或下载失败，没有保存。
- **结构化数据**：很多菜谱和商品页用 schema.org 公开了配料、步骤、价格。它们在 `structured.json`，并汇总在 `caption.txt` 末尾的"页面结构化数据"部分。这是网站作者写的，和正文同等可信；两者不一致时都写出来。

## metadata.json 里的网页字段

| 字段 | 含义 |
|---|---|
| `site_name` | 网站名 |
| `canonical_url` | 去掉追踪参数后的网址 |
| `text_chars` | 正文字数 |
| `images_found` / `image_count` | 正文里的图片数 / 实际保存并做了 OCR 的图片数 |
| `images_skipped` | 超过 `cost_policy.toml` 里 `[web] max_images` 而没有处理的图片数 |
| `images_small` / `images_failed` | 太小而丢弃的 / 下载或解码失败的图片数 |
| `cover_image` | 网页的分享封面图地址；不下载，因为它通常只是标题的预览图 |
| `structured_types` | 页面公开的 schema.org 类型，如 `Recipe`、`Product` |
| `unprocessed_media` | 页面中嵌入的视频地址，**没有转写**；结果里要说明视频内容没有包含进来 |
| `content_warning` | 正文很少：页面可能靠 JavaScript 加载内容或需要登录；照实告诉用户，不要凭标题猜内容 |

## 注意

- **作者**：可能是机构或网站名（如"维基媒体项目贡献者"），照实写。
- **发布时间**：来自页面元数据，有时是"最后更新时间"。只写日期，不要据此推断内容是否过时。
- **外文网页**：按通用规则翻译成简体中文，用量和专有名词保留原文写法。
- **图片**：最多处理 `max_images` 张（默认 8）。`images_skipped` 大于 0 时，在回复中说明还有图片没有处理。
- **成本**：网页通常只要几秒。贵的情况主要是正文特别长（`large_ai_text`），按 SKILL.md 的"成本"一节分段读取。
