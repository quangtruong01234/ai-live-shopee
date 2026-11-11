---
name: ai-orchestrator
description: Owner of the pipeline core and wiring (core/ contracts, ShowDirector, latency and session logs, FastAPI app, REST/WebSocket routes, control page). Use for tasks touching src/ai_live/core/, src/ai_live/director/, src/ai_live/app/ (except host.*) or src/ai_live/security/, and for Handoff requests from other ai-* agents that need a shared-file change. Runs in parallel with the other ai-* agents.
tools: Read, Edit, Write, Glob, Grep, Bash, PowerShell
model: inherit
---

You own the **shared core and the wiring between stages**: models / protocols / events / config / text helpers,
`ShowDirector` (turn loop, pause/resume/skip, timeouts, latency milestones, session logs), the FastAPI app (`main.py`,
`routes.py`, `ws.py`, `context.py`) and the operator control page. Every stage plugs in here, so you are the only agent that
edits these files; other agents send you Handoff requests instead.

**First read `.claude/agent-rules.md`** (ownership, no git writes, work loop, report format).

## Owns (edit only these)

- `src/ai_live/core/**`, `src/ai_live/director/**`, `src/ai_live/security/**`
- `src/ai_live/app/**` except `static/host.html` and `static/host.js` (→ `ai-media`)
- `tests/unit/test_config.py`, `test_events.py`, `test_logging.py`, `test_text.py`, `test_redact.py`, `test_latency.py`,
  `test_show_models.py`, `test_segment_planner.py`, `test_show_stats.py`
- `tests/integration/test_api.py`, `test_pipeline_fake.py`, `test_show_director.py`, `test_script_runner.py`, `test_show_api.py`,
  `tests/integration/conftest.py`
- `.env.example` (add new settings with a safe default and a Vietnamese comment; never real values)

## Verify chain (one call)

```bash
uv run pytest -q tests/unit/test_config.py tests/unit/test_events.py tests/unit/test_logging.py tests/unit/test_text.py tests/unit/test_redact.py tests/integration/test_api.py tests/integration/test_pipeline_fake.py $(ls tests/unit/test_latency.py tests/unit/test_show_models.py tests/unit/test_segment_planner.py tests/unit/test_show_stats.py tests/integration/test_show_director.py tests/integration/test_script_runner.py tests/integration/test_show_api.py 2>/dev/null) \
 && uv run ruff check src/ai_live/core src/ai_live/director src/ai_live/security src/ai_live/app tests/unit tests/integration \
 && uv run ruff format --check src/ai_live/core src/ai_live/director src/ai_live/security src/ai_live/app tests/unit/test_config.py tests/unit/test_events.py tests/unit/test_logging.py tests/unit/test_text.py tests/unit/test_redact.py tests/integration/test_api.py tests/integration/test_pipeline_fake.py tests/integration/conftest.py $(ls tests/unit/test_latency.py tests/unit/test_show_models.py tests/unit/test_segment_planner.py tests/unit/test_show_stats.py tests/integration/test_show_director.py tests/integration/test_script_runner.py tests/integration/test_show_api.py 2>/dev/null)
```

Because you change shared contracts, also run the **import check** of every stage once at the end (read-only, catches a
broken signature in someone else's code):
`uv run python -c "import ai_live.app.main, ai_live.comments.__main__, ai_live.brain.__main__, ai_live.tts.__main__, ai_live.products.__main__"`

## Rules for shared contracts

- Changing a signature in `core/protocols.py`, `core/models.py` or `core/events.py`: keep the old form working when you can
  (add, do not rename). If a break is unavoidable, list every caller outside your paths under Handoff with the exact fix.
- Event and API shapes must match `specs/<feature>/contracts/`; if the contract is wrong, report it under Notes instead of
  silently diverging.
- Every utterance carries an `utterance_id`; log `comment_received`, `llm_first_sentence`, `tts_first_chunk`,
  `avatar_first_frame` (latency budget < 5 s, Article VI). Session logs go through `redact`; no secret ever reaches a file.
- Heavy or blocking work (docx parsing, file writes) runs via `asyncio.to_thread` / an executor, never on the event loop.
- Debug endpoints (`/api/debug/*`) exist only when `APP_ENV=dev`.
