# ai-agent-skills

Reusable agent skills (Agnes image/video/TTS pipeline, etc.).

## Skills

- [`agnes-media`](./agnes-media/SKILL.md) — Agnes API image/video generation, edge-tts Chinese recitation, ffmpeg stitch.
- [`agnes-video-director`](./agnes-video-director/SKILL.md) — Cinematic action-design & film-direction skill for Agnes video prompts: four-rule choreography (time-slicing / causal chains / environment feedback / asset lock), three-beat pacing, six-section prompt structure, asset passports, camera & negative-prompt lexicons, 12s scene segmentation.

Install: copy a skill folder into `~/.agents/skills/` (OpenCode/Codex) or `~/.claude/skills/` (Claude Code).
