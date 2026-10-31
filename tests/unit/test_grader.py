"""T080: grading the sample question set (US5 #1-#3; FR-023, FR-024; research R13).

Every test builds its own small question set and writes run output to `tmp_path`, so nothing depends on the demo file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.guard import refusal_sentence
from ai_live.core.protocols import ReplyEngineError
from ai_live.products.docx_loader import load_catalog
from ai_live.qa_eval import __main__ as cli
from ai_live.qa_eval.grader import (
    EvalQuestion,
    QuestionSetError,
    grade_answer,
    load_question_set,
    parse_question_set,
)
from ai_live.qa_eval.runner import find_previous_run, run_eval, run_series
from fixtures.content_builder import valid_docx

CATALOG = load_catalog(valid_docx(), "valid.docx", 5_000_000)
# Known amounts in the test catalog: 250.000 / 420.000 (variants), 159.000, 1.250.000, promo 30.000 / 500.000.

PRICE_Q = "Kem chống nắng X giá bao nhiêu vậy shop?"
UNKNOWN_Q = "Kem này trị mụn được không shop?"


def question(
    qid: str = "q01",
    text: str = PRICE_Q,
    required: list[list[str]] | None = None,
    forbidden: list[list[str]] | None = None,
    author: str = "Lan",
) -> EvalQuestion:
    return EvalQuestion(
        id=qid,
        author=author,
        question=text,
        required=tuple(tuple(i) for i in (required or [])),
        forbidden=tuple(tuple(i) for i in (forbidden or [])),
    )


def question_dict(qid: str, text: str, required: list[list[str]], forbidden: list[list[str]] | None = None) -> dict:
    return {"id": qid, "author": "Lan", "question": text, "required": required, "forbidden": forbidden or []}


def ten_questions() -> list[dict]:
    """5 price questions and 5 questions the catalog cannot answer; `FakeReplyEngine()` answers all 10 correctly."""
    price = [
        question_dict(f"q0{i}", f"{PRICE_Q} ({i})", [["250.000", "250 nghìn"], ["420.000"]], [["99.000"]])
        for i in range(1, 6)
    ]
    unknown = [
        question_dict(
            f"q{i:02d}", f"{UNKNOWN_Q} ({i})", [["chưa có thông tin", "hỏi shop"]], [["trị mụn được", "trị được mụn"]]
        )
        for i in range(6, 11)
    ]
    return price + unknown


def write_questions(tmp_path: Path, questions: list[dict], content_version: str | None = None) -> Path:
    path = tmp_path / "questions.json"
    payload = {"content_version": content_version or CATALOG.version, "questions": questions}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class Sleeps:
    """Injected `sleep`: records the waits instead of waiting."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


# ---------- Grading rule (US5 #2, FR-023) ----------


@pytest.mark.parametrize(
    "answer",
    [
        "Dạ phần này em chưa có thông tin ạ.",
        "Da phan nay em CHUA CO THONG TIN a.",  # no diacritics, upper case
        "Dạ bạn Lan hỏi shop giúp em nha.",  # second phrasing of the same idea
        "Dạ em chưa-có thông tin, bạn hỏi... shop nha.",  # punctuation inside a phrase, folded like the guard
    ],
)
def test_required_idea_matches_any_phrasing_ignoring_diacritics(answer):
    grade = grade_answer(question(required=[["chưa có thông tin", "hỏi shop"]]), answer, CATALOG)
    assert grade.passed, grade
    assert grade.missing == []


@pytest.mark.parametrize(
    "answer", ["Dạ loại 100 ml giá 420.000đ ạ.", "Dạ 420k ạ.", "Dạ 420 nghìn ạ.", "Dạ 420000 VND."]
)
def test_money_is_normalized_before_matching(answer):
    grade = grade_answer(question(required=[["420.000"]]), answer, CATALOG)
    assert grade.passed, grade


