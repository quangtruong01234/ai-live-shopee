"""T014: `FakeReplyEngine.narrate()` beyond the contract (004 contracts/adapters.md §1)."""

from __future__ import annotations

import time

import anyio
import pytest

from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.guard import OutputGuard
from ai_live.core.models import Comment, SegmentRequest, Topic
from ai_live.core.protocols import ReplyEngineError
from ai_live.products.docx_loader import load_catalog
from ai_live.products.models import ProductCatalog
from fixtures.content_builder import valid_docx

pytestmark = pytest.mark.anyio


@pytest.fixture
def catalog() -> ProductCatalog:
    return load_catalog(valid_docx(), "valid.docx", 5_000_000)


def _request(topic: Topic, product_id: str | None, *, min_sentences: int = 2, max_sentences: int = 4) -> SegmentRequest:
    return SegmentRequest(
        segment_id=f"seg-{topic.value}",
        topic=topic,
        product_id=product_id,
        min_sentences=min_sentences,
        max_sentences=max_sentences,
    )


async def _collect(engine: FakeReplyEngine, request: SegmentRequest, catalog: ProductCatalog) -> list[str]:
    with anyio.fail_after(2):
        return [s async for s in engine.narrate(request, catalog)]


async def test_default_yields_min_sentences_naming_topic_and_product(catalog):
    product = catalog.primary
    out = await _collect(FakeReplyEngine(), _request(Topic.INTRO, product.id, min_sentences=3), catalog)
    assert out == [f"Câu {n} về {Topic.INTRO.label} của {product.name}." for n in (1, 2, 3)]


async def test_default_counter_keeps_rising_across_calls_so_nothing_repeats(catalog):
    engine = FakeReplyEngine()
    pid = catalog.primary.id
    first = await _collect(engine, _request(Topic.PRICE, pid), catalog)
    second = await _collect(engine, _request(Topic.PRICE, pid), catalog)
    assert first == [f"Câu {n} về {Topic.PRICE.label} của {catalog.primary.name}." for n in (1, 2)]
    assert second == [f"Câu {n} về {Topic.PRICE.label} của {catalog.primary.name}." for n in (3, 4)]
    assert len(set(first + second)) == 4


async def test_counter_is_per_engine(catalog):
    pid = catalog.primary.id
    await _collect(FakeReplyEngine(), _request(Topic.INTRO, pid), catalog)
    out = await _collect(FakeReplyEngine(), _request(Topic.INTRO, pid, min_sentences=1), catalog)
    assert out == [f"Câu 1 về {Topic.INTRO.label} của {catalog.primary.name}."]


@pytest.mark.parametrize("topic", [Topic.OPENING, Topic.CLOSING])
async def test_show_topics_use_shop_neutral_form(catalog, topic):
    out = await _collect(FakeReplyEngine(), _request(topic, None), catalog)
    assert out == [f"Câu {n} {topic.label}." for n in (1, 2)]
    assert all(p.name not in s for s in out for p in catalog.products)


@pytest.mark.parametrize("topic", list(Topic))
async def test_default_sentences_pass_the_guard(catalog, topic):
    # The runner guards every scripted sentence; the fake's own lines must never be the thing it blocks.
    pid = catalog.primary.id if topic.has_product else None
    out = await _collect(FakeReplyEngine(), _request(topic, pid, min_sentences=4), catalog)
    guard = OutputGuard()
    assert all(guard.check(s, catalog).ok for s in out), out


async def test_script_mapping_yields_its_sentences_verbatim(catalog):
    pid = catalog.primary.id
    script = {
        (pid, Topic.PRICE): ["Dạ giá **250.000đ** ạ.", "Cả nhà chốt nha."],
        (None, Topic.OPENING): ["Chào cả nhà nha."],
    }
    engine = FakeReplyEngine(script=script)
    assert await _collect(engine, _request(Topic.PRICE, pid), catalog) == script[(pid, Topic.PRICE)]
    assert await _collect(engine, _request(Topic.OPENING, None), catalog) == ["Chào cả nhà nha."]


