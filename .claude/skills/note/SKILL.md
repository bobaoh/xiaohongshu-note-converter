---
name: note
description: "把任意链接（小红书/RedNote 帖子、Reddit 帖子，或任何网页：文章、博客、菜谱网站、文档）提取出正文、评论、图片文字、语音转写，再转换成指定格式的 Markdown + JSON：菜谱、通用摘要、旅行攻略、好物测评、教程，或用户临时描述的任意格式。当用户给出链接并要求提取、整理、总结、转写、做成菜谱/攻略/清单/笔记，或要求把已提取的内容换一种格式时使用。会标出成本高的转换。"
argument-hint: "<链接> [格式名 | 自定义格式描述]"
---

# 任意链接 → 任意格式

分四层：
1. **提取**：`scripts/extract.py` 按链接自动选择来源（`notekit/sources/`），产出与格式无关的素材，并记录成本。
2. **来源说明**：`.claude/skills/note/sources/<source>.md`，每种来源的已知问题和注意事项。
3. **整理**：本文件里的通用规则，所有来源、所有格式共用。
4. **格式**：`.claude/skills/xhs-note/formats/<name>.md`，每种格式一个文件，按需读取。格式文件放在 `xhs-note` 目录下是因为 xhs-library 项目从那里读取，所有来源共用。

`/xhs-note` 是只处理小红书的旧入口，xhs-library 在用，保持不变。新的用法都走本 skill。

## 安全范围

- 只处理用户提供的、有权访问的公开链接。
- 不绕过登录、私密权限、付费墙、验证码或 DRM。
- 不索要、保存或展示 cookie、会话令牌、扫码登录数据或密码。
- 页面要求登录、出现验证或拒绝访问时，停止并说明无法获取公开内容。

## 流程

### 1. 解析参数

从 `$ARGUMENTS` 或用户消息中找出链接，剩下的文字用来确定格式：

- **与某个格式文件的 `name` 或 `title` 匹配**（如 `recipe`、`菜谱`、`旅行攻略`）→ 使用该格式。
- **是一段对输出内容的描述**（如"店名、地址、人均、推荐菜"）→ 临时格式，见第 4 步。
- **没有格式要求** → 自动选择，见第 4 步。

如果用户没给链接，而是说"把刚才那篇换成 X 格式"，就沿用对话中最近一次的提取目录。

### 2. 提取素材

```powershell
python scripts/extract.py "<链接>"
```

**这条命令单独运行**，不要在同一次调用里加别的命令（如 `cd`、刷新 PATH）。xhs-library 调用本 skill 时只允许以 `python scripts/extract.py` 和 `python scripts/validate_result.py` 开头的命令，合在一起的命令会被整条拒绝。

只有当它报错 "FFmpeg is not installed or is not on PATH"（Windows 上刚装完 FFmpeg 时）才刷新 PATH，然后**另起一次调用**重新运行上面的命令：

```powershell
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
```

- 脚本自己决定输出目录并打印出来：小红书是 `output/<短码或 note_id>/`，Reddit 是 `output/reddit/<帖子 id>/`，其他网页是 `output/web/<id>/`。只想知道目录时加 `--where`。
- 已有完整的提取结果时，脚本直接复用，不重新下载；用户要求重新提取时加 `--force`。
- 视频要转写，耗时 2–4 分钟，建议放到后台运行。网页通常几秒。Reddit 限制大约每分钟一次请求，可能要先等上一分钟。
- 失败时读取 `metadata.json` 的 `error` 字段，照实告诉用户，不要猜。

### 3. 读取素材

先读 `metadata.json`，按其中的 `source` 读取 `.claude/skills/note/sources/<source>.md`，再按顺序读取：

| 文件 | 内容 | 注意 |
|---|---|---|
| `metadata.json` | `source`、`note_id`、`note_type`、`title`、`author`、`published_at`、`cost`，以及来源特有字段 | 先看状态、警告和成本 |
| `caption.txt` | 作者自己写的文字：帖子正文，或网页正文 | 用量、清单、步骤经常完整写在这里 |
| `structured.json` | 网页公开的 schema.org 数据（菜谱配料、步骤、产品价格） | 只有部分网页有；内容已汇总在 `caption.txt` 末尾 |
| `ocr.txt` | 视频帧 `[12.0s|0.91]` 或图片 `[image-03|0.88]` 中的文字 | 视频的字幕通常最完整 |
| `transcript.txt` | 带时间戳的语音转写 | 没有语音时为空 |
| `comments.txt` | 帖子下的评论（目前只有 Reddit），`[楼主]` 标出作者本人的评论 | 只有部分来源有；读法见来源说明 |
| `media/image-NN.jpg` | 帖子或网页正文里的图片 | 有步骤图、价格牌、地图等只用图片表达的信息时，用 Read 直接看图 |

### 成本

`metadata.json` 的 `cost` 记录这次转换花了多少：各阶段耗时、下载量、视频时长、OCR 的帧数和图片数，以及整理这一步要读多少内容（`ai_input`）。超过 `cost_policy.toml` 的阈值时 `cost.expensive` 为 true，`cost.flags` 说明原因。

