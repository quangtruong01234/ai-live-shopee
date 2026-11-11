---
description: Update CLAUDE.md, docs/DECISIONS.md, docs/ROADMAP.md and reconcile progress/ after finishing a large task
argument-hint: "[summary of the task just finished (optional)]"
---

You are updating the AI-context skeleton of the AI Live Shopee project after a large task.

Summary from the user (may be empty): $ARGUMENTS

## Step 1: Collect what changed
- Read `progress/` first (`STATUS.md`, `FEATURES.md`, `OPEN.md`, the tail of `LOG.md`), then `CLAUDE.md`,
  `docs/DECISIONS.md`, `docs/ROADMAP.md`.
- If the repo uses git: check `git log` and `git diff --stat` since the last context update (look for a commit containing "update-context").
- Combine with the current conversation and the summary above.
- Briefly list: finished features, new decisions, new commands (run/test/lint), new constraints, `TODO:` questions now answered.

## Step 2: Update `docs/ROADMAP.md`
- Tick `[x]` only for **verified** items (tests pass, manually run, or confirmed by the user). Keep partial items `[ ]` with a short note.
- Add newly arising items under the right milestone.
- Update the "Mốc hiện tại" line at the top if the milestone changed.

## Step 3: Update `docs/DECISIONS.md`
- Each new decision is a new ADR with the next number and today's date (YYYY-MM-DD): Quyết định, Lý do, Phương án đã loại.
- **Never rewrite old ADRs.** When a decision changes, add a new ADR and set the old one's status to `Thay thế bởi ADR-xxx`.
- When a `TODO:` in an ADR is answered, record it in a new ADR (or change status `Đề xuất` to `Đã chốt` with the date).

## Step 4: Update `CLAUDE.md`
- Update the Commands section (drop placeholders once commands work), "Code status", the architecture summary (if changed) and the
  constraints / DO NOT lists (if new).
- Keep it **under 150 lines**: check with `wc -l CLAUDE.md`. Move long details into `docs/` and only link them from CLAUDE.md.
- Do not repeat content already in `docs/`.

## Step 5: Sync other docs (only when needed)
- If the change affects `docs/ARCHITECTURE.md`, `docs/PRD.md`, `docs/RISKS.md` or `docs/RUNPOD.md`, fix them for consistency.
- ADRs with status `Đề xuất` (created by `/sdd.plan`) that the user has approved become `Đã chốt`.

## Step 6: Reconcile `progress/` (rules in `progress/README.md` §1–§2)
- `FEATURES.md`: each feature's status matches the "Trạng thái" line in `spec.md`; `tasks` matches the `[x]` / `[~]` / `[ ]`
  counts in `tasks.md`; `artifacts` and `adrs` list what really exists.
- `OPEN.md`: drop answered items, add new `Đề xuất` ADRs, remaining `[NEEDS CLARIFICATION]` and important new `TODO:`s.
- `STATUS.md`: `last_updated`, `last_commit` (`git log -1`), `current_milestone` (matches ROADMAP), `active_feature`,
  `next_step`, `blockers`.
- Walk the "Khi đổi X thì rà Y" table for every change found in Step 1; fix mismatches or list them as `TODO:`.
- Append one line to `LOG.md`.

## Rules
- Never invent information. Where unsure, write `TODO:` with a specific question.
- Language (ADR-022): `CLAUDE.md` is in English; `docs/` are in Vietnamese with diacritics; code identifiers stay English.
- Do not change feature code in this command.

## Output
Print, in Vietnamese:
1. Files changed, one line each summarizing the change.
2. New ADRs (number + title).
3. ROADMAP items just ticked, and `progress/` mismatches fixed.
4. Up to 5 of the most important open `TODO:` questions.
