---
name: agnes-media
description: Use when generating AI images, AI video clips, or a multi-scene narrated video with the Agnes API (apihub.agnes-ai.com) plus edge-tts Chinese recitation, subtitles, and ffmpeg crossfade stitching. Covers create/poll/download for video, images/generations for stills, recitation-style TTS pacing, and the full scenes.json pipeline.
---

# Agnes media pipeline (image / video / TTS / stitch)

Base URL: `https://apihub.agnes-ai.com/v1`  
API key: read `auth.json` key path `agnes.key` from OpenCode auth store (never print the key):

```python
import json
KEY = json.load(open("/data/home/.local/share/opencode/auth.json"))["agnes"]["key"]
```

All requests: `Authorization: Bearer {KEY}`, `Content-Type: application/json`.

Reference implementation directory: `/data/home/videospace/xiaoyao/`  
Reusable scripts in this skill: `scripts/`.

---

## 1. Generate an image

`POST {BASE}/images/generations`

| Field | Notes |
|-------|--------|
| `model` | `agnes-image-2.5-flash` (preferred), also `2.1-flash`, `2.0-flash` |
| `prompt` | English descriptive prompt |
| `size` | e.g. `1K` |
| `ratio` | e.g. `16:9`, `1:1`, `4:3` |
| `return_base64` | `true` → `data[0].b64_json`; `false` → may return `data[0].url` |

Response: `{"data":[{"b64_json"|"url": ...}]}`. Decode b64 or download URL to file. Typical latency a few seconds to ~1 min; timeout 180–300s.

---

## 2. Generate a video clip

Async job pattern (create → poll → download).

**Create:** `POST {BASE}/videos`

```json
{
  "model": "agnes-video-2.5-flash",
  "prompt": "<English scene prompt>",
  "seconds": "12",
  "mode": "text",
  "size": "720P",
  "aspect_ratio": "16:9"
}
```

Success → `video_id` (also `task_id` / `id`).  
Common failure: HTTP 503 `{"code":"video_queue_full"}` — retry with backoff (8–45s), forever if needed.

**Poll:** `GET {BASE}/agnesapi?video_id={id}&model_name=agnes-video-2.5-flash`  
- `status`: `queued` / `pending` / `running` / `completed` / `failed`, plus `progress`  
- success: `status=completed` and `url`  
- poll every 8s (30s on 429); max wait ~1h then re-poll or recreate  
- on `failed`: delete saved `video_id`, recreate task  
- on transient error: keep same `video_id` and continue polling  

**Download:** stream `url` to file with `.part` + atomic rename.

**Resume:** if `segments/{id}.mp4` exists and size > 100KB, skip. Save `video_id` to `segments/{id}.video_id` so a restart resumes polling.

Working scripts: `scripts/generate_video.py` (multi-scene, retry-forever) or pattern in `/data/home/videospace/video_worker.py`.

---

## 3. Recitation-style Chinese TTS (edge-tts)

**Do not use whole-clip time-stretch** — it sounds rhythmless. Split text on Chinese punctuation, TTS each phrase, then pad/scale only the **gaps** so total duration fits the scene.

**Approved defaults (user confirmed):**

| Setting | Value |
|---------|--------|
| Voice | `zh-CN-YunyangNeural` |
| Rate | `-25%` |
| Clause pause (`，、：；`) | `0.50s` |
| Sentence pause (`。！？…`) | `0.75s` |
| Max single gap | `1.6s` |
| Tail after last phrase | `0.25s` |
| Fit margin (before crossfade) | `0.45s` |
| Output | 48kHz stereo AAC `tts_fit/{sid}.m4a` |

Split: `re.split(r'(?<=[，。；？！、：…])', text)` — keep punctuation with phrase. Merge orphan `…` / single punct into previous phrase (edge-tts errors on lone `…`).

Algorithm per scene:
1. TTS each phrase → measure durations  
2. `target = scene_duration - 0.45`  
3. Base gaps from punctuation; scale gaps up to fill `target - speech - tail`, cap each gap  
4. Remainder → trailing silence pad  
5. `ffmpeg` concat phrase WAVs + silence → `atrim`/`apad` to exact `target`

Install: `pip3 install --break-system-packages edge-tts` (binary may be at `/data/home/.local/bin/edge-tts`).

Script: `scripts/gen_tts_pause.py`.

Agnes has **no TTS model** (`/v1/audio/speech` → 404/429). Use edge-tts only.

---

## 4. Stitch scenes (subtitles + audio mix + xfade)

`scripts/stitch.py` does, per scene then across scenes:

1. **Normalize:** scale/pad to min WxH (even), `fps=24`, burn-in bottom subtitle via `drawtext`  
   - Font: `/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc`, fontsize 36, box `black@0.35`  
   - Escape: `\`, `'`, `:`, `%` → `\\`, `\'`, `\:` , `%%`  
2. **Mix audio** if `tts_fit/{sid}.m4a` exists: ambient `volume=0.25` + TTS full, `amix=inputs=2:duration=first:normalize=0`, 48kHz stereo AAC 192k. Else keep ambient only.  
3. **Chain:** `xfade=transition=fade:duration=1.0` + matching `acrossfade=d=1.0:c1=tri:c2=tri` so A/V stay aligned.  
   Offset for join i: `sum(durs[:i]) - i * XFADE`.

---

## 5. Full multi-scene pipeline

Project layout (e.g. `/data/home/videospace/xiaoyao/`):

```
scenes.json          # array of scenes
segments/s01.mp4 ...  # raw Agnes clips
tts_fit/s01.m4a ...   # fitted narration
frames/s01_n.mp4 ...  # normalized + subtitle + mixed
logs/gen.log
ALL_DONE
```

**scenes.json** entry:

```json
{
  "id": "s01",
  "seconds": "12",
  "zh": "中文旁白/字幕文本",
  "prompt": "English ink-wash (or other) video prompt, no text, no watermark"
}
```

Order of operations:

```bash
python3 scripts/generate_video.py   # or copy generate.py; writes segments/ + ALL_DONE
python3 scripts/gen_tts_pause.py    # writes tts_fit/*.m4a (after segments exist)
python3 scripts/stitch.py           # writes final mp4
```

Verify output:

```bash
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 OUT.mp4
ffmpeg -i OUT.mp4 -af volumedetect -f null - 2>&1 | grep -E 'mean_volume|max_volume'
```

Expected: video+audio streams present, duration ≈ `n*seg - (n-1)*xfade`, mean_volume roughly -30 dB (ducked ambient + narration).

---

## Pitfalls

- Never final-encode with `-an` or omit audio `-map`.  
- Video create: retry 503 queue-full; poll long; persist `video_id`.  
- TTS: fit by padding gaps, not `atempo`/rubberband on whole clip.  
- Short `zh` text (2 clauses) → large trailing silence pad is normal.  
- `PIL` may be absent; use `ffprobe`/struct for media probing.  
- Subtitle drawtext: test one frame if text looks tiled/duplicated.  
- Do not log or echo the Agnes API key.
