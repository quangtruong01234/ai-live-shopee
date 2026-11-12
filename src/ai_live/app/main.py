"""App FastAPI: `uv run uvicorn ai_live.app.main:app --port 8000` (contracts/api.md; FR-007, FR-015, FR-021).

Startup stops outright (no "degraded" mode) on bad config, an empty AI label, an invalid content file or a missing
platform or claim phrase list (`GuardConfigError`, 004 FR-013, ADR-050), or a model chain whose startup check fails
(`config_error`, 008 FR-011): going live with wrong data is worse than not going live.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ai_live.app import routes, ws
from ai_live.app.context import AppContext
from ai_live.app.errors import install_error_handlers
from ai_live.avatar.character import AvatarModeError
from ai_live.avatar.factory import avatar_image_path, create_renderer, load_session_character
from ai_live.brain.factory import create_reply_engine
from ai_live.brain.guard import load_guard
from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.comments.classifier import PriorityClassifier
from ai_live.comments.filters import CommentFilter
from ai_live.comments.intake import CommentIntake
from ai_live.comments.mock_source import MockSource
from ai_live.core.config import Settings
from ai_live.core.events import Event, EventBus, EventType
from ai_live.core.logging import configure_logging, log_event
from ai_live.core.protocols import ReplyEngine, TTSEngine, TTSEngineError
from ai_live.director.faults import FaultInjector
from ai_live.director.latency import LatencyTracker
from ai_live.director.session_log import SessionLog
from ai_live.director.show_director import ShowDirector
from ai_live.products.models import ContentLoadError
from ai_live.products.store import DocxProductStore
from ai_live.tts.factory import create_tts

if TYPE_CHECKING:
    from ai_live.brain.chain_engine import ChainReplyEngine

logger = logging.getLogger("ai_live.app")

# Stale comments leave the control page within about a second (research R9).
QUEUE_SWEEP_INTERVAL_S = 1.0


# Re-exported: startup raises it for a character that is not this customer's or not prepared (005 FR-004).
__all__ = ["AvatarModeError", "create_app"]


def create_app(
    settings: Settings | None = None,
    *,
    env_file: str | Path | None = ".env",
    reply_engine: ReplyEngine | None = None,
    tts: TTSEngine | None = None,
) -> FastAPI:
    """Build the app. Tests pass fake `settings`, `reply_engine` and `tts`; a real run reads `.env`.

    Settings are read right here (not in the lifespan) because debug routes are registered only when `APP_ENV=dev`.
    A whitespace-only `AI_LABEL_TEXT` raises `ValidationError` at this point.
    """
    settings = settings if settings is not None else Settings(_env_file=env_file)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        session_id = await asyncio.to_thread(_new_session_id, settings.session_data_dir)
        configure_logging(settings.log_level, session_id)
        bus = EventBus()
        store = _load_store(settings, bus)
        # Raises GuardConfigError when a phrase file is missing; read off the loop like every other file.
        guard = await asyncio.to_thread(load_guard, settings.platform_phrases_path, settings.claim_phrases_path)
        # 005 FR-004: someone else's or an unprepared character stops the start here (AvatarModeError).
        character = await asyncio.to_thread(load_session_character, settings)
        # One injector for step faults (004) and entry faults (008): the route queues on `director.faults` and the
        # chain engine pulls entry faults from the same object. Only a dev app gets the hook (008 FR-016); an engine
        # passed in by a test keeps whatever hook it was built with.
        faults = FaultInjector()
        if reply_engine is not None:
            engine = reply_engine
        else:
            fault_hook = faults.take_entry if settings.app_env == "dev" else None
            engine = create_reply_engine(settings, fault_hook=fault_hook)
        chain = _as_chain(engine)
        if chain is not None:
            # 008 FR-011: a wrong key or model stops the start here, before any request, not in the first turn.
            try:
                await chain.preflight()
            except BaseException:
                await chain.aclose()
                raise
            # 008 FR-017: every chain state change reaches /ws/control as one `llm_chain` message (contracts/api.md
            # §2). The engine calls this on the loop thread, in the turn, so publishing (no await) is enough.
            chain.add_state_observer(lambda snapshot: bus.publish(Event(EventType.LLM_CHAIN, dict(snapshot))))
        # Opened after every startup check, so a refused start leaves no empty session folder behind.
        session_log = await SessionLog.open(settings.session_data_dir, session_id)
        # Subscribe before any comment can arrive, so no early drop is missing from `comments.jsonl`.
        drops = bus.subscribe()
        # Before the renderer exists, so its first mode and health events reach `avatar.jsonl` too (005 T020).
        avatar_events = bus.subscribe()
        renderer = create_renderer(settings, bus=bus, character=character)
        tts_engine = tts if tts is not None else create_tts(settings)
        await _warm_up_tts(tts_engine, settings)
        queue = InMemoryCommentQueue(max_size=settings.comment_queue_max, max_age_s=settings.comment_max_age_s, bus=bus)
        source = MockSource(max_chars=settings.comment_max_chars)
        intake = CommentIntake(
            source=source,
            comment_filter=CommentFilter.from_settings(settings),
            classifier=PriorityClassifier.from_settings(settings),
            queue=queue,
            bus=bus,
        )
        director = ShowDirector(
            queue=queue,
            store=store,
            engine=engine,
            tts=tts_engine,
            renderer=renderer,
            bus=bus,
            llm_timeout_s=settings.llm_timeout_s,
            tts_timeout_s=settings.tts_timeout_s,
            latency=LatencyTracker(),
            session_log=session_log,
            llm_model=_llm_label(settings),
            guard=guard,
            settings=settings,
            faults=faults,
        )
        app.state.ctx = AppContext(
            settings=settings,
            session_id=session_id,
            bus=bus,
            store=store,
            queue=queue,
            source=source,
            intake=intake,
            renderer=renderer,
            director=director,
            session_log=session_log,
            chain=chain,
            avatar_image=avatar_image_path(settings, character),
            character=character,
        )
        await renderer.start()
        log_event(
            logger,
            "app_started",
            app_env=settings.app_env,
            reply_engine=settings.reply_engine,
            llm_model=_llm_label(settings) if settings.reply_engine != "fake" else None,
            tts_provider=settings.tts_provider,
            avatar_mode=settings.avatar_mode,
            catalog_version=store.catalog.version,
        )
        tasks = [
            asyncio.create_task(director.run(), name="show_director"),
            asyncio.create_task(queue.run_sweeper(QUEUE_SWEEP_INTERVAL_S), name="queue_sweeper"),
            asyncio.create_task(session_log.record_drops(drops), name="session_drops"),
            asyncio.create_task(session_log.record_avatar(avatar_events), name="session_avatar"),
        ]
        try:
            yield
        finally:
            # The show stops first, so its summary is written while the session log is still open.
            await director.close()
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await renderer.stop()
            if chain is not None:
                # After the director stopped, so no turn is still streaming on the client being closed.
                await chain.aclose()
            await session_log.write_summary(
                {
                    "session_id": session_id,
                    "all": director.latency.summary().to_json(),
                    "idle_only": director.latency.summary(idle_only=True).to_json(),
                }
            )
            await _write_tts_usage(tts_engine, session_log)
            await session_log.close()
            log_event(logger, "app_stopped")

    app = FastAPI(title="AI Live", lifespan=lifespan, docs_url="/docs" if settings.app_env == "dev" else None)
    install_error_handlers(app)
    app.include_router(routes.router)
    app.include_router(ws.router)
    if settings.app_env == "dev":
        app.include_router(routes.debug_router)
    app.mount("/static", StaticFiles(directory=routes.STATIC_DIR), name="static")
    return app


def _new_session_id(base_dir: Path) -> str:
    """`YYYYMMDD-HHMMSS` local time (data-model §3); a suffix keeps two starts in the same second apart."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate, n = stamp, 2
    while (Path(base_dir) / candidate).exists():
        candidate, n = f"{stamp}-{n}", n + 1
    return candidate


