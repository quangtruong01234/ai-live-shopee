"""T053 (008): each `LLM_CHAIN` entry, pinned with `only=`, against its real provider (marker `live_llm`).

Run only with the user's consent: `uv run pytest -m live_llm tests/live/test_chain_engine.py` when `.env` has the key
of each entry to test (and the local key gateway is running for loopback entries, ADR-034). Per entry: one
`GET /models` and two chat requests of the free quota (ADR-019). Entries whose key is missing are skipped.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ai_live.brain.chain_engine import ChainReplyEngine, TurnRecord
from ai_live.core.config import ChainEntryConfig, Settings
from ai_live.core.models import Comment, SegmentRequest, Topic
from ai_live.products.docx_loader import load_catalog_file

pytestmark = [pytest.mark.live_llm, pytest.mark.anyio]

DEMO = Path("data/products/demo.docx")


def _chain_labels() -> list[str]:
    # Read at collection so each entry gets its own test id. A broken `.env` must not break collecting the default
    # (deselected) run, so any settings error falls back to one skipped placeholder.
    try:
        return [entry.label for entry in Settings().llm_chain]
    except Exception:
        return []


_LABELS = _chain_labels()
_PARAMS = [pytest.param(label, id=label) for label in _LABELS] or [
    pytest.param(None, id="no-chain", marks=pytest.mark.skip(reason="không đọc được LLM_CHAIN từ .env"))
]


@pytest.fixture
def live_settings():
    # Function scope, so conftest has already cleared the shell environment and only `.env` is read.
    return Settings(reply_engine="chain")


@pytest.fixture
def catalog(live_settings):
    return load_catalog_file(DEMO, live_settings.content_max_bytes)


def _entry(settings: Settings, label: str) -> ChainEntryConfig:
    entry = next((e for e in settings.llm_chain if e.label == label), None)
    if entry is None:
        pytest.skip(f'LLM_CHAIN trong .env không có mục "{label}"')
    # Only a missing key skips; an unknown `key_env` or any other config problem must fail in `from_settings`.
    field = entry.key_env.lower()
    if field in Settings.model_fields:
        secret = getattr(settings, field)
        if secret is None or not secret.get_secret_value().strip():
            pytest.skip(f"chưa có {entry.key_env} trong .env cho mục {label}")
    return entry


def _platform_matches(provider: str | None, platform: str) -> bool:
    # Same rule as the engine's platform check: case-insensitive, on the part before "/".
    if not provider:
        return False
    return provider.split("/", 1)[0].strip().casefold() == platform.strip().casefold()


def _check_record(records: list[TurnRecord], entry: ChainEntryConfig, kind: str) -> None:
    assert len(records) == 1, records
    record = records[0]
    assert record.kind == kind
    assert record.outcome == "ok", record.attempts
    assert record.label == entry.label
    if entry.platform:
        assert _platform_matches(record.provider, entry.platform), (record.provider, entry.platform)


@pytest.mark.parametrize("label", _PARAMS)
async def test_preflight_passes(live_settings, label):
    entry = _entry(live_settings, label)
    engine = ChainReplyEngine.from_settings(live_settings, only=label)
    try:
        results = await engine.preflight()
    finally:
        await engine.aclose()
    assert [r.label for r in results] == [entry.label]
    assert results[0].ok, results[0]


@pytest.mark.parametrize("label", _PARAMS)
async def test_reply_speaks_with_pinned_entry(live_settings, catalog, label):
    entry = _entry(live_settings, label)
    engine = ChainReplyEngine.from_settings(live_settings, only=label)
    records: list[TurnRecord] = []
    engine.add_turn_observer(records.append)
    comment = Comment(
        id=f"live-{label}",
        source="mock",
        author="Lan",
        text="kem chống nắng giá bao nhiêu vậy shop?",
        received_at=time.monotonic(),
    )
    try:
        sentences = [s async for s in engine.reply(comment, catalog)]
    finally:
        await engine.aclose()
    assert any(s.strip() for s in sentences), sentences
    _check_record(records, entry, "reply")


@pytest.mark.parametrize("label", _PARAMS)
async def test_narrate_speaks_with_pinned_entry(live_settings, catalog, label):
    entry = _entry(live_settings, label)
    engine = ChainReplyEngine.from_settings(live_settings, only=label)
    records: list[TurnRecord] = []
    engine.add_turn_observer(records.append)
    request = SegmentRequest(
        segment_id=f"live-{label}", topic=Topic.OPENING, product_id=None, min_sentences=2, max_sentences=3
    )
    try:
        sentences = [s async for s in engine.narrate(request, catalog)]
    finally:
        await engine.aclose()
    assert any(s.strip() for s in sentences), sentences
    _check_record(records, entry, "segment")
