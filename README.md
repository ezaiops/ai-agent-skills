# ai-agent-skills

Reusable agent skills (Agnes image/video/TTS pipeline, etc.).

## Skills

- [`agnes-media`](./agnes-media/SKILL.md) — Agnes API image/video generation, edge-tts Chinese recitation, ffmpeg stitch.
- [`agnes-video-director`](./agnes-video-director/SKILL.md) — Cinematic action-design & film-direction skill for Agnes video prompts: four-rule choreography (time-slicing / causal chains / environment feedback / asset lock), three-beat pacing, six-section prompt structure, asset passports, camera & negative-prompt lexicons, 12s scene segmentation.
- [`story-localize-video`](./story-localize-video/SKILL.md) — Public-domain (公版) story adaptation into Chinese modern short-video full plans (华洲 fictional universe): copyright check, beat breakdown, localization/adaptation design, script & role passports, ≤12s storyboard, scenes.json for the Agnes pipeline, titles/covers. Ships two curated source catalogs: foreign classics (`references/story-catalog.md`) and Chinese public-domain works modernized (`references/story-catalog-cn.md`).
- [`story-logic-check`](./story-logic-check/SKILL.md) — Logic/consistency checker for the adaptation pipeline output (call before delivery): it verifies kernel preservation (不可变内核), causal chains across ≤12s segments, character-passport cross-references, knowledge-state, recalibrated economics/era symbols, world-bible consistency, and scenes.json structural integrity. Emits a severity-graded report (🔴 must-fix / 🟠 suggested / 🟡 confirm) with verbatim quotes — flags only, never rewrites; canon stays with the user. Includes a quick grep/python self-check script for scenes.json field gaps and id order.
- [`gemini-video-cleanup`](./gemini-video-cleanup/SKILL.md) — Batch cleanup of Gemini Notebook / NotebookLM video exports: burn Chinese subtitles (auto re-segmentation & proportional timing), cover the corner `✦ Gemini Notebook` watermark with an opaque per-user brand badge, and auto-detect + trim the end logo card (white and dark templates). Supports landscape 1280x720 and portrait 720x1280 mp4(+srt). Windows PowerShell 5.1 + ffmpeg (from PATH); no hard-coded user info — the watermark text is configured once per user via `set-config.ps1` (git-ignored `config.json`; `config.example.json` is the template). Landscape watermark vertical offset is tunable via `-LandscapeWatermarkOffsetY`.

Install: copy a skill folder into `~/.agents/skills/` (OpenCode/Codex) or `~/.claude/skills/` (Claude Code).