def _as_chain(engine: ReplyEngine) -> ChainReplyEngine | None:
    # Imported here, like the factory does, so an app on another engine does not load the chain's HTTP stack.
    from ai_live.brain.chain_engine import ChainReplyEngine

    return engine if isinstance(engine, ChainReplyEngine) else None


async def _warm_up_tts(tts: TTSEngine, settings: Settings) -> None:
    """Load the voice model before the show so the first sentence is not slow (003 contracts/events.md §1).

    A failure is logged and the app keeps running: the operator can fix `.env` or switch sources without losing
    the session, and each sentence then reports its own `tts` error.
    """
    started = time.perf_counter()
    try:
        await tts.warm_up()
    except TTSEngineError as exc:
        log_event(
            logger,
            "tts_warm_up_failed",
            logging.ERROR,
            provider=settings.tts_provider,
            kind=exc.kind,
            message=exc.message,
        )
        return
    fields: dict[str, Any] = {"provider": settings.tts_provider, "voice": _tts_voice(settings)}
    if settings.tts_provider == "gemini":
        fields["model"] = settings.gemini_tts_model
    log_event(logger, "tts_ready", **fields, warm_up_s=round(time.perf_counter() - started, 3))


def _tts_voice(settings: Settings) -> str | None:
    if settings.tts_provider == "vieneu":
        return settings.vieneu_voice
    if settings.tts_provider == "gemini":
        return settings.gemini_tts_voice
    return None


async def _write_tts_usage(tts: TTSEngine, session_log: SessionLog) -> None:
    # Only the `SpeechTTS` wrapper counts usage; a bare engine passed by a test or tool has none to report.
    usage = getattr(tts, "usage", None)
    if usage is None:
        return
    data = usage.to_json()
    await session_log.write_tts_usage(data)
    log_event(logger, "tts_usage", **data)


def _llm_label(settings: Settings) -> str:
    """The model name in the session files and logs: the Gemini model, else the engine name (`chain`, `fake`).

    A chain turn's real model and platform are in its own `llm_turn` / `llm_attempt` lines (008 FR-005).
    """
    return settings.llm_model if settings.reply_engine == "gemini" else settings.reply_engine


def _load_store(settings: Settings, bus: EventBus) -> DocxProductStore:
    path = settings.product_data_path
    if not path.is_file():
        log_event(logger, "content_missing", logging.ERROR, path=str(path))
        raise FileNotFoundError(f"Không tìm thấy file nội dung PRODUCT_DATA_PATH={path}")
    try:
        return DocxProductStore.from_file(path, settings.content_max_bytes, bus)
    except ContentLoadError as exc:
        # List every issue at once so the author fixes them all before the next run.
        log_event(
            logger,
            "content_rejected",
            logging.ERROR,
            source=path.name,
            issue_count=len(exc.issues),
            issues=[f"[{i.code}] {i.message}" for i in exc.issues],
        )
        raise


def __getattr__(name: str) -> Any:
    # `app` is built when uvicorn reads the attribute, not at import: tests import `create_app` without a valid `.env`.
    if name == "app":
        return create_app()
    raise AttributeError(name)
