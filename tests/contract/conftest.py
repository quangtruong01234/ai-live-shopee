"""Contract test infrastructure (T112; contracts/adapters.md "Hành vi bắt buộc").

Each Protocol in `core/protocols.py` has a list of adapter factories (`*_FACTORIES`). A factory is a small harness
class: it builds the adapter and knows the adapter-specific tricks (how to make it fail, how to attach a fake host).
Contract tests only see the harness and the public Protocol surface, so adding an adapter (YouTube source, real TTS,
LiveTalking renderer) means adding one harness class to the right list, never editing a test.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

import anyio
import pytest
from google.genai import types

from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.gemini_engine import GeminiReplyEngine
from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.comments.mock_source import MockSource
from ai_live.core.events import EventBus
from ai_live.core.models import Comment
from ai_live.core.protocols import (
    AvatarRenderer,
    CommentQueue,
    CommentSource,
    ProductStore,
    ReplyEngine,
    ReplyEngineError,
    TTSEngine,
)
from ai_live.products.docx_loader import load_catalog
from ai_live.products.models import ProductCatalog
from ai_live.products.store import DocxProductStore
from ai_live.tts.fake_tts import FakeTTS
from fixtures.content_builder import build_docx, product_blocks, valid_docx
from fixtures.fake_genai import FakeModels, api_error, chunk, fake_client, scripted_client
from fixtures.fake_host import FakeHostConnection

# ---------------------------------------------------------------- ReplyEngine


@dataclass(frozen=True)
class ReplyFailure:
    """A provider failure scenario. `make` may itself raise (config errors surface at construction)."""

    id: str
    kind: str
    make: Callable[[], ReplyEngine]


class ReplyEngineHarness(Protocol):
    name: ClassVar[str]

    def engine(self, sentences: Sequence[str]) -> ReplyEngine:
        """Engine whose `reply` speaks exactly `sentences`, streamed in small deltas."""
        ...

    def open_engine(self, sentences: Sequence[str]) -> ReplyEngine:
        """Engine that speaks `sentences` and then keeps the provider stream open (more may come)."""
        ...

    def upstream_closed(self) -> bool | None:
        """After `open_engine`: whether the provider stream was released; `None` if the adapter has none."""
        ...

    @classmethod
    def failures(cls) -> list[ReplyFailure]: ...


class FakeReplyEngineHarness:
    name = "fake"

    def engine(self, sentences: Sequence[str]) -> ReplyEngine:
        return FakeReplyEngine(" ".join(sentences), delta_chars=7)

    def open_engine(self, sentences: Sequence[str]) -> ReplyEngine:
        return FakeReplyEngine(" ".join(sentences), delta_chars=7)

    def upstream_closed(self) -> bool | None:
        return None

    @classmethod
    def failures(cls) -> list[ReplyFailure]:
        cases = [
            ReplyFailure(
                f"before-first-{kind}", kind, lambda kind=kind: FakeReplyEngine(error=ReplyEngineError(kind, "giả lập"))
            )
            for kind in ("api_error", "rate_limited", "provider_blocked", "config_error")
        ]
        cases.append(
            ReplyFailure(
                "mid-stream-api_error",
                "api_error",
                lambda: FakeReplyEngine(
                    "Dạ chào bạn. Còn câu nữa.",
                    error=ReplyEngineError("api_error", "giả lập"),
                    error_after_sentences=1,
                ),
            )
        )
        return cases


def _gemini(models: FakeModels, thinking_level: str = "low") -> GeminiReplyEngine:
    return GeminiReplyEngine(
        fake_client(models), model="gemini-test", thinking_level=thinking_level, max_output_tokens=300
    )


class GeminiReplyEngineHarness:
    name = "gemini"

    def __init__(self) -> None:
        self.models: FakeModels | None = None

    def engine(self, sentences: Sequence[str]) -> ReplyEngine:
        client, self.models = scripted_client(sentences)
        return GeminiReplyEngine(client, model="gemini-test", thinking_level="low", max_output_tokens=300)

    def open_engine(self, sentences: Sequence[str]) -> ReplyEngine:
        # One chunk per sentence, then the provider stalls: closing must not wait for it.
        self.models = FakeModels([chunk(s + " ") for s in sentences], hang_after=len(sentences))
        return _gemini(self.models)

    def upstream_closed(self) -> bool | None:
        assert self.models is not None
        return self.models.closed

    @classmethod
    def failures(cls) -> list[ReplyFailure]:
        return [
            ReplyFailure("http-500-on-call", "api_error", lambda: _gemini(FakeModels(call_error=api_error(500)))),
            ReplyFailure(
                "http-503-mid-stream",
                "api_error",
                lambda: _gemini(FakeModels([chunk("Dạ chào bạn. ")], iter_error=api_error(503, "UNAVAILABLE"))),
            ),
            ReplyFailure(
                "http-429",
                "rate_limited",
                lambda: _gemini(FakeModels(call_error=api_error(429, "RESOURCE_EXHAUSTED", "quota"))),
            ),
            ReplyFailure(
                "safety-finish",
                "provider_blocked",
                lambda: _gemini(FakeModels([chunk(None, finish_reason=types.FinishReason.SAFETY)])),
            ),
            ReplyFailure(
                "prompt-blocked",
                "provider_blocked",
                lambda: _gemini(FakeModels([chunk(None, block_reason=types.BlockedReason.SAFETY)])),
            ),
            ReplyFailure(
                "empty-text",
                "provider_blocked",
                lambda: _gemini(FakeModels([chunk(""), chunk(None, finish_reason=types.FinishReason.STOP)])),
            ),
            ReplyFailure(
                "bad-thinking-level", "config_error", lambda: _gemini(FakeModels(), thinking_level="khong-co")
            ),
        ]


REPLY_ENGINE_FACTORIES: list[type[ReplyEngineHarness]] = [FakeReplyEngineHarness, GeminiReplyEngineHarness]

# ---------------------------------------------------------------- TTSEngine


class TTSHarness(Protocol):
    name: ClassVar[str]

    def make(self) -> TTSEngine: ...

    def make_failing(self) -> TTSEngine:
        """Engine whose `synthesize` raises (provider down, bad voice, ...)."""
        ...


class FakeTTSHarness:
    name = "fake"

    def make(self) -> TTSEngine:
        return FakeTTS()

    def make_failing(self) -> TTSEngine:
        return FakeTTS(fail=True)


TTS_FACTORIES: list[type[TTSHarness]] = [FakeTTSHarness]

# ---------------------------------------------------------------- AvatarRenderer


class RendererHarness(Protocol):
    """`report_*` play the role of the output side (browser, LiveTalking) for the sentence being spoken now."""

    name: ClassVar[str]

    def make(self) -> AvatarRenderer: ...

    async def connect_host(self, renderer: AvatarRenderer, *, auto_ack: bool) -> None:
        """Attach a playback host. `auto_ack=False` holds every sentence until `report_*` is called."""
        ...

    async def report_playback_started(self, renderer: AvatarRenderer) -> None: ...

    async def report_sentence_played(self, renderer: AvatarRenderer) -> None: ...


class StaticRendererHarness:
    name = "static"

    def __init__(self) -> None:
        self.conn: FakeHostConnection | None = None
        self._acked: set[tuple[str, str, int]] = set()

    def make(self) -> AvatarRenderer:
        # Generous ack timeout: these tests drive acks by hand and must never hit it.
        return StaticRenderer(ack_timeout_s=5.0)

    async def connect_host(self, renderer: Any, *, auto_ack: bool) -> None:
        self.conn = FakeHostConnection(renderer, auto_ack=auto_ack)
        await renderer.attach(self.conn)
        renderer.handle_message(self.conn, {"type": "ready"})

    async def _ack(self, renderer: Any, kind: str) -> None:
        """Ack the newest fully sent sentence that has not had this ack yet (never re-ack an older one)."""
        assert self.conn is not None
        with anyio.fail_after(2):
            while True:
                starts = self.conn.json_messages("sentence_start")
                ended = {(m["utterance_id"], m["seq"]) for m in self.conn.json_messages("sentence_end")}
                if starts:
                    key = (starts[-1]["utterance_id"], starts[-1]["seq"])
                    if key in ended and (kind, *key) not in self._acked:
                        break
                await anyio.sleep(0.01)
        self._acked.add((kind, *key))
        renderer.handle_message(self.conn, {"type": kind, "utterance_id": key[0], "seq": key[1]})

    async def report_playback_started(self, renderer: AvatarRenderer) -> None:
        await self._ack(renderer, "playback_started")

    async def report_sentence_played(self, renderer: AvatarRenderer) -> None:
        await self._ack(renderer, "sentence_played")


RENDERER_FACTORIES: list[type[RendererHarness]] = [StaticRendererHarness]

# ---------------------------------------------------------------- CommentQueue / CommentSource


class QueueHarness(Protocol):
    name: ClassVar[str]

    def make(
        self, *, max_size: int, max_age_s: float, bus: EventBus | None, clock: Callable[[], float]
    ) -> CommentQueue: ...


class InMemoryQueueHarness:
    name = "memory"

    def make(
        self,
        *,
        max_size: int = 50,
        max_age_s: float = 30.0,
        bus: EventBus | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> CommentQueue:
        return InMemoryCommentQueue(max_size=max_size, max_age_s=max_age_s, bus=bus, clock=clock)


COMMENT_QUEUE_FACTORIES: list[type[QueueHarness]] = [InMemoryQueueHarness]


class SourceHarness(Protocol):
    name: ClassVar[str]

    def make(self) -> CommentSource: ...


class MockSourceHarness:
    name = "mock"

    def make(self) -> CommentSource:
        return MockSource()


COMMENT_SOURCE_FACTORIES: list[type[SourceHarness]] = [MockSourceHarness]

# ---------------------------------------------------------------- ProductStore


@dataclass(frozen=True)
class InvalidContent:
    id: str
    data: bytes
    source_name: str


class ProductStoreHarness(Protocol):
    name: ClassVar[str]

    def make(self, bus: EventBus | None = None) -> ProductStore:
        """Store already holding a valid catalog."""
        ...

    def valid_replacement(self) -> tuple[bytes, str]:
        """Valid content that differs from the initial catalog."""
        ...

    @classmethod
    def invalid_contents(cls) -> list[InvalidContent]: ...


class DocxProductStoreHarness:
    name = "docx"
    MAX_BYTES = 1_000_000

    def make(self, bus: EventBus | None = None) -> ProductStore:
        catalog = load_catalog(valid_docx(), "valid.docx", self.MAX_BYTES)
        return DocxProductStore(catalog, self.MAX_BYTES, bus)

    def valid_replacement(self) -> tuple[bytes, str]:
        blocks = [
            *product_blocks("Serum dưỡng ẩm A", "chính", price="320.000đ"),
            *product_blocks("Mặt nạ ngủ B", "phụ", price="89.000đ", forbidden=()),
        ]
        return build_docx(blocks), "moi.docx"

    @classmethod
    def invalid_contents(cls) -> list[InvalidContent]:
        return [
            InvalidContent("not-docx", "đây không phải file Word".encode(), "ghi-chu.txt"),
            InvalidContent("corrupt-zip", b"PK\x03\x04" + b"\x00" * 200, "hong.docx"),
            InvalidContent("too-large", b"PK\x03\x04" + b"\x00" * cls.MAX_BYTES, "qua-lon.docx"),
            InvalidContent("no-products", build_docx([("p", "Chỉ có ghi chú, chưa có sản phẩm")]), "trong.docx"),
            InvalidContent(
                "missing-price", build_docx(product_blocks("Kem chống nắng X", price=None)), "thieu-gia.docx"
            ),
        ]


PRODUCT_STORE_FACTORIES: list[type[ProductStoreHarness]] = [DocxProductStoreHarness]

# ---------------------------------------------------------------- pytest wiring


def _ids(factories: Sequence[type]) -> list[str]:
    return [f.name for f in factories]


@pytest.fixture(params=REPLY_ENGINE_FACTORIES, ids=_ids(REPLY_ENGINE_FACTORIES))
def reply_engine_harness(request: pytest.FixtureRequest) -> ReplyEngineHarness:
    return request.param()


@pytest.fixture(params=TTS_FACTORIES, ids=_ids(TTS_FACTORIES))
def tts_harness(request: pytest.FixtureRequest) -> TTSHarness:
    return request.param()


@pytest.fixture(params=RENDERER_FACTORIES, ids=_ids(RENDERER_FACTORIES))
def renderer_harness(request: pytest.FixtureRequest) -> RendererHarness:
    return request.param()


@pytest.fixture(params=COMMENT_QUEUE_FACTORIES, ids=_ids(COMMENT_QUEUE_FACTORIES))
def queue_harness(request: pytest.FixtureRequest) -> QueueHarness:
    return request.param()


@pytest.fixture(params=COMMENT_SOURCE_FACTORIES, ids=_ids(COMMENT_SOURCE_FACTORIES))
def source_harness(request: pytest.FixtureRequest) -> SourceHarness:
    return request.param()


@pytest.fixture(params=PRODUCT_STORE_FACTORIES, ids=_ids(PRODUCT_STORE_FACTORIES))
def product_store_harness(request: pytest.FixtureRequest) -> ProductStoreHarness:
    return request.param()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Per-adapter scenario lists become one test case each, with ids like `gemini-http-429`."""
    if "reply_failure" in metafunc.fixturenames:
        cases = [(h, c) for h in REPLY_ENGINE_FACTORIES for c in h.failures()]
        metafunc.parametrize("reply_failure", [c for _, c in cases], ids=[f"{h.name}-{c.id}" for h, c in cases])
    if "store_and_invalid" in metafunc.fixturenames:
        # The harness class rides along so the store and its invalid content come from the same adapter.
        pairs = [(h, c) for h in PRODUCT_STORE_FACTORIES for c in h.invalid_contents()]
        metafunc.parametrize("store_and_invalid", pairs, ids=[f"{h.name}-{c.id}" for h, c in pairs])


@pytest.fixture
def catalog() -> ProductCatalog:
    return load_catalog(valid_docx(), "valid.docx", 5_000_000)


@pytest.fixture
def comment() -> Comment:
    return Comment(id="c1", source="mock", author="Lan", text="giá bao nhiêu vậy shop?", received_at=time.monotonic())
