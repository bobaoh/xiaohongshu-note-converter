# 来源：Reddit 帖子（`source: reddit`）

reddit.com 和 redd.it 上的帖子链接，包括 App 分享出来的 `/r/<版块>/s/<代码>` 链接。版块首页（如 `reddit.com/r/Cooking/`）不是帖子，提取会被拒绝；要批量找热门帖子，用 `python scripts/discover.py`（见 docs/reddit.md）。

素材来自 Reddit 公开的 RSS，不登录。RSS 没有点赞数、评论数和楼层关系。

- **帖子类型**：`note_type` 是 `video`（GIF 动图和视频帖）或 `post`（其他）。更细的类型在 `post_kind`：
  - `text`：文字帖
  - `image`：单图
  - `gif`：动图，按无声视频处理，画面文字在 `ocr.txt`
  - `video`：Reddit 视频，有语音时会转写
  - `gallery`：多图帖
  - `link`：指向外部网页
  - `crosspost`：转帖
- **输出目录**：`output/reddit/<帖子 id>/`。
- **作者**：`metadata.author` 写成 `u/用户名`，原作者那一行照写，如 `原作者：u/TheLadyEve`。
- **正文**：`caption.txt` 包含标题、作者、版块、发布时间、帖子类型和正文。链接帖还附有外部网页的正文（只读了文字，没处理图片）和它的 schema.org 数据（`structured.json`）。

## comments.txt

- 评论按 Reddit 默认排序排列，回复紧跟在被回复的评论后面，但看不出谁回复谁。
- 保留了楼主的**全部**评论，以及其他人的前 `max_comments` 条（默认 20 条，在 `cost_policy.toml` 的 `[reddit]` 里设置）。机器人（AutoModerator）和已删除的评论已去掉。
- **`[楼主]` 的评论等同于作者本人写的正文。** r/GifRecipes、r/recipes 等版块要求把菜谱写在楼主自己的评论里，所以菜谱的配料和步骤常常只在那里。用到时 `sources_used` 写 `comments`。
- 其他人的评论只能作为补充，例如替换食材、常见问题、失败经验。写进结果时注明"来自评论"，不能覆盖楼主给出的数字。
- 评论里常有玩笑和跑题内容，与格式无关的不要写进结果。

## metadata.json 里的 Reddit 字段

| 字段 | 含义 |
|---|---|
| `post_kind` | 见上面的帖子类型 |
| `post_id` / `subreddit` | Reddit 的帖子 ID / 版块名 |
| `link` | 帖子指向的图片、视频、多图或外部网页 |
| `comments_read` / `comments_kept` / `op_comments` | RSS 里的评论数 / 保留下来的评论数 / 其中楼主的评论数 |
| `linked_page` | 链接帖读取外部网页的结果：`read`、`failed`（附 `error`）、`skipped`（视频网站）或 `not followed` |
| `unprocessed_media` | 没有处理的内容：多图帖第 2 张以后的图片、外部视频 |
| `content_warning` | 多图帖只有第一张图的预览、转帖没有读原帖、正文已被删除等；照实告诉用户 |
| `score` / `num_comments` | 只有以后接入官方 API 才会出现；RSS 没有 |

## 注意

- **外文**：Reddit 帖子大多是英文。按通用规则翻译成简体中文，用量和专有名词保留原文写法（如 "1½ tbsp cracked black pepper" 写成"粗磨黑胡椒 1½ 汤匙（1½ tbsp）"）。美制单位不要自行换算成克；需要的话在括号里注明"约"。
- **多图帖**：RSS 只给出第一张图裁切后的预览。图里的信息如果只能从其他图片得到，写进 `missing`，并告诉用户可以打开原帖看。
- **GIF 菜谱**：画面上的文字（OCR）通常只有步骤名和部分用量，完整的用量看楼主评论。两者冲突时都写出来。
- **成本**：Reddit 本身很快，慢的是等待限流（`cost.stages.rate_limit_wait`）和 GIF/视频的 OCR。GIF 文件可能有几十 MB（`large_download`）。
