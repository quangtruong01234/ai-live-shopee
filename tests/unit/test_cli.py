"""T039, T063 (001), T022, T056 (004), T058, T048 (008): run each stage on its own from the CLI (Article IV)."""

from __future__ import annotations

import json
import re
import wave
from pathlib import Path
from typing import Any

import pytest

from ai_live.brain import __main__ as brain_cli
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.comments import __main__ as comments_cli
from ai_live.core.config import Settings
from ai_live.core.models import Topic
from ai_live.core.protocols import TTSEngineError
from ai_live.products.docx_loader import load_catalog_file
from ai_live.qa_eval import __main__ as qa_eval_cli
from ai_live.tts import __main__ as tts_cli
from ai_live.tts.factory import load_normalizer
from ai_live.tts.speech import SpeechTTS
from fixtures.content_builder import SPARSE_PRODUCT_NAME, sparse_docx, valid_docx
from fixtures.fake_openai import (
    CHAT_PATH,
    MODELS_PATH,
    FakeOpenAI,
    ModelRow,
    build_chain_engine,
    http_error,
    models_connect_error,
    models_error,
    models_list,
    stream_reply,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLATFORM_PHRASES = _REPO_ROOT / "data" / "rules" / "platform_phrases.txt"
_CLAIM_PHRASES = _PLATFORM_PHRASES.with_name("claim_phrases.txt")


@pytest.fixture
def content(tmp_path):
    path = tmp_path / "valid.docx"
    path.write_bytes(valid_docx())
    return path


@pytest.fixture
def sparse_content(tmp_path):
    path = tmp_path / "sparse.docx"
    path.write_bytes(sparse_docx())
    return path


@pytest.fixture
def fake_env(monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE", "fake")
    monkeypatch.setenv("TTS_PROVIDER", "fake")
    # Absolute path: the default is relative to the cwd, and the brain CLI loads this file from 004 T026 on.
    monkeypatch.setenv("PLATFORM_PHRASES_PATH", str(_PLATFORM_PHRASES))
    monkeypatch.setenv("CLAIM_PHRASES_PATH", str(_CLAIM_PHRASES))


def _product_ids(path: Path) -> dict[str, str]:
    """Product name -> id, as the loader derives it, so the tests do not hardcode the slug rule."""
    # Explicit engine and no `.env`: the helper only needs the size limit, never the default engine (chain since 008).
    settings = Settings(_env_file=None, reply_engine="fake")
    catalog = load_catalog_file(path, settings.content_max_bytes)
    return {p.name: p.id for p in catalog.products}


def _run(cli, argv: list[str], **kwargs: Any) -> int:
    # argparse exits with SystemExit on a usage error; report it as an exit code like `main()`'s return value.
    try:
        return cli.main(argv, **kwargs)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


_TIMED_LINE = re.compile(r"^\[\s*\d+\.\d{2} s\] .+")


def test_brain_ask_prints_each_sentence_with_time(fake_env, content, capsys):
    code = brain_cli.main(["ask", "giá bao nhiêu vậy shop?", "--author", "Lan", "--content", str(content)])
    out = capsys.readouterr().out
    assert code == 0
    lines = [line for line in out.splitlines() if _TIMED_LINE.match(line)]
    assert lines, out
    joined = " ".join(lines)
    assert "bạn Lan" in joined
    assert "250.000đ" in joined and "420.000đ" in joined


def test_brain_ask_prints_guard_reason_when_blocked(fake_env, content, capsys, monkeypatch):
    def fake_factory(settings):
        return FakeReplyEngine("Dạ kem này chữa khỏi mụn luôn nha bạn Lan. Giá chỉ 99k thôi.")

    monkeypatch.setattr(brain_cli, "create_reply_engine", fake_factory)
    code = brain_cli.main(["ask", "kem có trị mụn không?", "--author", "Lan", "--content", str(content)])
    out = capsys.readouterr().out
    assert code == 0
    assert "forbidden_claim" in out
    assert "Dạ phần này em chưa có thông tin, bạn Lan nhắn shop giúp em nha." in out
    # A block stops generation: later sentences must not be printed.
    assert "99k" not in out


def test_brain_ask_missing_content_file_exits_1(fake_env, tmp_path, capsys):
    code = brain_cli.main(["ask", "giá?", "--content", str(tmp_path / "missing.docx")])
    assert code == 1


# 004 T022: `python -m ai_live.brain narrate --product ID --topic T` runs the script stage alone (Article IV).

_TIME_PREFIX = re.compile(r"^\[\s*\d+\.\d{2} s\]\s*")
_VIETNAMESE_LETTER = re.compile(r"[à-ỹÀ-Ỹđ]")


def _narrate_argv(product_id: str, topic: Topic, content: Path) -> list[str]:
    return ["narrate", "--product", product_id, "--topic", topic.value, "--content", str(content)]


@pytest.mark.parametrize("topic", [Topic.INTRO, Topic.PRICE, Topic.PROMOTION])
def test_brain_narrate_prints_each_sentence(fake_env, content, capsys, topic):
    product_id = _product_ids(content)["Kem chống nắng X"]
    code = _run(brain_cli, _narrate_argv(product_id, topic, content))
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert lines, captured.out
    # A time prefix like `ask` prints is allowed; the sentence after it must not be empty.
    assert all(_TIME_PREFIX.sub("", line).strip() for line in lines), captured.out


def test_brain_narrate_prints_scripted_sentences_in_order(fake_env, content, capsys, monkeypatch):
    product_id = _product_ids(content)["Kem chống nắng X"]
    sentences = (
        "Dạ cả nhà ơi, em nói về khuyến mãi của kem chống nắng nha.",
        "Đơn đủ điều kiện là được giảm giá liền ạ.",
        "Cả nhà cần hỏi thêm thì nhắn shop giúp em nha.",
    )
    engine = FakeReplyEngine(script={(product_id, Topic.PROMOTION): sentences})
    monkeypatch.setattr(brain_cli, "create_reply_engine", lambda settings: engine)
    code = _run(brain_cli, _narrate_argv(product_id, Topic.PROMOTION, content))
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    printed = [_TIME_PREFIX.sub("", line).strip() for line in captured.out.splitlines()]
    # Each sentence on its own line, in the order the engine yielded them.
    positions = [printed.index(s) for s in sentences if s in printed]
    assert len(positions) == len(sentences), captured.out
    assert positions == sorted(positions), captured.out
    assert [(r.product_id, r.topic) for r in engine.narrate_requests] == [(product_id, Topic.PROMOTION)]


@pytest.mark.parametrize("topic", [Topic.PROMOTION, Topic.SPECS, Topic.FAQ])
def test_brain_narrate_topic_without_data_exits_nonzero_with_vietnamese_message(
    fake_env, sparse_content, capsys, monkeypatch, topic
):
    # Research R5: the sparse product has no promotions, specs or FAQ. `price` always has data in a valid file.
    product_id = _product_ids(sparse_content)[SPARSE_PRODUCT_NAME]
    engine = FakeReplyEngine()
    monkeypatch.setattr(brain_cli, "create_reply_engine", lambda settings: engine)
    code = _run(brain_cli, _narrate_argv(product_id, topic, sparse_content))
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code != 0, message
    assert "dữ liệu" in message.lower(), message
    # Nothing to ground the segment in, so the LLM must not be called (data-model §5 SegmentRequest check).
    assert engine.narrate_requests == []


def test_brain_narrate_unknown_product_exits_nonzero_with_vietnamese_message(fake_env, content, capsys, monkeypatch):
    engine = FakeReplyEngine()
    monkeypatch.setattr(brain_cli, "create_reply_engine", lambda settings: engine)
    code = _run(brain_cli, _narrate_argv("khong-co-san-pham-nay", Topic.INTRO, content))
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code != 0, message
    assert _VIETNAMESE_LETTER.search(message), message
    assert engine.narrate_requests == []


# 008 T058: with REPLY_ENGINE=chain the brain CLI checks the chain (`preflight()`, one `GET /models`) before the first
# turn, refuses to call `/chat/completions` when that check fails, and always closes the engine (FR-011, US1 #6).
# The CLI builds its engine with `create_reply_engine(settings)`; the patch returns a real `ChainReplyEngine` built from
# those same settings, on the fake provider instead of the network.

_CHAIN_BASE = "http://127.0.0.1:3001/v1"
_CHAIN_MODEL = "gpt-oss-120b"
_CHAIN_LABEL = "gptoss"
_CHAIN_ROUTED_VIA = "groq/openai/gpt-oss-120b"
_CHAIN_KEY = "freellmapi-CLI-SECRET-7f3a9c0d"
_CHAIN_ENTRY = {
    "label": _CHAIN_LABEL,
    "base_url": _CHAIN_BASE,
    "model": _CHAIN_MODEL,
    "key_env": "FREELLMAPI_KEY",
    "platform": "groq",
    "first_sentence_timeout_s": 2.0,
}
_ASK_SENTENCES = ("Dạ chào bạn Lan nha.", "Kem 50 ml giá 250.000đ, loại 100 ml giá 420.000đ ạ!")
_NARRATE_SENTENCES = (
    "Dạ cả nhà ơi, hôm nay em giới thiệu kem chống nắng nha.",
    "Bản 50 ml giá 250.000đ, bản 100 ml giá 420.000đ ạ.",
)


class _ChainCli:
    """The fake provider plus a record of the engine calls the CLI makes, in order."""

    def __init__(self) -> None:
        self.fake = FakeOpenAI()
        self.calls: list[str] = []


def _spy_chain_engine(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    """Record `preflight`, `reply`, `narrate` and `aclose` calls on every `ChainReplyEngine`, in order.

    Spies on the class, not the instance, so they work whatever the class layout; each calls the real method.
    """
    from ai_live.brain.chain_engine import ChainReplyEngine

    real_preflight, real_reply = ChainReplyEngine.preflight, ChainReplyEngine.reply
    real_narrate, real_aclose = ChainReplyEngine.narrate, ChainReplyEngine.aclose

    async def preflight(self):
        calls.append("preflight")
        return await real_preflight(self)

    def reply(self, *args, **kwargs):
        calls.append("reply")
        return real_reply(self, *args, **kwargs)

    def narrate(self, *args, **kwargs):
        calls.append("narrate")
        return real_narrate(self, *args, **kwargs)

    async def aclose(self):
        calls.append("aclose")
        return await real_aclose(self)

    for name, spy in (("preflight", preflight), ("reply", reply), ("narrate", narrate), ("aclose", aclose)):
        monkeypatch.setattr(ChainReplyEngine, name, spy)


@pytest.fixture
def chain_cli(monkeypatch) -> _ChainCli:
    from ai_live.brain.chain_engine import ChainReplyEngine

    monkeypatch.setenv("REPLY_ENGINE", "chain")
    monkeypatch.setenv("TTS_PROVIDER", "fake")
    monkeypatch.setenv("PLATFORM_PHRASES_PATH", str(_PLATFORM_PHRASES))
    monkeypatch.setenv("CLAIM_PHRASES_PATH", str(_CLAIM_PHRASES))
    monkeypatch.setenv("LLM_CHAIN", json.dumps([_CHAIN_ENTRY]))
    monkeypatch.setenv("FREELLMAPI_KEY", _CHAIN_KEY)
    cli = _ChainCli()

    def factory(settings: Settings, **_: Any) -> ChainReplyEngine:
        assert settings.reply_engine == "chain"
        assert settings.freellmapi_key is not None
        return build_chain_engine(
            cli.fake,
            *settings.llm_chain,
            keys={"FREELLMAPI_KEY": settings.freellmapi_key.get_secret_value()},
            cooldown_s=settings.llm_chain_cooldown_s,
            max_tokens=settings.llm_max_tokens,
            script_max_tokens=settings.script_max_tokens,
        )

    monkeypatch.setattr(brain_cli, "create_reply_engine", factory)
    _spy_chain_engine(monkeypatch, cli.calls)
    return cli


def _chain_argv(command: str, content: Path) -> list[str]:
    if command == "ask":
        return ["ask", "giá bao nhiêu vậy shop?", "--author", "Lan", "--content", str(content)]
    return _narrate_argv(_product_ids(content)["Kem chống nắng X"], Topic.INTRO, content)


def _turn(command: str) -> str:
    return "reply" if command == "ask" else "narrate"


@pytest.mark.parametrize("command", ["ask", "narrate"])
def test_brain_chain_runs_preflight_before_first_turn_and_closes(chain_cli, content, capsys, command):
    sentences = _ASK_SENTENCES if command == "ask" else _NARRATE_SENTENCES
    chain_cli.fake.models(_CHAIN_BASE, models_list(ModelRow(_CHAIN_MODEL, available=True)))
    chain_cli.fake.chat(
        _CHAIN_BASE, _CHAIN_MODEL, stream_reply(*(s + " " for s in sentences), routed_via=_CHAIN_ROUTED_VIA)
    )

    code = _run(brain_cli, _chain_argv(command, content))
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err

    calls = chain_cli.calls
    assert calls.count("preflight") == 1, calls
    assert _turn(command) in calls, calls
    assert calls.index("preflight") < calls.index(_turn(command)), calls
    assert calls[-1] == "aclose", calls
    # On the wire too: the one model check goes out before the first chat request.
    paths = [r.path for r in chain_cli.fake.requests]
    assert paths == [MODELS_PATH, CHAT_PATH], paths
    assert chain_cli.fake.unscripted == []
    printed = [_TIME_PREFIX.sub("", line).strip() for line in captured.out.splitlines()]
    assert all(s in printed for s in sentences), captured.out


_PREFLIGHT_FAILURES = [
    # (id, GET /models answer, text the message must contain to name the problem)
    ("auth", models_error(401, message=f"invalid api key {_CHAIN_KEY}"), "401"),
    ("unreachable", models_connect_error(), "127.0.0.1:3001"),
    ("model_missing", models_list("gemma-sea-lion-v4-27b"), _CHAIN_MODEL),
]


@pytest.mark.parametrize("command", ["ask", "narrate"])
@pytest.mark.parametrize(
    ("listing", "detail"), [f[1:] for f in _PREFLIGHT_FAILURES], ids=[f[0] for f in _PREFLIGHT_FAILURES]
)
def test_brain_chain_preflight_failure_exits_1_without_chat_call(chain_cli, content, capsys, command, listing, detail):
    chain_cli.fake.models(_CHAIN_BASE, listing)
    # Scripted so that a turn started by mistake would succeed: only the absence of chat requests proves it was skipped.
    chain_cli.fake.chat(_CHAIN_BASE, _CHAIN_MODEL, stream_reply("Dạ chào bạn Lan nha. ", routed_via=_CHAIN_ROUTED_VIA))

    code = _run(brain_cli, _chain_argv(command, content))
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code == 1, message
    assert chain_cli.fake.chat_requests() == [], "no /chat/completions call after a failed preflight"
    assert _turn(command) not in chain_cli.calls, chain_cli.calls
    assert "aclose" in chain_cli.calls, "aclose() must run even when preflight fails"
    # Vietnamese, names the failing entry and the problem, never the key (contracts/config.md §4).
    assert _VIETNAMESE_LETTER.search(message), message
    assert _CHAIN_LABEL in message, message
    assert detail in message, message
    assert _CHAIN_KEY not in message, message


@pytest.mark.parametrize("command", ["ask", "narrate"])
def test_brain_chain_turn_error_exits_1_and_still_closes(chain_cli, content, capsys, command):
    chain_cli.fake.models(_CHAIN_BASE, models_list(ModelRow(_CHAIN_MODEL, available=True)))
    # The only entry fails before its first sentence, so the turn ends with the chain exhausted (research R7).
    chain_cli.fake.chat(_CHAIN_BASE, _CHAIN_MODEL, http_error(500, message=f"upstream rejected {_CHAIN_KEY}"))

    code = _run(brain_cli, _chain_argv(command, content))
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code == 1, message
    assert chain_cli.calls[:1] == ["preflight"], chain_cli.calls
    assert chain_cli.calls[-1] == "aclose", chain_cli.calls
    assert _CHAIN_KEY not in message, message


# 008 T048: `python -m ai_live.qa_eval run [--entry LABEL]` evaluates the whole chain or one pinned entry (US4, FR-021,
# FR-022, data-model §8, contracts/adapters.md §6, research R10). The CLI builds its engine with
# `create_reply_engine(settings, only=LABEL)`; the patch builds the real `ChainReplyEngine.from_settings()` from those
# same arguments on the fake provider, so the one-entry chain (`only`, cooldown 0) is the production one.

_SEALION_MODEL = "gemma-sea-lion-v4-27b"
_SEALION_ROUTED_VIA = "cloudflare/@cf/aisingapore/gemma-sea-lion-v4-27b-it"
_SEALION_ENTRY = {
    "label": "sealion",
    "base_url": _CHAIN_BASE,
    "model": _SEALION_MODEL,
    "key_env": "FREELLMAPI_KEY",
    "platform": "cloudflare",
    "first_sentence_timeout_s": 3.5,
}
# Grounded in `valid_docx()` (Kem chống nắng X: 250.000đ / 420.000đ), so every question below grades as right.
_PRICE_ANSWER = "Dạ kem 50 ml giá 250.000đ, loại 100 ml giá 420.000đ ạ!"
_EVAL_QUESTIONS = [
    {
        "id": "q01",
        "author": "Lan",
        "question": "Kem chống nắng X giá bao nhiêu vậy shop?",
        "required": [["250.000", "250k"], ["420.000", "420k"]],
    },
    {
        "id": "q02",
        "author": "Minh",
        "question": "Chai 100 ml giá nhiêu shop?",
        "required": [["420.000", "420k"]],
    },
]


class _QaChain:
    """The fake provider, the settings the CLI gets, the `only` values it asked for and the engine calls, in order."""

    def __init__(self, settings: Settings) -> None:
        self.fake = FakeOpenAI()
        self.settings = settings
        self.only: list[str | None] = []
        self.calls: list[str] = []

    def models_ok(self) -> None:
        self.fake.models(
            _CHAIN_BASE,
            models_list(ModelRow(_SEALION_MODEL, available=True), ModelRow(_CHAIN_MODEL, available=True)),
        )


@pytest.fixture
def qa_chain(monkeypatch, tmp_path) -> _QaChain:
    from ai_live.brain import factory as brain_factory
    from ai_live.brain.chain_engine import ChainReplyEngine

    # Explicit settings and no `.env`: two entries on the loopback gateway, in chain order sealion -> gptoss.
    settings = Settings(
        _env_file=None,
        reply_engine="chain",
        tts_provider="fake",
        avatar_mode="static",
        llm_chain=[_SEALION_ENTRY, _CHAIN_ENTRY],
        freellmapi_key=_CHAIN_KEY,
        platform_phrases_path=_PLATFORM_PHRASES,
        claim_phrases_path=_CLAIM_PHRASES,
        session_data_dir=tmp_path / "sessions",
    )
    qa = _QaChain(settings)
    real_factory = brain_factory.create_reply_engine

    def factory(settings: Settings, *, only: str | None = None, fault_hook: Any = None) -> Any:
        qa.only.append(only)
        if settings.reply_engine != "chain":
            return real_factory(settings, only=only, fault_hook=fault_hook)
        return ChainReplyEngine.from_settings(settings, only=only, fault_hook=fault_hook, transport=qa.fake.transport)

    monkeypatch.setattr(qa_eval_cli, "create_reply_engine", factory)
    _spy_chain_engine(monkeypatch, qa.calls)
    return qa


async def _no_sleep(_: float) -> None:
    return None


def _questions_file(tmp_path: Path) -> Path:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps({"questions": _EVAL_QUESTIONS}, ensure_ascii=False), encoding="utf-8")
    return path


def _qa_run(qa: _QaChain, content: Path, tmp_path: Path, *extra: str, settings: Settings | None = None) -> int:
    """`qa_eval run` on the two-question set, results in `tmp_path/runs`; `sleep` is a no-op (no real pacing)."""
    argv = [
        "run",
        "--content",
        str(content),
        "--questions",
        str(_questions_file(tmp_path)),
        "--runs-dir",
        str(tmp_path / "runs"),
        *extra,
    ]
    return _run(qa_eval_cli, argv, settings=settings or qa.settings, sleep=_no_sleep)


def _saved_runs(tmp_path: Path) -> list[tuple[dict[str, Any], Path]]:
    """Every saved run as (JSON, path of its `.md` report), oldest first."""
    runs_dir = tmp_path / "runs"
    if not runs_dir.is_dir():
        return []
    runs = [(json.loads(p.read_text(encoding="utf-8")), p.with_suffix(".md")) for p in runs_dir.glob("*.json")]
    return sorted(runs, key=lambda r: (r[0]["created_at"], r[0]["run_id"]))


def _results(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["question_id"]: r for r in run["results"]}


def _assert_preflight_first_and_closed(calls: list[str]) -> None:
    assert calls.count("preflight") >= 1, calls
    assert "reply" in calls, calls
    assert calls.index("preflight") < calls.index("reply"), calls
    assert calls[-1] == "aclose", calls


def test_qa_eval_run_entry_pins_one_entry_and_records_who_answered(qa_chain, content, tmp_path, capsys):
    qa_chain.models_ok()
    # Scripted so that a call to the other entry would succeed: only the absence of its requests proves the pin.
    qa_chain.fake.chat(_CHAIN_BASE, _SEALION_MODEL, stream_reply(_PRICE_ANSWER, routed_via=_SEALION_ROUTED_VIA))
    qa_chain.fake.chat(_CHAIN_BASE, _CHAIN_MODEL, stream_reply(_PRICE_ANSWER, routed_via=_CHAIN_ROUTED_VIA))

    code = _qa_run(qa_chain, content, tmp_path, "--entry", _CHAIN_LABEL)
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err

    assert qa_chain.only and set(qa_chain.only) == {_CHAIN_LABEL}, qa_chain.only
    assert qa_chain.fake.chat_requests(model=_SEALION_MODEL) == [], "a pinned run must not call another entry"
    assert len(qa_chain.fake.chat_requests(model=_CHAIN_MODEL)) == len(_EVAL_QUESTIONS)
    _assert_preflight_first_and_closed(qa_chain.calls)
    # On the wire too: the model check goes out before the first question.
    assert qa_chain.fake.requests[0].path == MODELS_PATH, [r.path for r in qa_chain.fake.requests]
    assert qa_chain.fake.unscripted == []

    [(run, _md)] = _saved_runs(tmp_path)
    assert run["engine"] == f"chain:{_CHAIN_LABEL}", run
    for qid, result in _results(run).items():
        assert result["passed"] is True, (qid, result)
        assert result["model_label"] == _CHAIN_LABEL, (qid, result)
        assert result["model"] == _CHAIN_MODEL, (qid, result)
        assert result["provider"] == _CHAIN_ROUTED_VIA, (qid, result)
    assert f"chain:{_CHAIN_LABEL}" in captured.out, captured.out


def test_qa_eval_run_whole_chain_records_the_entry_that_answered_each_question(qa_chain, content, tmp_path, capsys):
    qa_chain.models_ok()
    # q01: sealion answers. q02: sealion is rate limited, so the chain switches to gptoss within the same turn.
    qa_chain.fake.chat(
        _CHAIN_BASE,
        _SEALION_MODEL,
        stream_reply(_PRICE_ANSWER, routed_via=_SEALION_ROUTED_VIA),
        http_error(429, code="rate_limited", message=f"quota exceeded for {_CHAIN_KEY}"),
    )
    qa_chain.fake.chat(_CHAIN_BASE, _CHAIN_MODEL, stream_reply(_PRICE_ANSWER, routed_via=_CHAIN_ROUTED_VIA))

    code = _qa_run(qa_chain, content, tmp_path)
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err

    assert set(qa_chain.only) == {None}, qa_chain.only
    _assert_preflight_first_and_closed(qa_chain.calls)
    [(run, _md)] = _saved_runs(tmp_path)
    assert run["engine"] == "chain", run
    results = _results(run)
    assert results["q01"]["passed"] is True, results["q01"]
    assert (results["q01"]["model_label"], results["q01"]["model"], results["q01"]["provider"]) == (
        "sealion",
        _SEALION_MODEL,
        _SEALION_ROUTED_VIA,
    ), results["q01"]
    assert results["q02"]["passed"] is True, results["q02"]
    assert (results["q02"]["model_label"], results["q02"]["model"], results["q02"]["provider"]) == (
        _CHAIN_LABEL,
        _CHAIN_MODEL,
        _CHAIN_ROUTED_VIA,
    ), results["q02"]
    assert _CHAIN_KEY not in captured.out + captured.err


def test_qa_eval_run_entry_needs_chain_engine(qa_chain, content, tmp_path, capsys):
    settings = qa_chain.settings.model_copy(update={"reply_engine": "fake"})
    code = _qa_run(qa_chain, content, tmp_path, "--entry", _CHAIN_LABEL, settings=settings)
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code == qa_eval_cli.EXIT_ERROR == 1, message
    assert "REPLY_ENGINE" in message, message
    assert _saved_runs(tmp_path) == [], "a configuration error produces no run file"
    assert qa_chain.fake.requests == []


def test_qa_eval_run_unknown_entry_is_config_error(qa_chain, content, tmp_path, capsys):
    qa_chain.models_ok()
    code = _qa_run(qa_chain, content, tmp_path, "--entry", "khongco")
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code == qa_eval_cli.EXIT_ERROR == 1, message
    assert "khongco" in message, message
    assert _saved_runs(tmp_path) == [], "a configuration error produces no run file"
    assert qa_chain.fake.chat_requests() == []


@pytest.mark.parametrize("entry", [None, _CHAIN_LABEL], ids=["whole_chain", "pinned"])
def test_qa_eval_run_preflight_failure_exits_1_and_produces_nothing(qa_chain, content, tmp_path, capsys, entry):
    qa_chain.fake.models(_CHAIN_BASE, models_error(401, message=f"invalid api key {_CHAIN_KEY}"))
    # Scripted so that a question asked by mistake would succeed: only the absence of chat requests proves the skip.
    qa_chain.fake.chat(_CHAIN_BASE, _SEALION_MODEL, stream_reply(_PRICE_ANSWER, routed_via=_SEALION_ROUTED_VIA))
    qa_chain.fake.chat(_CHAIN_BASE, _CHAIN_MODEL, stream_reply(_PRICE_ANSWER, routed_via=_CHAIN_ROUTED_VIA))

    extra = ("--entry", entry) if entry else ()
    code = _qa_run(qa_chain, content, tmp_path, *extra)
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code == qa_eval_cli.EXIT_ERROR == 1, message
    assert "preflight" in qa_chain.calls, qa_chain.calls
    assert qa_chain.fake.chat_requests() == [], "no question may be sent after a failed preflight"
    assert "reply" not in qa_chain.calls, qa_chain.calls
    assert "aclose" in qa_chain.calls, "aclose() must run even when preflight fails"
    assert _saved_runs(tmp_path) == [], "a failed preflight produces no run file"
    assert not any(q["id"] in captured.out for q in _EVAL_QUESTIONS), captured.out
    assert "401" in message, message
    assert _CHAIN_KEY not in message, message


def test_qa_eval_run_pinned_entry_failure_is_service_error_not_wrong_answer(qa_chain, content, tmp_path, capsys):
    qa_chain.models_ok()
    # The pinned entry answers q01, then is rate limited for good (the last scripted reply repeats, retries included).
    qa_chain.fake.chat(
        _CHAIN_BASE,
        _SEALION_MODEL,
        stream_reply(_PRICE_ANSWER, routed_via=_SEALION_ROUTED_VIA),
        http_error(429, code="rate_limited", message=f"quota exceeded for {_CHAIN_KEY}"),
    )
    # Would answer q02 correctly if the chain switched: only its absence from the requests proves FR-021.
    qa_chain.fake.chat(_CHAIN_BASE, _CHAIN_MODEL, stream_reply(_PRICE_ANSWER, routed_via=_CHAIN_ROUTED_VIA))

    code = _qa_run(qa_chain, content, tmp_path, "--entry", "sealion", "--max-retries", "1")
    captured = capsys.readouterr()
    message = captured.out + captured.err
    # Same exit-code rule as `script` (research R10): nothing graded wrong, but a question was not graded, so the run
    # does not count towards SC-008.
    assert code == qa_eval_cli.EXIT_INCOMPLETE == 3, message
    assert qa_chain.fake.chat_requests(model=_CHAIN_MODEL) == [], "a pinned entry failing must not call another entry"
    assert len(qa_chain.fake.chat_requests(model=_SEALION_MODEL)) >= 2
    _assert_preflight_first_and_closed(qa_chain.calls)

    [(run, md_path)] = _saved_runs(tmp_path)
    assert run["engine"] == "chain:sealion", run
    results = _results(run)
    assert results["q01"]["passed"] is True, results["q01"]
    assert results["q01"]["model_label"] == "sealion", results["q01"]
    # q02 is a service error, recorded as such, and never shown as a wrong answer (US4 #1).
    assert "rate_limited" in (results["q02"]["error"] or ""), results["q02"]
    q02_lines = [line for line in captured.out.splitlines() if "q02" in line]
    assert q02_lines and not any("SAI" in line for line in q02_lines), captured.out
    md_rows = [line for line in md_path.read_text(encoding="utf-8").splitlines() if line.startswith("| q02 ")]
    assert md_rows, md_path.read_text(encoding="utf-8")
    assert all("Sai" not in [cell.strip() for cell in row.split("|")] for row in md_rows), md_rows
    assert _CHAIN_KEY not in message, message


_COMPARISON_SECTION = re.compile(r"^## So sánh.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def test_qa_eval_run_comparison_names_the_engine_of_both_runs(qa_chain, content, tmp_path, capsys):
    qa_chain.models_ok()
    qa_chain.fake.chat(_CHAIN_BASE, _SEALION_MODEL, stream_reply(_PRICE_ANSWER, routed_via=_SEALION_ROUTED_VIA))
    qa_chain.fake.chat(_CHAIN_BASE, _CHAIN_MODEL, stream_reply(_PRICE_ANSWER, routed_via=_CHAIN_ROUTED_VIA))

    first = _qa_run(qa_chain, content, tmp_path, "--entry", "sealion")
    assert first == 0, capsys.readouterr().out
    capsys.readouterr()
    second = _qa_run(qa_chain, content, tmp_path, "--entry", _CHAIN_LABEL)
    captured = capsys.readouterr()
    assert second == 0, captured.out + captured.err

    runs = _saved_runs(tmp_path)
    assert [r["engine"] for r, _ in runs] == ["chain:sealion", f"chain:{_CHAIN_LABEL}"], [r for r, _ in runs]
    latest, md_path = runs[-1]
    assert latest["previous_run_id"] == runs[0][0]["run_id"], latest
    # US4 #3: the comparison says which engine each run used, so scores of two models are never mixed up.
    match = _COMPARISON_SECTION.search(md_path.read_text(encoding="utf-8"))
    assert match, md_path.read_text(encoding="utf-8")
    assert "chain:sealion" in match.group(0) and f"chain:{_CHAIN_LABEL}" in match.group(0), match.group(0)
    # The console comparison line names the previous engine as well (this run's engine is printed at the start).
    assert "chain:sealion" in captured.out, captured.out


# 004 T056: `python -m ai_live.qa_eval script` grades sample segments (US4, FR-025, FR-026) or a past session (SC-003).
# CLI contract assumed (implemented by T059):
#   script [--content PATH] [--per-combo N] [--session DIR] [--runs-dir DIR]
#   --runs-dir defaults to data/eval/script_runs, like `run --runs-dir` defaults to data/eval/runs;
#   exit 0 when no violation, non-zero when a violation is found;
#   `main(argv, engine=...)` injects the ReplyEngine, as the `run` subcommand already allows.


def _script_runs(runs_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(runs_dir.glob("*.json"))]


def test_qa_eval_script_with_fake_engine_exits_0_and_saves_run(fake_env, content, tmp_path, capsys):
    runs_dir = tmp_path / "script_runs"
    code = _run(qa_eval_cli, ["script", "--content", str(content), "--runs-dir", str(runs_dir)])
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    runs = _script_runs(runs_dir)
    assert len(runs) == 1, captured.out
    # data-model §10: the fake engine's default lines are grounded, so the saved run has segments and no violation.
    assert runs[0]["segments"], runs[0]
    assert runs[0]["violation_count"] == 0, runs[0]


def test_qa_eval_script_violation_exits_nonzero_and_lists_sentence(fake_env, content, tmp_path, capsys):
    product_id = _product_ids(content)["Kem chống nắng X"]
    # Raw text with an invented price and a wrong pronoun: the grader must flag it whatever the guard does live.
    bad = "Dạ tôi giảm còn 99.000đ cho cả nhà nha."
    engine = FakeReplyEngine(script={(product_id, Topic.PRICE): (bad,)})
    runs_dir = tmp_path / "script_runs"
    code = _run(qa_eval_cli, ["script", "--content", str(content), "--runs-dir", str(runs_dir)], engine=engine)
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code != 0, message
    # US4 #2: the report names the violating sentence (and its reason).
    assert bad in captured.out, message
    runs = _script_runs(runs_dir)
    assert len(runs) == 1, message
    assert runs[0]["violation_count"] >= 1, runs[0]


def _sentence_record(seq: int, text: str, status: str = "spoken", **extra: Any) -> dict[str, Any]:
    """One `script_sentences.jsonl` line in the shape `director.session_log.script_sentence_record` writes."""
    record: dict[str, Any] = {
        "utterance_id": f"u{seq}",
        "segment_id": "s1",
        "seq": seq,
        "source": "script",
        "text": text,
        "raw_text": text,
        "status": status,
        "guard_reason": None,
        "guard_detail": None,
        "drop_reason": None,
        "marks": {},
        "played_at": None,
    }
    record.update(extra)
    return record


def _session_dir(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    directory = tmp_path / "sessions" / "20261102-100000"
    directory.mkdir(parents=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    (directory / "script_sentences.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return directory


def _script_session_argv(session: Path, content: Path, runs_dir: Path) -> list[str]:
    return ["script", "--session", str(session), "--content", str(content), "--runs-dir", str(runs_dir)]


def test_qa_eval_script_session_clean_exits_0(fake_env, content, tmp_path, capsys):
    # SC-003 grades only `spoken` sentences: a blocked or dropped sentence never reached the viewer.
    session = _session_dir(
        tmp_path,
        [
            _sentence_record(0, "Dạ cả nhà ơi, hôm nay em giới thiệu kem chống nắng nha."),
            _sentence_record(1, "Bản 50 ml giá 250.000đ, bản 100 ml giá 420.000đ ạ."),
            _sentence_record(2, "Tôi cam kết chữa khỏi mụn.", "blocked", guard_reason="forbidden_claim"),
            _sentence_record(3, "Giá chỉ 99.000đ thôi.", "dropped", drop_reason="sentence_count_exceeded"),
        ],
    )
    code = _run(qa_eval_cli, _script_session_argv(session, content, tmp_path / "script_runs"))
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err


@pytest.mark.parametrize(
    "bad",
    [
        "Dạ kem này giá chỉ 99.000đ thôi cả nhà.",
        "Tôi thấy kem này hợp với da dầu lắm.",
        "Cả nhà vào https://example.com/kem-x để đặt nha.",
        "Kem này chữa khỏi mụn luôn đó cả nhà.",
    ],
    ids=["unknown_amount", "bad_pronoun", "link", "forbidden_claim"],
)
def test_qa_eval_script_session_spoken_violation_exits_nonzero(fake_env, content, tmp_path, capsys, bad):
    session = _session_dir(
        tmp_path,
        [
            _sentence_record(0, "Dạ cả nhà ơi, hôm nay em giới thiệu kem chống nắng nha."),
            _sentence_record(1, bad),
        ],
    )
    code = _run(qa_eval_cli, _script_session_argv(session, content, tmp_path / "script_runs"))
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code != 0, message
    assert bad in captured.out, message


def test_tts_say_writes_readable_wav(fake_env, tmp_path, capsys):
    out_file = tmp_path / "out.wav"
    code = tts_cli.main(["say", "Dạ chào bạn Lan", "--out", str(out_file)])
    out = capsys.readouterr().out
    assert code == 0
    assert "chunk đầu" in out
    with wave.open(str(out_file), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000
        assert wav.getnframes() == pytest.approx(4 * 0.25 * 16000, rel=0.05)


def test_tts_say_unknown_provider_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TTS_PROVIDER", "azure")
    code = tts_cli.main(["say", "xin chào", "--out", str(tmp_path / "x.wav")])
    assert code == 1
    assert "TTS_PROVIDER" in capsys.readouterr().out


# ---------- 003 T038: `say` warms up, shows what was sent and reports TTS errors by kind (FR-012) ----------


class _SpyEngine:
    """Records the order of `warm_up` and `synthesize` calls; can fail with a `TTSEngineError`."""

    sample_rate = 16000

    def __init__(self, *, fail: TTSEngineError | None = None, fail_warm_up: TTSEngineError | None = None) -> None:
        self.calls: list[str] = []
        self.received: list[str] = []
        self._fail = fail
        self._fail_warm_up = fail_warm_up

    async def warm_up(self) -> None:
        self.calls.append("warm_up")
        if self._fail_warm_up is not None:
            raise self._fail_warm_up

    async def synthesize(self, text: str):
        self.calls.append("synthesize")
        self.received.append(text)
        if self._fail is not None:
            raise self._fail
        yield b"\x00\x00" * 1600


def _spy_say(monkeypatch, engine: _SpyEngine, provider: str = "gemini") -> None:
    def create(settings):
        return SpeechTTS(engine, provider=provider, normalize=load_normalizer(settings), quota_cooldown_s=60)

    monkeypatch.setattr(tts_cli, "create_tts", create)


def test_tts_say_warms_up_before_the_first_sentence(fake_env, monkeypatch, tmp_path):
    engine = _SpyEngine()
    _spy_say(monkeypatch, engine)
    assert tts_cli.main(["say", "Dạ", "--out", str(tmp_path / "x.wav")]) == 0
    assert engine.calls == ["warm_up", "synthesize"]


def test_tts_say_prints_provider_spoken_text_and_chars_sent(fake_env, monkeypatch, tmp_path, capsys):
    engine = _SpyEngine()
    _spy_say(monkeypatch, engine, provider="gemini")
    code = tts_cli.main(["say", "Giá chỉ 259.000đ", "--out", str(tmp_path / "x.wav")])
    out = capsys.readouterr().out
    spoken = "Giá chỉ hai trăm năm mươi chín ngàn đồng"
    assert code == 0
    assert engine.received == [spoken]
    assert "gemini" in out
    assert spoken in out
    assert re.search(rf"ký tự[^\n]*\b{len(spoken)}\b", out), out


@pytest.mark.parametrize("stage", ["synthesize", "warm_up"])
def test_tts_say_engine_error_prints_kind_and_message(fake_env, monkeypatch, tmp_path, capsys, stage):
    error = TTSEngineError("api_error", "Gemini TTS lỗi HTTP 500: boom")
    engine = _SpyEngine(fail=error) if stage == "synthesize" else _SpyEngine(fail_warm_up=error)
    _spy_say(monkeypatch, engine)
    out_file = tmp_path / "x.wav"
    code = tts_cli.main(["say", "Dạ", "--out", str(out_file)])
    out = capsys.readouterr().out
    assert code != 0
    assert "api_error" in out
    assert "Gemini TTS lỗi HTTP 500: boom" in out
    assert not out_file.exists()


def test_tts_say_gemini_without_key_exits_1_with_vietnamese_fix(monkeypatch, tmp_path, capsys):
    # No `.env` in the cwd: an empty variable is ignored (env_ignore_empty), so the real key would be read from there.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TTS_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code = tts_cli.main(["say", "Dạ", "--out", str(tmp_path / "x.wav")])
    out = capsys.readouterr().out
    assert code == 1
    assert "GEMINI_API_KEY" in out


def test_tts_say_creates_the_missing_output_folder(fake_env, monkeypatch, tmp_path):
    _spy_say(monkeypatch, _SpyEngine())
    out_file = tmp_path / "chua_co" / "x.wav"
    assert tts_cli.main(["say", "Dạ", "--out", str(out_file)]) == 0
    with wave.open(str(out_file), "rb") as wav:
        assert wav.getnframes() == 1600


def test_tts_say_unwritable_output_fails_before_the_voice_source_is_called(fake_env, monkeypatch, tmp_path, capsys):
    # A cloud source would spend quota on a sentence that cannot be saved.
    engine = _SpyEngine()
    _spy_say(monkeypatch, engine)
    blocker = tmp_path / "la_file"
    blocker.write_text("")
    code = tts_cli.main(["say", "Dạ", "--out", str(blocker / "x.wav")])
    out = capsys.readouterr().out
    assert code == 1
    assert "Không ghi được" in out
    assert "TTS lỗi" not in out
    assert engine.calls == []


def test_comments_cli_prints_priority_drop_reason_and_queue_order(capsys):
    code = comments_cli.main(["Lan: giá bao nhiêu?", "Huy: hello shop", "x: http://a.b"])
    out = capsys.readouterr().out
    assert code == 0
    lines = out.splitlines()
    lan = next(line for line in lines if "giá bao nhiêu?" in line)
    huy = next(line for line in lines if "hello shop" in line)
    spam = next(line for line in lines if "http://a.b" in line)
    assert "HIGH" in lan
    assert "LOW" in huy
    assert "link" in spam
    # Queue order section: HIGH first, the dropped comment is not in it.
    order_start = next(i for i, line in enumerate(lines) if "hàng đợi" in line.lower())
    queue_lines = [line for line in lines[order_start + 1 :] if line.strip()]
    assert len(queue_lines) == 2
    assert "giá bao nhiêu?" in queue_lines[0]
    assert "hello shop" in queue_lines[1]


def test_comments_cli_argument_without_author(capsys):
    code = comments_cli.main(["chất liệu gì vậy?"])
    out = capsys.readouterr().out
    assert code == 0
    assert "MEDIUM" in out


# ---------- 003 T030: `normalize` prints the spoken form without building a voice source (FR-010) ----------


def test_tts_normalize_prints_spoken_text_without_a_voice_source(monkeypatch, capsys):
    def no_source(settings):
        raise AssertionError("normalize must not build a voice source")

    monkeypatch.setattr(tts_cli, "create_tts", no_source)
    # Even a provider with no adapter is fine: normalize never touches the voice source.
    monkeypatch.setenv("TTS_PROVIDER", "gemini")
    code = tts_cli.main(["normalize", "Combo 250k, giảm 15%"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "Combo hai trăm năm mươi ngàn, giảm mười lăm phần trăm"


def test_tts_normalize_bad_abbreviations_file_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TTS_ABBREVIATIONS_PATH", str(tmp_path / "missing.json"))
    code = tts_cli.main(["normalize", "SP này"])
    assert code == 1
    assert "TTS_ABBREVIATIONS_PATH" in capsys.readouterr().out
