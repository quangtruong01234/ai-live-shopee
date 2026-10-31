---
description: "SDD step 2: ask up to 5 questions to clarify the spec and write the answers straight into it"
argument-hint: "[feature NNN or slug (optional)]"
---

Input: $ARGUMENTS

You are running the **clarify** step of the Spec-Driven workflow (see `docs/WORKFLOW.md`).
Ask questions and write spec updates in Vietnamese; reply to the user in Vietnamese.

## Identify the feature
In order: (1) `NNN` or slug in the input; (2) the current git branch if it matches `NNN-*`; (3) the highest-numbered feature in
`specs/README.md` that is not `Done`. If ambiguous, ask the user.

## Steps
1. Read `specs/NNN-slug/spec.md` and `.specify/memory/constitution.md`.
2. Review the spec by category and mark each as Clear / Partial / Missing:
   scope and boundaries; user roles (operator, viewer, customer); data and entities; main and error flows; edge cases;
   latency and performance; compliance (AI label, real time, consent); security; measurable criteria; consistent terminology.
3. Build the question list: every `[NEEDS CLARIFICATION]` plus high-impact "Missing" items. Rank by
   (impact × uncertainty). Take **at most 5**. Only ask questions whose answer changes the design, tests or scope.
4. Ask **one question at a time** with the AskUserQuestion tool. Each has 2–4 options; put the recommended option first, labeled
   "(Recommended)" with a short reason. The user can always answer something else.
5. After **each** answer, update the spec immediately:
   - Add `- Q: ... → A: ...` under "Làm rõ / Phiên YYYY-MM-DD".
   - Edit exactly the affected parts (FR, SC, story, assumptions, edge cases) and remove the matching `[NEEDS CLARIFICATION]` marker.
   - Leave no sentence that contradicts the new answer.
6. Stop when no important questions remain, 5 have been asked, or the user says stop.
7. If no markers remain and the checklist passes: set the spec status and its row in `specs/README.md` to `Clarified`.

## Do not
- Ask about implementation details (libraries, code structure); those belong to the plan.
- Answer business or policy questions on the user's behalf.

## Report
- Number of questions asked, spec sections edited, coverage table by category.
- Open questions (if any) and the risk of leaving them.
- Next step: `/sdd.plan` (or another `/sdd.clarify` round). **Stop.**