- `cost.expensive` 为 true 时，在回复里用一句话告诉用户哪里贵、贵在哪（例如"视频 OCR 用了 159 秒"），不要省略。
- `large_ai_text`（正文很长）：不要一次读完全文。先读开头和目录结构，再用 Read 的 offset/limit 或 Grep 只读格式需要的部分，并在回复中说明只用了哪些部分。
- `many_ai_images`（图片很多）：只看文字素材说不清的图片，并在 `sources_used` 和回复中如实说明看了哪些。
- 不要为了降低成本而跳过格式要求的信息；读不到的写进 `missing`。

### 4. 确定格式

- **指定格式**：读取 `formats/<name>.md` 全文。
- **自动选择**：列出 `formats/` 下所有非 `_` 开头的文件，只读它们的 frontmatter（`name`、`title`、`description`），结合素材内容选出最合适的一个，并在回复里用一句话说明理由。都不合适时用 `summary`。
- **临时格式**：
  - 根据用户的描述自行设计 `data` 字段：字段名用英文 snake_case，未提及的信息不要加字段。
  - JSON 外壳不变，`format` 写成 `custom:<简短英文名>`。
  - 生成结果后问用户是否保存为可复用格式。用户同意后，按 `formats/_TEMPLATE.md` 的结构写入 `formats/<name>.md`。

### 5. 生成结果

先遵守下面的通用规则和来源说明，再遵守格式文件里的"格式专属规则"。

生成两份内容：
- **Markdown**：按格式文件的"Markdown 模板"。
- **JSON**：外壳如下，其中 `data` 按格式文件的"JSON 示例"。

```json
{
  "format": "recipe",
  "source": {
    "url": "<metadata.input_url>",
    "note_id": "<metadata.note_id>",
    "title": "<metadata.title>",
    "author": "<metadata.author 或 null>",
    "note_type": "<metadata.note_type>",
    "published_at": "<metadata.published_at 或 null>"
  },
  "sources_used": ["caption", "ocr", "transcript", "images", "structured"],
  "data": {},
  "uncertain": ["蒸制时间：字幕写 15 分钟，语音说 10 分钟"],
  "missing": ["总用时"]
}
```

- `sources_used` 只列实际用到的来源，取值限于 `caption`、`ocr`、`transcript`、`images`、`structured`、`comments`。
- `uncertain` 列出有疑问的内容：识别不清的文字，以及不同来源之间有冲突的地方。
- `missing` 列出格式要求但素材里没有的字段。这些字段在 `data` 中填 `null`（数组字段填 `[]`）。

**原作者和原链接（所有格式都要有，包括临时格式）**

Markdown 第一行的 `#` 标题下面，紧接着写这两行，每行前后都空一行：

```markdown
# <标题>

原作者：<source.author>

原链接：[点这里](<source.url>)
```

- `<source.author>` 取 `metadata.author`；为 null 时写 `原作者：未知`。
- `<source.url>` 就是用户提供的原链接，和 JSON 里的 `source.url` 一致。不要换成跳转后的长链接，那条链接常带有分享者 ID 等追踪参数。
- 这两行放在格式模板的其他内容（如 `📅 行程`、`> 一句话概括`）之前。
- 格式文件的 Markdown 模板里不用写这两行。

### 6. 保存并校验

写入两个文件（`results/` 不存在就先创建）：
- `results/<note_id>-<format>.md`
- `results/<note_id>-<format>.json`

临时格式的文件名用 `custom-<name>`。然后运行：

```powershell
python scripts/validate_result.py "results/<note_id>-<format>.json"
```

退出码非 0 时按提示修正，再重新校验，直到通过。

### 7. 回复用户

- 在对话中展示 Markdown 结果。
- 用一两句话说明：内容来自哪些素材、哪些地方不确定或缺失。
- 成本高的转换（`cost.expensive`）说明原因。
- 给出两个结果文件的路径。

## 通用整理规则

**来源优先级**
- 作者自己写的文字（帖子正文、作者本人的评论、网页正文、网页公开的结构化数据）> 视频字幕/图片文字（OCR）> 语音转写 > 其他人的评论 > 看图推断。
- 其他人的评论只能作为补充（如替换食材、常见问题），写进结果时注明"来自评论"，不能覆盖作者给出的数字。
- 数字、用量、价格、时间、地址优先取正文和清晰的 OCR。

**不编造**
- 素材里没有的数量、温度、时长、价格、地址一律不补。字段填 `null`，并记入 `missing`。
- 可以根据图片描述清楚可见的内容，比如"面皮铺进模具"。但只要是推断出来的，就标 `[不确定]`，并记入 `uncertain`。

**冲突处理**
- 不同来源给出的数字不一致时，两个都写出来并注明来源，比如"蒸 15 分钟（字幕）/ 10 分钟（语音）"，不要替用户选。

**识别错误**
- OCR 看不清 → `[不确定]`；语音听不清 → `[听不清]`。
- 同音错字只在上下文能完全确定时才改正。

**噪音**
- 去掉包装上的文字、品牌宣传语、水印、用户名、界面文字、推荐位和广告位文字，以及重复出现的片段。

**语言**
- 输出统一用简体中文，除非用户另有要求。原文是外文时，专有名词和用量单位保留原文写法（如 `100g plain flour` 译为"普通面粉 100g"，必要时括注原文）。

**广告与合作**
- 正文里出现"合作""广告""赞助""sponsored"字样，或明显是推广内容时，在结果里如实注明，不做评价。