async def test_script_miss_falls_back_to_default(catalog):
    pid = catalog.primary.id
    engine = FakeReplyEngine(script={(pid, Topic.PRICE): ["Dạ giá 250.000đ ạ."]})
    out = await _collect(engine, _request(Topic.INTRO, pid, min_sentences=1), catalog)
    assert out == [f"Câu 1 về {Topic.INTRO.label} của {catalog.primary.name}."]


async def test_requests_are_recorded(catalog):
    engine = FakeReplyEngine()
    request = _request(Topic.INTRO, catalog.primary.id)
    await _collect(engine, request, catalog)
    assert engine.narrate_requests == [request]


async def test_first_sentence_delay_and_delay_between_sentences(catalog):
    engine = FakeReplyEngine(first_sentence_delay_s=0.15, delay_s=0.1)
    stamps: list[float] = []
    start = time.monotonic()
    with anyio.fail_after(2):
        async for _ in engine.narrate(_request(Topic.INTRO, catalog.primary.id, min_sentences=3), catalog):
            stamps.append(time.monotonic() - start)
    assert len(stamps) == 3
    assert stamps[0] >= 0.14
    assert stamps[1] - stamps[0] >= 0.09
    assert stamps[2] - stamps[1] >= 0.09


async def test_no_delay_by_default(catalog):
    start = time.monotonic()
    await _collect(FakeReplyEngine(), _request(Topic.INTRO, catalog.primary.id, min_sentences=4), catalog)
    assert time.monotonic() - start < 0.1


async def test_narrate_delays_do_not_slow_reply(catalog):
    engine = FakeReplyEngine("Dạ chào bạn.", first_sentence_delay_s=1.0, delay_s=1.0)
    comment = Comment(id="c1", source="mock", author="Lan", text="chào shop", received_at=time.monotonic())
    with anyio.fail_after(0.5):
        assert [s async for s in engine.reply(comment, catalog)] == ["Dạ chào bạn."]


async def test_fail_next_raises_for_count_calls_then_recovers(catalog):
    engine = FakeReplyEngine()
    engine.fail_next("rate_limited", 2)
    request = _request(Topic.INTRO, catalog.primary.id)
    for _ in range(2):
        with pytest.raises(ReplyEngineError) as exc:
            await _collect(engine, request, catalog)
        assert exc.value.kind == "rate_limited"
    assert len(await _collect(engine, request, catalog)) == 2


async def test_fail_next_raises_before_any_sentence(catalog):
    engine = FakeReplyEngine()
    engine.fail_next("api_error", 1)
    got: list[str] = []
    with pytest.raises(ReplyEngineError):
        async for s in engine.narrate(_request(Topic.INTRO, catalog.primary.id), catalog):
            got.append(s)
    assert got == []


async def test_failed_calls_do_not_advance_the_counter(catalog):
    engine = FakeReplyEngine()
    engine.fail_next("api_error", 1)
    request = _request(Topic.INTRO, catalog.primary.id, min_sentences=1)
    with pytest.raises(ReplyEngineError):
        await _collect(engine, request, catalog)
    assert await _collect(engine, request, catalog) == [f"Câu 1 về {Topic.INTRO.label} của {catalog.primary.name}."]


async def test_fail_next_does_not_affect_reply(catalog):
    engine = FakeReplyEngine("Dạ chào bạn.")
    engine.fail_next("api_error", 1)
    comment = Comment(id="c1", source="mock", author="Lan", text="chào shop", received_at=time.monotonic())
    assert [s async for s in engine.reply(comment, catalog)] == ["Dạ chào bạn."]
    with pytest.raises(ReplyEngineError):
        await _collect(engine, _request(Topic.INTRO, catalog.primary.id), catalog)


async def test_fail_next_adds_up(catalog):
    engine = FakeReplyEngine()
    engine.fail_next("api_error", 1)
    engine.fail_next("provider_blocked", 1)
    request = _request(Topic.INTRO, catalog.primary.id)
    kinds = []
    for _ in range(2):
        with pytest.raises(ReplyEngineError) as exc:
            await _collect(engine, request, catalog)
        kinds.append(exc.value.kind)
    assert kinds == ["api_error", "provider_blocked"]


@pytest.mark.parametrize("count", [0, -1])
def test_fail_next_rejects_non_positive_count(count):
    with pytest.raises(ValueError):
        FakeReplyEngine().fail_next("api_error", count)
