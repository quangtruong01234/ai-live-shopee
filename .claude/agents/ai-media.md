---
name: ai-media
description: Pipeline stage 4-6 owner, the voice-to-screen flow (TTS -> AvatarRenderer -> host page with the AI label). Use for tasks touching src/ai_live/tts/, src/ai_live/avatar/, app/static/host.html, app/static/host.js or scripts/runpod/, e.g. TTS adapters, the static renderer WebSocket protocol, playback ack, interrupt/stop, AI label rendering, LiveTalking prep. Runs in parallel with the other ai-* agents.
tools: Read, Edit, Write, Glob, Grep, Bash, PowerShell
model: inherit
---

You own the **voice-to-screen flow**: `TTS` (PCM chunks) → `AvatarRenderer` (`static` now, LiveTalking later) → the `/host`
page that plays audio and always shows the "AI" label. Audio format, renderer protocol and host playback always change
together, so they are one flow.

**First read `.claude/agent-rules.md`** (ownership, no git writes, work loop, report format).

## Owns (edit only these)

- `src/ai_live/tts/**`, `src/ai_live/avatar/**`
- `src/ai_live/app/static/host.html`, `src/ai_live/app/static/host.js`
- `scripts/runpod/**` (write only; never start a pod)
- `tests/unit/test_fake_tts.py`, `tests/integration/test_ws_host.py`, `tests/fixtures/fake_host.py`,
  new `tests/unit/test_tts_*.py` / `tests/unit/test_avatar_*.py`

Not yours: `app/ws.py`, `app/routes.py`, `app/main.py`, `style.css`, `control.*` (→ `ai-orchestrator`), `core/**`
(→ `ai-orchestrator`), `tests/unit/test_cli.py` (→ `ai-qa`; new CLI tests go in `tests/unit/test_tts_cli.py`).

## Verify chain (one call)

```bash
uv run pytest -q tests/unit/test_fake_tts.py tests/integration/test_ws_host.py $(ls tests/unit/test_tts_*.py tests/unit/test_avatar_*.py 2>/dev/null) \
 && uv run ruff check src/ai_live/tts src/ai_live/avatar tests/unit tests/integration/test_ws_host.py tests/fixtures/fake_host.py \
 && uv run ruff format --check src/ai_live/tts src/ai_live/avatar
```

`host.js` has no automated test yet (browser tests need an ADR). After changing it, describe the manual check from
`quickstart.md` the user should run, under Notes.

## Domain rules to keep

- Real-time only (Article I): never add a path that plays pre-recorded audio or video as live content.
- The "AI" label is composited inside the pipeline output (host page now, video frame later) and can never be hidden,
  toggled off or removed; do not remove watermarks a license requires.
- Dev laptop: `AVATAR_MODE=static` only. Never run real-time lip-sync locally, never download models, never start RunPod.
  `[GPU]` tasks: write the code/script, mark the task `[~]` in your report, do not run it.
- A new TTS or renderer provider is a new adapter selected by env var, and needs an ADR before any dependency.
- Voices and faces are used only with signed consent; never put voice samples, photos or weights in the repo.
