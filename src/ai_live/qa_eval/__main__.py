"""Grade the sample question set (001: research R13; FR-023, FR-024) or the show script (004 US4: FR-025, FR-026).

    uv run python -m ai_live.qa_eval run --content data/products/demo.docx \\
        --questions data/eval/demo_questions.json [--repeat 3] [--runs-dir data/eval/runs] [--entry LABEL]
    uv run python -m ai_live.qa_eval script [--content PATH] [--per-combo N] [--session DIR] \\
        [--runs-dir data/eval/script_runs] [--entry LABEL]

Both use the `ReplyEngine` chosen by `REPLY_ENGINE` and the live `OutputGuard`, without TTS or the renderer. Each run
is saved as `<runs-dir>/<ts>.json` and `.md` and compared with the latest comparable run.

With `REPLY_ENGINE=chain` (feature 008) the chain is checked with `preflight()` before the first question or segment,
and `--entry LABEL` pins one `LLM_CHAIN` entry with no switch to another (FR-021): its 429 is a service error, never a
wrong answer. The engine is recorded as `chain` or `chain:<label>`, and every answer records the entry that gave it.

Exit codes, `run`: 0 when every run reaches the threshold (SC-008) with every question graded, 2 when a run is below
it even if its ungraded questions had all been right, 3 otherwise when a question hit a service error, 1 on a content,
question-file, configuration or preflight error.
Exit codes, `script`: 0 when no sentence breaks a rule, 2 when one does, 3 when there is no violation but some segment
hit a service error (429, timeout), 1 on a content, session-folder, configuration or preflight error. 3 is not 0
because the missing questions or segments were never graded: such a run does not count towards SC-008 (research R14).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from ai_live.brain.factory import create_reply_engine
from ai_live.brain.guard import GuardConfigError, load_guard
from ai_live.core.config import Settings
from ai_live.core.models import Topic
from ai_live.core.protocols import ReplyEngine, ReplyEngineError
from ai_live.products.docx_loader import load_catalog_file
from ai_live.products.models import ContentLoadError, ProductCatalog
from ai_live.qa_eval.grader import QuestionSetError, load_question_set
from ai_live.qa_eval.runner import (
    DEFAULT_RUNS_DIR,
    GEMINI_PACE_S,
    EvalResult,
    EvalRun,
    SeriesResult,
    Sleep,
    chain_label,
    chain_session,
    run_series,
)
from ai_live.qa_eval.script_eval import (
    DEFAULT_SCRIPT_RUNS_DIR,
    ScriptCheckResult,
    ScriptEvalError,
    ScriptEvalRun,
    ScriptEvalSegment,
    engine_label_and_model,
    run_script_check,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FAILED = 2  # `run`: below the threshold; `script`: at least one violation
EXIT_INCOMPLETE = 3  # nothing failed, but some questions / segments were not graded (service error)

_ENTRY_HELP = "chỉ dùng một mục của LLM_CHAIN (nhãn), không chuyển sang mục khác; cần REPLY_ENGINE=chain"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ai_live.qa_eval")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="chấm bộ câu hỏi mẫu, ghi báo cáo .json và .md")
    run.add_argument("--content", type=Path, default=None, help="file Word nội dung; mặc định PRODUCT_DATA_PATH")
    run.add_argument(
        "--questions", type=Path, required=True, help="file JSON bộ câu hỏi (contracts/content-template.md §2)"
    )
    run.add_argument("--repeat", type=int, default=1, help="số lần chạy liên tiếp; đạt khi mọi lần ≥ 8/10 (SC-008)")
    run.add_argument(
        "--runs-dir",
        type=Path,
        default=DEFAULT_RUNS_DIR,
        help=f"thư mục lưu kết quả (mặc định {DEFAULT_RUNS_DIR.as_posix()})",
    )
    run.add_argument(
        "--pace",
        type=float,
        default=None,
        help=f"số giây nghỉ giữa hai lần gọi (mặc định {GEMINI_PACE_S:g} với gemini, 0 với fake)",
    )
    run.add_argument("--max-retries", type=int, default=4, help="số lần thử lại khi gặp 429 (mặc định 4)")
    run.add_argument(
        "--backoff", type=float, default=15.0, help="số giây chờ lần đầu khi gặp 429, gấp đôi mỗi lần (mặc định 15)"
    )
    run.add_argument("--timeout", type=float, default=60.0, help="số giây tối đa cho một câu trả lời (mặc định 60)")
    run.add_argument("--entry", default=None, metavar="LABEL", help=_ENTRY_HELP)

    script = sub.add_parser(
        "script", help="tự kiểm tra kịch bản: sinh phân đoạn mẫu hoặc chấm lại một phiên, ghi .json và .md"
    )
    script.add_argument("--content", type=Path, default=None, help="file Word nội dung; mặc định PRODUCT_DATA_PATH")
    script.add_argument(
        "--per-combo", type=int, default=1, help="số phân đoạn sinh cho mỗi tổ hợp sản phẩm × chủ đề (mặc định 1)"
    )
    script.add_argument(
        "--session",
        type=Path,
        default=None,
        help="thư mục phiên (data/sessions/<id>): chấm lại mọi câu đã nói thay vì sinh mẫu, không gọi LLM",
    )
    script.add_argument(
        "--runs-dir",
        type=Path,
        default=DEFAULT_SCRIPT_RUNS_DIR,
        help=f"thư mục lưu kết quả (mặc định {DEFAULT_SCRIPT_RUNS_DIR.as_posix()})",
    )
    script.add_argument("--entry", default=None, metavar="LABEL", help=_ENTRY_HELP)
    return parser


def _load_content(args: argparse.Namespace, settings: Settings) -> ProductCatalog | None:
    """The catalog, or `None` after printing why it cannot be loaded."""
    content: Path = args.content or settings.product_data_path
    if not content.is_file():
        print(f"Không tìm thấy file nội dung: {content}")
        return None
    try:
        return load_catalog_file(content, settings.content_max_bytes)
    except ContentLoadError as exc:
        print(f"File '{content.name}' có {len(exc.issues)} lỗi:")
        for issue in exc.issues:
            print(f"  - [{issue.code}] {issue.message}")
        return None


def _build_engine(settings: Settings, entry: str | None) -> ReplyEngine | None:
    """The engine for `REPLY_ENGINE` (pinned to `entry` if given), or `None` after printing the configuration error.

    Looked up through this module's `create_reply_engine`, so tests can swap the factory.
    """
    try:
        if entry is not None:
            return create_reply_engine(settings, only=entry)
        return create_reply_engine(settings)
    except ReplyEngineError as exc:
        print(f"Lỗi cấu hình LLM ({exc.kind}): {exc}")
        return None


async def _in_session[T](engine: ReplyEngine, work: Callable[[], Awaitable[T]]) -> T:
    """Preflight, every turn and close in one event loop: the chain's httpx client is bound to the loop it first ran
    on. `work` is a factory, so a failed preflight leaves no coroutine that was never awaited."""
    async with chain_session(engine):
        return await work()


def _print_result(result: EvalResult) -> None:
    # A service error is not a wrong answer (008 US4 #1): it never prints as SAI.
    verdict = "LỖI" if result.error is not None else ("ĐÚNG" if result.passed else "SAI ")
    detail = result.error or "; ".join(
        [*(f"thiếu “{m}”" for m in result.missing), *(f"có ý cấm “{f}”" for f in result.found_forbidden)]
    )
    who = f" [{result.model_label}]" if result.model_label else ""
    print(f"  {result.question_id} {verdict}{who} {detail}".rstrip())


def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    engine: ReplyEngine | None = None,
    sleep: Sleep | None = None,
) -> int:
    """`settings`, `engine` and `sleep` are injectable so tests run without `.env`, network or real waiting."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    if args.command == "script":
        return _script(args, settings or Settings(), engine, sleep)
    return _questions(args, settings or Settings(), engine, sleep)


