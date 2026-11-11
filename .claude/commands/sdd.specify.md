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
2. Read `progress/STATUS.md` and `progress/FEATURES.md` first (existing features, their cards, the "Đề xuất chưa tạo" table),
   then `.specify/memory/constitution.md`, `docs/PRD.md` and `docs/ROADMAP.md` to understand scope and avoid duplicating
   existing features. You may read `docs/ARCHITECTURE.md` for context, but **keep implementation details out of the spec**.
3. Assign the Feature ID:
   - `NNN` = highest number in `specs/` plus 1, zero-padded to 3 digits (starting at `001`), unless the input or the
     "Đề xuất chưa tạo" table already fixes the ID.
   - `slug` = 2–4 English words, kebab-case, describing the feature (e.g. `local-reply-pipeline`).
4. Stay on the current branch (`main`); do **not** create a feature branch (ADR-027). Write `Branch: main` in the spec header.
5. Create `specs/NNN-slug/spec.md` from `.specify/templates/spec-template.md`, then fill in:
   - Split the description into **independently testable** user stories, prioritized P1/P2/P3. P1 is the smallest demoable MVP.
   - Given/When/Then acceptance scenarios; testable FR-###; measurable, technology-agnostic SC-###.
   - Fill the "Ràng buộc từ Hiến pháp" section for the relevant articles.
   - Mark unclear points with `[NEEDS CLARIFICATION: question]`, **at most 3**, prioritized by impact:
     scope > compliance/security > experience > technical. For the rest pick a sensible default and record it under "Giả định".
   - Delete sections that do not apply.
6. Self-check against the "Checklist chất lượng spec" at the end of the file and tick the passing items. Fix the spec for failing
   items (at most 3 rounds).
7. Register it in `progress/` (protocol: `progress/README.md` §3):
   - `FEATURES.md`: a row in "Bảng tổng" (status `Draft`) and a new card with every key filled (`adrs`, `depends_on`,
     `agents`, `roadmap`, `open`); remove the matching line from "Đề xuất chưa tạo" if there was one.
   - `OPEN.md` §1: one row per `[NEEDS CLARIFICATION]`. `STATUS.md`: `active_feature`, `next_step`. `LOG.md`: one line.

## Do not
- Write a plan, tasks or code. Name frameworks, libraries or file names in the spec.
- Invent business figures (prices, Shopee policy, customer information). Use `[NEEDS CLARIFICATION]` for those.

## Report
- Spec path, number of user stories, number of FR/SC, `progress/` files updated.
- Remaining `[NEEDS CLARIFICATION]` markers.
- Next step: `/sdd.clarify` if anything is unclear, otherwise `/sdd.plan`. **Stop for the user to read the spec.**