@pytest.mark.parametrize(
    ("phrase", "answer", "present"),
    [
        # Phrasings with a unit suffix, as in data/eval/*.json, still match by amount.
        ("420.000đ", "Dạ loại 100 ml giá 420 nghìn ạ.", True),
        ("420.000 đ", "Dạ 420.000đ ạ.", True),
        ("420 nghìn đồng", "Dạ 420k ạ.", True),
        # Words beside the amount must be said too.
        ("giảm 30.000đ", "Dạ đơn từ 500.000đ được giảm 30k ạ.", True),
        ("giảm 30.000đ", "Dạ đơn từ 500.000đ được tặng 30.000đ ạ.", False),
        # Numbers that are not money match as words.
        ("2-3 tiếng", "Dạ bôi lại sau 2 - 3 tiếng nha.", True),
        ("4 tiếng", "Dạ bôi lại sau 24 tiếng nha.", False),
    ],
)
def test_phrasing_forms(phrase, answer, present):
    grade = grade_answer(question(required=[[phrase]]), answer, CATALOG)
    assert grade.passed is present, grade


def test_money_inside_a_larger_amount_does_not_count():
    # "1.250.000" must not satisfy "250.000" just because the digits appear in it.
    grade = grade_answer(question(required=[["250.000"]]), "Dạ Toner Z giá 1.250.000đ ạ.", CATALOG)
    assert not grade.passed
    assert grade.missing == ["250.000"]


def test_phrase_matches_whole_words_only():
    grade = grade_answer(question(required=[["hỏi shop"]]), "Dạ bạn hỏi shopee nha.", CATALOG)
    assert not grade.passed


def test_missing_required_idea_fails_and_names_it():
    q = question(required=[["250.000"], ["420.000", "420 nghìn"]])
    grade = grade_answer(q, "Dạ loại 50 ml giá 250.000đ ạ.", CATALOG)
    assert not grade.passed
    # The idea is named by its first phrasing.
    assert grade.missing == ["420.000"]
    assert grade.found_forbidden == []


@pytest.mark.parametrize(
    "answer",
    ["Dạ kem này trị mụn được nha.", "Da kem nay TRI DUOC MUN nha.", "Dạ trị-mụn, được nha."],
)
def test_forbidden_idea_fails_and_names_it(answer):
    q = question(text=UNKNOWN_Q, required=[["chưa có thông tin"]], forbidden=[["trị mụn được", "trị được mụn"]])
    grade = grade_answer(q, f"Dạ em chưa có thông tin. {answer}", CATALOG)
    assert not grade.passed
    assert grade.found_forbidden == ["trị mụn được"]
    assert grade.missing == []


def test_forbidden_money_matches_any_written_form():
    q = question(forbidden=[["99.000"]])
    grade = grade_answer(q, "Dạ giá 99k ạ.", CATALOG)
    assert not grade.passed
    assert "99.000" in grade.found_forbidden


def test_unknown_amount_is_an_automatic_forbidden_idea():
    # No forbidden idea is listed, yet an amount outside the catalog still fails the question.
    grade = grade_answer(question(required=[["250.000"]]), "Dạ loại 50 ml giá 250.000đ, đang giảm còn 199k ạ.", CATALOG)
    assert not grade.passed
    assert len(grade.found_forbidden) == 1
    assert "199.000" in grade.found_forbidden[0]
    assert "không có trong dữ liệu" in grade.found_forbidden[0]


def test_known_amounts_pass():
    q = question(required=[["250.000"], ["420.000"]])
    grade = grade_answer(q, "Dạ loại 50 ml 250.000đ, loại 100 ml 420.000đ, đơn từ 500.000đ giảm 30k ạ.", CATALOG)
    assert grade.passed, grade


def test_question_with_no_required_idea_only_checks_forbidden():
    q = question(forbidden=[["trị mụn được"]])
    assert grade_answer(q, "Dạ em chưa rõ ạ.", CATALOG).passed


