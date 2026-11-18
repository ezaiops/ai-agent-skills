# 负向提示词清单（Negative Prompt / Constraints）

agnes 不直接支持独立负向字段——把负向要求**改写为正向约束**写进 prompt 末尾的 CONSTRAINTS 段。每次挑 3-5 条，按项目覆盖。

## 改写规则

"不要文字" → 写 `no text, no subtitles, no watermark`
"不要多余的人" → 写 `no extra characters, no crowd, no bystanders`
"不要变脸" → 写 `no face morphing, consistent appearance`

## 六个方向的常用词条

| 方向 | 词条 |
|---|---|
| 画面噪声 | `no text overlays, no watermarks, no floating UI, no lens flares` |
| 主体漂移 | `no extra characters, no crowd, no mirrors reflecting others` |
| 镜头混乱 | `no snap zooms, no whip pans, no Dutch angles, no jump cuts` |
| 肢体伪影 | `no extra fingers, no deformed hands, no warped objects, no melting edges` |
| 品牌元素 | `no logos, no labels, no recognizable brands` |
| 色彩/环境 | `no neon lighting, no heavy teal-orange grade, no cartoon saturation; no rain/fog/smoke unless stated` |

## agnes 场景常用组合

- 水墨/古典：`no text, no watermark, no lens flares, no extra characters, no cartoon saturation`
- 打戏：`no text, no watermark, no jump cuts, no deformed hands, no snap zooms`
- 一镜到底：`single continuous shot, no cuts, no jump cuts, no scene transitions`
- 写实现代：`no text, no watermark, no neon lighting, no lens flares, no crowd`

## 技术约束

- 画幅/帧率：写进六段式 CONTRROLS 段（`16:9, 24fps`），或由 scenes.json 的 `aspect_ratio`/`size` 字段控制。
- 时长：agnes 单段 `seconds` 只支持 `"4"`–`"12"`，超 12 秒拆段拼接（xfade 在 stitch.py 处理）。