def _questions(args: argparse.Namespace, settings: Settings, engine: ReplyEngine | None, sleep: Sleep | None) -> int:
    if args.repeat < 1:
        print("--repeat phải ≥ 1")
        return EXIT_ERROR
    catalog = _load_content(args, settings)
    if catalog is None:
        return EXIT_ERROR
    try:
        question_set = load_question_set(args.questions)
    except QuestionSetError as exc:
        print(f"File câu hỏi '{args.questions}' có {len(exc.issues)} lỗi:")
        for issue in exc.issues:
            print(f"  - {issue}")
        return 1

    try:
        guard = load_guard(settings.platform_phrases_path, settings.claim_phrases_path)
    except GuardConfigError as exc:
        print(f"Lỗi cấu hình guard: {exc}")
        return 1
    # An injected engine belongs to the caller; one built here is preflighted and closed here.
    owned = engine is None
    if engine is None:
        engine = _build_engine(settings, args.entry)
        if engine is None:
            return EXIT_ERROR
    if settings.reply_engine == "chain":
        label = chain_label(args.entry)
    else:
        label = "fake" if settings.reply_engine == "fake" else settings.llm_model
    pace = args.pace if args.pace is not None else (0.0 if settings.reply_engine == "fake" else GEMINI_PACE_S)

    def on_run(run: EvalRun, md_path: Path) -> None:
        print(
            f"Lần chạy {run.run_id}: {run.score}/{run.total} (ngưỡng {run.threshold}/{run.total}). Báo cáo: {md_path}"
        )
        for warning in run.warnings:
            print(f"  Cảnh báo: {warning}")
        if run.error_count:
            print(f"  {run.error_count} câu lỗi dịch vụ, không được chấm (không tính là trả lời sai)")
        if run.previous_run_id is not None:
            changed = ", ".join(d["id"] for d in run.diff) or "không có"
            engine_before = f" (engine {run.previous_engine})" if run.previous_engine else ""
            print(
                f"  So với {run.previous_run_id}{engine_before}: {run.previous_score}/{run.previous_total}; "
                f"câu đổi kết quả: {changed}"
            )

    def series_of_runs() -> Awaitable[SeriesResult]:
        return run_series(
            engine,
            catalog,
            question_set,
            questions_file=args.questions,
            engine_label=label,
            runs_dir=args.runs_dir,
            repeat=args.repeat,
            pace_s=pace,
            max_retries=args.max_retries,
            backoff_s=args.backoff,
            timeout_s=args.timeout,
            sleep=sleep or asyncio.sleep,
            progress=_print_result,
            on_run=on_run,
            guard=guard,
        )

    print(f"Chấm {len(question_set.questions)} câu × {args.repeat} lần, engine {label}, nội dung {catalog.source_name}")
    try:
        series = asyncio.run(_in_session(engine, series_of_runs) if owned else series_of_runs())
    except ReplyEngineError as exc:
        # Only the preflight raises here: a turn's error is recorded on its question.
        print(f"Lỗi cấu hình LLM ({exc.kind}): {exc}")
        return EXIT_ERROR
    reached = sum(r.reached_threshold and r.complete for r in series.runs)
    total = len(question_set.questions)
    if series.passed:
        verdict = "ĐẠT"
    elif series.failed:
        verdict = "CHƯA ĐẠT"
    else:
        verdict = "CHƯA CHẤM ĐỦ (có câu lỗi dịch vụ; lần chạy này không tính cho SC-008)"
    print(f"Kết quả: {verdict}, {reached}/{len(series.runs)} lần ≥ {series.threshold}/{total} (SC-008 cần mọi lần đạt)")
    if series.passed:
        return EXIT_OK
    return EXIT_FAILED if series.failed else EXIT_INCOMPLETE