# ---------- Question file (contracts/content-template.md §2) ----------


def test_load_question_set(tmp_path):
    path = write_questions(tmp_path, ten_questions(), content_version="abc")
    qs = load_question_set(path)
    assert qs.content_version == "abc"
    assert len(qs.questions) == 10
    assert qs.questions[0].required[0] == ("250.000", "250 nghìn")


def test_invalid_question_set_lists_every_issue():
    data = {
        "questions": [
            {"id": "q01", "question": "", "required": [["a"]], "forbidden": []},
            {"id": "q01", "question": "giá?", "required": "250.000", "forbidden": []},
            {"question": "x", "required": [[]], "forbidden": [["b"]]},
        ]
    }
    with pytest.raises(QuestionSetError) as exc:
        parse_question_set(data)
    assert len(exc.value.issues) >= 4  # empty question, duplicate id, bad required, missing id, empty idea


# ---------- Runner (US5 #1, #3; FR-024) ----------


async def _series(tmp_path, engine, questions_path, repeat=1, **kwargs):
    return await run_series(
        engine,
        CATALOG,
        load_question_set(questions_path),
        questions_file=questions_path,
        engine_label="fake",
        runs_dir=tmp_path / "runs",
        repeat=repeat,
        sleep=Sleeps(),
        **kwargs,
    )


@pytest.mark.anyio
async def test_run_writes_json_and_markdown_report(tmp_path):
    path = write_questions(tmp_path, ten_questions())
    series = await _series(tmp_path, FakeReplyEngine(), path)

    run = series.runs[0]
    assert run.score == 10 and run.total == 10
    json_path = tmp_path / "runs" / f"{run.run_id}.json"
    md_path = tmp_path / "runs" / f"{run.run_id}.md"
    assert json_path.is_file() and md_path.is_file()

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["score"] == 10
    assert saved["content_version"] == CATALOG.version
    assert saved["previous_run_id"] is None
    first = saved["results"][0]
    assert first["question_id"] == "q01"
    assert "250.000đ" in first["answer"]
    assert first["passed"] is True
    assert {"missing", "found_forbidden", "guard_reason", "first_sentence_s"} <= first.keys()

    md = md_path.read_text(encoding="utf-8")
    assert "Chấm tay" in md
    assert "10/10" in md
    assert PRICE_Q in md  # each question, with the host answer
    assert "250.000đ" in md


@pytest.mark.anyio
async def test_report_names_the_reason_of_a_wrong_answer(tmp_path):
    questions = [question_dict("q01", PRICE_Q, [["250.000"], ["999 nghìn tỷ"]], [["420.000"]])]
    path = write_questions(tmp_path, questions)
    series = await _series(tmp_path, FakeReplyEngine(), path)

    result = series.runs[0].results[0]
    assert not result.passed
    assert result.missing == ["999 nghìn tỷ"]
    assert result.found_forbidden == ["420.000"]
    md = (tmp_path / "runs" / f"{series.runs[0].run_id}.md").read_text(encoding="utf-8")
    assert "999 nghìn tỷ" in md and "420.000" in md
    assert "0/1" in md


@pytest.mark.anyio
async def test_answer_is_what_the_host_says_after_the_guard(tmp_path):
    # The second sentence carries an invented amount: the host stops there and says the refusal sentence instead.
    engine = FakeReplyEngine("Dạ loại 50 ml giá 250.000đ ạ. Hôm nay giảm còn 199.000đ nha. Chốt đơn đi ạ.")
    path = write_questions(tmp_path, [question_dict("q01", PRICE_Q, [["250.000"]])])
    series = await _series(tmp_path, engine, path)

    result = series.runs[0].results[0]
    assert result.guard_reason == "unknown_amount"
    assert "199.000" not in result.answer
    assert "Chốt đơn" not in result.answer
    assert result.answer.endswith(refusal_sentence("bạn Lan"))
    assert result.passed


