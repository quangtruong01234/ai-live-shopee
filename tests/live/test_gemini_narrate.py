"""T038 (004): real Gemini `narrate()` on `data/products/demo.docx` (marker `live_llm`, deselected by default).

Run only with the user's consent: `uv run pytest -m live_llm tests/live/test_gemini_narrate.py` when `.env` has
`GEMINI_API_KEY`. Each run uses 2 free-tier requests (ADR-018).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_live.brain.gemini_engine import GeminiReplyEngine
from ai_live.brain.guard import OutputGuard, load_platform_phrases
from ai_live.brain.sanitize import clean_spoken
from ai_live.core.config import Settings
from ai_live.core.models import SegmentRequest, Topic
from ai_live.core.text import extract_amounts
from ai_live.products.docx_loader import load_catalog_file

pytestmark = [pytest.mark.live_llm, pytest.mark.anyio]

DEMO = Path("data/products/demo.docx")


@pytest.fixture(scope="module")
def live_settings():
    # conftest clears the environment; the key is read again from `.env`. The engine is pinned because the
    # default became `chain` (feature 008) and these tests exercise Gemini directly.
    s = Settings(reply_engine="gemini")
    if s.gemini_api_key is None:
        pytest.skip("chưa có GEMINI_API_KEY trong .env")
    return s


@pytest.fixture(scope="module")
def catalog(live_settings):
    return load_catalog_file(DEMO, live_settings.content_max_bytes)


@pytest.fixture(scope="module")
def guard(live_settings):
    return OutputGuard(load_platform_phrases(live_settings.platform_phrases_path))


async def _narrate(settings, catalog, request: SegmentRequest) -> list[str]:
    engine = GeminiReplyEngine.from_settings(settings)
    return [s async for s in engine.narrate(request, catalog)]


def _spoken(sentences: list[str]) -> list[str]:
    # The runner cleans before the guard (ADR-031); a symbols-only sentence is dropped, not spoken.
    return [c for s in sentences if (c := clean_spoken(s))]


async def test_opening_segment_is_short_and_guarded(live_settings, catalog, guard):
    request = SegmentRequest(
        segment_id="live-0001", topic=Topic.OPENING, product_id=None, min_sentences=2, max_sentences=3
    )
    spoken = _spoken(await _narrate(live_settings, catalog, request))
    assert spoken, "Gemini returned no sentence"
    # The engine never cuts the count (the runner does), so allow a little slack over max before failing the prompt.
    assert 1 <= len(spoken) <= request.max_sentences + 1, spoken
    for sentence in spoken:
        assert guard.check(sentence, catalog).ok, (sentence, guard.check(sentence, catalog))


async def test_price_segment_reads_only_file_prices(live_settings, catalog, guard):
    product = catalog.primary
    request = SegmentRequest(
        segment_id="live-0002",
        topic=Topic.PRICE,
        product_id=product.id,
        min_sentences=3,
        max_sentences=6,
        previous_sentence=f"Hôm nay em giới thiệu {product.name} nha anh chị.",
    )
    spoken = _spoken(await _narrate(live_settings, catalog, request))
    text = " ".join(spoken)
    assert spoken, "Gemini returned no sentence"
    for sentence in spoken:
        assert guard.check(sentence, catalog).ok, (sentence, guard.check(sentence, catalog))
    amounts = set(extract_amounts(text))
    assert amounts, text
    assert amounts <= set(catalog.known_amounts), text
    low, high = product.price_range
    assert {low, high} & amounts, text
