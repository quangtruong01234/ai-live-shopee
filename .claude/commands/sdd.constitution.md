---
description: "SDD: view or amend the project constitution (.specify/memory/constitution.md) and sync dependent files"
argument-hint: "[desired change (leave empty to only view a summary)]"
---

Input: $ARGUMENTS

Reply to the user in Vietnamese. The constitution itself is written in English.

## If the input is empty
Summarize the articles in `.specify/memory/constitution.md` (one line each), with the version and last-amended date. Change nothing.

## If a change is requested
1. Read the constitution, `progress/OPEN.md` §3 (pending amendments and the ADRs behind them), `CLAUDE.md` and
   `docs/DECISIONS.md`.
2. Draft the change and determine the version bump: MAJOR (remove or redefine an article), MINOR (add or expand), PATCH (wording).
3. Present it to the user: old text → new text, version bump, reason. **Wait for the user's approval.**
4. After approval:
   - Edit the constitution, bump the version, update "Last amended".
   - Add an ADR to `docs/DECISIONS.md` (date, decision, rationale, rejected alternatives).
   - **Sync:** check and align `.specify/templates/*.md` (the Constitution check table, the constraints section),
     `.claude/commands/sdd.*.md`, the "Mandatory constraints" and "DO NOT" sections of `CLAUDE.md`, and `docs/WORKFLOW.md`.
   - List features in `progress/FEATURES.md` with status Planned, Tasked or In progress that may be affected.
   - Update `progress/`: remove the settled items from `OPEN.md` §3, note affected features in their cards (`open`),
     `STATUS.md` `blockers`, one line in `LOG.md`.

## Do not
- Loosen Article I or Article II (compliance, consent, security) unless the user says so explicitly and the reason is recorded.

## Report
Old → new version, changed articles, synced files, new ADR, affected features.
