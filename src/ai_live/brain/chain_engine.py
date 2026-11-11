"""`ReplyEngine` over an ordered chain of pinned OpenAI-compatible models (feature 008, ADR-035, ADR-037).

Each turn tries the entries in order and speaks with the first one that produces a first sentence in time; once a
sentence has been yielded the turn stays on that entry (FR-008). The per-entry first-sentence limit is the only time
limit here: the whole-turn limits stay with `ScriptRunner` and `ShowDirector` (contracts/adapters.md §1).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, TypedDict
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from ai_live.brain.chain_state import RESTING_REASONS, AttemptReason, ChainState
from ai_live.brain.openai_compat import (
    ModelListing,
    OpenAICompatClient,
    ProviderFailure,
    ResolvedEntry,
    StreamMeta,
    Usage,
    make_http_client,
)
from ai_live.brain.prompt import build_system_prompt, build_user_message
from ai_live.brain.script_prompt import build_script_system_prompt, build_segment_message
from ai_live.brain.sentence_splitter import SentenceSplitter
from ai_live.core.config import ChainEntryConfig, Settings
from ai_live.core.logging import log_event
from ai_live.core.models import Comment, SegmentRequest
from ai_live.core.protocols import ReplyEngineError
from ai_live.products.models import ProductCatalog

__all__ = [
    "Attempt",
    "ChainEntrySnapshot",
    "ChainReplyEngine",
    "ChainSnapshot",
    "FaultHook",
    "PreflightResult",
    "ResolvedEntry",
    "StateObserver",
    "TurnRecord",
    "Usage",
]

logger = logging.getLogger("ai_live.brain")

FaultHook = Callable[[str], str | None]  # label -> entry fault mode or None (dev only, research R8)

# `key_env` value -> `Settings` field holding the key (data-model §1).
_KEY_FIELDS = {
    "GEMINI_API_KEY": "gemini_api_key",
    "FREELLMAPI_KEY": "freellmapi_key",
    "GROQ_API_KEY": "groq_api_key",
}
# The engine owns these request fields; an entry overriding them would break streaming or the pinned model.
_FORBIDDEN_PARAMS = ("model", "messages", "stream", "stream_options")
_PREFLIGHT_UNREACHABLE = frozenset({AttemptReason.CONNECTION, AttemptReason.TIMEOUT})

# Entry fault modes (research R8). The list itself lives in `director/faults.py` (`ENTRY_FAULT_MODES`); `brain/` must
# not import `director/`, so the mode strings are mapped here. Modes that fail at once, with no network call:
_IMMEDIATE_FAULTS = {
    "rate_limited": AttemptReason.RATE_LIMITED,
    "overloaded": AttemptReason.OVERLOADED,
    "wrong_platform": AttemptReason.WRONG_PLATFORM,
}
_FAULT_MODES = frozenset({*_IMMEDIATE_FAULTS, "empty", "timeout", "interrupted"})

PreflightProblem = Literal["unreachable", "auth", "model_missing", "model_unavailable", "http_error"]


@dataclass(frozen=True)
class Attempt:
    """One try of one entry within a turn (data-model §4)."""

    label: str
    outcome: Literal["ok", "failed", "skipped", "cancelled"]
    reason: AttemptReason | None
    routed_via: str | None  # full X-Routed-Via value, also on wrong_platform
    elapsed_s: float
    injected: bool = False


@dataclass(frozen=True)
class TurnRecord:
    """Sent to the turn observers when a turn ends, whatever the outcome (data-model §5)."""

    turn_key: str  # comment.id or segment_id
    kind: Literal["reply", "segment"]
    label: str | None
    model: str | None
    provider: str | None
    attempts: list[Attempt]
    outcome: Literal["ok", "interrupted", "exhausted", "cancelled"]
    usage: Usage | None


class ChainEntrySnapshot(TypedDict):
    """One `entries[]` item of a `ChainSnapshot` (data-model §6). Plain JSON values: the app sends it as is."""

    label: str
    model: str
    platform: str | None
    position: int
    status: Literal["ready", "resting"]
    reason: str | None  # an `AttemptReason` value, only when resting
    retry_at: str | None  # ISO 8601 with offset, only when resting


class ChainSnapshot(TypedDict):
    """Chain state for the control page (data-model §6): `/api/state` `llm_chain` and the `llm_chain` event payload."""

    entries: list[ChainEntrySnapshot]
    last_entry: str | None  # entry that spoke the latest turn; `None` until one has
    using_backup: bool  # `last_entry` is not the entry at position 1


StateObserver = Callable[[ChainSnapshot], None]


@dataclass(frozen=True)
class PreflightResult:
    """Startup check of one entry (data-model §9); only logged, not kept."""

    label: str
    position: int
    ok: bool
    problem: PreflightProblem | None = None
    detail: str | None = None  # already redacted
    execution_status: str | None = None


def _now() -> datetime:
    return datetime.now().astimezone()


def _config_error(message: str) -> ReplyEngineError:
    return ReplyEngineError("config_error", message)


def _host(base_url: str) -> str | None:
    return urlsplit(base_url).hostname


class ChainReplyEngine:
    """Implements `ReplyEngine` (contracts/adapters.md §2). One instance serves the app run; `ChainState` is shared by
    the scripted and comment paths (research R5)."""

    def __init__(
        self,
        entries: list[ResolvedEntry],
        *,
        cooldown_s: float,
        max_tokens: int,
        script_max_tokens: int,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] = _now,
        fault_hook: FaultHook | None = None,
    ) -> None:
        if not entries:
            raise ValueError("ChainReplyEngine needs at least one entry")
        self._entries = list(entries)
        self.cooldown_s = cooldown_s
        self._max_tokens = max_tokens
        self._script_max_tokens = script_max_tokens
        self._http = make_http_client(transport)
        self._client = OpenAICompatClient(self._http, [entry.key for entry in self._entries])
        self._state = ChainState([entry.label for entry in self._entries], clock)
        self._fault_hook = fault_hook
        self._turn_observers: list[Callable[[TurnRecord], None]] = []
        self._state_observers: list[StateObserver] = []
        self._positions = {entry.label: entry.position for entry in self._entries}
        self._last_entry: str | None = None  # shared by both paths, like `ChainState` (research R5)

    # -- construction -------------------------------------------------------------------------------------------------

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        only: str | None = None,
        fault_hook: FaultHook | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> ChainReplyEngine:
        """Check the chain rules of contracts/config.md §3 and build the engine.

        Every problem is reported in one `config_error`, one line each, so a broken `.env` is fixed in one pass.
        `only=LABEL` builds a one-entry chain with no cooldown (qa_eval `--entry`, research R10); only that entry is
        checked, so evaluating one model does not need the keys of the others. `transport` is for tests.
        """
        chain = list(settings.llm_chain)
        if not chain:
            raise _config_error("LLM_CHAIN trống: cần ít nhất một mục khi REPLY_ENGINE=chain")

        problems: list[str] = []
        seen: set[str] = set()
        for config in chain:
            if config.label in seen:
                problems.append(f'LLM_CHAIN: nhãn "{config.label}" bị trùng')
            seen.add(config.label)

        numbered = [(config.position or index, config) for index, config in enumerate(chain, start=1)]
        if only is not None:
            numbered = [(position, config) for position, config in numbered if config.label == only][:1]
            if not numbered:
                labels = ", ".join(config.label for config in chain)
                raise _config_error(f'LLM_CHAIN không có mục "{only}"; các mục hiện có: {labels}')

        entries: list[ResolvedEntry] = []
        for position, config in numbered:
            entry_problems, key = _check_entry(settings, position, config)
            problems.extend(entry_problems)
            if not entry_problems and key is not None:
                entries.append(ResolvedEntry(config=config, position=position, local=config.local, key=key))

        # The first-sentence limits run one after another in the worst case; together they must fit in the
        # shortest whole-turn limit, or the backup entries could never be reached in time (FR-009).
        total = sum(config.first_sentence_timeout_s for _, config in numbered)
        limit = float(min(settings.llm_timeout_s, settings.script_llm_timeout_s))
        if total > limit:
            problems.append(
                f"LLM_CHAIN: tổng first_sentence_timeout_s là {round(total, 3)} s, vượt {limit} s "
                "(min của LLM_TIMEOUT_S và SCRIPT_LLM_TIMEOUT_S)"
            )
        if problems:
            raise _config_error("\n".join(problems))
        return cls(
            entries,
            cooldown_s=0.0 if only is not None else settings.llm_chain_cooldown_s,
            max_tokens=settings.llm_max_tokens,
            script_max_tokens=settings.script_max_tokens,
            transport=transport,
            fault_hook=fault_hook,
        )

    # -- public surface -----------------------------------------------------------------------------------------------

    @property
    def entries(self) -> list[ChainEntryConfig]:
        return [entry.config for entry in self._entries]

    def add_turn_observer(self, cb: Callable[[TurnRecord], None]) -> None:
        self._turn_observers.append(cb)

    def add_state_observer(self, cb: StateObserver) -> None:
        """`cb` gets a fresh `snapshot()` whenever the chain state changes: an entry starts resting, or a turn speaks
        with an entry other than `last_entry` (contracts/api.md §2). Called before that turn's first sentence is
        yielded, so the control page sees a switch while the backup entry speaks (SC-007).

        A rest running out is not reported: no task watches the clock, and the page reads a past `retry_at` as ready
        (research R9). Skipped entries, `blocked` failures and cancellations change nothing, so they send nothing.
        """
        self._state_observers.append(cb)

    def snapshot(self) -> ChainSnapshot:
        """Chain state as read now (data-model §6); a rest whose `retry_at` has passed reads as ready (FR-019)."""
        rows: list[ChainEntrySnapshot] = []
        for entry in self._entries:
            state = self._state.status(entry.label)
            resting = state.status == "resting"
            rows.append(
                ChainEntrySnapshot(
                    label=entry.label,
                    model=entry.config.model,
                    platform=entry.config.platform,
                    position=entry.position,
                    status=state.status,
                    reason=state.reason.value if resting and state.reason is not None else None,
                    retry_at=state.retry_at.isoformat(timespec="seconds")
                    if resting and state.retry_at is not None
                    else None,
                )
            )
        last = self._last_entry
        return ChainSnapshot(
            entries=rows,
            last_entry=last,
            using_backup=last is not None and self._positions[last] != 1,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]:
        messages = [
            {"role": "system", "content": build_system_prompt(catalog)},
            {"role": "user", "content": build_user_message(comment)},
        ]
        return self._turn("reply", comment.id, messages, self._max_tokens, {"comment_id": comment.id})

    def narrate(self, request: SegmentRequest, catalog: ProductCatalog) -> AsyncIterator[str]:
        messages = [
            {"role": "system", "content": build_script_system_prompt(catalog)},
            {"role": "user", "content": build_segment_message(request, catalog)},
        ]
        fields = {"segment_id": request.segment_id, "topic": request.topic.value}
        return self._turn("segment", request.segment_id, messages, self._script_max_tokens, fields)

    # -- preflight ----------------------------------------------------------------------------------------------------

    async def preflight(self) -> list[PreflightResult]:
        """One `GET /models` per distinct (`base_url`, `key_env`), then check every entry (research R9).

        Raises `config_error` listing every failing entry. Called once at startup, never during a show.
        """
        groups: dict[tuple[str, str], ResolvedEntry] = {}
        for entry in self._entries:
            groups.setdefault((entry.config.base_url, entry.config.key_env), entry)

        async def fetch(entry: ResolvedEntry) -> ModelListing | ProviderFailure:
            try:
                return await self._client.list_models(entry.config.base_url, entry.key)
            except ProviderFailure as exc:
                return exc

        listings = dict(zip(groups, await asyncio.gather(*(fetch(e) for e in groups.values())), strict=True))
        results: list[PreflightResult] = []
        messages: list[str] = []
        for entry in self._entries:
            result, message = _preflight_entry(entry, listings[(entry.config.base_url, entry.config.key_env)])
            results.append(result)
            if message is not None:
                messages.append(message)
            level = logging.INFO
            if not result.ok:
                level = logging.ERROR
            elif result.execution_status == "exhausted":
                level = logging.WARNING  # today's quota is used up; it may come back, so it does not block startup
            optional = {"problem": result.problem, "detail": result.detail, "execution_status": result.execution_status}
            log_event(
                logger,
                "llm_preflight",
                level,
                label=result.label,
                position=result.position,
                ok=result.ok,
                **{name: value for name, value in optional.items() if value is not None},
            )
        if messages:
            raise _config_error("\n".join(messages))
        return results

    # -- one turn -----------------------------------------------------------------------------------------------------

    async def _turn(
        self,
        kind: Literal["reply", "segment"],
        turn_key: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        log_fields: dict[str, Any],
    ) -> AsyncIterator[str]:
        attempts: list[Attempt] = []
        winner: ResolvedEntry | None = None
        meta = StreamMeta()
        stream: AsyncGenerator[str, None] | None = None
        outcome: Literal["ok", "interrupted", "exhausted", "cancelled"] = "exhausted"
        previous_failure: tuple[str, AttemptReason] | None = None
        try:
            for entry in self._entries:
                state = self._state.status(entry.label)
                if state.status == "resting":
                    attempts.append(Attempt(entry.label, "skipped", state.reason, None, 0.0))
                    self._log_attempt(entry, attempts[-1], None, None, log_fields)
                    continue
                if previous_failure is not None:
                    log_event(
                        logger,
                        "llm_switch",
                        logging.WARNING,
                        **log_fields,
                        from_label=previous_failure[0],
                        to_label=entry.label,
                        reason=previous_failure[1].value,
                    )

                meta = StreamMeta()
                # Asked only for an entry that is really tried, so a fault queued for a resting entry waits (R8).
                fault = self._take_fault(entry)
                interrupt = fault == "interrupted"  # needs the real stream: it cuts it after the first sentence
                injected = fault is not None and not interrupt
                if injected:
                    stream = _injected_stream(fault)
                else:
                    stream = self._client.stream_chat(entry, messages, max_tokens, meta)
                splitter = SentenceSplitter()
                started = time.monotonic()
                first: list[str] = []
                ended = False
                failure: ProviderFailure | None = None
                try:
                    # Research R1: the timeout block must close before the first `yield`, because the consumer may
                    # run each step in its own task and a timeout scope cannot span tasks.
                    async with asyncio.timeout(entry.config.first_sentence_timeout_s):
                        while not first:
                            try:
                                delta = await anext(stream)
                            except StopAsyncIteration:
                                ended = True
                                first = splitter.flush()
                                break
                            first = splitter.feed(delta)
                except TimeoutError:
                    failure = ProviderFailure(
                        AttemptReason.TIMEOUT,
                        None,
                        f"quá {entry.config.first_sentence_timeout_s:g} s chưa có câu đầu",
                        routed_via=meta.routed_via,
                    )
                except ProviderFailure as exc:
                    failure = exc
                except asyncio.CancelledError:
                    elapsed = round(time.monotonic() - started, 3)
                    attempts.append(Attempt(entry.label, "cancelled", None, meta.routed_via, elapsed, injected))
                    raise
                if failure is None and not first:
                    # A content-filter stop says nothing about the entry's health (research R3), an empty stream does.
                    blocked = meta.finish_reason == "content_filter"
                    reason = AttemptReason.BLOCKED if blocked else AttemptReason.EMPTY
                    detail = "nhà cung cấp chặn nội dung" if blocked else "luồng kết thúc mà không có chữ"
                    failure = ProviderFailure(reason, None, detail, routed_via=meta.routed_via)

                elapsed = round(time.monotonic() - started, 3)
                if failure is not None:
                    await _close(stream)
                    stream = None
                    attempts.append(Attempt(entry.label, "failed", failure.reason, meta.routed_via, elapsed, injected))
                    self._log_attempt(entry, attempts[-1], meta, failure, log_fields)
                    self._rest(entry, failure.reason, log_fields)
                    previous_failure = (entry.label, failure.reason)
                    continue

                winner = entry
                attempts.append(Attempt(entry.label, "ok", None, meta.routed_via, elapsed))
                self._log_attempt(entry, attempts[-1], meta, None, log_fields)
                if self._last_entry != entry.label:
                    self._last_entry = entry.label
                    self._notify_state()
                try:
                    if interrupt:
                        yield first[0]
                        raise ProviderFailure(
                            AttemptReason.INTERRUPTED, None, "lỗi giả lập (dev)", routed_via=meta.routed_via
                        )
                    for sentence in first:
                        yield sentence
                    if not ended:
                        async for delta in stream:
                            for sentence in splitter.feed(delta):
                                yield sentence
                        for sentence in splitter.flush():
                            yield sentence
                except ProviderFailure as exc:
                    outcome = "interrupted"
                    # Keep `routed_via`: the record must still say which platform spoke the first sentences.
                    attempts[-1] = replace(
                        attempts[-1], outcome="failed", reason=AttemptReason.INTERRUPTED, injected=interrupt
                    )
                    self._log_attempt(entry, attempts[-1], meta, exc, log_fields)
                    self._rest(entry, AttemptReason.INTERRUPTED, log_fields)
                    raise ReplyEngineError(
                        "api_error", f"Model {entry.label} ngắt giữa chừng sau câu đầu: {exc.message}"
                    ) from exc
                outcome = "ok"
                return

            raise self._exhausted(attempts, log_fields)
        except (asyncio.CancelledError, GeneratorExit):
            # Skip, pause, stop or an outer limit: not the entry's fault, so `ChainState` is left as it is.
            outcome = "cancelled"
            raise
        finally:
            if stream is not None:
                await _close(stream)
            model = (meta.model or winner.config.model) if winner is not None else None
            provider = self._provider(winner, meta) if winner is not None else None
            if winner is not None and meta.usage is not None:
                log_event(
                    logger,
                    "llm_usage",
                    **log_fields,
                    label=winner.label,
                    model=model,
                    provider=provider,
                    prompt_tokens=meta.usage.prompt_tokens,
                    output_tokens=meta.usage.completion_tokens,
                    cached_tokens=meta.usage.cached_tokens,
                )
            self._emit(
                TurnRecord(
                    turn_key=turn_key,
                    kind=kind,
                    label=winner.label if winner is not None else None,
                    model=model,
                    provider=provider,
                    attempts=attempts,
                    outcome=outcome,
                    usage=meta.usage if winner is not None else None,
                )
            )

    # -- helpers ------------------------------------------------------------------------------------------------------

    def _take_fault(self, entry: ResolvedEntry) -> str | None:
        """The fault mode queued for this entry (dev only, research R8), or `None`.

        A broken hook or an unknown mode must not change a real turn: it is logged and the entry is tried normally.
        """
        if self._fault_hook is None:
            return None
        try:
            mode = self._fault_hook(entry.label)
        except Exception:
            logger.exception("fault hook failed")
            return None
        if mode is None:
            return None
        if mode not in _FAULT_MODES:
            logger.warning("unknown entry fault mode %r for %s; ignored", mode, entry.label)
            return None
        return mode

    @staticmethod
    def _provider(entry: ResolvedEntry, meta: StreamMeta | None) -> str | None:
        routed_via = meta.routed_via if meta is not None else None
        return routed_via or _host(entry.config.base_url)

    def _log_attempt(
        self,
        entry: ResolvedEntry,
        attempt: Attempt,
        meta: StreamMeta | None,
        failure: ProviderFailure | None,
        log_fields: dict[str, Any],
    ) -> None:
        fields: dict[str, Any] = {
            **log_fields,
            "label": entry.label,
            "model": (meta.model if meta is not None else None) or entry.config.model,
            "provider": self._provider(entry, meta),
            "outcome": attempt.outcome,
            "elapsed_s": attempt.elapsed_s,
            "injected": attempt.injected,
        }
        if attempt.routed_via is not None:
            fields["routed_via"] = attempt.routed_via
        if attempt.reason is not None:
            fields["reason"] = attempt.reason.value
        if failure is not None and failure.status is not None:
            fields["status"] = failure.status
        log_event(logger, "llm_attempt", **fields)

    def _rest(self, entry: ResolvedEntry, reason: AttemptReason, log_fields: dict[str, Any]) -> None:
        if reason not in RESTING_REASONS or self.cooldown_s <= 0:
            return
        retry_at = self._state.rest(entry.label, self.cooldown_s, reason)
        log_event(
            logger,
            "llm_entry_rest",
            logging.WARNING,
            **log_fields,
            label=entry.label,
            reason=reason.value,
            seconds=self.cooldown_s,
            retry_at=retry_at.isoformat(timespec="seconds"),
        )
        self._notify_state()

    def _exhausted(self, attempts: list[Attempt], log_fields: dict[str, Any]) -> ReplyEngineError:
        """Research R7: `rate_limited` only when every entry is out for a rate limit, else `api_error`."""
        reasons = [attempt.reason for attempt in attempts]
        kind = "rate_limited" if reasons and all(r is AttemptReason.RATE_LIMITED for r in reasons) else "api_error"
        parts = []
        for attempt in attempts:
            reason = attempt.reason.value if attempt.reason is not None else "?"
            if attempt.outcome == "skipped":
                retry_at = self._state.status(attempt.label).retry_at
                when = f", thử lại {retry_at:%H:%M:%S}" if retry_at is not None else ""
                parts.append(f"{attempt.label} đang nghỉ ({reason}{when})")
            else:
                parts.append(f"{attempt.label} lỗi {reason}")
        log_event(
            logger,
            "llm_chain_exhausted",
            logging.ERROR,
            **log_fields,
            kind=kind,
            entries=[{"label": a.label, "reason": a.reason.value if a.reason else None} for a in attempts],
        )
        return ReplyEngineError(kind, "Hết chuỗi model: " + "; ".join(parts))

    def _emit(self, record: TurnRecord) -> None:
        for cb in self._turn_observers:
            try:
                cb(record)
            except Exception:
                # An observer bug (stats, control page) must never break the spoken turn.
                logger.exception("turn observer failed")

    def _notify_state(self) -> None:
        for cb in self._state_observers:
            try:
                cb(self.snapshot())  # one snapshot per observer: none can change what another one sees
            except Exception:
                # The control page is a view; its bug must never break the spoken turn.
                logger.exception("state observer failed")


async def _injected_stream(mode: str) -> AsyncGenerator[str, None]:
    """Stands in for `stream_chat` without any network call, failing the way a real provider would (research R8).

    The result goes through the same classification and switch code as a real failure: `empty` ends with no text and
    `timeout` hangs until the entry's own first-sentence limit, so the operator can still cancel the turn meanwhile.
    """
    if mode == "timeout":
        await asyncio.Event().wait()
    reason = _IMMEDIATE_FAULTS.get(mode)
    if reason is not None:
        raise ProviderFailure(reason, None, f"lỗi giả lập (dev): {mode}")
    return
    yield  # unreachable; makes this function an async generator


async def _close(stream: AsyncGenerator[str, None]) -> None:
    """Release the HTTP response; a failure while closing must not replace the turn's own outcome or error."""
    try:
        await stream.aclose()
    except Exception:
        logger.debug("closing the provider stream failed", exc_info=True)


