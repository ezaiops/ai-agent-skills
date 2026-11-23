# ai-agent-skills

Reusable agent skills (Agnes image/video/TTS pipeline, etc.).

## Skills

- [`agnes-media`](./agnes-media/SKILL.md) — Agnes API image/video generation, edge-tts Chinese recitation, ffmpeg stitch.
- [`agnes-video-director`](./agnes-video-director/SKILL.md) — Cinematic action-design & film-direction skill for Agnes video prompts: four-rule choreography (time-slicing / causal chains / environment feedback / asset lock), three-beat pacing, six-section prompt structure, asset passports, camera & negative-prompt lexicons, 12s scene segmentation.
- [`story-localize-video`](./story-localize-video/SKILL.md) — Public-domain (公版) story adaptation into Chinese modern short-video full plans (华洲 fictional universe): copyright check, beat breakdown, localization/adaptation design, script & role passports, ≤12s storyboard, scenes.json for the Agnes pipeline, titles/covers. Ships two curated source catalogs: foreign classics (`references/story-catalog.md`) and Chinese public-domain works modernized (`references/story-catalog-cn.md`).

Install: copy a skill folder into `~/.agents/skills/` (OpenCode/Codex) or `~/.claude/skills/` (Claude Code).