@pytest.mark.anyio
async def test_second_run_compares_score_and_lists_changed_questions(tmp_path):
    answers = {f"{PRICE_Q} ({i})": "Dạ loại 50 ml 250.000đ, loại 100 ml 420.000đ ạ." for i in range(1, 6)}
    answers |= {f"{UNKNOWN_Q} ({i})": "Dạ phần này em chưa có thông tin ạ." for i in range(6, 11)}
    engine = FakeReplyEngine(lambda comment, _catalog: answers[comment.text])
    path = write_questions(tmp_path, ten_questions())

    first = (await _series(tmp_path, engine, path)).runs[0]
    assert first.score == 10

    answers[f"{UNKNOWN_Q} (7)"] = "Dạ kem này trị mụn được nha."
    answers[f"{PRICE_Q} (2)"] = "Dạ loại 50 ml 250.000đ ạ."
    second = (await _series(tmp_path, engine, path)).runs[0]

    assert second.score == 8
    assert second.previous_run_id == first.run_id
    assert second.previous_score == 10
    assert sorted((d["id"], d["before"], d["after"]) for d in second.diff) == [
        ("q02", True, False),
        ("q07", True, False),
    ]
    md = (tmp_path / "runs" / f"{second.run_id}.md").read_text(encoding="utf-8")
    assert "So sánh" in md
    assert first.run_id in md
    assert "10/10" in md and "8/10" in md
    assert "q02" in md and "q07" in md


@pytest.mark.anyio
async def test_comparison_only_uses_runs_of_the_same_question_file(tmp_path):
    path = write_questions(tmp_path, ten_questions())
    other = tmp_path / "other"
    other.mkdir()
    other_path = write_questions(other, ten_questions()[:3])
    await _series(tmp_path, FakeReplyEngine(), other_path)

    run = (await _series(tmp_path, FakeReplyEngine(), path)).runs[0]
    assert run.previous_run_id is None
    assert find_previous_run(tmp_path / "runs", path).run_id == run.run_id


@pytest.mark.anyio
async def test_repeat_passes_only_when_every_run_reaches_8_of_10(tmp_path):
    answers = {f"{PRICE_Q} ({i})": "Dạ loại 50 ml 250.000đ, loại 100 ml 420.000đ ạ." for i in range(1, 6)}
    answers |= {f"{UNKNOWN_Q} ({i})": "Dạ phần này em chưa có thông tin ạ." for i in range(6, 11)}
    calls = 0

    def answer(comment, _catalog):
        nonlocal calls
        calls += 1
        # Run 2 (calls 11-20) gets 3 questions wrong: 7/10.
        if 11 <= calls <= 13:
            return "Dạ em không biết ạ."
        return answers[comment.text]

    path = write_questions(tmp_path, ten_questions())
    series = await _series(tmp_path, FakeReplyEngine(answer), path, repeat=3)
    assert [r.score for r in series.runs] == [10, 7, 10]
    assert series.threshold == 8
    assert not series.passed


@pytest.mark.anyio
async def test_unreadable_previous_run_is_skipped(tmp_path):
    path = write_questions(tmp_path, ten_questions())
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "broken.json").write_text("{not json", encoding="utf-8")
    series = await _series(tmp_path, FakeReplyEngine(), path)
    assert series.runs[0].previous_run_id is None


@pytest.mark.anyio
async def test_content_version_mismatch_is_a_warning_not_an_error(tmp_path):
    path = write_questions(tmp_path, ten_questions(), content_version="000000000000")
    series = await _series(tmp_path, FakeReplyEngine(), path)
    run = series.runs[0]
    assert run.score == 10
    assert any("000000000000" in w for w in run.warnings)
    md = (tmp_path / "runs" / f"{run.run_id}.md").read_text(encoding="utf-8")
    assert "000000000000" in md


# ---------- Pacing and 429 backoff (R13) ----------


