# AI Live Shopee — CLAUDE.md

> Context memory for Claude Code. Keep this file **under 150 lines**; details live in `docs/`.
> After every large task run `/update-context` to update this file, `docs/DECISIONS.md` and `docs/ROADMAP.md`.
> **Always reply to the user in Vietnamese.** AI-context files (this file, `.claude/commands/`, constitution, templates) are in English.

## Project overview

A livestream-selling service with an **AI host**: a real-time lip-synced avatar, a Vietnamese voice, and automatic replies to comments.

- **Business model:** done-for-you service. The customer only provides product data; we handle the avatar, voice, script and live
  operation. Reporting uses Shopee's built-in statistics. Getting Shopee to whitelist AI live is the customer's job.
- **Current phase: DEMO.** 1 customer, 1 main product and 2–3 secondary products. The demo runs **outside Shopee**: over Google Meet
  (sharing a Chrome tab with audio), then optionally a YouTube Unlisted livestream. The customer pays only if the demo is good.
- **Later phase:** Shopee Live via OBS (RTMP + Stream Key), about 15 hours/day.
- **Code status:** `src/ai_live/` has the 001 pipeline (101/116 tasks, paused by ADR-026), the 004 show director (74/81), the
  003 Vietnamese TTS (done), the 005 lip-sync fork (63/83, US1 and US2 done) and the 008 LLM chain (done).
  Current status: `progress/STATUS.md`.

## Architecture (summary)

The pipeline has 6 stages, each an adapter behind a common interface:
**Comment source** (mock / YouTube Live Chat / Shopee) → **Priority queue** (spam filter, dedup, drop stale comments)
→ **ReplyEngine** (`REPLY_ENGINE=chain`: pinned free models, SEA-LION via freellmapi then Qwen3.8 on Groq, switching on
error, ADR-035/040; streams sentence by sentence, grounded only in product data) → **Vietnamese TTS**
(`TTS_PROVIDER`: VieNeu on CPU for live sessions, Gemini TTS free tier only for short tries, ADR-024; PCM16 mono 16 kHz
in chunks) → **AvatarRenderer** (local: `static` = image + audio; GPU: LiveTalking fork with Wav2Lip or MuseTalk)
→ **Output** (WebRTC for the demo, virtual cam or RTMP for OBS / YouTube / Shopee).
The "AI" label layer is composited directly into the frame before output. **ADR-026: reading chat to reply to viewers is postponed;**
the host's main content is a product-introduction script that `ShowDirector` generates in real time (feature 004). The 001 comment
path stays in code as a test tool. Every stage logs timestamps. Latency targets (constitution VI): scripted show first sentence
≤ 5 s and sentence gap p95 ≤ 1.5 s; comment → mouth-starts-speaking < 5 s p95. Details in `docs/ARCHITECTURE.md`.

## Commands

```bash
# Environment: uv + Python 3.12 (pinned in .python-version and pyproject.toml, ADR-012, ADR-020)
uv sync
cp .env.example .env                                   # then fill in secrets
uv run uvicorn ai_live.app.main:app --reload --port 8000
uv run pytest                                          # skips `live_llm` (real LLM calls) by default
uv run ruff check . && uv run ruff format --check .    # ruff only (ADR-015)
```

- Dev laptop (GTX 1650 Ti 4GB): `AVATAR_MODE=static` by default for tests and logic work. Lip-sync may run on the laptop
  (ADR-023, a slow avatar is accepted) but must still be generated in real time; lower FPS/resolution, never pre-render.
- Rented GPU (RunPod RTX 3090/4090): fallback only, follow `docs/RUNPOD.md`; ask the user about cost before starting a pod.

## Workflow: Spec-Driven (details in `docs/WORKFLOW.md`)

- New features go through all 7 steps: `/sdd.specify` → `/sdd.clarify` → `/sdd.plan` → `/sdd.tasks` → `/sdd.analyze` → `/sdd.implement` → `/update-context`.
- After each step **stop for the user to review**; never run the next step on your own.
- Parallel option for step 6: `/sdd.dispatch` splits tasks across the `ai-*` sub-agents in `.claude/agents/` (rules in
  `.claude/agent-rules.md`, owners in WORKFLOW §2b).
- The highest law is `.specify/memory/constitution.md`. Each feature has a folder `specs/NNN-slug/`.
- **Progress hub `progress/` (ADR-028):** read `progress/STATUS.md` and the feature's card in `progress/FEATURES.md` first;
  every command updates them (plus `OPEN.md`, `LOG.md`) at the end. Protocol and "change X → review Y" map: `progress/README.md`.
- Work directly on `main`; no per-feature branches (ADR-027). Commit only when the user asks.
- Bug fixes, refactors and docs may take the shortcut (WORKFLOW §2). To change behavior, edit the spec first, then the code.

## Code conventions

