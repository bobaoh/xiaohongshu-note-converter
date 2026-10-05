# 使用说明（Codex 版）

把链接整理成结构化的 Markdown + JSON 文档，比如菜谱、旅行攻略、好物测评、教程、通用摘要，或者你自己定义的格式。支持：

- **小红书帖子**：视频帖和图文帖
- **Reddit 帖子**：文字帖、图片、GIF、视频、多图帖、链接帖，连同评论（楼主写在评论里的菜谱也会读到）
- **任意网页**：文章、博客、菜谱网站、百科、文档

所有处理都在你的电脑上完成：语音识别和文字识别（OCR）都在本地运行，视频、音频和图片不会上传到第三方服务。每次转换都会记录花费的时间和资源，成本高的会被标出来。

> 在仓库根目录启动 Codex 时，它会自动读取 `AGENTS.md`。`AGENTS.md` 会让 Codex 去读 `.claude/skills/note/SKILL.md` 里的整理规则，这份规则和 Claude Code 版共用，所以两个工具的输出格式和规则完全一致。

## 1. 准备（只需一次）

你需要：

- **Python 3.11 到 3.14**（CI 测试过的版本范围）
- **Codex CLI**
- **FFmpeg**：Windows 用户由安装脚本自动安装
- 约 **1GB 磁盘空间**，用于 Whisper 语音模型和 OCR 模型

### Windows

```powershell
git clone https://github.com/bobaoh/xiaohongshu-note-converter.git
cd xiaohongshu-note-converter
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
```

如果你是在 WSL 里运行 Codex，请按下面 Linux 的步骤安装，保证 Codex 能在同一个环境里找到 Python 和 FFmpeg。

### macOS / Linux

```bash
git clone https://github.com/bobaoh/xiaohongshu-note-converter.git
cd xiaohongshu-note-converter
brew install ffmpeg            # macOS
# sudo apt install ffmpeg      # Ubuntu / Debian
python3 -m pip install -r requirements.txt -c requirements.lock
```

### 允许 Codex 联网

提取脚本要联网：打开帖子页面、下载图片或视频，第一次运行时还要下载语音模型。Codex 默认的沙箱会**禁止网络访问**，脚本会报网络错误。有两种解决方法，任选一种：

**方法一（推荐）：** 在 `~/.codex/config.toml` 中打开沙箱内的网络访问：

```toml
[sandbox_workspace_write]
network_access = true
```

**方法二：** Codex 请求在沙箱外运行命令时，确认命令内容后批准。

不同版本的 Codex 配置项可能不同，以你所用版本的官方文档为准。

## 2. 使用

**一定要在仓库根目录启动 Codex**，否则它读不到 `AGENTS.md`：

```bash
cd xiaohongshu-note-converter
codex
```

然后直接贴链接，并说明你想要的格式：

```
http://xhslink.com/o/xxxx 整理成旅行攻略
https://example.com/某篇菜谱 recipe                （任意网页）
https://www.reddit.com/r/GifRecipes/comments/xxxx/ 菜谱   （Reddit 帖子）
http://xhslink.com/o/xxxx                       （不写格式，自动选择）
https://example.com/某篇游记 店名、地址、人均、推荐菜  （临时描述你想要的字段）
把刚才那篇换成 tutorial 格式                       （复用已提取的内容，不重新下载）
```

如果 Codex 没有按规则处理，比如没生成结果文件、没做校验，就在消息开头加一句"按 AGENTS.md 的流程处理"。

Codex 会依次完成这些步骤：
1. 运行 `scripts/extract.py` 提取素材，它会自动识别是小红书、Reddit 还是普通网页。
2. 读取 `.claude/skills/xhs-note/formats/` 下对应的格式文件。
3. 写出结果文件。
4. 运行 `scripts/validate_result.py` 校验结果。
5. 如果这次转换成本高，在回复里说明原因。

### 找 Reddit 热门帖子

在 `reddit_topics.toml` 里写好你关心的主题（看哪些版块、按什么排序、标题里要有或不要有哪些词），然后在终端运行：

```bash
python scripts/discover.py             # 列出每个主题会选中的帖子，不做任何改动
python scripts/discover.py --extract   # 同时提取选中的帖子
```

已经提取过的帖子不会再被选中。提取完后，把帖子链接发给 Codex 整理成笔记。每天自动抓取并生成笔记的功能已经设计好（见 `docs/reddit.md`），还没有实现。

Reddit 限制大约每分钟一次请求，所以每看一个版块、每提取一个帖子都要等将近一分钟。

## 3. 可用格式

| 格式名 | 中文名 | 适合的帖子 |
|---|---|---|
| `recipe` | 菜谱 | 做菜、烘焙、甜品、饮品 |
| `summary` | 通用摘要 | 任何帖子；没有更合适的格式时的默认选择 |
| `travel-guide` | 旅行攻略 | 行程、景点、交通、住宿 |
| `product-review` | 好物测评 | 好物推荐、开箱、对比、避雷 |
| `tutorial` | 教程 | 化妆、穿搭、手工、软件操作等分步骤教学 |

## 4. 结果在哪里

