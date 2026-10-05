# 使用说明（Claude Code 版）

把链接整理成结构化的 Markdown + JSON 文档，比如菜谱、旅行攻略、好物测评、教程、通用摘要，或者你自己定义的格式。支持：

- **小红书帖子**：视频帖和图文帖
- **Reddit 帖子**：文字帖、图片、GIF、视频、多图帖、链接帖，连同评论（楼主写在评论里的菜谱也会读到）
- **任意网页**：文章、博客、菜谱网站、百科、文档

所有处理都在你的电脑上完成：语音识别和文字识别（OCR）都在本地运行，视频、音频和图片不会上传到第三方服务。每次转换都会记录花费的时间和资源，成本高的会被标出来。

## 1. 准备（只需一次）

你需要：

- **Python 3.11 到 3.14**（CI 测试过的版本范围）
- **[Claude Code](https://claude.com/claude-code)**
- **FFmpeg**：Windows 用户由安装脚本自动安装
- 约 **1GB 磁盘空间**，用于 Whisper 语音模型和 OCR 模型

### Windows

```powershell
git clone https://github.com/bobaoh/xiaohongshu-note-converter.git
cd xiaohongshu-note-converter
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
```

安装脚本会用 winget 安装 FFmpeg，并安装 `requirements.txt` 里的 Python 包。

### macOS / Linux

```bash
git clone https://github.com/bobaoh/xiaohongshu-note-converter.git
cd xiaohongshu-note-converter
brew install ffmpeg            # macOS
# sudo apt install ffmpeg      # Ubuntu / Debian
python3 -m pip install -r requirements.txt -c requirements.lock
```

## 2. 使用

**一定要在仓库根目录启动 Claude Code**（也就是 `xiaohongshu-note-converter` 文件夹）。这个工具是项目级 skill，放在 `.claude/skills/note/` 里，在别的目录打开 Claude Code 就找不到它。

```bash
cd xiaohongshu-note-converter
claude
```

然后在 Claude Code 里输入：

```
/note http://xhslink.com/o/xxxx                      小红书帖子，自动选择最合适的格式
/note https://example.com/某篇菜谱                     任意网页
/note https://www.reddit.com/r/GifRecipes/comments/xxxx/ 菜谱   Reddit 帖子
/note http://xhslink.com/o/xxxx recipe               指定格式
/note https://example.com/某篇游记 店名、地址、人均、推荐菜   临时描述你想要的格式
/note 把刚才那篇换成 tutorial 格式                      复用已提取的内容，不重新下载
```

也可以不用 `/note` 命令，直接贴链接并说"整理成旅行攻略"，Claude 会自动调用这个 skill。

原来的 `/xhs-note` 命令仍然可以用，但只支持小红书。新用法都用 `/note`。

第一次运行时，Claude Code 会请求权限，比如运行 Python、写入文件。确认命令内容后同意即可。

### 找 Reddit 热门帖子

在 `reddit_topics.toml` 里写好你关心的主题（看哪些版块、按什么排序、标题里要有或不要有哪些词），然后在终端运行：

```powershell
python .\scripts\discover.py             # 列出每个主题会选中的帖子，不做任何改动
python .\scripts\discover.py --extract   # 同时提取选中的帖子
```

已经提取过的帖子不会再被选中。提取完后，用 `/note <帖子链接>` 把它整理成笔记。每天自动抓取并生成笔记的功能已经设计好（见 `docs/reddit.md`），还没有实现。

Reddit 限制大约每分钟一次请求，所以每看一个版块、每提取一个帖子都要等将近一分钟。

## 3. 可用格式

| 格式名 | 中文名 | 适合的帖子 |
|---|---|---|
| `recipe` | 菜谱 | 做菜、烘焙、甜品、饮品 |
| `summary` | 通用摘要 | 任何帖子；没有更合适的格式时的默认选择 |
| `travel-guide` | 旅行攻略 | 行程、景点、交通、住宿 |
| `product-review` | 好物测评 | 好物推荐、开箱、对比、避雷 |
| `tutorial` | 教程 | 化妆、穿搭、手工、软件操作等分步骤教学 |

格式名和中文名都可以用，比如 `/note <链接> 菜谱`。

## 4. 结果在哪里

| 位置 | 内容 |
|---|---|
| `results/<ID>-<格式>.md` | 整理好的文档，可以直接阅读 |
| `results/<ID>-<格式>.json` | 同样内容的结构化数据，方便导入其他工具 |
| `output/<短码>/` | 小红书帖子提取的原始素材：正文、语音转写、OCR 文字和图片 |
| `output/reddit/<帖子ID>/` | Reddit 帖子提取的原始素材：正文、评论、图片或 GIF 里的文字、视频转写 |
| `output/web/<ID>/` | 网页提取的原始素材：正文、图片和图片里的文字 |
| `logs/conversions.jsonl` | 每次转换的成本记录，见下一节 |

Claude 会在结果里标出：
- 每部分内容来自哪里（正文、字幕、语音还是图片）
- 哪些地方不确定（`[不确定]`、`[听不清]`）
- 缺了哪些信息

它**不会编造**用量、价格、时间等数字。

每份 Markdown 结果的标题下面都会写上 `原作者：<作者昵称>` 和 `原链接：点这里`，点"点这里"会打开原帖，方便分享时注明出处。

`results/`、`output/`、`logs/` 都不会被 git 提交，因为里面是别人的内容和你自己的使用记录。

## 5. 转换成本

每次转换都会记录花了多少：
- 各步骤耗时
- 下载量
- 视频时长
- 做了多少帧和图片的 OCR
- 整理时 AI 要读多少内容

超过 `cost_policy.toml` 里的阈值就会被标为"成本高"，Claude 会在回复里告诉你原因。

| 链接类型 | 一般耗时 |
|---|---|
| 网页 | 1–8 秒 |
| Reddit 文字帖 | 几秒，另外可能要等 Reddit 限流，最多约 1 分钟 |
| Reddit GIF 菜谱 | GIF 常有几十 MB，约 2–3 分钟，主要花在逐帧 OCR 上 |
| 小红书图文帖 | 约 30 秒 |
| 2 分钟的小红书视频 | 约 3 分钟，其中约 85% 花在视频截图的 OCR 上 |

查看哪些转换成本高、时间花在哪里：

```powershell
python .\scripts\cost_report.py              # 汇总
python .\scripts\cost_report.py --expensive  # 只看成本高的
```

现在只标记，不会拒绝任何转换。网页最多处理 8 张图（`cost_policy.toml` 里的 `[web] max_images` 可以改）。

## 6. 添加自己的格式

**方法一：临时描述**

直接写出你想要的字段，例如：

```
/note <链接> 适合人群、难度、关键技巧、所需工具
```

Claude 生成结果后，会问你要不要把它保存成可复用的格式。

**方法二：写一个格式文件**

1. 复制 `.claude/skills/xhs-note/formats/_TEMPLATE.md`，改名为 `<格式名>.md`，放在同一个文件夹里。格式文件对小红书和网页通用。
2. 按模板里的说明填写四部分：字段说明表、JSON 示例、Markdown 模板、格式专属规则。
3. 用 `/note <链接> <格式名>` 调用。

不需要改任何代码。如果这个格式对别人也有用，欢迎提交 Pull Request。

## 7. 常见问题

**视频帖处理很慢？**
第一次运行要下载 Whisper 模型，约 500MB。之后每个视频还需要 2–4 分钟做语音转写，这是正常的。

**提示找不到 FFmpeg？**
刚装完 FFmpeg 时，已经打开的终端还读不到新的 PATH。关掉终端和 Claude Code 再重新打开即可。

**`/note` 命令不存在？**
确认 Claude Code 是在仓库根目录启动的，并且 `.claude/skills/note/SKILL.md` 这个文件存在。

**网页提示"No readable content"，或者结果里说正文很少？**
这个网页可能要靠 JavaScript 加载内容、需要登录，或者拒绝自动访问。这个工具只读取直接打开就能看到的公开内容。

**网页里的视频没有被整理进去？**
目前只处理网页的文字和图片。页面里嵌入的视频（YouTube、B 站等）会列在结果里，但不会转写。

**网页的图片只处理了一部分？**
默认最多处理 8 张，太小的图标和缩略图会跳过。可以在 `cost_policy.toml` 的 `[web]` 里调整。

**Reddit 链接要等很久才开始？**
Reddit 限制大约每分钟一次请求，工具会按 Reddit 的要求等待，最多约一分钟。不要同时开好几个 Reddit 提取，它们共用同一个限额。

**Reddit 多图帖只整理了第一张图？**
工具读取的是 Reddit 公开的 RSS，不登录。RSS 只给出多图帖第一张图的预览。其他图片里的信息会写在"缺少的信息"里，可以打开原帖查看。

**Reddit 提示 HTTP 403？**
版块可能是私密或隔离的，或者 Reddit 暂时拒绝自动访问。工具不会绕过，过一段时间再试即可。

**转写结果只有 "You" 或者一堆繁体错字？**
- 只有 "You"：说明视频只有背景音乐，Whisper 识别出了无意义的内容。Claude 会自动改用屏幕字幕。
- 繁体错字：通常是粤语配音，Claude 同样会以字幕为准。

**提示"帖子不可用"？**
帖子可能已被删除、是私密帖，或者需要登录才能查看。这个工具只处理公开帖子，不会绕过登录。

## 8. 注意事项

- 只处理你有权访问的公开帖子和网页。Reddit 只读公开的 RSS，不登录，也不绕过限流或封锁。
- 不要把 cookie、登录二维码、账号密码交给脚本或 AI。
- 整理出的内容版权属于原作者。分享时请注明出处，不要当作自己的原创内容发布。
