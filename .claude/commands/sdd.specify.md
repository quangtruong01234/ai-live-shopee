---
description: "SDD step 1: create a spec (WHAT + WHY) for a new feature from a natural-language description"
argument-hint: "<feature description>"
---

Feature description from the user:

$ARGUMENTS

You are running the **specify** step of the Spec-Driven workflow (see `docs/WORKFLOW.md`).
Write the spec in Vietnamese; reply to the user in Vietnamese.

## Steps

1. If the description is empty, stop and ask the user which feature they want.
2. Read `.specify/memory/constitution.md`, `docs/PRD.md`, `docs/ROADMAP.md` and `specs/README.md` to understand scope and avoid
   duplicating existing features. You may read `docs/ARCHITECTURE.md` for context, but **keep implementation details out of the spec**.
3. Assign the Feature ID:
   - `NNN` = highest number in `specs/` plus 1, zero-padded to 3 digits (starting at `001`).
   - `slug` = 2–4 English words, kebab-case, describing the feature (e.g. `local-reply-pipeline`).
4. If the folder is a git repo: create and switch to branch `NNN-slug` (`git checkout -b`). If the working tree has uncommitted
   changes, ask the user first. Without git, skip this step and note it in the report.
5. Create `specs/NNN-slug/spec.md` from `.specify/templates/spec-template.md`, then fill in:
   - Split the description into **independently testable** user stories, prioritized P1/P2/P3. P1 is the smallest demoable MVP.
   - Given/When/Then acceptance scenarios; testable FR-###; measurable, technology-agnostic SC-###.
   - Fill the "Ràng buộc từ Hiến pháp" section for the relevant articles.
   - Mark unclear points with `[NEEDS CLARIFICATION: question]`, **at most 3**, prioritized by impact:
     scope > compliance/security > experience > technical. For the rest pick a sensible default and record it under "Giả định".
   - Delete sections that do not apply.
6. Self-check against the "Checklist chất lượng spec" at the end of the file and tick the passing items. Fix the spec for failing
   items (at most 3 rounds).
7. Add a row to the table in `specs/README.md`: ID, name, roadmap milestone, status `Draft`.

## Do not
- Write a plan, tasks or code. Name frameworks, libraries or file names in the spec.
- Invent business figures (prices, Shopee policy, customer information). Use `[NEEDS CLARIFICATION]` for those.

## Report
- Spec path, branch (if any), number of user stories, number of FR/SC.
- Remaining `[NEEDS CLARIFICATION]` markers.
- Next step: `/sdd.clarify` if anything is unclear, otherwise `/sdd.plan`. **Stop for the user to read the spec.**