| 位置 | 内容 |
|---|---|
| `results/<ID>-<格式>.md` | 整理好的文档，可以直接阅读 |
| `results/<ID>-<格式>.json` | 同样内容的结构化数据，方便导入其他工具 |
| `output/<短码>/` | 小红书帖子提取的原始素材：正文、语音转写、OCR 文字和图片 |
| `output/reddit/<帖子ID>/` | Reddit 帖子提取的原始素材：正文、评论、图片或 GIF 里的文字、视频转写 |
| `output/web/<ID>/` | 网页提取的原始素材：正文、图片和图片里的文字 |
| `logs/conversions.jsonl` | 每次转换的成本记录 |

结果里会标出：
- 每部分内容来自哪里（正文、字幕、语音还是图片）
- 哪些地方不确定（`[不确定]`、`[听不清]`）
- 缺了哪些信息

规则要求**不编造**用量、价格、时间等数字。

每份 Markdown 结果的标题下面都会写上 `原作者：<作者昵称>` 和 `原链接：点这里`，点"点这里"会打开原帖，方便分享时注明出处。

**请检查 Codex 有没有跑校验。** 如果回复里没有提到 `validate_result.py` 的结果，可以让它补跑：

```bash
python scripts/validate_result.py results/<帖子ID>-<格式>.json
```

**关于图片：** `SKILL.md` 要求在需要时直接查看 `media/` 里的图片，比如步骤图、路线图、价目表。如果你的 Codex 看不到本地图片，结果就只能依赖 OCR 文字，图片里没有文字说明的步骤可能会缺失。这种情况下可以请它在 `missing` 里注明。

**转换成本：** 每次转换的耗时、OCR 数量、AI 要读的内容量都会记录下来，超过 `cost_policy.toml` 的阈值会被标为成本高。查看汇总：

```bash
python scripts/cost_report.py              # 汇总
python scripts/cost_report.py --expensive  # 只看成本高的
```

网页一般 1–8 秒，小红书图文帖约 30 秒，2 分钟的视频约 3 分钟（大部分时间花在视频截图的 OCR 上）。Reddit 帖子可能要先等最多约 1 分钟的限流；GIF 菜谱常有几十 MB，约 2–3 分钟。

## 5. 添加自己的格式

1. 复制 `.claude/skills/xhs-note/formats/_TEMPLATE.md`，改名为 `<格式名>.md`，放在同一个文件夹里。
2. 按模板里的说明填写四部分：字段说明表、JSON 示例、Markdown 模板、格式专属规则。
3. 发链接时写上格式名，比如 `http://xhslink.com/o/xxxx <格式名>`。

也可以先临时描述字段，满意后请 Codex "按 `_TEMPLATE.md` 的结构把这个格式保存到 formats 文件夹"。

## 6. 常见问题

**脚本报网络错误或超时？**
多半是 Codex 沙箱禁止了联网，按第 1 节"允许 Codex 联网"设置。

**视频帖处理很慢？**
第一次运行要下载 Whisper 模型，约 500MB。之后每个视频还需要 2–4 分钟做语音转写，这是正常的。

**提示找不到 FFmpeg？**
- 关掉终端再重新打开，让新的 PATH 生效。
- 如果你在 WSL 里运行 Codex，FFmpeg 也要装在 WSL 里。

**Codex 没按格式输出，或者跳过了某些规则？**
- 先确认 Codex 是在仓库根目录启动的，这样才会读到 `AGENTS.md`。
- 然后提醒它重新阅读 `.claude/skills/note/SKILL.md` 和对应的格式文件，修正结果并重新校验。

**Reddit 链接要等很久才开始？**
Reddit 限制大约每分钟一次请求，工具会按 Reddit 的要求等待，最多约一分钟。不要同时开好几个 Reddit 提取，它们共用同一个限额。

**Reddit 多图帖只整理了第一张图？**
工具读取的是 Reddit 公开的 RSS，不登录。RSS 只给出多图帖第一张图的预览。其他图片里的信息会写在"缺少的信息"里，可以打开原帖查看。

**Reddit 提示 HTTP 403？**
版块可能是私密或隔离的，或者 Reddit 暂时拒绝自动访问。工具不会绕过，过一段时间再试即可。

**网页提示"No readable content"，或者结果里说正文很少？**
这个网页可能要靠 JavaScript 加载内容、需要登录，或者拒绝自动访问。这个工具只读取直接打开就能看到的公开内容。

**网页里的视频没有被整理进去？**
目前只处理网页的文字和图片。页面里嵌入的视频会列在结果里，但不会转写。

**转写结果只有 "You" 或者一堆繁体错字？**
- 只有 "You"：说明视频只有背景音乐，应改用屏幕字幕。
- 繁体错字：通常是粤语配音，也应以字幕为准。

这两种情况 `SKILL.md` 里都有说明，Codex 按规则会自动处理。

**提示"帖子不可用"？**
帖子可能已被删除、是私密帖，或者需要登录才能查看。这个工具只处理公开帖子，不会绕过登录。

## 7. 注意事项

- 只处理你有权访问的公开帖子和网页。
- 不要把 cookie、登录二维码、账号密码交给脚本或 AI。
- 整理出的内容版权属于原作者。分享时请注明出处，不要当作自己的原创内容发布。
