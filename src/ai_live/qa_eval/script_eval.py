"""Script self-check: generate sample segments, grade them, store and compare (004 US4; FR-025, FR-026, research R15).

Two modes, one stored result (`ScriptEvalRun`, data-model §10):
- **Generate** (`run_script_eval`): every product x topic with data (research R5), plus `opening` and `closing`, goes
  through the very `narrate()` the live show uses (`create_reply_engine(settings)`), `per_combo` times each. Calls are
  sequential and `pace_s` apart, so a run fits the Gemini free-tier rate limit (ADR-018, research R14).
- **Session** (`grade_session`): every `spoken` line of a past show's `script_sentences.jsonl` is graded again (SC-003).

A service error (429, timeout, API error) is recorded on its segment and never counted as a violation; a run with
errors does not count towards SC-008. With the model chain (008) every segment records the entry that spoke it and the
run records `chain` or `chain:<label>` (FR-022). `run_script_check` is the single entry for the CLI (T059).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_live.brain.factory import create_reply_engine
from ai_live.brain.guard import OutputGuard, load_platform_phrases, word_form
from ai_live.brain.sanitize import clean_spoken
from ai_live.core.config import Settings
from ai_live.core.models import SegmentRequest, SpokenHistory, SpokenLine, Topic
from ai_live.core.protocols import ReplyEngine, ReplyEngineError
from ai_live.director.script_runner import CLOSING_MAX_SENTENCES, CLOSING_MIN_SENTENCES
from ai_live.director.segment_planner import topics_for
from ai_live.director.session_log import SCRIPT_SENTENCES_FILE, SEGMENTS_FILE
from ai_live.products.models import ProductCatalog
from ai_live.qa_eval.runner import GEMINI_PACE_S, TurnTracker, chain_label, chain_models, chain_session
from ai_live.qa_eval.script_grader import (
    BAD_PRONOUNS,
    VIOLATION_KINDS,
    GradedSentence,
    count_by_kind,
    grade_sentence,
    grade_sentences,
    sentence_count_warning,
)

Sleep = Callable[[float], Awaitable[None]]

DEFAULT_SCRIPT_RUNS_DIR = Path("data/eval/script_runs")
SESSION_ENGINE = "session"
_SPOKEN = "spoken"


class ScriptEvalError(RuntimeError):
    """The check cannot run, e.g. a session folder without `script_sentences.jsonl`. The message is Vietnamese."""


@dataclass
class ScriptEvalSegment:
    product_id: str | None
    topic: str
    sentences: list[GradedSentence] = field(default_factory=list)
    sentence_count_warning: bool = False
    error: str | None = None  # service error: no sentences, not a violation
    segment_id: str | None = None  # set in session mode, to find the segment in the session files
    # The chain entry that spoke the segment (008 FR-022); `None` in session mode, with an engine that does not report
    # it, or when no entry answered. `provider` is the full `X-Routed-Via` value.
    model_label: str | None = None
    model: str | None = None
    provider: str | None = None

    @property
    def violation_count(self) -> int:
        return sum(len(s.violations) for s in self.sentences)

    def to_json(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "topic": self.topic,
            "segment_id": self.segment_id,
            "sentences": [s.to_json() for s in self.sentences],
            "sentence_count_warning": self.sentence_count_warning,
            "error": self.error,
            "model_label": self.model_label,
            "model": self.model,
            "provider": self.provider,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ScriptEvalSegment:
        return cls(
            product_id=data.get("product_id"),
            topic=data["topic"],
            sentences=[GradedSentence.from_json(s) for s in data.get("sentences", [])],
            sentence_count_warning=bool(data.get("sentence_count_warning", False)),
            error=data.get("error"),
            segment_id=data.get("segment_id"),
            model_label=data.get("model_label"),
            model=data.get("model"),
            provider=data.get("provider"),
        )


@dataclass
class ScriptEvalRun:
    """One self-check run (data-model §10). `session` is the regraded session folder, `None` for a generated run."""

    run_id: str
    started_at: str
    finished_at: str
    engine: str
    model: str
    content_source: str
    catalog_version: str
    segments: list[ScriptEvalSegment]
    totals: dict[str, int]
    violation_count: int
    previous: dict[str, Any] | None = None  # {run_id, engine, model, violation_count, totals} of the previous run
    delta: dict[str, int] | None = None  # totals - previous.totals, per kind
    error_count: int = 0
    per_combo: int = 1
    session: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """No segment hit a service error, so the run counts towards SC-008."""
        return self.error_count == 0

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "engine": self.engine,
            "model": self.model,
            "content_source": self.content_source,
            "catalog_version": self.catalog_version,
            "session": self.session,
            "per_combo": self.per_combo,
            "segments": [s.to_json() for s in self.segments],
            "totals": dict(self.totals),
            "violation_count": self.violation_count,
            "error_count": self.error_count,
            "previous": self.previous,
            "delta": self.delta,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ScriptEvalRun:
        return cls(
            run_id=data["run_id"],
            started_at=data["started_at"],
            finished_at=data["finished_at"],
            engine=data["engine"],
            model=data["model"],
            content_source=data["content_source"],
            catalog_version=data["catalog_version"],
            segments=[ScriptEvalSegment.from_json(s) for s in data["segments"]],
            totals={str(k): int(v) for k, v in data["totals"].items()},
            violation_count=int(data["violation_count"]),
            previous=data.get("previous"),
            delta=data.get("delta"),
            error_count=int(data.get("error_count", 0)),
            per_combo=int(data.get("per_combo", 1)),
            session=data.get("session"),
            warnings=list(data.get("warnings", [])),
        )


@dataclass(frozen=True)
class ScriptCheckResult:
    """What `run_script_check` hands to the CLI: the stored run and its two files."""

    run: ScriptEvalRun
    json_path: Path
    md_path: Path

    @property
    def violation_count(self) -> int:
        return self.run.violation_count

    @property
    def error_count(self) -> int:
        return self.run.error_count


def _stamp(at: datetime) -> str:
    return at.isoformat(timespec="seconds")


def _finish(
    *,
    started: datetime,
    finished: datetime,
    engine: str,
    model: str,
    catalog: ProductCatalog,
    segments: list[ScriptEvalSegment],
    per_combo: int = 1,
    session: str | None = None,
    warnings: list[str] | None = None,
) -> ScriptEvalRun:
    totals = count_by_kind(s for seg in segments for s in seg.sentences)
    return ScriptEvalRun(
        run_id=started.strftime("%Y%m%d-%H%M%S"),
        started_at=_stamp(started),
        finished_at=_stamp(finished),
        engine=engine,
        model=model,
        content_source=catalog.source_name,
        catalog_version=catalog.version,
        segments=segments,
        totals=totals,
        violation_count=sum(totals.values()),
        error_count=sum(seg.error is not None for seg in segments),
        per_combo=per_combo,
        session=session,
        warnings=warnings or [],
    )


# ---------- Generate mode ----------


def eval_combos(catalog: ProductCatalog) -> list[tuple[str | None, Topic]]:
    """`opening`, every product x topic with data in catalog and R5 order (the planner's rule), then `closing`."""
    combos: list[tuple[str | None, Topic]] = [(None, Topic.OPENING)]
    for product in catalog.products:
        combos += [(product.id, topic) for topic in topics_for(product)]
    combos.append((None, Topic.CLOSING))
    return combos


async def _narrate(
    engine: ReplyEngine, request: SegmentRequest, catalog: ProductCatalog, timeout_s: float | None
) -> tuple[list[str], str | None]:
    """Raw sentences of one segment, or `([], error)`: a broken segment is not graded, like a failed one on live."""
    raw: list[str] = []
    lines: AsyncIterator[str] = engine.narrate(request, catalog)
    try:
        # One deadline for the whole segment, as `SCRIPT_LLM_TIMEOUT_S` on live.
        async with asyncio.timeout(timeout_s):
            async for line in lines:
                raw.append(line)
    except ReplyEngineError as exc:
        return [], f"{exc.kind}: {exc}"
    except TimeoutError:
        return [], f"timeout: không sinh xong phân đoạn trong {timeout_s:g} s"
    finally:
        aclose = getattr(lines, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()
    return raw, None


def _bounds(topic: Topic, min_sentences: int, max_sentences: int) -> tuple[int, int]:
    # Same bounds as the live runner: the closing is 1-2 sentences (FR-017), every other segment uses the settings.
    if topic is Topic.CLOSING:
        return CLOSING_MIN_SENTENCES, CLOSING_MAX_SENTENCES
    return min_sentences, max_sentences


async def run_script_eval(
    engine: ReplyEngine,
    catalog: ProductCatalog,
    *,
    guard: OutputGuard,
    engine_label: str,
    model: str,
    min_sentences: int,
    max_sentences: int,
    per_combo: int = 1,
    pace_s: float = 0.0,
    timeout_s: float | None = 10.0,
    history_sentences: int = 12,
    sleep: Sleep = asyncio.sleep,
    now: Callable[[], datetime] = datetime.now,
    progress: Callable[[ScriptEvalSegment], None] | None = None,
) -> ScriptEvalRun:
    """Generate and grade every combination `per_combo` times, `pace_s` seconds between two calls. Not saved.

    Requests carry the previous sentence and the recent lines about the same product, built from the lines that
    would have been spoken (cleaned and passing the guard), so the prompt looks like one on live.
    """
    if per_combo < 1:
        raise ValueError(f"per_combo must be >= 1, got {per_combo}")
    started = now()
    tracker = TurnTracker(engine)
    history = SpokenHistory()
    previous_sentence: str | None = None
    segments: list[ScriptEvalSegment] = []
    calls = 0
    for product_id, topic in eval_combos(catalog):
        low, high = _bounds(topic, min_sentences, max_sentences)
        for _ in range(per_combo):
            if calls and pace_s > 0:
                await sleep(pace_s)
            calls += 1
            request = SegmentRequest(
                segment_id=uuid.uuid4().hex,
                topic=topic,
                product_id=product_id,
                min_sentences=low,
                max_sentences=high,
                previous_sentence=previous_sentence,
                recent_lines=history.recent_for(product_id, history_sentences),
            )
            raw, error = await _narrate(engine, request, catalog, timeout_s)
            label, model_name, provider = tracker.answered_by(request.segment_id)
            who = {"model_label": label, "model": model_name, "provider": provider}
            if error is not None:
                segment = ScriptEvalSegment(product_id=product_id, topic=topic.value, error=error, **who)
            else:
                segment = ScriptEvalSegment(
                    product_id=product_id,
                    topic=topic.value,
                    sentences=grade_sentences(raw, catalog, guard),
                    sentence_count_warning=sentence_count_warning(len(raw), low, high),
                    **who,
                )
                for line in raw:
                    spoken = clean_spoken(line)
                    if spoken and guard.check(spoken, catalog).ok:
                        history.add(SpokenLine(spoken, word_form(spoken), product_id, "script"))
                        previous_sentence = spoken
            segments.append(segment)
            if progress is not None:
                progress(segment)
    return _finish(
        started=started,
        finished=now(),
        engine=engine_label,
        model=model,
        catalog=catalog,
        segments=segments,
        per_combo=per_combo,
    )


# ---------- Session mode (SC-003) ----------


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Rows of a JSONL file and the number of unreadable lines (a line cut by a crash is skipped, not fatal)."""
    rows: list[dict[str, Any]] = []
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad += 1
    return rows, bad


def _grade_session_files(
    session_dir: Path, catalog: ProductCatalog, guard: OutputGuard
) -> tuple[list[ScriptEvalSegment], list[str]]:
    sentences_path = session_dir / SCRIPT_SENTENCES_FILE
    if not sentences_path.is_file():
        raise ScriptEvalError(f"Không tìm thấy {SCRIPT_SENTENCES_FILE} trong thư mục phiên {session_dir}.")
    try:
        rows, bad = _read_jsonl(sentences_path)
        segment_rows, bad_segments = (
            _read_jsonl(session_dir / SEGMENTS_FILE) if (session_dir / SEGMENTS_FILE).is_file() else ([], 0)
        )
    except (OSError, UnicodeDecodeError) as exc:
        raise ScriptEvalError(f"Không đọc được file của phiên {session_dir}: {exc}") from exc

    warnings: list[str] = []
    if bad or bad_segments:
        warnings.append(f"Bỏ qua {bad + bad_segments} dòng không đọc được trong file của phiên.")
    info = {r["segment_id"]: r for r in segment_rows if r.get("segment_id")}
    versions = sorted({str(v) for r in segment_rows if (v := r.get("catalog_version")) and v != catalog.version})
    if versions:
        warnings.append(
            f"Phiên dùng nội dung version {', '.join(versions)}, đang chấm với version {catalog.version} "
            f"({catalog.source_name}); kết quả chấm số tiền có thể lệch."
        )

    segments: dict[str, ScriptEvalSegment] = {}
    for row in rows:
        text = row.get("text")
        if row.get("status") != _SPOKEN or not isinstance(text, str):
            continue
        segment_id = str(row.get("segment_id") or "")
        segment = segments.get(segment_id)
        if segment is None:
            meta = info.get(segment_id, {})
            segment = ScriptEvalSegment(
                product_id=meta.get("product_id"), topic=str(meta.get("topic") or ""), segment_id=segment_id or None
            )
            segments[segment_id] = segment
        # SC-003 is about what viewers heard: the cleaned `text`, not the raw LLM line.
        segment.sentences.append(
            GradedSentence(
                raw_text=str(row.get("raw_text") or text), text=text, violations=grade_sentence(text, catalog, guard)
            )
        )
    if not segments:
        warnings.append("Phiên không có câu nào đã nói (status spoken).")
    return list(segments.values()), warnings


async def grade_session(
    session_dir: Path,
    catalog: ProductCatalog,
    *,
    guard: OutputGuard,
    now: Callable[[], datetime] = datetime.now,
) -> ScriptEvalRun:
    """Grade again every `spoken` line of `session_dir/script_sentences.jsonl` (SC-003). Not saved.

    Product and topic come from `segments.jsonl` when it is there. `catalog` must be the content the show used:
    the session files do not hold it, only its version, which is checked and reported as a warning when it differs.
    """
    started = now()
    segments, warnings = await asyncio.to_thread(_grade_session_files, session_dir, catalog, guard)
    return _finish(
        started=started,
        finished=now(),
        engine=SESSION_ENGINE,
        model="",
        catalog=catalog,
        segments=segments,
        session=session_dir.as_posix(),
        warnings=warnings,
    )


# ---------- Comparison and storage ----------


def _same_session(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return a is b
    return Path(a).resolve() == Path(b).resolve()


def find_previous_script_run(runs_dir: Path, *, content_source: str, session: str | None) -> ScriptEvalRun | None:
    """The latest saved run of the same content file and the same mode (generated, or the same session folder)."""
    if not runs_dir.is_dir():
        return None
    runs: list[ScriptEvalRun] = []
    for path in runs_dir.glob("*.json"):
        try:
            run = ScriptEvalRun.from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if run.content_source == content_source and _same_session(run.session, session):
            runs.append(run)
    return max(runs, key=lambda r: (r.started_at, r.run_id), default=None)


def compare_script_runs(run: ScriptEvalRun, previous: ScriptEvalRun | None) -> None:
    """Fill `previous` and `delta` (FR-026, US4 #3). A kind missing on one side counts as 0 there."""
    if previous is None:
        run.previous = None
        run.delta = None
        return
    run.previous = {
        "run_id": previous.run_id,
        # Named in the comparison, so the violations of two models are never mixed up (008 US4 #3).
        "engine": previous.engine,
        "model": previous.model,
        "violation_count": previous.violation_count,
        "totals": dict(previous.totals),
    }
    kinds = list(dict.fromkeys([*VIOLATION_KINDS, *run.totals, *previous.totals]))
    run.delta = {k: run.totals.get(k, 0) - previous.totals.get(k, 0) for k in kinds}


def save_script_run(run: ScriptEvalRun, runs_dir: Path) -> tuple[Path, Path]:
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


_KIND_LABELS = {
    "unknown_amount": "số tiền không có trong file",
    "unknown_percent": "phần trăm không có trong file",
    "forbidden_claim": "khẳng định bị cấm",
    "link": "đọc link",
    "platform_phrase": "cơ chế nền tảng shop không có",
    "bad_pronoun": "sai xưng hô",
    "formatting": "ký hiệu định dạng",
}


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _signed(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


def _segment_name(segment: ScriptEvalSegment) -> str:
    topic = segment.topic
    with contextlib.suppress(ValueError):
        topic = Topic(segment.topic).label
    return f"{segment.product_id} · {topic}" if segment.product_id else topic or "(không rõ chủ đề)"


def _spoken_by(segment: ScriptEvalSegment) -> str:
    if segment.model_label is None:
        return "—"
    return " · ".join([segment.model_label, *(p for p in (segment.model, segment.provider) if p)])


def render_markdown(run: ScriptEvalRun) -> str:
    title = "Chấm lại lịch sử phiên" if run.session else "Tự kiểm tra kịch bản"
    lines = [
        f"# {title}: {run.run_id}",
        "",
        f"- Thời điểm: {run.started_at} → {run.finished_at}",
        f"- File nội dung: `{run.content_source}` (version `{run.catalog_version}`)",
    ]
    if run.session:
        lines.append(f"- Thư mục phiên: `{run.session}`")
    else:
        lines.append(f"- Engine: `{run.engine}` (model `{run.model}`), {run.per_combo} phân đoạn mỗi tổ hợp")
    lines.append(f"- **Tổng số vi phạm: {run.violation_count}** trên {len(run.segments)} phân đoạn")
    if run.error_count:
        lines.append(
            f"- Lỗi dịch vụ: {run.error_count} phân đoạn (không tính là vi phạm; lần chạy này không dùng cho SC-008)"
        )
    lines += [f"- Cảnh báo: {w}" for w in run.warnings]

    lines += [
        "",
        "## Vi phạm theo loại",
        "",
        "| Loại | Số câu | So với lần trước |",
        "|------|--------|------------------|",
    ]
    for kind, count in run.totals.items():
        change = "—" if run.delta is None else _signed(run.delta.get(kind, 0))
        lines.append(f"| {_KIND_LABELS.get(kind, kind)} (`{kind}`) | {count} | {change} |")

    lines += ["", "## So sánh với lần chạy trước", ""]
    if run.previous is None:
        lines.append("Chưa có lần chạy trước với cùng file nội dung" + (" và cùng phiên." if run.session else "."))
    else:
        before = int(run.previous.get("violation_count", 0))
        diff = run.violation_count - before
        trend = f"tăng {diff}" if diff > 0 else (f"giảm {-diff}" if diff < 0 else "không đổi")
        before_engine = run.previous.get("engine")
        before_name = f" (engine `{before_engine}`)" if before_engine else ""
        now_name = "" if run.session else f" (engine `{run.engine}`)"
        lines.append(
            f"Lần trước `{run.previous.get('run_id')}`{before_name}: {before} vi phạm → "
            f"lần này{now_name} {run.violation_count} ({trend})."
        )

    lines += ["", "## Câu vi phạm", ""]
    flagged = [(seg, s) for seg in run.segments for s in seg.sentences if s.violations]
    if flagged:
        lines += ["| Phân đoạn | Câu | Lý do |", "|-----------|-----|-------|"]
        for seg, sentence in flagged:
            reasons = "; ".join(
                f"{_KIND_LABELS.get(v.kind, v.kind)}" + (f" ({v.detail})" if v.detail else "")
                for v in sentence.violations
            )
            text = sentence.text if sentence.text is not None else sentence.raw_text
            lines.append(f"| {_cell(_segment_name(seg))} | {_cell(text)} | {_cell(reasons)} |")
    else:
        lines.append("Không có câu nào vi phạm.")

    lines += [
        "",
        "## Từng phân đoạn",
        "",
        "| Phân đoạn | Model nói | Số câu | Vi phạm | Ghi chú |",
        "|-----------|-----------|--------|---------|---------|",
    ]
    for seg in run.segments:
        notes = []
        if seg.error:
            notes.append(f"Lỗi dịch vụ: {seg.error}")
        if seg.sentence_count_warning:
            notes.append("số câu ngoài khoảng cho phép (cảnh báo)")
        name, note, who = _cell(_segment_name(seg)), _cell("; ".join(notes)), _cell(_spoken_by(seg))
        lines.append(f"| {name} | {who} | {len(seg.sentences)} | {seg.violation_count} | {note} |")

    lines += [
        "",
        "## Luật chấm",
        "",
        "- Số tiền, phần trăm, khẳng định bị cấm, link, cơ chế nền tảng: chấm bằng đúng `OutputGuard` của lúc live.",
        "- Sai xưng hô: "
        + ", ".join(f"“{p}”" for p in BAD_PRONOUNS)
        + " (“bên mình” và “bạn” ở ngôi thứ ba như “nhiều bạn”, “các bạn khác”, “bạn nào” không tính).",
        "- Ký hiệu định dạng: câu thô khác câu sau khi làm sạch.",
        "- Lỗi dịch vụ (429, quá giờ) không tính là vi phạm.",
    ]
    return "\n".join(lines) + "\n"


# ---------- Entry for the CLI (T059) ----------


def engine_label_and_model(settings: Settings, only: str | None = None) -> tuple[str, str]:
    """`engine` and `model` of a generated run (data-model §10, 008 FR-022).

    `fake` / `fake`; `gemini` / `LLM_MODEL`; `chain` or `chain:<label>` / the models of the entries in use,
    comma-separated in chain order.
    """
    engine = settings.reply_engine
    if engine == "chain":
        return chain_label(only), chain_models(settings.llm_chain, only)
    if engine == "gemini":
        return "gemini", settings.llm_model
    return engine, engine


async def run_script_check(
    settings: Settings,
    catalog: ProductCatalog,
    *,
    per_combo: int = 1,
    session_dir: Path | None = None,
    runs_dir: Path = DEFAULT_SCRIPT_RUNS_DIR,
    engine: ReplyEngine | None = None,
    only: str | None = None,
    guard: OutputGuard | None = None,
    pace_s: float | None = None,
    sleep: Sleep = asyncio.sleep,
    now: Callable[[], datetime] = datetime.now,
    progress: Callable[[ScriptEvalSegment], None] | None = None,
) -> ScriptCheckResult:
    """Run one check, compare it with the previous run of the same content and mode, and save it.

    Generate mode by default; `session_dir` regrades that session instead (no LLM call). `guard` defaults to the live
    guard built from `PLATFORM_PHRASES_PATH` (`GuardConfigError` when the file is missing). `engine` is owned by the
    caller; without one, `create_reply_engine(settings, only=only)` builds it (`ReplyEngineError` on a configuration
    error) and the chain is preflighted and closed here. `only` is the pinned `LLM_CHAIN` label (`--entry`), used for
    the engine label too. `pace_s` defaults to `GEMINI_PACE_S` for any real LLM and 0 for the fake engine. The CLI
    exits non-zero when `result.violation_count > 0`.
    """
    if guard is None:
        guard = OutputGuard(load_platform_phrases(settings.platform_phrases_path))
    if session_dir is not None:
        run = await grade_session(session_dir, catalog, guard=guard, now=now)
    else:
        label, model = engine_label_and_model(settings, only)
        fake = settings.reply_engine == "fake"

        async def generate(llm: ReplyEngine) -> ScriptEvalRun:
            return await run_script_eval(
                llm,
                catalog,
                guard=guard,
                engine_label=label,
                model=model,
                min_sentences=settings.script_segment_min_sentences,
                max_sentences=settings.script_segment_max_sentences,
                per_combo=per_combo,
                pace_s=pace_s if pace_s is not None else (0.0 if fake else GEMINI_PACE_S),
                timeout_s=settings.script_llm_timeout_s,
                history_sentences=settings.script_history_sentences,
                sleep=sleep,
                now=now,
                progress=progress,
            )

        if engine is not None:
            run = await generate(engine)
        else:
            built = create_reply_engine(settings, only=only) if only is not None else create_reply_engine(settings)
            async with chain_session(built):
                run = await generate(built)
    previous = await asyncio.to_thread(
        find_previous_script_run, runs_dir, content_source=run.content_source, session=run.session
    )
    compare_script_runs(run, previous)
    json_path, md_path = await asyncio.to_thread(save_script_run, run, runs_dir)
    return ScriptCheckResult(run=run, json_path=json_path, md_path=md_path)
