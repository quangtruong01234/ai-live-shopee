---
description: "SDD step 6: implement tasks.md phase by phase, tests first, stopping at each checkpoint"
argument-hint: "[NNN/slug] [scope: e.g. 'US1' or 'T001-T010' (optional)]"
---

Input: $ARGUMENTS

You are running the **implement** step of the Spec-Driven workflow (see `docs/WORKFLOW.md`).
Reply to the user in Vietnamese.

## Identify feature and scope
- Feature: same as `/sdd.clarify`. Requires `tasks.md`.
- Scope: from the input. Otherwise do the **first unfinished phase** and stop at that phase's checkpoint.
- If `/sdd.analyze` has not run on the current tasks version, recommend running it first. If CRITICAL issues are known, **do not implement**.

## Before starting
1. Read `tasks.md`, `plan.md`, `spec.md`, `data-model.md`, `contracts/`, `quickstart.md` and `CLAUDE.md`.
2. Check that `.gitignore` blocks `.env`, models and media. In a git repo make sure you are on branch `NNN-slug`.

## Per-task loop (in order; `[P]` tasks may be done back to back)
1. **Test task:** write the test, run `uv run pytest <file>` and confirm it **FAILS** for the right reason (missing behavior, not a
   syntax error).
2. **Implementation task:** write the minimal code to turn the test green, following the conventions in `CLAUDE.md` (English
   identifiers, comments and docstrings; Vietnamese only for user-facing runtime text; async; never block the event loop).
   When editing an existing file that still has Vietnamese comments/docstrings, translate them to English in the same change (ADR-022).
3. Re-run the related tests. When green, tick `[x]` in `tasks.md`.
4. **`[GPU]` task:** do not run it on the laptop. Write the code or script, mark it `[~]` (waiting for GPU) and add it to the GPU
   batch list in the report.

## When to stop and ask
- A dependency not approved in the plan is needed: ask first, then `uv add` and record an ADR.
- The spec or plan is wrong, incomplete, or contradicts the real code: stop and propose a spec/plan fix first. Never silently deviate.
- A test fails for an unclear reason after 2 attempts: stop and report with the error output.
- End of a phase or a **Checkpoint**: stop, report, wait for the user.

## Do not
- Do tasks outside the chosen scope. "Fix" a test by loosening it relative to the acceptance scenario.
- Commit `.env`, models, media or customer data. Commit only when the user asks.
- Download models or start RunPod.

## When the scope is done
- Run `uv run pytest` and `uv run ruff check .` (if configured) and report the exact results.
- When the **whole** feature is done: run the laptop-capable steps of `quickstart.md`, set the spec status and `specs/README.md`
  to `Done`, then suggest `/update-context`.

## Report
- Completed tasks (IDs), tasks waiting for GPU, blocked tasks with reasons.
- Test/lint results (pass/fail counts, verbatim errors if any).
- Deviations from the spec/plan (if any) and proposals.
- Next step.
