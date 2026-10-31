"""Runs the sample question set through the live reply path and stores the graded result (research R13; FR-023, FR-024).

Each question goes through the same `ReplyEngine` and `OutputGuard` as a live turn, without TTS or the renderer: the
answer that gets graded is what the host would say (sentences that passed the guard, plus the refusal sentence when
the guard stopped the reply). Calls are sequential and paced, and a 429 backs off and retries, so a run fits the
Gemini free-tier rate limit (ADR-018).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_live.brain.guard import OutputGuard, refusal_sentence
from ai_live.brain.prompt import addressee
from ai_live.core.models import Comment
from ai_live.core.protocols import ReplyEngine, ReplyEngineError
from ai_live.products.models import ProductCatalog
from ai_live.qa_eval.grader import EvalQuestion, QuestionSet, grade_answer

Sleep = Callable[[float], Awaitable[None]]

DEFAULT_RUNS_DIR = Path("data/eval/runs")
PASS_RATIO = 0.8  # SC-008: >= 8/10
# Gap between Gemini calls. 6 s keeps a run at <= 10 requests per minute, under the free-tier per-minute limit
# (ADR-018); the fake engine needs no gap.
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
    error: str | None = None


@dataclass
class EvalRun:
    run_id: str
    created_at: str
    questions_file: str
    content_source: str
    content_version: str
    llm_model: str
    results: list[EvalResult]
    score: int
    total: int
    threshold: int
    warnings: list[str] = field(default_factory=list)
    previous_run_id: str | None = None
    previous_score: int | None = None
    previous_total: int | None = None
    diff: list[dict[str, Any]] = field(default_factory=list)

    @property
    def reached_threshold(self) -> bool:
        return self.score >= self.threshold

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> EvalRun:
        fields = dict(data)
        fields["results"] = [EvalResult(**r) for r in data["results"]]
        return cls(**fields)


@dataclass
class SeriesResult:
    runs: list[EvalRun]
    threshold: int
    report_paths: list[Path]

    @property
    def passed(self) -> bool:
        """SC-008: every run reaches the threshold."""
        return all(r.reached_threshold for r in self.runs)


def pass_threshold(total: int, ratio: float = PASS_RATIO) -> int:
    # The small epsilon keeps 0.8 * 10 at 8 despite float rounding.
    return math.ceil(total * ratio - 1e-9)


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
        async for sentence in replies:
            if first is None:
                first = round(time.perf_counter() - started, 3)
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
) -> EvalRun:
    """Ask every question once, in order, `pace_s` seconds apart. Not saved; see `run_series`."""
    started = now()
    guard = OutputGuard()
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
        llm_model=engine_label,
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


def compare_with(run: EvalRun, previous: EvalRun | None) -> None:
    """Fill the comparison fields of `run`: previous score and the questions whose result changed (FR-024)."""
    if previous is None:
        return
    run.previous_run_id = previous.run_id
    run.previous_score = previous.score
    run.previous_total = previous.total
    before = {r.question_id: r.passed for r in previous.results}
    after = {r.question_id: r.passed for r in run.results}
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


def _verdict(passed: bool | None) -> str:
    return "—" if passed is None else ("Đúng" if passed else "Sai")


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
    status = "đạt" if run.reached_threshold else "chưa đạt"
    lines = [
        f"# Kết quả chấm bộ câu hỏi mẫu: {run.run_id}",
        "",
        f"- Thời điểm: {run.created_at}",
        f"- File câu hỏi: `{run.questions_file}`",
        f"- File nội dung: `{run.content_source}` (version `{run.content_version}`)",
        f"- Engine: `{run.llm_model}`",
        f"- **Tổng điểm: {run.score}/{run.total}** ({status} ngưỡng {run.threshold}/{run.total})",
    ]
    for warning in run.warnings:
        lines.append(f"- Cảnh báo: {warning}")

    lines += ["", "## So sánh với lần chạy trước", ""]
    if run.previous_run_id is None:
        lines.append("Chưa có lần chạy trước với cùng file câu hỏi.")
    else:
        delta = run.score - (run.previous_score or 0)
        trend = f"tăng {delta}" if delta > 0 else (f"giảm {-delta}" if delta < 0 else "không đổi")
        lines.append(
            f"Lần trước `{run.previous_run_id}`: {run.previous_score}/{run.previous_total} → "
            f"lần này {run.score}/{run.total} ({trend})."
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
        "| Câu | Người hỏi | Câu hỏi | Câu trả lời của host | Tự chấm | Lý do | Chấm tay |",
        "|-----|-----------|---------|----------------------|---------|-------|----------|",
    ]
    for r in run.results:
        answer = _cell(r.answer) or "(không có câu trả lời)"
        lines.append(
            f"| {r.question_id} | {_cell(r.author)} | {_cell(r.question)} | {answer} | {_verdict(r.passed)} "
            f"| {_cell(_reason(r))} |  |"
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
) -> SeriesResult:
    """Run the set `repeat` times; save each run compared with the one before it (the latest saved run at first)."""
    previous = find_previous_run(runs_dir, questions_file)
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