def _check_entry(settings: Settings, position: int, config: ChainEntryConfig) -> tuple[list[str], SecretStr | None]:
    """The per-entry rules of contracts/config.md §3; returns the problems and the resolved key."""
    prefix = f"LLM_CHAIN mục {position} ({config.label}):"
    problems: list[str] = []
    model = config.model.strip()
    lowered = model.lower()
    if not model:
        problems.append(f"{prefix} thiếu model")
    elif lowered in ("auto", "fusion") or lowered.startswith("auto:"):
        # A router model picks its own target, so replies could come from an unpinned, unevaluated model (ADR-035).
        problems.append(f'{prefix} không được dùng model "{config.model}"; ghi tên model cụ thể (ADR-035)')
    if config.local and not config.platform:
        problems.append(f'{prefix} base_url trỏ tới dịch vụ gom key nên phải khai platform (ví dụ "cloudflare")')
    key: SecretStr | None = None
    field = _KEY_FIELDS.get(config.key_env)
    if field is None:
        problems.append(
            f'{prefix} key_env "{config.key_env}" không hợp lệ; dùng GEMINI_API_KEY, FREELLMAPI_KEY hoặc GROQ_API_KEY'
        )
    else:
        secret: SecretStr | None = getattr(settings, field)
        value = secret.get_secret_value().strip() if secret is not None else ""
        if value:
            key = SecretStr(value)
        else:
            problems.append(f"{prefix} {config.key_env} chưa có giá trị trong .env")
    for name in _FORBIDDEN_PARAMS:
        if name in config.params:
            problems.append(f'{prefix} params không được đặt "{name}"')
    return problems, key


