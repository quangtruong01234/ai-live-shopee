---
description: "SDD step 6 (parallel): split a tasks.md scope by owning ai-* agent, run the agents at the same time, then verify and tick"
argument-hint: "[NNN/slug] [scope: e.g. 'US3' or 'T071-T079' or 'US3 T080 T084' (optional)]"
---

Input: $ARGUMENTS

Parallel version of `/sdd.implement`. Same rules, same stop points; the difference is that independent tasks run in
parallel sub-agents instead of one by one. It bundles the steps that always follow each other (implement → full verify →
tick tasks → report) into one command. Reply to the user in Vietnamese.

## 1. Scope (same as `/sdd.implement`)

- Feature and scope from the input; default is the **first unfinished phase**, stopping at its checkpoint.
- Tasks from a later phase are included only when the user lists them explicitly in the input.
- If `/sdd.analyze` has not run on the current `tasks.md`, recommend it first. Known CRITICAL issues: do not dispatch.

## 2. Assign each task to one owner (by the files the task names)

| Files in the task | Agent |
|---|---|
| `comments/`, `comment_queue/`, `data/rules/` | `ai-comments` |
| `products/`, `brain/`, `qa_eval/`, `scripts/make_demo_content.py`, `tests/live/` | `ai-brain` |
| `tts/`, `avatar/`, `static/host.*`, `scripts/runpod/` | `ai-media` |
| `core/`, `director/`, `security/`, `app/` (not `host.*`), `test_api.py`, `test_pipeline_fake.py`, `test_show_director.py` | `ai-orchestrator` |
| `data/eval/`, `tests/contract/`, `tests/conftest.py`, `tests/fixtures/content_builder.py`, `tests/unit/test_cli.py` | `ai-qa` |
| `docs/`, `quickstart.md` runs, ADRs, measurements needing the user, `/update-context` | main session (not dispatched) |

- A task whose files span two owners goes to the owner of the file it **mainly** changes; the other part becomes a
  Handoff the agent reports.
- Show the assignment table to the user in one short message, then continue without waiting (the user can interrupt).

## 3. Build waves from the dependencies in `tasks.md`

- Wave 1 = every assigned task whose dependencies are already `[x]`. Later waves = tasks unlocked by the previous wave.
- Inside a wave, each agent gets **all** of its tasks in one prompt, in tasks.md order (its own tests first), so it runs
  test → implement → verify as one flow and never waits on another agent.
- Launch every agent of the wave **in a single message** (multiple Agent tool calls) so they run concurrently. Each prompt
  contains: feature folder, task IDs with their full text, "read `.claude/agent-rules.md` first", and "end with the report
  format of agent-rules §5".
- Do not use `isolation: worktree` while the repo has no commit (the worktree would be empty); ownership keeps the shared
  working tree safe.

## 4. After each wave (always, in this order, no extra command needed)

1. Collect the reports. Apply Handoffs: route each one to its owning agent as part of the next wave (or run a small
   follow-up wave of just those agents).
2. Full check: once **every** agent of the wave has reported (never while one is still running), launch `ai-qa` with the
   prompt "mode: wave-check" plus the list of files changed in this wave. Do not run the full suite yourself; rely on its
   report (exact counts, and for each failure the owning agent plus the verbatim error).
   Failures: send each failing test back to its owning agent once, then run `ai-qa` wave-check again; still failing →
   stop and report verbatim.
3. Tick `[x]` in `tasks.md` only for tasks the report marked Done **and** the `ai-qa` wave-check confirms green.
   `[GPU]` tasks → `[~]`.
   Add any error worth remembering to "Nhật ký lỗi gặp khi implement".
4. Next wave, until the scope is done or nothing is unblocked.

## 5. Stop and report (Vietnamese)

- Stop at the phase checkpoint, on a BLOCKED task that blocks the rest, on any request for a new dependency, a model
  download, RunPod, a paid service or a real-API (`live_llm`) run: those need the user.
- Report: assignment table with outcome per task, waves run, the `ai-qa` wave-check counts verbatim, Handoffs applied, blocked tasks,
  spec/contract mismatches, next step. Never commit unless the user asks.
