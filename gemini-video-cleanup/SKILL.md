---
name: Gemini Notebook 视频净化成片
description: 批量处理 Gemini Notebook / NotebookLM 导出的视频：烧录中文字幕（自动断句与时间重分配）、用自定义小水印遮盖右下角 Gemini Notebook 水印、自动检测并裁掉片尾 logo。支持横版 1280x720 与竖版 720x1280 的 mp4(+srt)，输出到「成片」文件夹。触发词：加字幕、盖水印、去水印、去片尾、批量剪辑、视频净化、Gemini Notebook、NotebookLM。
---

# Gemini Notebook 视频净化成片

把 NotebookLM / Gemini Notebook 导出的 `mp4 (+ srt)` 批量处理成可发布的成片：

1. **字幕**（可选）：把 SRT 烧录进画面；长段落 SRT 会按标点自动拆成 ≤20 字的小句，并按字数比例重新分配时间。样式：微软雅黑粗体、**黄色 #FFE000**、黑色描边（40px / 720p 基准，随分辨率缩放）。
2. **水印**：在右下角原 `✦ Gemini Notebook` 水印位置盖一枚不透明的品牌小标签（默认米色底 + 深棕字），彻底遮住原水印。**水印文字不在技能内写死**，由使用者首次配置（见下文）。
3. **片尾**：自动检测片尾卡（白底或黑底 Gemini logo），在其前一帧截断。

已验证：Windows PowerShell 5.1 + ffmpeg/ffprobe（需在 PATH 中），横版 1280x720@24 与竖版 720x1280@30 素材，白/黑两种片尾模板均覆盖。

## 首次使用（必须）

水印文字按使用者区分，技能本身**不内置任何人的品牌/账号信息**。

1. 首次使用先设置水印文字（之后每次处理自动使用，无需反复输入）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\scripts\set-config.ps1" -WatermarkText "<你的品牌文字>"
```

2. 如果 `config.json` 中 `watermark_text` 为空，直接运行 `process-video.ps1` 会给出提示并停止，直到配置完成（或临时改用 `-WatermarkText` 参数）。
3. **给 AI 的执行规范**：开始处理任何视频前，若用户未提供水印文字且 `config.json` 为空，**必须先向用户询问「水印上想显示什么内容」，确认后写入配置，再继续**。不得自行编造水印内容。

## 环境要求

- Windows + PowerShell（Windows PowerShell 5.1 即可）
- ffmpeg / ffprobe：加入 PATH（`ffmpeg`, `ffprobe` 命令可被 `Get-Command` 找到）
- 无其它依赖（水印 PNG 用 System.Drawing 生成，无需 Python/ImageMagick）

## 禁止改代码（给 AI 的硬性规范）

- 本技能的三个脚本**已参数化覆盖常规需求**（字幕、水印、片尾、批量），**默认禁止直接修改任何脚本文件**。
- 需求变化时按顺序处理：① 先查参数表，能用参数解决就用参数；② 参数不够时，**先向用户说明"需要小改脚本"并征得同意**，且只改本地副本、改动最小化；③ **不得用其它语言（如 Python）重写整个流程**——本技能只依赖 PowerShell + ffmpeg。
- 运行前若不确定参数，先跑 `process-video.ps1 -Help` 看参数总览，不要读代码猜。
- 若本会话看不到 `gemini-video-cleanup` 技能（不在技能列表），说明技能未加载：先提示用户用 `@gemini-video-cleanup` 引用，或把技能文件夹装到 `~/.agents/skills/`（OpenCode/Codex）或 `~/.claude/skills/`（Claude Code），**不要自己重写**。

## 快速使用

先对单条视频做 **DryRun**（只探测、不渲染），确认计划参数：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\scripts\process-video.ps1" `
  -Path "<素材目录>\示例横版.mp4" -DryRun
```

确认无误后去掉 `-DryRun` 正式渲染，输出到 `<视频目录>\成片\<原文件名>.mp4`。

批量处理整个文件夹（顶层；加 `-Recurse` 递归子目录，自动跳过「成片」目录）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\scripts\process-video.ps1" `
  -Path "<素材目录>"
```

竖版且画面里已经自带烧录字幕的，显式关掉字幕烧录：

```powershell
... -Path "<竖版视频>.mp4" -Subtitles off
```

## 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `-Path` | 必填 | 视频文件或文件夹 |
| `-Recurse` | 关 | 文件夹模式递归子目录 |
| `-Srt` | 自动配对 | 显式指定 SRT；默认找同名或 `同名 (transcribed ...).srt` |
| `-Subtitles` | `auto` | `auto` / `on` / `off`，见下方决策规则 |
| `-WatermarkText` | 读 `config.json` | 水印文字；未配置时提示并停止 |
| `-WatermarkStyle` | `beige` | `beige`（米色）/ `dark`（深色） |
| `-SubtitleFontSize` | `40` | 字幕字号（720p 基准，随分辨率缩放） |
| `-SubtitleColor` | `&H0000E0FF` | ASS 颜色（BBGGRR，#FFE000 黄色） |
| `-SubtitleMarginBottom` | `14` | 字幕距底边距离（720p 基准，随分辨率缩放） |
| `-LandscapeWatermarkOffsetY` | `0` | 横版水印纵向偏移（720p 基准，负值上移）；`0` 贴帧底 |
| `-OutputDir` | `<视频目录>\成片` | 输出目录 |
| `-TrimSeconds` | `-1`（自动） | 手动指定截断秒数；不建议通常使用 |
| `-EndScanSeconds` | `15` | 片尾检测回扫窗口 |
| `-Preset` | `medium` | x264 编码预设（用 `-Fast` 更省事） |
| `-Fast` | 关 | 快速渲染：`veryfast` + crf 20（更快、体积略大） |
| `-SkipExisting` | 关 | 已存在输出文件的直接跳过（不覆盖） |
| `-DryRun` | 关 | 只输出处理计划，不渲染 |

## 性能与提速（重要）

- **渲染本身很快**（约 350fps，一条 6 分钟视频 10~25s）。慢的通常是**模型多轮交互**（DryRun→确认→渲染→抽帧→调参），本地模型尤甚。
- **批量/本地模型：用"一条命令直出"，不要逐条确认**。不需要 DryRun、不需要每帧抽查——跑完只抽查 1~2 条代表即可：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\scripts\process-video.ps1" `
  -Path "<素材目录>" -Fast -SkipExisting
