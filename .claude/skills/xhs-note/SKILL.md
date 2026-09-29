---
name: xhs-note
description: "把小红书/RedNote 帖子（xhslink.com 短链或 xiaohongshu.com 链接，视频帖或图文帖）提取出正文、语音转写和图片/字幕文字，再转换成指定格式的 Markdown + JSON：菜谱、通用摘要、旅行攻略、好物测评、教程，或用户临时描述的任意格式。当用户给出小红书链接并要求提取、整理、转写、总结、做成菜谱/攻略/清单/笔记，或要求把已提取的帖子换一种格式时使用。"
argument-hint: "<小红书链接> [格式名 | 自定义格式描述]"
---

# 小红书帖子 → 任意格式

分三层：
1. **提取**：`scripts/extract_note.py` 产出与格式无关的素材。
2. **整理**：本文件里的通用规则，所有格式共用。
3. **格式**：`.claude/skills/xhs-note/formats/<name>.md`，每种格式一个文件，按需读取。

新增格式只需要往 `formats/` 里加一个文件，不改代码。

## 安全范围

- 只处理用户提供的、有权访问的公开链接。
- 不绕过登录、私密权限、付费墙、验证码或 DRM。
- 不索要、保存或展示 cookie、会话令牌、扫码登录数据或密码。
- 页面要求登录或出现验证时，停止并说明无法获取公开内容。

## 流程

### 1. 解析参数

从 `$ARGUMENTS` 或用户消息中找出链接，剩下的文字用来确定格式：

- **与某个格式文件的 `name` 或 `title` 匹配**（如 `recipe`、`菜谱`、`旅行攻略`）→ 使用该格式。
- **是一段对输出内容的描述**（如"店名、地址、人均、推荐菜"）→ 临时格式，见第 4 步。
- **没有格式要求** → 自动选择，见第 4 步。

如果用户没给链接，而是说"把刚才那篇换成 X 格式"，就沿用对话中最近一次的提取目录。

### 2. 提取素材（能复用就复用）

输出目录用 `output/<key>`：
- `xhslink.com/o/<短码>` → key = 短码
- `xiaohongshu.com/.../<24 位 note_id>` → key = note_id

如果 `output/<key>/metadata.json` 已存在且 `status` 为 `complete`，直接复用，不重新下载。否则运行：

```powershell
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
python scripts/extract_note.py "<链接>" --output "output/<key>"
```

第一行在 Windows 上刷新 PATH，避免新装的 FFmpeg 找不到。

- 视频帖要转写，耗时 2–4 分钟，建议放到后台运行。
- 失败时读取 `metadata.json` 的 `error` 字段，照实告诉用户，不要猜。

### 3. 读取素材

按顺序读取：

| 文件 | 内容 | 注意 |
|---|---|---|
| `metadata.json` | `note_id`、`note_type`（`video`/`normal`）、`title`、`author`、`published_at`、`video.has_audio`、`transcription` | 先看状态和警告。旧的提取结果没有 `author` 字段时，重新提取一次 |
| `caption.txt` | 作者写的标题、正文、标签 | 配料表、清单、行程经常完整写在这里 |
| `ocr.txt` | 视频帧 `[12.0s|0.91]` 或图片 `[image-03|0.88]` 中的文字 | 视频的字幕通常最完整 |
| `transcript.txt` | 带时间戳的语音转写 | 图文帖和无声视频为空 |
| `media/image-NN.jpg` | 图文帖的原图 | 有步骤图、价格牌、地图等只用图片表达的信息时，用 Read 直接看图 |

### 4. 确定格式

- **指定格式**：读取 `formats/<name>.md` 全文。
- **自动选择**：列出 `formats/` 下所有非 `_` 开头的文件，只读它们的 frontmatter（`name`、`title`、`description`），结合素材内容选出最合适的一个，并在回复里用一句话说明理由。都不合适时用 `summary`。
- **临时格式**：
  - 根据用户的描述自行设计 `data` 字段：字段名用英文 snake_case，未提及的信息不要加字段。
  - JSON 外壳不变，`format` 写成 `custom:<简短英文名>`。
  - 生成结果后问用户是否保存为可复用格式。用户同意后，按 `formats/_TEMPLATE.md` 的结构写入 `formats/<name>.md`。

### 5. 生成结果

先遵守下面的通用规则，再遵守格式文件里的"格式专属规则"。

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
  "sources_used": ["caption", "ocr", "transcript", "images"],
  "data": {},
  "uncertain": ["蒸制时间：字幕写 15 分钟，语音说 10 分钟"],
  "missing": ["总用时"]
}
```

- `sources_used` 只列实际用到的来源，取值限于 `caption`、`ocr`、`transcript`、`images`。
- `uncertain` 列出有疑问的内容：识别不清的文字，以及不同来源之间有冲突的地方。
- `missing` 列出格式要求但素材里没有的字段。这些字段在 `data` 中填 `null`（数组字段填 `[]`）。

**原作者和原帖链接（所有格式都要有，包括临时格式）**

Markdown 第一行的 `#` 标题下面，紧接着写这两行，每行前后都空一行：

```markdown
# <标题>

原作者：<source.author>

原链接：[点这里](<source.url>)
```

- `<source.author>` 取 `metadata.author`，也就是作者昵称；为 null 时写 `原作者：未知`。
- `<source.url>` 就是用户提供的原链接，和 JSON 里的 `source.url` 一致。不要换成跳转后的长链接，那条链接带有分享者 ID 等追踪参数。
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
- 给出两个结果文件的路径。

## 通用整理规则

**来源优先级**
- 作者正文 > 视频字幕/图片文字（OCR）> 语音转写 > 看图推断。
- 数字、用量、价格、时间、地址优先取正文和清晰的 OCR。

**不编造**
- 素材里没有的数量、温度、时长、价格、地址一律不补。字段填 `null`，并记入 `missing`。
- 可以根据图片描述清楚可见的动作，比如"面皮铺进模具"。但只要是推断出来的，就标 `[不确定]`，并记入 `uncertain`。

**冲突处理**
- 不同来源给出的数字不一致时，两个都写出来并注明来源，比如"蒸 15 分钟（字幕）/ 10 分钟（语音）"，不要替用户选。

**识别错误**
- OCR 看不清 → `[不确定]`；语音听不清 → `[听不清]`。
- 同音错字（如"糯米分"→"糯米粉"）只在上下文能完全确定时才改正。

**语音转写的已知问题**
- `transcription.warning` 存在：音轨基本是背景音乐，Whisper 容易幻觉出 "You" 之类的短句。忽略转写，以字幕 OCR 为准。
- 粤语配音：转写结果是繁体，同音错字很多（如"熟米澱粉"其实是"玉米淀粉"）。以字幕为准，转写只用来交叉核对。
- 输出统一用简体中文，除非用户另有要求。

**OCR 噪音**
- 去掉包装上的文字、品牌宣传语、`小红书` 水印、用户名、界面文字、推荐位文字，以及重复出现的片段。

**Live Photo**
- `metadata.json` 里的 `live_photo_count` 是图文帖中 2–4 秒的无声动图，不是教程视频，不要当作视频内容。

**广告与合作**
- 正文里出现"合作""广告""赞助"字样，或 @ 了品牌账号时，在结果里如实注明，不做评价。
