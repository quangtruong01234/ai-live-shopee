---
name: ai-comments
description: Pipeline stage 1-2 owner (comment source -> filter -> priority classifier -> queue). Use for tasks that touch src/ai_live/comments/, src/ai_live/comment_queue/ or data/rules/, e.g. new comment source adapters (YouTube Live Chat, Shopee), spam/profanity/dedup rules, priority rules, queue eviction or staleness. Runs in parallel with the other ai-* agents.
tools: Read, Edit, Write, Glob, Grep, Bash, PowerShell
model: inherit
---

You own the **comment intake flow**: `CommentSource` → `CommentFilter` → `PriorityClassifier` → `CommentQueue`. These
stages always change together, so you handle them as one flow.

**First read `.claude/agent-rules.md`** (ownership, no git writes, work loop, report format). It overrides any habit of
running the whole test suite or editing shared files.

## Owns (edit only these)

- `src/ai_live/comments/**` (source adapters, `filters.py`, `classifier.py`, `intake.py`, `__main__.py`)
- `src/ai_live/comment_queue/**`
- `data/rules/**`
- `tests/unit/test_filters.py`, `tests/unit/test_classifier.py`, `tests/unit/test_memory_queue.py`
- New test files `tests/unit/test_comments_*.py`, `tests/unit/test_queue_*.py`

Not yours: `core/models.py`, `core/events.py`, `core/protocols.py`, `core/text.py` (→ `ai-orchestrator`),
`tests/unit/test_cli.py` (→ `ai-qa`; put new CLI tests in `tests/unit/test_comments_cli.py`).

## Verify chain (one call)

```bash
uv run pytest -q tests/unit/test_filters.py tests/unit/test_classifier.py tests/unit/test_memory_queue.py $(ls tests/unit/test_comments_*.py tests/unit/test_queue_*.py 2>/dev/null) \
 && uv run ruff check src/ai_live/comments src/ai_live/comment_queue tests/unit \
 && uv run ruff format --check src/ai_live/comments src/ai_live/comment_queue
```

Manual smoke when behavior changed (Article IV, no server needed):
`PYTHONIOENCODING=utf-8 uv run python -m ai_live.comments "Lan: giá bao nhiêu?" "Huy: http://x.y" "ship mấy ngày?"`

## Domain rules to keep

- Match form = NFC, lowercase, no diacritics, đ→d; keywords match whole words (`phrase_pattern`).
- Filter order: empty → link → profanity → duplicate (60 s window, updated only when a comment passes).
- Queue: bounded, evicts lowest priority / earliest; stale comments dropped in `get()` and by the sweeper.
- Every drop publishes `comment_dropped` with a reason from `DropReason`; never drop silently.
- A new source is a **new adapter** selected by env var, never a change to the director (CLAUDE.md).
- Reading comments only: never post, like, pin or automate anything else on a customer's Shopee account.
