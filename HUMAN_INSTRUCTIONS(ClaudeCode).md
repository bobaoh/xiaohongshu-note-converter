# 使用说明（Claude Code 版）

把小红书帖子（视频或图文）整理成结构化的 Markdown + JSON 文档，比如菜谱、旅行攻略、好物测评、教程、通用摘要，或者你自己定义的格式。

所有处理都在你的电脑上完成：语音识别和文字识别（OCR）都在本地运行，视频和音频不会上传到第三方服务。

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

**一定要在仓库根目录启动 Claude Code**（也就是 `xiaohongshu-note-converter` 文件夹）。这个工具是项目级 skill，放在 `.claude/skills/xhs-note/` 里，在别的目录打开 Claude Code 就找不到它。

```bash
cd xiaohongshu-note-converter
claude
```

然后在 Claude Code 里输入：

```
/xhs-note http://xhslink.com/o/xxxx                      自动选择最合适的格式
/xhs-note http://xhslink.com/o/xxxx recipe               指定格式
/xhs-note http://xhslink.com/o/xxxx 店名、地址、人均、推荐菜   临时描述你想要的格式
/xhs-note 把刚才那篇换成 tutorial 格式                      复用已提取的内容，不重新下载
```

也可以不用 `/xhs-note` 命令，直接贴链接并说"整理成旅行攻略"，Claude 会自动调用这个 skill。

第一次运行时，Claude Code 会请求权限，比如运行 Python、写入文件。确认命令内容后同意即可。

## 3. 可用格式

| 格式名 | 中文名 | 适合的帖子 |
|---|---|---|
| `recipe` | 菜谱 | 做菜、烘焙、甜品、饮品 |
| `summary` | 通用摘要 | 任何帖子；没有更合适的格式时的默认选择 |
| `travel-guide` | 旅行攻略 | 行程、景点、交通、住宿 |
| `product-review` | 好物测评 | 好物推荐、开箱、对比、避雷 |
| `tutorial` | 教程 | 化妆、穿搭、手工、软件操作等分步骤教学 |

格式名和中文名都可以用，比如 `/xhs-note <链接> 菜谱`。

## 4. 结果在哪里

| 位置 | 内容 |
|---|---|
| `results/<帖子ID>-<格式>.md` | 整理好的文档，可以直接阅读 |
| `results/<帖子ID>-<格式>.json` | 同样内容的结构化数据，方便导入其他工具 |
| `output/<短码>/` | 提取的原始素材：正文、语音转写、OCR 文字和图片 |

Claude 会在结果里标出：
- 每部分内容来自哪里（正文、字幕、语音还是图片）
- 哪些地方不确定（`[不确定]`、`[听不清]`）
- 缺了哪些信息

它**不会编造**用量、价格、时间等数字。

每份 Markdown 结果的标题下面都会写上 `原作者：<作者昵称>` 和 `原链接：点这里`，点"点这里"会打开原帖，方便分享时注明出处。

`results/` 和 `output/` 都不会被 git 提交，因为里面是别人帖子的内容。

## 5. 添加自己的格式

**方法一：临时描述**

直接写出你想要的字段，例如：

```
/xhs-note <链接> 适合人群、难度、关键技巧、所需工具
```

Claude 生成结果后，会问你要不要把它保存成可复用的格式。

**方法二：写一个格式文件**

1. 复制 `.claude/skills/xhs-note/formats/_TEMPLATE.md`，改名为 `<格式名>.md`，放在同一个文件夹里。
2. 按模板里的说明填写四部分：字段说明表、JSON 示例、Markdown 模板、格式专属规则。
3. 用 `/xhs-note <链接> <格式名>` 调用。

不需要改任何代码。如果这个格式对别人也有用，欢迎提交 Pull Request。

## 6. 常见问题

**视频帖处理很慢？**
第一次运行要下载 Whisper 模型，约 500MB。之后每个视频还需要 2–4 分钟做语音转写，这是正常的。

**提示找不到 FFmpeg？**
刚装完 FFmpeg 时，已经打开的终端还读不到新的 PATH。关掉终端和 Claude Code 再重新打开即可。

**`/xhs-note` 命令不存在？**
确认 Claude Code 是在仓库根目录启动的，并且 `.claude/skills/xhs-note/SKILL.md` 这个文件存在。

**转写结果只有 "You" 或者一堆繁体错字？**
- 只有 "You"：说明视频只有背景音乐，Whisper 识别出了无意义的内容。Claude 会自动改用屏幕字幕。
- 繁体错字：通常是粤语配音，Claude 同样会以字幕为准。

**提示"帖子不可用"？**
帖子可能已被删除、是私密帖，或者需要登录才能查看。这个工具只处理公开帖子，不会绕过登录。

## 7. 注意事项

- 只处理你有权访问的公开帖子。
- 不要把 cookie、登录二维码、账号密码交给脚本或 AI。
- 整理出的内容版权属于原作者。分享时请注明出处，不要当作自己的原创内容发布。
