"""Integration fixtures: Settings pointing at a temporary valid content file, a JSON log collector, and a model chain
(feature 008) built over a fake OpenAI-compatible transport."""

from __future__ import annotations

import json
import logging

import pytest
from pydantic import SecretStr

from ai_live.core.config import Settings
from ai_live.core.logging import JsonFormatter
from fixtures.content_builder import valid_docx

# Not real keys; tests assert they never show up in a message or a log line.
FAKE_FREELLMAPI_KEY = "freellmapi-TEST-not-a-real-key-0123456789"
FAKE_GROQ_KEY = "gsk_TEST-not-a-real-key-0123456789abcdefgh"

# Two entries: a loopback one through the key gateway (needs `platform`) and a direct one. Same shape as the default
# chain (contracts/config.md §2), shorter so a test only scripts what it needs.
CHAIN_ENTRIES = (
    {
        "label": "sealion",
        "base_url": "http://127.0.0.1:3001/v1",
        "model": "gemma-sea-lion-v4-27b",
        "key_env": "FREELLMAPI_KEY",
        "platform": "cloudflare",
        "first_sentence_timeout_s": 2.0,
    },
    {
        "label": "qwen",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "qwen/qwen3.8-27b",
        "key_env": "GROQ_API_KEY",
        "first_sentence_timeout_s": 2.0,
    },
)


@pytest.fixture
def content_path(tmp_path):
    path = tmp_path / "valid.docx"
    path.write_bytes(valid_docx())
    return path


@pytest.fixture
def app_settings(settings, content_path):
    return settings.model_copy(update={"product_data_path": content_path})


@pytest.fixture
def json_log_lines():
    """Every `ai_live.*` log record, formatted by the real JSON formatter and parsed back.

    App startup (`configure_logging`) replaces the `ai_live` handlers, so with a TestClient request this fixture
    after the client fixture.
    """
    lines: list[dict] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(json.loads(self.format(record)))

    handler = Collect()
    handler.setFormatter(JsonFormatter("test-session"))
    root = logging.getLogger("ai_live")
    saved_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield lines
    finally:
        root.removeHandler(handler)
        root.setLevel(saved_level)


def _with_chain(settings: Settings) -> Settings:
    chain = Settings(_env_file=None, llm_chain=list(CHAIN_ENTRIES)).llm_chain
    return settings.model_copy(
        update={
            "reply_engine": "chain",
            "llm_chain": chain,
            "freellmapi_key": SecretStr(FAKE_FREELLMAPI_KEY),
            "groq_api_key": SecretStr(FAKE_GROQ_KEY),
        }
    )


@pytest.fixture
def with_chain():
    """`with_chain(settings)`: `settings` switched to `REPLY_ENGINE=chain` with `CHAIN_ENTRIES` and the fake keys.

    The chain goes through a validated Settings, so every entry carries its 1-based `position`. Tests read entries
    and keys back from the returned Settings (`llm_chain[i]`, `freellmapi_key`), since a conftest is not imported.
    """
    return _with_chain


@pytest.fixture
def make_chain_engine():
    """Builder of a `ChainReplyEngine` over `transport` (an `httpx.MockTransport`, e.g. `FakeOpenAI().transport`).

    `from_settings()` takes no transport (contracts/adapters.md §2), so the entries are resolved here the way it does
    (data-model §10). Imported inside the builder: until `brain/chain_engine.py` exists only the chain tests fail.
    """

    def build(settings: Settings, transport, **kwargs):
        from ai_live.brain.chain_engine import ChainReplyEngine, ResolvedEntry

        keys = {"FREELLMAPI_KEY": settings.freellmapi_key, "GROQ_API_KEY": settings.groq_api_key}
        entries = [
            ResolvedEntry(config=entry, position=entry.position, local=entry.local, key=keys[entry.key_env])
            for entry in settings.llm_chain
        ]
        return ChainReplyEngine(
            entries,
            cooldown_s=settings.llm_chain_cooldown_s,
            max_tokens=settings.llm_max_tokens,
            script_max_tokens=settings.script_max_tokens,
            transport=transport,
            **kwargs,
        )

    return build