def _preflight_entry(
    entry: ResolvedEntry, listing: ModelListing | ProviderFailure
) -> tuple[PreflightResult, str | None]:
    """Check one entry against its `GET /models` answer (contracts/config.md §4)."""
    config = entry.config
    prefix = f"LLM_CHAIN mục {entry.position} ({config.label}):"

    def failed(problem: PreflightProblem, detail: str | None, message: str) -> tuple[PreflightResult, str]:
        return PreflightResult(config.label, entry.position, False, problem, detail), f"{prefix} {message}"

    if isinstance(listing, ProviderFailure):
        if listing.reason in _PREFLIGHT_UNREACHABLE:
            hint = "; dịch vụ gom key đã chạy chưa?" if entry.local else ""
            return failed("unreachable", listing.message, f"không kết nối được {config.base_url}{hint}")
        if listing.status in (401, 403):
            return failed("auth", f"status={listing.status}", f"{config.key_env} bị từ chối ({listing.status})")
        return failed("http_error", f"status={listing.status}", f"kiểm model trả status {listing.status}")
    row = listing.get(config.model)
    if row is None:
        return failed("model_missing", None, f'không có model "{config.model}" ở {config.base_url}')
    if row.available is False:
        detail = f"unavailable_reason={row.unavailable_reason}"
        return failed("model_unavailable", detail, f'model "{config.model}" chưa dùng được ({detail})')
    return PreflightResult(config.label, entry.position, True, execution_status=row.execution_status), None
