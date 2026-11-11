---
description: "SDD step 3: technical plan (HOW) with research, data model, contracts and quickstart"
argument-hint: "[NNN/slug] [extra technical notes (optional)]"
---

Input: $ARGUMENTS

You are running the **plan** step of the Spec-Driven workflow (see `docs/WORKFLOW.md`).
Write the plan documents in Vietnamese; reply to the user in Vietnamese.

## Identify the feature
Same as `/sdd.clarify`: from the input, then `active_feature` in `progress/STATUS.md`, then the newest non-`Done` feature in
`progress/FEATURES.md`. Read the feature's card and `progress/OPEN.md` first: pending ADRs and constitution amendments there
affect the Constitution gate.

## Preconditions
- `specs/NNN-slug/spec.md` must exist.
- If the spec still has `[NEEDS CLARIFICATION]`: warn and ask whether to run `/sdd.clarify` first or accept the risk.
  If the user accepts, carry those points into research.

## Steps
1. Read the spec, `.specify/memory/constitution.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/RISKS.md`
   and the existing code in `src/` related to the feature.
2. Create `specs/NNN-slug/plan.md` from `.specify/templates/plan-template.md`. Fill the summary and technical context based on the
   stack settled in the ADRs (never change the stack on your own).
3. **Constitution gate (pass 1):** fill the check table. On a violation without a good reason, **stop**, tell the user and propose a
   spec or design change. Justified violations go into "Theo dõi độ phức tạp".
4. **Phase 0, write `research.md`:** resolve unknowns using the Decision / Rationale / Alternatives considered format. When outside
   information is needed (library docs, APIs), look it up and cite the source. If unsure, write `TODO:` with a question; never guess.
5. **Phase 1, design:**
   - `data-model.md`: entities, fields, types, validation rules, state transitions.
   - `contracts/`: adapter Protocols, HTTP/WebSocket endpoints, event schemas. Compare with `docs/ARCHITECTURE.md` §3 and call out
     any differences.
   - `quickstart.md`: steps to run and verify each user story, marking which steps need a GPU (laptop GPU first, RunPod as fallback) and which run without one.
6. Fill the "Ảnh hưởng ngân sách độ trễ" table if the feature touches the pipeline.
7. **Constitution gate (pass 2)** after the design is done, then update the table.
8. List the ADRs to record and new risks. Add ADRs to `docs/DECISIONS.md` with status `Đề xuất`, and risks to `docs/RISKS.md`.
9. Set the spec status to `Planned`.
10. Update `progress/` (`progress/README.md` §3): the card in `FEATURES.md` (`status`, `artifacts`, `adrs`, `depends_on`,
    `agents`), new `Đề xuất` ADRs and dependencies awaiting approval in `OPEN.md` §2, `STATUS.md` `next_step` / `blockers`,
    one line in `LOG.md`.

## Do not
- Create tasks.md or write feature code.
- Install dependencies (`uv add`). New dependencies are only **listed** in the plan for the user to approve.
- Download models.

## Report
- Files created, results of both Constitution gate passes, new dependencies to approve, proposed ADRs, new risks, open `TODO:`s.
- Next step: `/sdd.tasks`. **Stop for the user to review the plan**, especially dependencies and ADRs.