- **Language (ADR-022):**
  - Identifiers, file/module/branch names, commit messages, **code comments and docstrings: English** (applies to new and edited
    code; existing Vietnamese comments are translated only when that file is touched).
  - Documents for humans (`docs/`, `specs/`): Vietnamese with diacritics.
  - Runtime text that users see (UI pages, API error messages, LLM prompts and replies, TTS text): Vietnamese.
- Comments explain *why*, not *what*. Naming: `snake_case` for functions/variables/modules, `PascalCase` for classes,
  `UPPER_SNAKE_CASE` for constants.
- Python 3.12+, type hints on every public interface. Adapter interfaces are `typing.Protocol`.
- Async-first: I/O uses `asyncio`. Never block the event loop; heavy CPU/GPU work runs in an executor or a separate process.
- New sources or providers mean **a new adapter**, not changes to the pipeline core. Adapters are selected by environment variables.
- Config is read only from environment variables / `.env` via `pydantic-settings` (ADR-015). Never hardcode keys, URLs or model paths.
- Every utterance has an `utterance_id`; log the milestones `comment_received`, `llm_first_sentence`, `tts_first_chunk`,
  `avatar_first_frame` to track the latency budget. Scripted sentences use `segment_id` + `segment_requested` instead of
  `comment_received`.
- Tests: pipeline logic must run entirely without a GPU (mock source, fake TTS and static renderer).

## Mandatory constraints

1. **Real-time generation only.** Shopee bans pre-recorded video as live content, including AI video. The pipeline must generate
   picture and sound in real time.
2. **The "AI" label is always visible on screen**, composited into the frame inside the pipeline (not dependent on OBS).
3. **One AI host per account.** An avatar and voice belong to exactly one customer / one shop.
4. **Signed consent** from the model for both likeness and voice before use. The signed copy is stored outside git.
5. **Check licenses before commercialization:** LiveTalking (requires a watermark), Wav2Lip, MuseTalk, S3FD, whisper and the TTS
   model. Tracked in `docs/RISKS.md`.
6. **Secrets live only in `.env`** (never committed). The customer's Shopee session must be **stored encrypted** and only on the
   machine that runs the live.
7. **Replies are grounded only in product data.** When data is missing, say so or invite the viewer to ask the shop; never guess.

## DO NOT

- DO NOT stream pre-recorded video or audio on Shopee Live. The 2–3 minute backup video is **only** for Meet/YouTube demos.
- DO NOT hide or remove the "AI" label, and do not remove watermarks a license requires.
- DO NOT commit `.env`, API keys, stream keys, Shopee cookies/sessions, model weights, model photos/videos/voices or customer data.
- DO NOT use the likeness or voice of anyone who has not signed consent. Never clone a celebrity's voice or face.
- DO NOT reuse one customer's avatar or voice for another customer or another account.
- DO NOT let the LLM invent prices, promotions, stock, product effects, medical claims or return policies.
- DO NOT automate anything on the customer's Shopee account beyond reading the agreed comments.
- DO NOT leave a RunPod pod running when unused. Laptop lip-sync is allowed only as in ADR-023.
- DO NOT install new dependencies, download models or switch providers without an ADR in `docs/DECISIONS.md`.
- DO NOT invent information in docs. Where unsure, write `TODO:` with a specific question.
- DO NOT change a version (Python, a dependency, a model, a schema, the constitution) in one place only. In the same task, grep
  the repo for the old value and update every live mention (`CLAUDE.md`, `docs/`, templates, `.claude/`, `pyproject.toml`, open
  specs). ADRs and finished specs are history: do not rewrite them, add "changed by ADR-NNN" to the old entry instead.
- DO NOT delete existing files in the repo unless asked.

## Documents

- `docs/PRD.md`: demo scope, phase 2, success criteria, out of scope
- `docs/ARCHITECTURE.md`: pipeline, Mermaid diagrams, adapter interfaces, latency budget
- `docs/DECISIONS.md`: decision log (ADRs)
- `docs/ROADMAP.md`: milestones Demo → Pilot → real Shopee → Multi-customer, with checklists
- `docs/RISKS.md`: policy, technical, license, GPU and security risks
- `docs/RUNPOD.md`: setting up the rented GPU environment for demos
- `docs/VENDORS.md`: candidate SDKs/APIs per stage (not installed; using one requires an ADR)
- `docs/WORKFLOW.md`: the Spec-Driven process and the `/sdd.*` commands
- `.specify/memory/constitution.md`: project constitution · `.specify/templates/`: spec, plan, tasks templates
- `progress/`: current status, feature registry, pending decisions, work log (single place for progress)
- `src/README.md`: source tree layout
- `.claude/commands/`: `/update-context` and `/sdd.*`

## Open questions

The important ones are in `progress/OPEN.md`; full list: search `TODO:` in `docs/`. When a question is answered, update the
doc, record an ADR and remove it from `progress/OPEN.md`.
