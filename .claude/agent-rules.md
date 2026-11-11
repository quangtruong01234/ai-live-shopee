# Shared rules for pipeline sub-agents

Every agent in `.claude/agents/` reads this file first. These rules let several agents run **at the same time on the same
working tree** without waiting for each other or breaking each other's work. The project rules in `CLAUDE.md` and
`.specify/memory/constitution.md` still apply in full; this file only adds the parallel-work rules.

## 1. Ownership (what makes parallel runs safe)

- Edit **only** the paths your agent file lists under "Owns". Read anything.
- Shared files have exactly one owner (`ai-orchestrator` for `src/ai_live/core/`, `app/`, `director/`; `ai-qa` for
  `tests/conftest.py` and `tests/fixtures/`). If your task needs a change there, **do not edit it**: finish what you can, and
  write the exact change you need (file, function, signature, why) under **Handoff** in your report. Do not wait for it.
- Never edit `specs/**/tasks.md`, `progress/`, `CLAUDE.md`, `docs/`, `pyproject.toml`, `uv.lock`, `.env*`. The main session
  ticks tasks and updates docs and progress after every agent of the wave has reported.
- If a needed file is owned by nobody, treat it as owned by the main session: report it under Handoff.

## 2. Things that would break other agents (never do them)

- No git writes of any kind: no `commit`, `stash`, `checkout`, `reset`, `restore`, `clean`, `add`. Read-only git is fine.
- No `uv add` / `uv sync` / `uv lock`, no new dependency, no model download, no RunPod (needs an ADR and the user).
- Run `ruff format` / `ruff check --fix` **only on your owned paths**, never on `.` or on another agent's files.
- Do not run the full `uv run pytest` as your pass/fail signal: other agents may be mid-edit. Run your own slice (below).
  If a test outside your slice fails, mention it in the report; do not fix it.
- Do not start a server on port 8000. Prefer `fastapi.testclient.TestClient`. If you really need a live server, use a free
  port in 8100–8199, and stop it before you finish.
- Put temporary files in your scratchpad directory, never in the repo.

## 3. Work loop (one flow, not one command at a time)

For each task given to you, in order:

0. Once per run, read the feature's card in `progress/FEATURES.md` (folder, artifacts, related ADRs, dependencies) instead of
   scanning `docs/` or `specs/`. Open an ADR or doc only when the card or the task points to it.
1. Read the task text in `tasks.md`, plus only the spec/contract sections it cites.
2. Test task: write the test, then run your **verify chain** once; confirm the new test fails for the right reason
   (missing behavior, not an import or syntax error).
3. Implementation task: write the minimal code, then run the **verify chain** again until green.
4. A test still failing for an unclear reason after 2 fix attempts: stop that task, mark it BLOCKED with the error output,
   and continue with your next independent task.
5. Never loosen a test relative to its acceptance scenario to make it pass.

The verify chain is the single command in your agent file: your test slice, then `ruff check`, then `ruff format --check`,
on your owned paths only, joined with `&&` so one call tells you everything.

## 4. Conventions (from CLAUDE.md, ADR-022)

- Code, identifiers, comments, docstrings: English. Translate leftover Vietnamese comments in any file you touch.
- User-facing runtime text (UI, API error messages, LLM prompts, TTS text): Vietnamese.
- Python 3.12, type hints on public interfaces, adapters are `typing.Protocol`, async I/O, never block the event loop.
- Default tests need no GPU, network or API key. Real API tests carry the `live_llm` marker and are never run by you
  unless the task says so.
- Windows + Git Bash: use `uv run python`, set `PYTHONIOENCODING=utf-8` for Vietnamese console output, send Vietnamese
  HTTP bodies from a UTF-8 file (`curl --data-binary @file.json`), write regex with the Write/Edit tools, not heredocs.

## 5. Report (your final message; the main session reads only this)

```
Agent: <name>   Scope: <task IDs>
Done: <IDs>     Blocked: <ID: reason + verbatim error>
Verify chain: <passed/failed counts, ruff result>
Files changed: <paths>
Handoff: <changes needed in files you do not own, or "none">
Notes: <spec/contract mismatches found, decisions needing the user>
```
