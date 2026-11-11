"""Runs the sample question set through the live reply path and stores the graded result (research R13; FR-023, FR-024).

Each question goes through the same `ReplyEngine` and `OutputGuard` as a live turn, without TTS or the renderer: the
answer that gets graded is what the host would say (sentences that passed the guard, plus the refusal sentence when
the guard stopped the reply). Calls are sequential and paced, and a 429 backs off and retries, so a run fits the
free-tier rate limits (ADR-018). With the model chain (008) every answer records the entry that gave it (FR-022).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_live.brain.guard import OutputGuard, refusal_sentence
from ai_live.brain.prompt import addressee
from ai_live.brain.sanitize import clean_spoken
from ai_live.core.models import Comment
from ai_live.core.protocols import ReplyEngine, ReplyEngineError
from ai_live.products.models import ProductCatalog
from ai_live.qa_eval.grader import EvalQuestion, QuestionSet, grade_answer

if TYPE_CHECKING:
    from ai_live.brain.chain_engine import TurnRecord
    from ai_live.core.config import ChainEntryConfig

Sleep = Callable[[float], Awaitable[None]]

DEFAULT_RUNS_DIR = Path("data/eval/runs")
PASS_RATIO = 0.8  # SC-008: >= 8/10
# Gap between two LLM calls. 6 s keeps a run at <= 10 requests per minute, under the free-tier per-minute limits
# (ADR-018) of Gemini and of the chain entries alike; the fake engine needs no gap.
GEMINI_PACE_S = 6.0


@dataclass
class EvalResult:
    question_id: str
    author: str
    question: str
    answer: str
    passed: bool
    missing: list[str]
    found_forbidden: list[str]
    guard_reason: str | None = None
    first_sentence_s: float | None = None
    error: str | None = None  # service error (429, timeout, API error): not graded, never a wrong answer
    # The chain entry that gave the answer (008 FR-022): `None` with an engine that does not report it, or when no
    # entry answered. `provider` is the full `X-Routed-Via` value.
    model_label: str | None = None
    model: str | None = None
    provider: str | None = None


@dataclass
class EvalRun:
    run_id: str
    created_at: str
    questions_file: str
    content_source: str
    content_version: str
    engine: str  # `fake`, the Gemini model, `chain` or `chain:<label>` (008 FR-022)
    results: list[EvalResult]
    score: int
    total: int
    threshold: int
    warnings: list[str] = field(default_factory=list)
    previous_run_id: str | None = None
    previous_score: int | None = None
    previous_total: int | None = None
    previous_engine: str | None = None
    diff: list[dict[str, Any]] = field(default_factory=list)

    @property
    def reached_threshold(self) -> bool:
        return self.score >= self.threshold

    @property
    def error_count(self) -> int:
        """Questions not graded because of a service error."""
        return sum(r.error is not None for r in self.results)

    @property
    def complete(self) -> bool:
        """Every question was graded, so the run counts towards SC-008."""
        return self.error_count == 0

    @property
    def failed(self) -> bool:
        """Below the threshold even if every ungraded question had been right: a real failure, not bad luck."""
        return self.score + self.error_count < self.threshold

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> EvalRun:
        fields = dict(data)
        # Files written before 008 name the engine `llm_model`.
        legacy = fields.pop("llm_model", None)
        fields.setdefault("engine", legacy)
        fields["results"] = [EvalResult(**r) for r in data["results"]]
        return cls(**fields)


@dataclass
class SeriesResult:
    runs: list[EvalRun]
    threshold: int
    report_paths: list[Path]

    @property
    def passed(self) -> bool:
        """SC-008: every run reaches the threshold with every question graded."""
        return all(r.reached_threshold and r.complete for r in self.runs)

    @property
    def failed(self) -> bool:
        """Some run is below the threshold however its ungraded questions would have gone."""
        return any(r.failed for r in self.runs)

    @property
    def incomplete(self) -> bool:
        """Not passed only because of service errors: the series does not count towards SC-008 either way."""
        return not self.passed and not self.failed


def pass_threshold(total: int, ratio: float = PASS_RATIO) -> int:
    # The small epsilon keeps 0.8 * 10 at 8 despite float rounding.
    return math.ceil(total * ratio - 1e-9)


# ---------- Who answered (008 FR-022) ----------


class TurnTracker:
    """Keeps the last `TurnRecord` per turn key, for engines with `add_turn_observer` (the chain).

    Duck-typed like `ShowDirector`: Gemini and the fake engine report nothing, so every answer reads `(None, None,
    None)`. The chain sends the record from the turn's `finally`, so it is here once the stream is finished or closed.
    """

    def __init__(self, engine: object) -> None:
        self._records: dict[str, TurnRecord] = {}
        add = getattr(engine, "add_turn_observer", None)
        if callable(add):
            add(self._on_turn)

    def _on_turn(self, record: TurnRecord) -> None:
        self._records[record.turn_key] = record

    def forget(self, turn_key: str) -> None:
        self._records.pop(turn_key, None)

    def answered_by(self, turn_key: str) -> tuple[str | None, str | None, str | None]:
        """(label, model, provider) of the entry that spoke the turn; all `None` when none did."""
        record = self._records.get(turn_key)
        if record is None:
            return None, None, None
        return record.label, record.model, record.provider


@contextlib.asynccontextmanager
async def chain_session(engine: ReplyEngine) -> AsyncIterator[None]:
    """`preflight()` before the first turn and `aclose()` after the last, for the chain (008 FR-011, T052).

    Callers run the whole evaluation inside one event loop: the chain's httpx client is bound to the loop it first ran
    on. Other engines need neither. A failed preflight raises `config_error`; the engine is still closed.
    """
    from ai_live.brain.chain_engine import ChainReplyEngine  # lazy, like the factory: `fake` does not need it

    if not isinstance(engine, ChainReplyEngine):
        yield
        return
    try:
        await engine.preflight()
        yield
    finally:
        await engine.aclose()


def chain_label(only: str | None) -> str:
    """Engine label of a chain run: `chain`, or `chain:<label>` when pinned to one entry (`--entry`)."""
    return "chain" if only is None else f"chain:{only}"


def chain_models(entries: Iterable[ChainEntryConfig], only: str | None) -> str:
    """Model names of the chain entries in use, comma-separated: the pinned one, or every entry in chain order."""
    return ", ".join(e.model for e in entries if only is None or e.label == only)


# ---------- Asking ----------


async def _host_answer(
    engine: ReplyEngine, guard: OutputGuard, comment: Comment, catalog: ProductCatalog
) -> tuple[list[str], str | None, float | None]:
    """Sentences the host would say, the guard reason if it stopped the reply, and seconds to the first sentence."""
    started = time.perf_counter()
    first: float | None = None
    said: list[str] = []
    replies: AsyncIterator[str] = engine.reply(comment, catalog)
    try:
        async for raw in replies:
            if first is None:
                first = round(time.perf_counter() - started, 3)
            # Cleaned before the guard, as on the live path (ADR-031); a symbols-only sentence is not spoken.
            sentence = clean_spoken(raw)
            if not sentence:
                continue
            result = guard.check(sentence, catalog)
            if result.ok:
                said.append(sentence)
                continue
            # Same as a live turn: stop at the blocked sentence and say the refusal sentence instead (FR-010, FR-011).
            said.append(refusal_sentence(addressee(comment.author)))
            return said, result.reason.value if result.reason else None, first
    finally:
        aclose = getattr(replies, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()
    return said, None, first


async def _ask(
    engine: ReplyEngine,
    guard: OutputGuard,
    question: EvalQuestion,
    catalog: ProductCatalog,
    *,
    max_retries: int,
    backoff_s: float,
    timeout_s: float | None,
    sleep: Sleep,
    tracker: TurnTracker | None = None,
) -> EvalResult:
    comment = Comment(
        id=f"eval-{question.id}",
        source="qa_eval",
        author=question.author,
        text=question.question,
        received_at=time.monotonic(),
    )
    said: list[str] = []
    guard_reason: str | None = None
    first: float | None = None
    error: str | None = None
    if tracker is not None:
        tracker.forget(comment.id)
    for attempt in range(max_retries + 1):
        try:
            async with asyncio.timeout(timeout_s):
                said, guard_reason, first = await _host_answer(engine, guard, comment, catalog)
            error = None
            break
        except ReplyEngineError as exc:
            error = f"{exc.kind}: {exc}"
            if exc.kind != "rate_limited" or attempt == max_retries:
                break
            # Free-tier quota is per minute: wait longer each time instead of hammering the API.
            await sleep(backoff_s * 2**attempt)
        except TimeoutError:
            error = f"timeout: không trả lời xong trong {timeout_s:g} s"
            break

    answer = " ".join(said)
    # The last attempt's record: an earlier one may have been rate limited before a retry answered.
    label, model, provider = tracker.answered_by(comment.id) if tracker is not None else (None, None, None)
    if error is not None:
        return EvalResult(
            question_id=question.id,
            author=question.author,
            question=question.question,
            answer=answer,
            passed=False,
            missing=[],
            found_forbidden=[],
            guard_reason=guard_reason,
            first_sentence_s=first,
            error=error,
            model_label=label,
            model=model,
            provider=provider,
        )
    grade = grade_answer(question, answer, catalog)
    return EvalResult(
        question_id=question.id,
        author=question.author,
        question=question.question,
        answer=answer,
        passed=grade.passed,
        missing=grade.missing,
        found_forbidden=grade.found_forbidden,
        guard_reason=guard_reason,
        first_sentence_s=first,
        model_label=label,
        model=model,
        provider=provider,
    )


async def run_eval(
    engine: ReplyEngine,
    catalog: ProductCatalog,
    question_set: QuestionSet,
    *,
    questions_file: Path,
    engine_label: str,
    pace_s: float = 0.0,
    pace_before_first: bool = False,
    max_retries: int = 4,
    backoff_s: float = 15.0,
    timeout_s: float | None = 60.0,
    pass_ratio: float = PASS_RATIO,
    sleep: Sleep = asyncio.sleep,
    progress: Callable[[EvalResult], None] | None = None,
    now: Callable[[], datetime] = datetime.now,
    guard: OutputGuard | None = None,
    tracker: TurnTracker | None = None,
) -> EvalRun:
    """Ask every question once, in order, `pace_s` seconds apart. Not saved; see `run_series`.

    `guard` should be the live guard, built with the platform phrases (`__main__` does that). `None` keeps the
    phrase-free guard for callers that only grade grounding. `tracker` lets a series register one observer on the
    engine instead of one per run.
    """
    started = now()
    guard = guard if guard is not None else OutputGuard()
    tracker = tracker if tracker is not None else TurnTracker(engine)
    warnings: list[str] = []
    if question_set.content_version and question_set.content_version != catalog.version:
        warnings.append(
            f"Bộ câu hỏi soạn cho nội dung version {question_set.content_version}, "
            f"đang chấm trên version {catalog.version} ({catalog.source_name}); điểm có thể lệch."
        )
    results: list[EvalResult] = []
    for n, question in enumerate(question_set.questions):
        if pace_s > 0 and (n > 0 or pace_before_first):
            await sleep(pace_s)
        result = await _ask(
            engine,
            guard,
            question,
            catalog,
            max_retries=max_retries,
            backoff_s=backoff_s,
            timeout_s=timeout_s,
            sleep=sleep,
            tracker=tracker,
        )
        results.append(result)
        if progress is not None:
            progress(result)
    total = len(results)
    return EvalRun(
        run_id=started.strftime("%Y%m%d-%H%M%S"),
        created_at=started.isoformat(),
        questions_file=questions_file.as_posix(),
        content_source=catalog.source_name,
        content_version=catalog.version,
        engine=engine_label,
        results=results,
        score=sum(r.passed for r in results),
        total=total,
        threshold=pass_threshold(total, pass_ratio),
        warnings=warnings,
    )


# ---------- Comparison and storage ----------


def _same_file(a: str | Path, b: str | Path) -> bool:
    return Path(a).resolve() == Path(b).resolve()


def find_previous_run(runs_dir: Path, questions_file: Path) -> EvalRun | None:
    """The latest saved run of the same question file; unreadable files are skipped."""
    if not runs_dir.is_dir():
        return None
    runs: list[EvalRun] = []
    for path in runs_dir.glob("*.json"):
        try:
            run = EvalRun.from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if _same_file(run.questions_file, questions_file):
            runs.append(run)
    return max(runs, key=lambda r: (r.created_at, r.run_id), default=None)


def _outcome(result: EvalResult) -> bool | str:
    """`True` / `False` for a graded answer, `"error"` for a service error (never shown as a wrong answer)."""
    return "error" if result.error is not None else result.passed


def compare_with(run: EvalRun, previous: EvalRun | None) -> None:
    """Fill the comparison fields of `run`: previous score and the questions whose result changed (FR-024)."""
    if previous is None:
        return
    run.previous_run_id = previous.run_id
    run.previous_score = previous.score
    run.previous_total = previous.total
    run.previous_engine = previous.engine
    before = {r.question_id: _outcome(r) for r in previous.results}
    after = {r.question_id: _outcome(r) for r in run.results}
    diff = [{"id": qid, "before": before.get(qid), "after": passed} for qid, passed in after.items()]
    diff += [{"id": qid, "before": passed, "after": None} for qid, passed in before.items() if qid not in after]
    run.diff = [d for d in diff if d["before"] != d["after"]]


def save_run(run: EvalRun, runs_dir: Path) -> tuple[Path, Path]:
    """Write `<run_id>.json` and `<run_id>.md`; a suffix keeps two runs started in the same second apart."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    base, n = run.run_id, 1
    while (runs_dir / f"{run.run_id}.json").exists() or (runs_dir / f"{run.run_id}.md").exists():
        n += 1
        run.run_id = f"{base}-{n}"
    json_path = runs_dir / f"{run.run_id}.json"
    md_path = runs_dir / f"{run.run_id}.md"
    json_path.write_text(json.dumps(run.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(run), encoding="utf-8")
    return json_path, md_path


# ---------- Report (Vietnamese: read by the operator) ----------


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _verdict(outcome: bool | str | None) -> str:
    if outcome is None:
        return "—"
    if outcome == "error":
        return "Lỗi dịch vụ"
    return "Đúng" if outcome else "Sai"


def _answered_by(result: EvalResult) -> str:
    if result.model_label is None:
        return "—"
    return " · ".join([result.model_label, *(p for p in (result.model, result.provider) if p)])


def _reason(result: EvalResult) -> str:
    parts: list[str] = []
    if result.error:
        parts.append(f"Lỗi: {result.error}")
    if result.missing:
        parts.append("Thiếu ý: " + "; ".join(f"“{m}”" for m in result.missing))
    if result.found_forbidden:
        parts.append("Có ý cấm: " + "; ".join(f"“{f}”" for f in result.found_forbidden))
    if result.guard_reason:
        parts.append(f"Guard đã chặn ({result.guard_reason}), host nói câu từ chối")
    return ". ".join(parts)


def render_markdown(run: EvalRun) -> str:
    if run.failed or run.complete:
        status = "đạt" if run.reached_threshold and run.complete else "chưa đạt"
    else:
        status = "chưa chấm đủ, không tính cho SC-008;"
    lines = [
        f"# Kết quả chấm bộ câu hỏi mẫu: {run.run_id}",
        "",
        f"- Thời điểm: {run.created_at}",
        f"- File câu hỏi: `{run.questions_file}`",
        f"- File nội dung: `{run.content_source}` (version `{run.content_version}`)",
        f"- Engine: `{run.engine}`",
        f"- **Tổng điểm: {run.score}/{run.total}** ({status} ngưỡng {run.threshold}/{run.total})",
    ]
    if run.error_count:
        lines.append(f"- Lỗi dịch vụ: {run.error_count} câu (không chấm, không tính là trả lời sai)")
    for warning in run.warnings:
        lines.append(f"- Cảnh báo: {warning}")

    lines += ["", "## So sánh với lần chạy trước", ""]
    if run.previous_run_id is None:
        lines.append("Chưa có lần chạy trước với cùng file câu hỏi.")
    else:
        delta = run.score - (run.previous_score or 0)
        trend = f"tăng {delta}" if delta > 0 else (f"giảm {-delta}" if delta < 0 else "không đổi")
        # Both engines are named, so the scores of two models are never mixed up (008 US4 #3).
        before_engine = f" (engine `{run.previous_engine}`)" if run.previous_engine else ""
        lines.append(
            f"Lần trước `{run.previous_run_id}`{before_engine}: {run.previous_score}/{run.previous_total} → "
            f"lần này (engine `{run.engine}`) {run.score}/{run.total} ({trend})."
        )
        lines.append("")
        if run.diff:
            lines += ["| Câu | Lần trước | Lần này |", "|-----|-----------|---------|"]
            lines += [f"| {d['id']} | {_verdict(d['before'])} | {_verdict(d['after'])} |" for d in run.diff]
        else:
            lines.append("Không có câu nào đổi kết quả.")

    lines += [
        "",
        "## Chi tiết từng câu",
        "",
        "Cột **Chấm tay** để người vận hành điền Đúng/Sai, đối chiếu với kết quả tự chấm (SC-009: khớp ≥ 9/10 câu).",
        "",
        "| Câu | Người hỏi | Câu hỏi | Câu trả lời của host | Model trả lời | Tự chấm | Lý do | Chấm tay |",
        "|-----|-----------|---------|----------------------|---------------|---------|-------|----------|",
    ]
    for r in run.results:
        answer = _cell(r.answer) or "(không có câu trả lời)"
        lines.append(
            f"| {r.question_id} | {_cell(r.author)} | {_cell(r.question)} | {answer} | {_cell(_answered_by(r))} "
            f"| {_verdict(_outcome(r))} | {_cell(_reason(r))} |  |"
        )
    return "\n".join(lines) + "\n"


# ---------- Series (--repeat) ----------


async def run_series(
    engine: ReplyEngine,
    catalog: ProductCatalog,
    question_set: QuestionSet,
    *,
    questions_file: Path,
    engine_label: str,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    repeat: int = 1,
    pace_s: float = 0.0,
    max_retries: int = 4,
    backoff_s: float = 15.0,
    timeout_s: float | None = 60.0,
    pass_ratio: float = PASS_RATIO,
    sleep: Sleep = asyncio.sleep,
    progress: Callable[[EvalResult], None] | None = None,
    on_run: Callable[[EvalRun, Path], None] | None = None,
    guard: OutputGuard | None = None,
) -> SeriesResult:
    """Run the set `repeat` times; save each run compared with the one before it (the latest saved run at first)."""
    previous = find_previous_run(runs_dir, questions_file)
    tracker = TurnTracker(engine)
    runs: list[EvalRun] = []
    paths: list[Path] = []
    for i in range(repeat):
        run = await run_eval(
            engine,
            catalog,
            question_set,
            questions_file=questions_file,
            engine_label=engine_label,
            pace_s=pace_s,
            pace_before_first=i > 0,
            max_retries=max_retries,
            backoff_s=backoff_s,
            timeout_s=timeout_s,
            pass_ratio=pass_ratio,
            sleep=sleep,
            progress=progress,
            guard=guard,
            tracker=tracker,
        )
        compare_with(run, previous)
        _, md_path = save_run(run, runs_dir)
        runs.append(run)
        paths.append(md_path)
        if on_run is not None:
            on_run(run, md_path)
        previous = run
    return SeriesResult(
        runs=runs, threshold=pass_threshold(len(question_set.questions), pass_ratio), report_paths=paths
    )
