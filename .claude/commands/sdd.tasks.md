---
description: "SDD step 4: break the plan into an ordered tasks.md, per user story, tests first"
argument-hint: "[feature NNN or slug (optional)]"
---

Input: $ARGUMENTS

You are running the **tasks** step of the Spec-Driven workflow (see `docs/WORKFLOW.md`).
Write task descriptions in Vietnamese; reply to the user in Vietnamese.

## Identify the feature
Same as `/sdd.clarify` (read the feature's card in `progress/FEATURES.md` first). Requires `spec.md` and `plan.md`. Also read `research.md`, `data-model.md`, `contracts/` and
`quickstart.md` when present.

## Steps
1. Create `specs/NNN-slug/tasks.md` from `.specify/templates/tasks-template.md` and remove the template's guidance block.
2. Generate tasks from these sources:
   - **Setup:** project structure, configuration, dependencies approved in the plan.
   - **Foundational:** what every story needs (shared models, configuration, the Protocols in contracts/).
   - **Each user story (by P1, P2...):** its own phase. Test tasks come from the acceptance scenarios and go **before** the
     implementation tasks. Order: models, then adapters/services, then endpoints/integration. End with a Checkpoint.
   - **Polish:** update docs, run the quickstart, clean test/lint, `/update-context`.
3. Line format: `- [ ] T### [P?] [GPU?] [US#?] Description with a concrete file path`. IDs run continuously T001, T002...
   - Use `[P]` only when the task touches a different file and depends on no unfinished task.
   - Use `[GPU]` for work that needs a GPU (dev laptop first per ADR-023; RunPod only as a fallback with the user's cost
     approval). Collect those under "Đợt GPU".
4. Coverage check: every FR and SC in the spec must map to at least one task (test or implementation). Add tasks for gaps.
5. Set the spec status to `Tasked`.
6. Update `progress/` (`progress/README.md` §3): the row and card in `FEATURES.md` (`status`, `artifacts` + tasks link,
   `tasks` = `0/N`, `analyze` = "chưa chạy trên bản tasks này"), `STATUS.md` `next_step`, one line in `LOG.md`.

## Do not
- Write code. Create vague tasks ("finish X", "optimize").
- Add work outside the spec and plan. If something seems missing, put it in the report for the user to decide.

## Report
- Total tasks, tasks per story, number of `[P]` and `[GPU]` tasks.
- MVP scope (usually Setup + Foundational + US1).
- FR/SC without tasks (if any).
- Next step: `/sdd.analyze` (recommended), then `/sdd.implement`. **Stop.**
