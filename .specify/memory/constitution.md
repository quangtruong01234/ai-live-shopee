# AI Live Shopee Project Constitution

> Version: **1.2.0** · Ratified: 2026-10-30 · Last amended: 2026-11-01 (ADR-029)
> These principles are **non-negotiable**. Every spec, plan, tasks file and line of code must comply.
> `/sdd.plan` checks each article at the "Kiểm tra Constitution" gate. `/sdd.analyze` treats every violation as **CRITICAL**.
> To amend the constitution use `/sdd.constitution` together with an ADR (see Governance).

## Article I: Real-time generation only, platform compliance (NON-NEGOTIABLE)
- Every picture and sound sent to a live stream is generated in real time. No code path streams a pre-recorded video/audio file to Shopee.
- The "AI" label is always composited into the frame inside the pipeline. No setting can disable it when the output is a live platform.
- Each AI host (avatar + voice) is bound to exactly one account/customer. The code must block reuse.
- The backup video is used only for demos outside Shopee.

## Article II: Consent and security (NON-NEGOTIABLE)
- Never use the likeness or voice of anyone without signed consent.
- Secrets are read only from environment variables / `.env`. Never log secrets, stream keys or cookies.
- The customer's Shopee session is stored encrypted, only on the machine that runs the live, with the key kept apart from the data.

## Article III: Grounded replies
- The LLM only states information present in the product data. When data is missing it declines politely and never guesses.
- Every change to the prompt or the ReplyEngine must re-run the sample question set (regression) without lowering the score.

## Article IV: Adapters first, core second
- Each pipeline stage (CommentSource, CommentQueue, ProductStore, ReplyEngine, TTSEngine, AvatarRenderer, OutputSink) sits behind
  a `typing.Protocol` in `docs/ARCHITECTURE.md`. A new provider means a new adapter, not a change to the core.
- Each adapter can run on its own for testing (e.g. `uv run python -m ai_live.<module>` or a debug endpoint).

## Article V: Test-First
- For logic that needs no GPU: write tests from the spec's acceptance scenarios, run them to confirm they **FAIL** (red), then write
  the code that makes them green.
- Default tests run without a GPU, network or API key (mock source, `FakeTTS`, static renderer, fake LLM).
  Tests that call real APIs carry their own marker and are not run by default.
- GPU work (lip-sync) is verified by manual scenarios in `quickstart.md`, run on the dev laptop GPU first (ADR-023: low
  FPS/resolution accepted, still generated in real time, never pre-rendered). RunPod is the fallback: batch the `[GPU]` tasks
  and get the user's cost approval before starting a pod.

## Article VI: The latency budget is a requirement
- Scripted show (the main content, ADR-026): from "Start" to the first sentence playing ≤ 5 seconds, and the gap between
  consecutive sentences p95 ≤ 1.5 seconds, never > 5 seconds (pauses and injected faults excluded).
- Answering a comment (mock now, real chat later): from comment received to the avatar starting to speak < 5 seconds (p95).
  Per-stage budget in `docs/ARCHITECTURE.md` §4.
- Targets are judged on the machine and mode used for the demo; laptop lip-sync numbers (ADR-023) are indicative and are
  re-measured there.
- Any feature that touches the pipeline states its latency impact in the plan and measures it with the `utterance_id` log milestones.
- Never block the event loop; heavy work runs in an executor or a separate process.

## Article VII: Simplicity first
- Do not add infrastructure (Redis, DB, vector DB, external queue, new service) before the current phase needs it.
- No speculative abstractions. Apart from the Protocols in Article IV, abstract only once there are 2 real implementations.
- Use framework features (FastAPI, asyncio, pydantic) directly instead of wrapping them.
- A new dependency needs an ADR and user approval before running `uv add`.

## Article VIII: Observability
- Structured logs; every utterance has an `utterance_id` and the milestones `comment_received`, `llm_first_sentence`,
  `tts_first_chunk`, `avatar_first_frame`. Scripted sentences carry a `segment_id` and use `segment_requested` in place of
  `comment_received`; the gap between consecutive sentences is logged.
- Every stage has a timeout and a fallback; one failed turn must never stall the whole live session.

## Article IX: Language and documentation
- Code is in English: identifiers, file names, commit messages, comments and docstrings. This applies to new and edited code;
  existing Vietnamese comments are translated when their file is touched (ADR-022).
- AI-context files (`CLAUDE.md`, `.claude/commands/`, this constitution, `.specify/templates/` guidance) are in English.
- Documents for humans (`docs/`, `specs/`) and runtime text users see (UI, API error messages, LLM prompts/replies, TTS text)
  are in Vietnamese with diacritics. The assistant replies to the user in Vietnamese.
- Never invent information. Specs use `[NEEDS CLARIFICATION: question]`, other docs use `TODO: question`.

## Governance
- The constitution overrides every other document. On conflict the constitution wins and the other document must be fixed.
- Amending: propose the change with `/sdd.constitution`, get user approval, record an ADR in `docs/DECISIONS.md`, then bump the version:
  - **MAJOR**: remove or redefine an article incompatibly.
  - **MINOR**: add an article or expand one substantially.
  - **PATCH**: wording or clarification without changing meaning.
- A deliberate violation is accepted only when recorded in the plan's "Theo dõi độ phức tạp" table, with a reason, and approved by the user.
