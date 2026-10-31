"""Grade the sample question set (research R13; FR-023, FR-024).

    uv run python -m ai_live.qa_eval run --content data/products/demo.docx \\
        --questions data/eval/demo_questions.json [--repeat 3] [--runs-dir data/eval/runs]

Uses the `ReplyEngine` chosen by `REPLY_ENGINE` and the live `OutputGuard`, without TTS or the renderer. Each run is
saved as `<runs-dir>/<ts>.json` and `.md` and compared with the latest run of the same question file.
Exit code: 0 when every run reaches the threshold (SC-008), 2 when a run is below it, 1 on a content, question-file
or configuration error.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from ai_live.brain.factory import create_reply_engine
from ai_live.core.config import Settings
from ai_live.core.protocols import ReplyEngine, ReplyEngineError
from ai_live.products.docx_loader import load_catalog_file
from ai_live.products.models import ContentLoadError
from ai_live.qa_eval.grader import QuestionSetError, load_question_set
from ai_live.qa_eval.runner import DEFAULT_RUNS_DIR, GEMINI_PACE_S, EvalResult, EvalRun, Sleep, run_series


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
    return parser


def _print_result(result: EvalResult) -> None:
    verdict = "ĐÚNG" if result.passed else "SAI "
    detail = result.error or "; ".join(
        [*(f"thiếu “{m}”" for m in result.missing), *(f"có ý cấm “{f}”" for f in result.found_forbidden)]
    )
    print(f"  {result.question_id} {verdict} {detail}".rstrip())


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
    if args.repeat < 1:
        print("--repeat phải ≥ 1")
        return 1

    settings = settings or Settings()
    content: Path = args.content or settings.product_data_path
    if not content.is_file():
        print(f"Không tìm thấy file nội dung: {content}")
        return 1
    try:
        catalog = load_catalog_file(content, settings.content_max_bytes)
    except ContentLoadError as exc:
        print(f"File '{content.name}' có {len(exc.issues)} lỗi:")
        for issue in exc.issues:
            print(f"  - [{issue.code}] {issue.message}")
        return 1
    try:
        question_set = load_question_set(args.questions)
    except QuestionSetError as exc:
        print(f"File câu hỏi '{args.questions}' có {len(exc.issues)} lỗi:")
        for issue in exc.issues:
            print(f"  - {issue}")
        return 1

    try:
        engine = engine or create_reply_engine(settings)
    except ReplyEngineError as exc:
        print(f"Lỗi cấu hình LLM ({exc.kind}): {exc}")
        return 1
    label = "fake" if settings.reply_engine == "fake" else settings.llm_model
    pace = args.pace if args.pace is not None else (0.0 if settings.reply_engine == "fake" else GEMINI_PACE_S)

    def on_run(run: EvalRun, md_path: Path) -> None:
        print(
            f"Lần chạy {run.run_id}: {run.score}/{run.total} (ngưỡng {run.threshold}/{run.total}). Báo cáo: {md_path}"
        )
        for warning in run.warnings:
            print(f"  Cảnh báo: {warning}")
        if run.previous_run_id is not None:
            changed = ", ".join(d["id"] for d in run.diff) or "không có"
            print(
                f"  So với {run.previous_run_id}: {run.previous_score}/{run.previous_total}; câu đổi kết quả: {changed}"
            )

    print(f"Chấm {len(question_set.questions)} câu × {args.repeat} lần, engine {label}, nội dung {catalog.source_name}")
    series = asyncio.run(
        run_series(
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
        )
    )
    reached = sum(r.reached_threshold for r in series.runs)
    total = len(question_set.questions)
    verdict = "ĐẠT" if series.passed else "CHƯA ĐẠT"
    print(f"Kết quả: {verdict}, {reached}/{len(series.runs)} lần ≥ {series.threshold}/{total} (SC-008 cần mọi lần đạt)")
    return 0 if series.passed else 2


if __name__ == "__main__":
    sys.exit(main())