class RateLimitedThenFake:
    """Raises `rate_limited` for the first `failures` calls, then answers like `FakeReplyEngine()`."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0
        self._fake = FakeReplyEngine()

    async def reply(self, comment, catalog):
        self.calls += 1
        if self.calls <= self.failures:
            raise ReplyEngineError("rate_limited", "Gemini lỗi HTTP 429")
        async for sentence in self._fake.reply(comment, catalog):
            yield sentence


@pytest.mark.anyio
async def test_429_backs_off_and_retries_without_real_waiting(tmp_path):
    path = write_questions(tmp_path, ten_questions()[:2])
    sleeps = Sleeps()
    engine = RateLimitedThenFake(failures=2)
    run = await run_eval(
        engine,
        CATALOG,
        load_question_set(path),
        questions_file=path,
        engine_label="fake",
        pace_s=4.0,
        backoff_s=10.0,
        max_retries=3,
        sleep=sleeps,
    )
    assert run.score == 2
    assert engine.calls == 4
    # Two growing backoffs for the first question, then the pacing gap before the second question.
    assert sleeps.calls == [10.0, 20.0, 4.0]


@pytest.mark.anyio
async def test_429_after_max_retries_fails_only_that_question(tmp_path):
    path = write_questions(tmp_path, ten_questions()[:2])
    engine = RateLimitedThenFake(failures=3)
    run = await run_eval(
        engine,
        CATALOG,
        load_question_set(path),
        questions_file=path,
        engine_label="fake",
        backoff_s=1.0,
        max_retries=2,
        sleep=Sleeps(),
    )
    first, second = run.results
    assert not first.passed
    assert first.error is not None and "rate_limited" in first.error
    assert second.passed
    assert run.score == 1


@pytest.mark.anyio
async def test_other_engine_error_fails_the_question_without_retry(tmp_path):
    path = write_questions(tmp_path, ten_questions()[:1])
    sleeps = Sleeps()
    engine = FakeReplyEngine(error=ReplyEngineError("provider_blocked", "Gemini chặn"))
    run = await run_eval(
        engine, CATALOG, load_question_set(path), questions_file=path, engine_label="fake", sleep=sleeps
    )
    assert not run.results[0].passed
    assert "provider_blocked" in (run.results[0].error or "")
    assert sleeps.calls == []


# ---------- CLI (T085) ----------


@pytest.fixture
def content_file(tmp_path) -> Path:
    path = tmp_path / "valid.docx"
    path.write_bytes(valid_docx())
    return path


def test_cli_repeat_3_reports_pass(tmp_path, settings, content_file, capsys):
    path = write_questions(tmp_path, ten_questions())
    runs_dir = tmp_path / "runs"
    code = cli.main(
        ["run", "--content", str(content_file), "--questions", str(path), "--repeat", "3", "--runs-dir", str(runs_dir)],
        settings=settings,
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert len(list(runs_dir.glob("*.json"))) == 3
    assert len(list(runs_dir.glob("*.md"))) == 3
    assert "ĐẠT" in out
    assert "3/3" in out


def test_cli_repeat_reports_fail_when_a_run_is_below_8(tmp_path, settings, content_file, capsys):
    questions = ten_questions()
    for q in questions[:3]:
        q["required"].append(["không bao giờ có cụm này"])
    path = write_questions(tmp_path, questions)
    code = cli.main(
        [
            "run",
            "--content",
            str(content_file),
            "--questions",
            str(path),
            "--repeat",
            "3",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
        settings=settings,
    )
    out = capsys.readouterr().out
    assert code == 2, out
    assert "CHƯA ĐẠT" in out


def test_cli_bad_question_file_exits_1(tmp_path, settings, content_file, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{}", encoding="utf-8")
    code = cli.main(["run", "--content", str(content_file), "--questions", str(path)], settings=settings)
    assert code == 1
    assert "bad.json" in capsys.readouterr().out
