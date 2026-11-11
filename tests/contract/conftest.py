"""Contract test infrastructure (T112; contracts/adapters.md "Hành vi bắt buộc").

Each Protocol in `core/protocols.py` has a list of adapter factories (`*_FACTORIES`). A factory is a small harness
class: it builds the adapter and knows the adapter-specific tricks (how to make it fail, how to attach a fake host).
Contract tests only see the harness and the public Protocol surface, so adding an adapter (YouTube source, real TTS,
LiveTalking renderer) means adding one harness class to the right list, never editing a test.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol

import anyio
import pytest
from google.genai import types
from websockets.asyncio.client import connect as ws_connect

from ai_live.avatar.livetalking_renderer import LiveTalkingRenderer
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.avatar.switching_renderer import SwitchingRenderer
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.gemini_engine import GeminiReplyEngine
from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.comments.mock_source import MockSource
from ai_live.core.config import Settings
from ai_live.core.events import EventBus
from ai_live.core.models import Comment
from ai_live.core.protocols import (
    AvatarRenderer,
    CommentQueue,
    CommentSource,
    ProductStore,
    RendererUnavailable,
    ReplyEngine,
    ReplyEngineError,
    TTSEngine,
)
from ai_live.products.docx_loader import load_catalog
from ai_live.products.models import ProductCatalog
from ai_live.products.store import DocxProductStore
from ai_live.tts.fake_tts import FakeTTS
from ai_live.tts.gemini_tts import GeminiTTS
from ai_live.tts.vieneu_tts import VieneuTTS
from fixtures.content_builder import build_docx, product_blocks, valid_docx
from fixtures.fake_fork import FakeFork
from fixtures.fake_gemini_tts import FakeGeminiClient, FakeInteractions
from fixtures.fake_gemini_tts import http_error as gemini_http_error
from fixtures.fake_genai import FakeModels, api_error, chunk, fake_client, scripted_client
from fixtures.fake_host import FakeHostConnection
from fixtures.fake_openai import (
    ChatReply,
    Disconnect,
    Done,
    ErrorFrame,
    FakeOpenAI,
    Hang,
    Role,
    Text,
    UsageChunk,
    build_chain_engine,
    connect_error,
    content_filtered,
    empty_stream,
    hang_without_text,
    http_error,
    stream_reply,
)
from fixtures.fake_vieneu import FakeVieneuModel

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

    def narrator(self) -> ReplyEngine:
        """Engine whose `narrate` speaks at least one sentence for any valid `SegmentRequest`."""
        ...

    @classmethod
    def narrate_failures(cls) -> list[ReplyFailure]:
        """Scenarios where `narrate` itself (not construction) must raise `ReplyEngineError`."""
        ...


def _failing_fake(kind: str) -> ReplyEngine:
    engine = FakeReplyEngine(delta_chars=7)
    engine.fail_next(kind, 1)
    return engine


class FakeReplyEngineHarness:
    name = "fake"

    def narrator(self) -> ReplyEngine:
        # Default script ("Câu {n} về {topic} của {product_name}."): the contract must hold without a custom script.
        return FakeReplyEngine(delta_chars=7)

    @classmethod
    def narrate_failures(cls) -> list[ReplyFailure]:
        return [
            ReplyFailure(f"fail-next-{kind}", kind, lambda kind=kind: _failing_fake(kind))
            for kind in ("api_error", "rate_limited", "provider_blocked", "config_error")
        ]

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


NARRATE_SENTENCES = [
    "Chào cả nhà, mình bắt đầu buổi live nha.",
    "Hôm nay em giới thiệu kem chống nắng X ạ.",
]


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

    def narrator(self) -> ReplyEngine:
        client, self.models = scripted_client(NARRATE_SENTENCES)
        return GeminiReplyEngine(client, model="gemini-test", thinking_level="low", max_output_tokens=300)

    @classmethod
    def narrate_failures(cls) -> list[ReplyFailure]:
        # Provider-side failures only: a bad config raises at construction, before `narrate` is ever reached.
        return [f for f in cls.failures() if f.kind != "config_error"]

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


# ChainReplyEngine (feature 008 T018): the real engine on `fixtures/fake_openai.py`. The main entry is shaped like the
# default chain's freellmapi entry (loopback + `platform`), so the platform check runs on every contract case.
CHAIN_LOCAL_BASE = "http://127.0.0.1:3001/v1"
CHAIN_DIRECT_BASE = "https://api.groq.com/openai/v1"
CHAIN_MODEL = "gpt-oss-120b"
CHAIN_DIRECT_MODEL = "qwen/qwen3.8-27b"
CHAIN_ROUTED_VIA = "groq/openai/gpt-oss-120b"
# Short first-sentence limits keep the timeout case well inside the tests' 2 s `fail_after`.
CHAIN_ENTRY: dict[str, Any] = {
    "label": "gptoss",
    "base_url": CHAIN_LOCAL_BASE,
    "model": CHAIN_MODEL,
    "key_env": "FREELLMAPI_KEY",
    "platform": "groq",
    "first_sentence_timeout_s": 0.4,
    "params": {"reasoning_effort": "low"},
}
CHAIN_DIRECT_ENTRY: dict[str, Any] = {
    "label": "qwen",
    "base_url": CHAIN_DIRECT_BASE,
    "model": CHAIN_DIRECT_MODEL,
    "key_env": "GROQ_API_KEY",
    "first_sentence_timeout_s": 0.4,
}


def _deltas(text: str, size: int = 7) -> list[str]:
    """Cut text into small deltas that split words and sentences apart, as real providers stream."""
    return [text[i : i + size] for i in range(0, len(text), size)]


def _chain(fake: FakeOpenAI, *entries: dict[str, Any]) -> ReplyEngine:
    return build_chain_engine(fake, *(entries or (CHAIN_ENTRY,)))


def _chain_with(*replies: ChatReply) -> ReplyEngine:
    """One-entry chain (the freellmapi entry) answering with `replies`, the last one repeating."""
    fake = FakeOpenAI().chat(CHAIN_LOCAL_BASE, CHAIN_MODEL, *replies)
    return _chain(fake)


def _two_entry_chain(first: ChatReply, second: ChatReply) -> ReplyEngine:
    fake = FakeOpenAI().chat(CHAIN_LOCAL_BASE, CHAIN_MODEL, first).chat(CHAIN_DIRECT_BASE, CHAIN_DIRECT_MODEL, second)
    return _chain(fake, CHAIN_ENTRY, CHAIN_DIRECT_ENTRY)


def _chain_from_settings(**overrides: Any) -> ReplyEngine:
    # No `.env`, no key in the environment (tests/conftest.py `_clean_env`): only what the case sets.
    from ai_live.brain.chain_engine import ChainReplyEngine

    return ChainReplyEngine.from_settings(Settings(_env_file=None, reply_engine="chain", **overrides))


class ChainReplyEngineHarness:
    name = "chain"

    def __init__(self) -> None:
        self.fake = FakeOpenAI()

    def _streaming(self, text: str) -> ReplyEngine:
        self.fake.chat(
            CHAIN_LOCAL_BASE,
            CHAIN_MODEL,
            stream_reply(*_deltas(text), routed_via=CHAIN_ROUTED_VIA, usage=UsageChunk()),
        )
        return _chain(self.fake)

    def engine(self, sentences: Sequence[str]) -> ReplyEngine:
        # No trailing space after the last sentence: it only comes out through the end-of-stream `flush()`.
        return self._streaming(" ".join(sentences))

    def open_engine(self, sentences: Sequence[str]) -> ReplyEngine:
        # One delta per sentence, then the provider stalls with the HTTP response still open.
        events = [Role(), *(Text(s + " ") for s in sentences), Hang()]
        self.fake.chat(CHAIN_LOCAL_BASE, CHAIN_MODEL, ChatReply(events=events, routed_via=CHAIN_ROUTED_VIA))
        return _chain(self.fake)

    def upstream_closed(self) -> bool | None:
        assert self.fake.served, "the engine never opened a chat stream"
        return all(s.closed for s in self.fake.served)

    def narrator(self) -> ReplyEngine:
        return self._streaming(" ".join(NARRATE_SENTENCES))

    @classmethod
    def narrate_failures(cls) -> list[ReplyFailure]:
        # Config errors raise in `from_settings`, before `narrate` is ever reached.
        return [f for f in cls.failures() if f.kind != "config_error"]

    @classmethod
    def failures(cls) -> list[ReplyFailure]:
        # Inside a turn the chain only raises `rate_limited` (every reason was a rate limit) or `api_error`
        # (research R7); `config_error` only comes from `from_settings` (contracts/config.md §3).
        first = "Dạ chào bạn Lan nha. "
        return [
            ReplyFailure("http-429", "rate_limited", lambda: _chain_with(http_error(429, code="rate_limited"))),
            ReplyFailure(
                "http-429-every-entry",
                "rate_limited",
                lambda: _two_entry_chain(http_error(429, code="rate_limited"), http_error(429, type="rate_limit")),
            ),
            ReplyFailure("http-429-then-500", "api_error", lambda: _two_entry_chain(http_error(429), http_error(500))),
            ReplyFailure("http-500", "api_error", lambda: _chain_with(http_error(500))),
            ReplyFailure("http-401", "api_error", lambda: _chain_with(http_error(401, code="invalid_api_key"))),
            ReplyFailure(
                "http-502-empty-completion", "api_error", lambda: _chain_with(http_error(502, code="empty_completion"))
            ),
            ReplyFailure("connect-error", "api_error", lambda: _chain_with(connect_error())),
            ReplyFailure("empty-stream", "api_error", lambda: _chain_with(empty_stream(routed_via=CHAIN_ROUTED_VIA))),
            ReplyFailure(
                "content-filter", "api_error", lambda: _chain_with(content_filtered(routed_via=CHAIN_ROUTED_VIA))
            ),
            ReplyFailure(
                "first-sentence-timeout",
                "api_error",
                lambda: _chain_with(hang_without_text(routed_via=CHAIN_ROUTED_VIA)),
            ),
            ReplyFailure(
                "wrong-platform",
                "api_error",
                lambda: _chain_with(stream_reply(first, routed_via="cerebras/gpt-oss-120b")),
            ),
            ReplyFailure(
                "error-frame-before-first",
                "api_error",
                lambda: _chain_with(ChatReply(events=[Role(), ErrorFrame(), Done()], routed_via=CHAIN_ROUTED_VIA)),
            ),
            ReplyFailure(
                "error-frame-mid-stream",
                "api_error",
                lambda: _chain_with(
                    ChatReply(
                        events=[Role(), Text(first), Text("Còn"), ErrorFrame(), Done()], routed_via=CHAIN_ROUTED_VIA
                    )
                ),
            ),
            ReplyFailure(
                "disconnect-mid-stream",
                "api_error",
                lambda: _chain_with(
                    ChatReply(events=[Role(), Text(first), Text("Còn"), Disconnect()], routed_via=CHAIN_ROUTED_VIA)
                ),
            ),
            ReplyFailure("empty-chain", "config_error", lambda: _chain_from_settings(llm_chain=[])),
            ReplyFailure("default-chain-without-keys", "config_error", lambda: _chain_from_settings()),
        ]


REPLY_ENGINE_FACTORIES: list[type[ReplyEngineHarness]] = [
    FakeReplyEngineHarness,
    GeminiReplyEngineHarness,
    ChainReplyEngineHarness,
]

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


class VieneuTTSHarness:
    """`VieneuTTS` over a fake loaded model: no download, same threading and resampling as the real one."""

    name = "vieneu"

    def _make(self, model: FakeVieneuModel) -> TTSEngine:
        return VieneuTTS(voice="Thục Đoan", cpu_threads=2, model_cache=Path("unused"), load_model=lambda _t: model)

    def make(self) -> TTSEngine:
        return self._make(FakeVieneuModel())

    def make_failing(self) -> TTSEngine:
        # The lazy warm-up read is call 1; the sentence itself fails.
        return self._make(FakeVieneuModel(fail_after_calls=1))


class GeminiTTSHarness:
    """`GeminiTTS` over a fake `genai.Client`: no network, no quota."""

    name = "gemini"

    def _make(self, interactions: FakeInteractions) -> TTSEngine:
        return GeminiTTS(client=FakeGeminiClient(interactions), model="gemini-3.8-flash-tts", voice="Leda")

    def make(self) -> TTSEngine:
        return self._make(FakeInteractions())

    def make_failing(self) -> TTSEngine:
        return self._make(FakeInteractions(call_error=gemini_http_error(500)))


TTS_FACTORIES: list[type[TTSHarness]] = [FakeTTSHarness, VieneuTTSHarness, GeminiTTSHarness]

# ---------------------------------------------------------------- AvatarRenderer


class RendererHarness(Protocol):
    """`report_*` play the role of the output side (browser, LiveTalking) for the sentence being spoken now."""

    name: ClassVar[str]
    # What `speak` raises with no host page: the still image has nowhere to play (`RendererUnavailable`); lip-sync
    # has no WebRTC session to feed (`RendererError("lipsync_unavailable")`).
    unavailable_error: ClassVar[type[Exception]]

    def make(self) -> AvatarRenderer: ...

    async def connect_host(self, renderer: AvatarRenderer, *, auto_ack: bool) -> None:
        """Attach a playback host. `auto_ack=False` holds every sentence until `report_*` is called."""
        ...

    async def report_playback_started(self, renderer: AvatarRenderer) -> None: ...

    async def report_sentence_played(self, renderer: AvatarRenderer) -> None: ...

    async def aclose(self) -> None: ...


class StaticRendererHarness:
    name = "static"
    unavailable_error: ClassVar[type[Exception]] = RendererUnavailable

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

    async def aclose(self) -> None:
        return None


class SwitchingStaticHarness(StaticRendererHarness):
    """`SwitchingRenderer` built for `AVATAR_MODE=static`: every sentence goes to the still image."""

    name = "switching-static"

    def make(self) -> AvatarRenderer:
        lipsync = LiveTalkingRenderer("http://127.0.0.1:9", StaticRenderer())
        return SwitchingRenderer(lipsync, StaticRenderer(ack_timeout_s=5.0), configured="static")


class LiveTalkingHarness:
    """`LiveTalkingRenderer` against the fake fork; the fork plays the role of the output side."""

    name = "livetalking"
    # No host page means no WebRTC session either: reported as the page, like 001 (005 contracts/adapters.md §5).
    unavailable_error: ClassVar[type[Exception]] = RendererUnavailable
    _PLACEHOLDER = "ws://fork.invalid"

    def __init__(self) -> None:
        self.fork: FakeFork | None = None
        self.conn: FakeHostConnection | None = None
        self._acked: set[tuple[str, str, int]] = set()

    def _connect(self, uri: str, **kwargs: Any) -> Any:
        # The fork starts only in `connect_host`, after `make` fixed the URL, so point the socket at it lazily.
        assert self.fork is not None, "the renderer connected before a host reported a session"
        return ws_connect(uri.replace(self._PLACEHOLDER, f"ws://127.0.0.1:{self.fork.port}"), **kwargs)

    def _lipsync(self, host: StaticRenderer) -> LiveTalkingRenderer:
        return LiveTalkingRenderer(
            self._PLACEHOLDER.replace("ws://", "http://"),
            host,
            first_frame_timeout_s=5.0,
            ack_timeout_s=5.0,
            reconnect_max_s=0.2,
            connect=self._connect,
        )

    def make(self) -> AvatarRenderer:
        return self._lipsync(StaticRenderer())

    def _host_side(self, renderer: Any) -> Any:
        return renderer._host

    def _lipsync_of(self, renderer: Any) -> LiveTalkingRenderer:
        return renderer

    async def connect_host(self, renderer: Any, *, auto_ack: bool) -> None:
        self.fork = await FakeFork().start()
        self.fork.ack = auto_ack
        host = self._host_side(renderer)
        self.conn = FakeHostConnection(host, auto_ack=auto_ack)
        await host.attach(self.conn)
        host.handle_message(self.conn, {"type": "ready", "lipsync_session": "sess-1"})
        lipsync = self._lipsync_of(renderer)
        with anyio.fail_after(3):
            while not lipsync.ready:  # noqa: ASYNC110
                await anyio.sleep(0.01)

    async def _ack(self, kind: str) -> None:
        assert self.fork is not None
        with anyio.fail_after(2):
            while True:
                if self.fork.sentences:
                    last = self.fork.sentences[-1]
                    key = (last.utterance_id, last.seq)
                    if (kind, *key) not in self._acked:
                        break
                await anyio.sleep(0.01)
        self._acked.add((kind, *key))
        await self.fork.send({"type": kind, "utterance_id": key[0], "seq": key[1]})

    async def report_playback_started(self, renderer: AvatarRenderer) -> None:
        await self._ack("playback_started")

    async def report_sentence_played(self, renderer: AvatarRenderer) -> None:
        await self._ack("sentence_played")

    async def aclose(self) -> None:
        if self.fork is not None:
            await self.fork.stop()


class SwitchingLiveTalkingHarness(LiveTalkingHarness):
    """`SwitchingRenderer` for `AVATAR_MODE=livetalking`: the host page attaches to it, sentences go to the fork."""

    name = "switching-livetalking"

    def make(self) -> AvatarRenderer:
        static = StaticRenderer(ack_timeout_s=5.0)
        return SwitchingRenderer(self._lipsync(static), static, configured="livetalking")

    def _host_side(self, renderer: Any) -> Any:
        return renderer

    def _lipsync_of(self, renderer: Any) -> LiveTalkingRenderer:
        return renderer.lipsync


RENDERER_FACTORIES: list[type[RendererHarness]] = [
    StaticRendererHarness,
    SwitchingStaticHarness,
    LiveTalkingHarness,
    SwitchingLiveTalkingHarness,
]

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
async def renderer_harness(request: pytest.FixtureRequest) -> AsyncIterator[RendererHarness]:
    harness = request.param()
    yield harness
    await harness.aclose()


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
    if "narrate_failure" in metafunc.fixturenames:
        cases = [(h, c) for h in REPLY_ENGINE_FACTORIES for c in h.narrate_failures()]
        metafunc.parametrize("narrate_failure", [c for _, c in cases], ids=[f"{h.name}-{c.id}" for h, c in cases])
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
