"""T059 (004), T047 (008): exit codes and error paths of `python -m ai_live.qa_eval script` beyond ai-qa's cases in
test_cli.py.

Exit codes: 0 no violation, 2 violation, 3 no violation but some segments hit a service error (not graded, so the run
does not count towards SC-008), 1 content / session / configuration error.

The 008 cases run the real `ChainReplyEngine.from_settings()` (so `--entry` gives the production one-entry chain) on the
fake OpenAI-compatible provider: no network, no key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.core.config import Settings
from ai_live.core.models import Topic
from ai_live.core.protocols import ReplyEngineError
from ai_live.qa_eval import __main__ as cli
from ai_live.qa_eval import script_eval
from fixtures.content_builder import valid_docx
from fixtures.fake_openai import (
    MODELS_PATH,
    FakeOpenAI,
    ModelRow,
    http_error,
    models_error,
    models_list,
    stream_reply,
)

REPO_PHRASES = Path(__file__).resolve().parents[2] / "data" / "rules" / "platform_phrases.txt"


@pytest.fixture
def content(tmp_path):
    path = tmp_path / "valid.docx"
    path.write_bytes(valid_docx())
    return path


@pytest.fixture
def cli_settings(settings):
    return settings.model_copy(update={"platform_phrases_path": REPO_PHRASES})


def _main(argv: list[str], settings: Settings, **kwargs) -> int:
    try:
        return cli.main(argv, settings=settings, **kwargs)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


def _argv(content: Path, runs_dir: Path, *extra: str) -> list[str]:
    return ["script", "--content", str(content), "--runs-dir", str(runs_dir), *extra]


def test_only_service_errors_exit_3_and_say_not_counted(cli_settings, content, tmp_path, capsys):
    engine = FakeReplyEngine()
    engine.fail_next("rate_limited")
    runs_dir = tmp_path / "runs"
    code = _main(_argv(content, runs_dir), cli_settings, engine=engine)
    out = capsys.readouterr().out
    assert code == cli.EXIT_INCOMPLETE == 3, out
    assert "rate_limited" in out
    assert "SC-008" in out
    [saved] = [json.loads(p.read_text(encoding="utf-8")) for p in runs_dir.glob("*.json")]
    assert saved["violation_count"] == 0 and saved["error_count"] == 1


def test_violation_wins_over_service_error(cli_settings, content, tmp_path, capsys):
    engine = FakeReplyEngine(script={(None, Topic.CLOSING): ("Tôi chào bạn nha.",)})
    engine.fail_next("rate_limited")
    code = _main(_argv(content, tmp_path / "runs"), cli_settings, engine=engine)
    out = capsys.readouterr().out
    assert code == cli.EXIT_FAILED == 2, out
    assert "Tôi chào bạn nha." in out and "bad_pronoun" in out


def test_clean_run_prints_comparison_on_second_run(cli_settings, content, tmp_path, capsys):
    runs_dir = tmp_path / "runs"
    assert _main(_argv(content, runs_dir), cli_settings) == 0
    capsys.readouterr()
    assert _main(_argv(content, runs_dir), cli_settings) == 0
    assert "So với" in capsys.readouterr().out


def test_per_combo_below_one_exits_1(cli_settings, content, tmp_path, capsys):
    assert _main(_argv(content, tmp_path / "runs", "--per-combo", "0"), cli_settings) == 1
    assert "--per-combo" in capsys.readouterr().out


def test_missing_content_exits_1(cli_settings, tmp_path, capsys):
    assert _main(_argv(tmp_path / "missing.docx", tmp_path / "runs"), cli_settings) == 1
    assert "Không tìm thấy file nội dung" in capsys.readouterr().out


def test_session_without_script_sentences_exits_1(cli_settings, content, tmp_path, capsys):
    session = tmp_path / "sessions" / "empty"
    session.mkdir(parents=True)
    runs_dir = tmp_path / "runs"
    code = _main(_argv(content, runs_dir, "--session", str(session)), cli_settings)
    out = capsys.readouterr().out
    assert code == 1, out
    assert "script_sentences.jsonl" in out
    assert not runs_dir.exists() or not list(runs_dir.glob("*.json"))


def test_missing_platform_phrases_exits_1(settings, content, tmp_path, capsys):
    broken = settings.model_copy(update={"platform_phrases_path": tmp_path / "missing.txt"})
    assert _main(_argv(content, tmp_path / "runs"), broken) == 1
    assert "Lỗi cấu hình guard" in capsys.readouterr().out


def test_engine_config_error_exits_1(cli_settings, content, tmp_path, capsys, monkeypatch):
    def broken_factory(settings, **_):
        raise ReplyEngineError("config_error", "thiếu GEMINI_API_KEY")

    # Patched where the CLI builds the engine (008 T052) and where `run_script_check` builds its own.
    monkeypatch.setattr(cli, "create_reply_engine", broken_factory)
    monkeypatch.setattr(script_eval, "create_reply_engine", broken_factory)
    assert _main(_argv(content, tmp_path / "runs"), cli_settings) == 1
    out = capsys.readouterr().out
    assert "Lỗi cấu hình LLM (config_error)" in out


def test_session_mode_never_builds_an_engine(cli_settings, content, tmp_path, capsys, monkeypatch):
    def no_engine(settings, **_):
        raise AssertionError("session mode must not call the LLM")

    monkeypatch.setattr(cli, "create_reply_engine", no_engine)
    monkeypatch.setattr(script_eval, "create_reply_engine", no_engine)
    session = tmp_path / "sessions" / "s"
    session.mkdir(parents=True)
    line = {"segment_id": "s1", "seq": 0, "text": "Dạ em chào cả nhà nha.", "raw_text": "Dạ em chào cả nhà nha."}
    (session / "script_sentences.jsonl").write_text(
        json.dumps({**line, "status": "spoken"}, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    code = _main(_argv(content, tmp_path / "runs", "--session", str(session), "--per-combo", "2"), cli_settings)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "Bỏ qua --per-combo" in out


# ---------- 008 T047: `script [--entry LABEL]` on the chain (US4, FR-021, FR-022, contracts/adapters.md §6) ----------

_BASE = "http://127.0.0.1:3001/v1"
_KEY = "freellmapi-SCRIPT-SECRET-5b1e2d9a"
_SEALION = {
    "label": "sealion",
    "base_url": _BASE,
    "model": "gemma-sea-lion-v4-27b",
    "key_env": "FREELLMAPI_KEY",
    "platform": "cloudflare",
    "first_sentence_timeout_s": 3.5,
}
_GPTOSS = {
    "label": "gptoss",
    "base_url": _BASE,
    "model": "gpt-oss-120b",
    "key_env": "FREELLMAPI_KEY",
    "platform": "groq",
    "first_sentence_timeout_s": 2.0,
}
_SEALION_VIA = "cloudflare/@cf/aisingapore/gemma-sea-lion-v4-27b-it"
_GPTOSS_VIA = "groq/openai/gpt-oss-120b"
# No amount, no link, no platform phrase, "em" / "cả nhà": grades clean for every segment of `valid_docx()`.
_CLEAN = ("Dạ cả nhà ơi, em giới thiệu sản phẩm này nha. ", "Cả nhà xem thêm thông tin trong file của shop ạ.")


class _Chain:
    """The fake provider, the `only` values the CLI asked for and the engine calls, in order."""

    def __init__(self, settings: Settings) -> None:
        self.fake = FakeOpenAI()
        self.settings = settings
        self.only: list[str | None] = []
        self.calls: list[str] = []

    def models_ok(self) -> None:
        self.fake.models(
            _BASE,
            models_list(ModelRow(_SEALION["model"], available=True), ModelRow(_GPTOSS["model"], available=True)),
        )

    def answer_all(self) -> None:
        self.fake.chat(_BASE, _SEALION["model"], stream_reply(*_CLEAN, routed_via=_SEALION_VIA))
        self.fake.chat(_BASE, _GPTOSS["model"], stream_reply(*_CLEAN, routed_via=_GPTOSS_VIA))


@pytest.fixture
def chain(monkeypatch, tmp_path) -> _Chain:
    from ai_live.brain import factory as brain_factory
    from ai_live.brain.chain_engine import ChainReplyEngine

    settings = Settings(
        _env_file=None,
        reply_engine="chain",
        tts_provider="fake",
        avatar_mode="static",
        llm_chain=[_SEALION, _GPTOSS],
        freellmapi_key=_KEY,
        platform_phrases_path=REPO_PHRASES,
        session_data_dir=tmp_path / "sessions",
    )
    state = _Chain(settings)
    real_factory = brain_factory.create_reply_engine

    def factory(settings: Settings, *, only: str | None = None, fault_hook: Any = None) -> Any:
        state.only.append(only)
        if settings.reply_engine != "chain":
            return real_factory(settings, only=only, fault_hook=fault_hook)
        return ChainReplyEngine.from_settings(
            settings, only=only, fault_hook=fault_hook, transport=state.fake.transport
        )

    # Both places that may build the engine, so the test does not depend on which one the CLI uses.
    monkeypatch.setattr(cli, "create_reply_engine", factory)
    monkeypatch.setattr(script_eval, "create_reply_engine", factory)

    real_preflight, real_narrate, real_aclose = (
        ChainReplyEngine.preflight,
        ChainReplyEngine.narrate,
        ChainReplyEngine.aclose,
    )

    async def preflight(self):
        state.calls.append("preflight")
        return await real_preflight(self)

    def narrate(self, *args, **kwargs):
        state.calls.append("narrate")
        return real_narrate(self, *args, **kwargs)

    async def aclose(self):
        state.calls.append("aclose")
        return await real_aclose(self)

    monkeypatch.setattr(ChainReplyEngine, "preflight", preflight)
    monkeypatch.setattr(ChainReplyEngine, "narrate", narrate)
    monkeypatch.setattr(ChainReplyEngine, "aclose", aclose)
    return state


async def _no_sleep(_: float) -> None:
    return None


def _chain_main(chain: _Chain, content: Path, runs_dir: Path, *extra: str, settings: Settings | None = None) -> int:
    return _main(_argv(content, runs_dir, *extra), settings or chain.settings, sleep=_no_sleep)


def _saved(runs_dir: Path) -> list[dict[str, Any]]:
    if not runs_dir.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(runs_dir.glob("*.json"))]


def _assert_preflight_first_and_closed(calls: list[str]) -> None:
    assert calls.count("preflight") == 1, calls
    assert "narrate" in calls and calls.index("preflight") < calls.index("narrate"), calls
    assert calls[-1] == "aclose", calls


def test_script_entry_pins_one_entry_and_records_who_answered(chain, content, tmp_path, capsys):
    chain.models_ok()
    chain.answer_all()  # sealion would answer too: only the absence of its requests proves the pin
    runs_dir = tmp_path / "runs"
    code = _chain_main(chain, content, runs_dir, "--entry", "gptoss")
    captured = capsys.readouterr()
    assert code == cli.EXIT_OK, captured.out + captured.err

    assert chain.only and set(chain.only) == {"gptoss"}, chain.only
    assert chain.fake.chat_requests(model=_SEALION["model"]) == [], "a pinned run must not call another entry"
    assert chain.fake.requests[0].path == MODELS_PATH, [r.path for r in chain.fake.requests]
    assert chain.fake.unscripted == []
    _assert_preflight_first_and_closed(chain.calls)

    [run] = _saved(runs_dir)
    assert run["engine"] == "chain:gptoss", run["engine"]
    assert run["model"] == "gpt-oss-120b", run["model"]
    assert len(chain.fake.chat_requests(model=_GPTOSS["model"])) == len(run["segments"])
    for segment in run["segments"]:
        assert segment["error"] is None, segment
        assert (segment["model_label"], segment["model"], segment["provider"]) == (
            "gptoss",
            "gpt-oss-120b",
            _GPTOSS_VIA,
        ), segment
    assert run["violation_count"] == 0
    assert "chain:gptoss" in captured.out, captured.out


def test_script_whole_chain_is_labelled_chain(chain, content, tmp_path, capsys):
    chain.models_ok()
    chain.answer_all()
    runs_dir = tmp_path / "runs"
    code = _chain_main(chain, content, runs_dir)
    captured = capsys.readouterr()
    assert code == cli.EXIT_OK, captured.out + captured.err
    assert set(chain.only) == {None}, chain.only
    _assert_preflight_first_and_closed(chain.calls)
    [run] = _saved(runs_dir)
    assert run["engine"] == "chain", run["engine"]
    # The first entry answers every segment, so the second is never asked.
    assert chain.fake.chat_requests(model=_GPTOSS["model"]) == []
    assert {(s["model_label"], s["provider"]) for s in run["segments"]} == {("sealion", _SEALION_VIA)}


def test_script_entry_needs_chain_engine(chain, content, tmp_path, capsys):
    settings = chain.settings.model_copy(update={"reply_engine": "fake"})
    runs_dir = tmp_path / "runs"
    code = _chain_main(chain, content, runs_dir, "--entry", "gptoss", settings=settings)
    out = capsys.readouterr().out
    assert code == cli.EXIT_ERROR == 1, out
    assert "REPLY_ENGINE" in out, out
    assert _saved(runs_dir) == [], "a configuration error produces no run file"
    assert chain.fake.requests == []


def test_script_unknown_entry_is_config_error(chain, content, tmp_path, capsys):
    chain.models_ok()
    runs_dir = tmp_path / "runs"
    code = _chain_main(chain, content, runs_dir, "--entry", "khongco")
    out = capsys.readouterr().out
    assert code == cli.EXIT_ERROR == 1, out
    assert "khongco" in out, out
    assert _saved(runs_dir) == []
    assert chain.fake.chat_requests() == []


@pytest.mark.parametrize("entry", [None, "gptoss"], ids=["whole_chain", "pinned"])
def test_script_preflight_failure_exits_1_and_generates_nothing(chain, content, tmp_path, capsys, entry):
    chain.fake.models(_BASE, models_error(401, message=f"invalid api key {_KEY}"))
    chain.answer_all()  # a segment started by mistake would succeed: only the absence of chat requests proves the skip
    runs_dir = tmp_path / "runs"
    extra = ("--entry", entry) if entry else ()
    code = _chain_main(chain, content, runs_dir, *extra)
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code == cli.EXIT_ERROR == 1, message
    assert "preflight" in chain.calls, chain.calls
    assert "narrate" not in chain.calls, chain.calls
    assert chain.fake.chat_requests() == [], "no segment may be generated after a failed preflight"
    assert chain.calls[-1] == "aclose", "aclose() must run even when preflight fails"
    assert _saved(runs_dir) == [], "a failed preflight produces no run file"
    assert "401" in message, message
    assert _KEY not in message, message


def test_script_pinned_entry_429_is_service_error_not_violation(chain, content, tmp_path, capsys):
    chain.models_ok()
    chain.fake.chat(_BASE, _SEALION["model"], stream_reply(*_CLEAN, routed_via=_SEALION_VIA))
    chain.fake.chat(_BASE, _GPTOSS["model"], http_error(429, code="rate_limited", message=f"quota for {_KEY}"))
    runs_dir = tmp_path / "runs"
    code = _chain_main(chain, content, runs_dir, "--entry", "gptoss")
    captured = capsys.readouterr()
    message = captured.out + captured.err
    assert code == cli.EXIT_INCOMPLETE == 3, message
    assert chain.fake.chat_requests(model=_SEALION["model"]) == [], "a pinned entry failing must not call another"
    _assert_preflight_first_and_closed(chain.calls)
    [run] = _saved(runs_dir)
    assert run["engine"] == "chain:gptoss"
    assert run["violation_count"] == 0
    assert run["error_count"] == len(run["segments"]) > 0
    assert all("rate_limited" in (s["error"] or "") for s in run["segments"]), run["segments"]
    assert all(s["model_label"] is None for s in run["segments"]), "nobody answered a failed segment"
    assert _KEY not in message, message


def test_script_session_mode_ignores_entry_and_builds_no_engine(chain, content, tmp_path, capsys):
    session = tmp_path / "sessions" / "s"
    session.mkdir(parents=True)
    line = {"segment_id": "s1", "seq": 0, "text": "Dạ em chào cả nhà nha.", "raw_text": "Dạ em chào cả nhà nha."}
    (session / "script_sentences.jsonl").write_text(
        json.dumps({**line, "status": "spoken"}, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    code = _chain_main(chain, content, tmp_path / "runs", "--session", str(session), "--entry", "gptoss")
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK, out
    assert "Bỏ qua --entry" in out, out
    assert chain.only == [] and chain.fake.requests == []
