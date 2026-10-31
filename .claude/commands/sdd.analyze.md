---
description: "SDD step 5 (read-only): check consistency between spec, plan, tasks and the constitution before coding"
argument-hint: "[feature NNN or slug (optional)]"
---

Input: $ARGUMENTS

You are running the **analyze** step of the Spec-Driven workflow. This step is **READ-ONLY: do not edit any file.**
Write the report in Vietnamese.

## Identify the feature
Same as `/sdd.clarify`. Requires `spec.md`, `plan.md` and `tasks.md`.

## Checks
1. **Constitution violations** (`.specify/memory/constitution.md`): every violation not listed in "Theo dõi độ phức tạp" is **CRITICAL**.
2. **Coverage:** which task covers each FR-### and SC-###? Which tasks trace back to no FR, SC or story?
3. **Test-first:** does every story have test tasks before its implementation tasks?
4. **Ambiguity:** unmeasurable wording ("fast", "stable", "friendly") without a number; leftover `[NEEDS CLARIFICATION]` and `TODO:`.
5. **Contradictions:** between spec, plan, tasks and `docs/ARCHITECTURE.md` / `docs/DECISIONS.md` (e.g. different interface,
   different stack, inconsistent terminology).
6. **Duplication:** repeated requirements or tasks.
7. **Latency:** a feature touching the pipeline whose plan lacks the latency-impact table, or whose tasks lack a measurement step.
8. **Task markers:** wrong `[P]` (same file, dependencies); GPU work missing `[GPU]`.

## Severity
- **CRITICAL:** constitution violation, core FR without tasks, a contradiction that leads to wrong behavior. Must be fixed before implementing.
- **HIGH:** a story missing tests, an unmeasurable SC, interface contradictions.
- **MEDIUM:** inconsistent terminology, minor ambiguity, wrong `[P]`.
- **LOW:** wording, presentation.

## Report
- Table: `ID | Mức | Loại | Vị trí (file:mục) | Vấn đề | Đề xuất sửa`, at most 30 rows, sorted by severity.
- Coverage table: `FR/SC | Task | Ghi chú`.
- Totals per severity.
- Verdict: **Sẵn sàng implement** (no CRITICAL) or **Chưa sẵn sàng**.
- Ask the user whether to fix the issues. Fix only with their consent, using the command of the matching phase or a reported manual edit.