def _segment_name(segment: ScriptEvalSegment) -> str:
    try:
        topic = Topic(segment.topic).label
    except ValueError:  # a session line whose segment is missing from segments.jsonl
        topic = segment.topic or "(không rõ chủ đề)"
    return f"{segment.product_id} · {topic}" if segment.product_id else topic


def _print_segment(segment: ScriptEvalSegment) -> None:
    if segment.error:
        print(f"  {_segment_name(segment)}: lỗi dịch vụ, không chấm ({segment.error})")
        return
    warn = ", số câu ngoài khoảng cho phép" if segment.sentence_count_warning else ""
    print(f"  {_segment_name(segment)}: {len(segment.sentences)} câu, {segment.violation_count} vi phạm{warn}")


def _print_script_run(run: ScriptEvalRun, md_path: Path) -> None:
    flagged = [(seg, s) for seg in run.segments for s in seg.sentences if s.violations]
    if flagged:
        print("Câu vi phạm:")
    for segment, sentence in flagged:
        # Verbatim: the operator searches the report and the session files for this exact text.
        text = sentence.text if sentence.text is not None else sentence.raw_text
        reasons = "; ".join(v.kind + (f" ({v.detail})" if v.detail else "") for v in sentence.violations)
        print(f"  [{_segment_name(segment)}] {text}")
        print(f"      → {reasons}")
    found = {kind: n for kind, n in run.totals.items() if n}
    by_kind = ", ".join(f"{kind} {n}" for kind, n in found.items()) or "không có"
    print(f"Lần chạy {run.run_id}: {run.violation_count} vi phạm ({by_kind}) trên {len(run.segments)} phân đoạn")
    if run.error_count:
        print(f"  {run.error_count} phân đoạn lỗi dịch vụ, không được chấm: lần chạy này không tính cho SC-008")
    for warning in run.warnings:
        print(f"  Cảnh báo: {warning}")
    if run.previous is not None and run.delta is not None:
        changed = ", ".join(f"{kind} {d:+d}" for kind, d in run.delta.items() if d) or "không đổi"
        engine_before = f" (engine {run.previous['engine']})" if run.previous.get("engine") else ""
        print(
            f"  So với {run.previous['run_id']}{engine_before}: {run.previous['violation_count']} vi phạm; "
            f"thay đổi: {changed}"
        )
    print(f"  Báo cáo: {md_path}")