```

- 嫌模型慢/想彻底绕过模型：直接在终端里运行上面这条命令即可，脚本是全自动的。
- 只有当结果异常（片尾没切掉、水印没盖住）时才需要 DryRun 排查或调 `-TrimSeconds`。
- 给 AI 的执行规范：用户明确要"快/本地模型/批量"时，**默认走直出模式**，唯一的确认点是水印文字（首次）。

## 自动决策规则（重要）

- **字幕烧录判断（`-Subtitles auto`）**：
  - 只对**横版**视频烧录；
  - SRT 末尾时间 / 视频时长 必须在 `0.85 ~ 1.18` 之间（说明 SRT 与该视频匹配）；
  - 竖版默认不烧（NotebookLM 竖版一般自带烧录字幕）；SRT 明显不匹配时也会自动跳过并给出警告。
  - 如果竖版 SRT 确实匹配且画面没有自带字幕，用 `-Subtitles on` 强制烧录。
- **片尾截断（自动）**：回扫最后 15 秒逐帧统计亮度，从视频末尾往前找连续的"片尾卡"区间——**白卡**（YAVG ≥ 215）或**黑卡**（YAVG ≤ 58 且无纯黑像素 YMIN ≥ 10），并要求卡起点处有 ≥12 的亮度阶跃（硬切保护）。截在卡起点前一帧。若检测点早于总时长 60%（异常保护），则保留全片并警告。
- **水印位置**：按模板测量值自适应（见 `references/pipeline-notes.md`）：
  - 横版：标签 `142×34`（按 1280 宽等比），右边缘距帧边 4px，默认贴帧底；若视频底部自带黑边想避开，用 `-LandscapeWatermarkOffsetY -2` 上移；
  - 竖版：标签 `178×34`（按 720 宽等比），右下留 20/18px 边距。
  - 水印必须**完全不透明**，否则原水印会透出来。
- **输出**：统一写入 `<视频目录>\成片\`，同名覆盖。

## 质检流程（每次批量后执行）

渲染完抽帧检查（读图确认）：取 `2s`、中段、`cut-0.5s` 三帧。

```powershell
$out = "<输出目录>\成片\<名字>.mp4"
foreach ($t in @(2, 200, 344.5)) {
  & ffmpeg -y -v error -ss $t -i $out -frames:v 1 "chk_$t.png"
}
```

检查点：
1. 右下角只剩自己的水印，看不到 `Gemini Notebook` 任何残影；
2. 字幕位置不压水印、字号正常；
3. 最后一帧还是正片（不是片尾 logo 卡）；
4. 竖版：确认没有重复字幕（自带字幕 + 烧录）。

## 常见问题

- **SRT 与视频不匹配**：NotebookLM 同集横/竖版 SRT 可能互换或对应错版本。看 DryRun 输出的 `SrtRatio`（≈1.0 才匹配）；不匹配就别烧字幕。
- **水印位置对不上**（换了 NotebookLM 模板/分辨率）：按 `references/pipeline-notes.md` 里的方法重新量取模板坐标，并同步修改 `process-video.ps1` 的 `Get-WatermarkLayout`。
- **PS 脚本乱码/中文路径出错**：脚本本身保持纯 ASCII，中文只通过参数传入；主脚本已内置 UTF-8 控制台编码设置，中文路径素材可直接运行；如需改脚本中的中文字面量，保存为 UTF-8 with BOM。
- **ffmpeg 滤镜路径转义**：主脚本用 `filter_complex_script` + 切换工作目录的方式规避 Windows 盘符冒号转义问题，不要改回内联滤镜。
- **视频底部有自带黑边**：属正常现象，水印标签贴底时会盖住黑边，不影响。

## 文件结构

```
gemini-video-cleanup/
├── SKILL.md                     # 本文件：工作流程 + 决策规则 + 质检规范
├── config.example.json          # 配置模板：复制为 config.json 后写入自己的水印文字
├── .gitignore                   # 忽略 config.json（用户私有配置不入库）
├── references/
│   └── pipeline-notes.md        # 模板测量数据、算法细节、实测记录、踩坑清单
└── scripts/
    ├── process-video.ps1        # 主入口：探测 / 配对 / 检测 / 渲染
    ├── srt-to-ass.ps1           # SRT→ASS（自动断句 + 时间重分配 + 样式缩放）
    ├── make-watermark.ps1       # 生成圆角水印 PNG（beige/dark 两种风格，4x 超采样）
    └── set-config.ps1           # 写入水印文字等配置到 config.json
```

`config.json` 由 `set-config.ps1` 在用户机器上生成并写入各自的水印文字，不入库。