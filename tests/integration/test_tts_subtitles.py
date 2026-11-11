"""T029 (003): the host page shows the sentence as written while the voice source reads it in words (US2 #5, FR-009).

Both speaking paths use the real `create_tts` (`fake` provider) with the engine behind the wrapper swapped for one
that records the text it receives: a comment reply through ShowDirector and a script segment through ScriptRunner.
The price is the catalog's own (`250.000đ`), so the output guard lets the sentence through.
"""

from __future__ import annotations

import pytest

from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.core.models import TurnOutcome
from ai_live.tts.factory import create_tts
from ai_live.tts.fake_tts import FakeTTS
from ai_live.tts.speech import SpeechTTS

from .test_pipeline_fake import Pipeline, _comment, _queued
from .test_script_runner import ScriptRig, wait_until

pytestmark = pytest.mark.anyio

PRICE_SENTENCE = "Giá chỉ 250.000đ thôi ạ."
PRICE_SPOKEN = "Giá chỉ hai trăm năm mươi ngàn đồng thôi ạ."


class _RecordingEngine(FakeTTS):
    def __init__(self) -> None:
        super().__init__(sample_rate=16000)
        self.received: list[str] = []

    def synthesize(self, text: str):
        self.received.append(text)
        return super().synthesize(text)


def _recording_tts(settings) -> tuple[SpeechTTS, _RecordingEngine]:
    tts = create_tts(settings)
    tts.engine = recorder = _RecordingEngine()
    return tts, recorder


async def test_comment_reply_subtitle_keeps_the_written_price(settings):
    tts, recorder = _recording_tts(settings)
    p = Pipeline(FakeReplyEngine(f"Dạ chào bạn Lan nha. {PRICE_SENTENCE}"), tts=tts)
    await p.connect()
    utt = await p.director.run_turn(_queued(_comment("giá bao nhiêu vậy shop?")))

    assert utt.outcome is TurnOutcome.COMPLETED
    assert PRICE_SENTENCE in p.spoken()
    assert PRICE_SPOKEN in recorder.received
    assert not any("250.000đ" in text for text in recorder.received)


class _PriceFirstEngine(FakeReplyEngine):
    """The first segment opens with the price sentence; the rest are the usual numbered lines."""

    async def narrate(self, request, catalog):
        first = not self.narrate_requests
        if first:
            self.narrate_requests.append(request)
            yield PRICE_SENTENCE
            yield "Chị em nhớ ghé shop nha."
            return
        async for line in super().narrate(request, catalog):
            yield line


async def test_script_segment_subtitle_keeps_the_written_price(tmp_path, settings):
    tts, recorder = _recording_tts(settings)
    async with ScriptRig(tmp_path, settings, _PriceFirstEngine(), tts=tts) as rig:
        await wait_until(lambda: PRICE_SPOKEN in recorder.received and PRICE_SENTENCE in rig.started_texts())

    assert PRICE_SENTENCE in rig.started_texts()
    assert not any("250.000đ" in text for text in recorder.received)