def _script(args: argparse.Namespace, settings: Settings, engine: ReplyEngine | None, sleep: Sleep | None) -> int:
    if args.per_combo < 1:
        print("--per-combo phải ≥ 1")
        return EXIT_ERROR
    if args.session is not None and args.per_combo != 1:
        print("Bỏ qua --per-combo: chế độ --session chỉ chấm lại các câu đã nói, không sinh mẫu.")
    catalog = _load_content(args, settings)
    if catalog is None:
        return EXIT_ERROR

    owned = False
    if args.session is not None:
        if args.entry is not None:
            print("Bỏ qua --entry: chế độ --session chỉ chấm lại các câu đã nói, không gọi LLM.")
        print(f"Chấm lại phiên {args.session}, nội dung {catalog.source_name}")
    else:
        # Built here, not in `run_script_check`, so a configuration error is reported before anything runs.
        owned = engine is None
        if engine is None:
            engine = _build_engine(settings, args.entry)
            if engine is None:
                return EXIT_ERROR
        label, model = engine_label_and_model(settings, args.entry)
        print(
            f"Sinh mẫu kịch bản ({args.per_combo} phân đoạn mỗi tổ hợp), engine {label} (model {model}), "
            f"nội dung {catalog.source_name}"
        )

    def check() -> Awaitable[ScriptCheckResult]:
        return run_script_check(
            settings,
            catalog,
            per_combo=args.per_combo,
            session_dir=args.session,
            runs_dir=args.runs_dir,
            engine=engine,
            only=args.entry if args.session is None else None,
            sleep=sleep or asyncio.sleep,
            progress=_print_segment,
        )

    try:
        result = asyncio.run(_in_session(engine, check) if owned and engine is not None else check())
    except ScriptEvalError as exc:
        print(f"Không chấm được phiên: {exc}")
        return EXIT_ERROR
    except GuardConfigError as exc:
        print(f"Lỗi cấu hình guard: {exc}")
        return EXIT_ERROR
    except ReplyEngineError as exc:
        print(f"Lỗi cấu hình LLM ({exc.kind}): {exc}")
        return EXIT_ERROR

    _print_script_run(result.run, result.md_path)
    if result.violation_count:
        print("Kết quả: CÓ VI PHẠM")
        return EXIT_FAILED
    if result.error_count:
        print("Kết quả: CHƯA CHẤM ĐỦ (không có vi phạm nhưng có phân đoạn lỗi dịch vụ)")
        return EXIT_INCOMPLETE
    print("Kết quả: KHÔNG CÓ VI PHẠM")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
