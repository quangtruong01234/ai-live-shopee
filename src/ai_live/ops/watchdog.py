"""Show watchdog (007 US2, data-model §2, research R1-R3, R9).

`ShowWatchdog` is pure: it is told what happened and what time it is, and answers with the alert changes, so the rules
table of research R2 is tested with a fake clock. `WatchdogService` feeds it from the event bus and the renderer's
playback notices, publishes each change as an `ALERT` event, writes it to `alerts.jsonl` and runs the one auto-skip.

The watchdog only observes: it never sits on the sentence path (constitution VI, FR-012). Its one action is the same
call as the "Bỏ qua câu đang nói" button, made once per silent stretch (R3).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from ai_live.core.events import Event, EventBus, EventType, Subscription
from ai_live.core.logging import log_event
from ai_live.core.models import HostStatus

if TYPE_CHECKING:
    from ai_live.core.config import Settings
    from ai_live.director.session_log import SessionLog

logger = logging.getLogger("ai_live.ops")

TEXT_MAX_CHARS = 120
# Enough to recognise a SENTENCE event that the bus delivers after its own playback notice.
_STARTED_MEMORY = 64


class AlertKind(StrEnum):
    SILENCE = "silence"
    FROZEN = "frozen"
    AUDIO_MISSING = "audio_missing"
    FORK_LOST = "fork_lost"
    HOST_CLOSED = "host_closed"
    FALLBACK_MODE = "fallback_mode"
    STATIC_MODE = "static_mode"


class AlertLevel(StrEnum):
    WARNING = "warning"  # cảnh báo
    OPERATOR = "operator"  # cần người vận hành


ChangeEvent = Literal["open", "level", "auto_skip", "close"]

# Roots first: a kind is only decided after every kind that can cover it (research R2).
_ORDER = (
    AlertKind.HOST_CLOSED,
    AlertKind.FORK_LOST,
    AlertKind.STATIC_MODE,
    AlertKind.FALLBACK_MODE,
    AlertKind.FROZEN,
    AlertKind.AUDIO_MISSING,
    AlertKind.SILENCE,
)
COVERED_BY: dict[AlertKind, frozenset[AlertKind]] = {
    AlertKind.HOST_CLOSED: frozenset(),
    AlertKind.FORK_LOST: frozenset({AlertKind.HOST_CLOSED}),
    AlertKind.STATIC_MODE: frozenset({AlertKind.HOST_CLOSED}),
    AlertKind.FALLBACK_MODE: frozenset(),
    AlertKind.FROZEN: frozenset({AlertKind.HOST_CLOSED, AlertKind.FORK_LOST, AlertKind.STATIC_MODE}),
    AlertKind.AUDIO_MISSING: frozenset({AlertKind.HOST_CLOSED}),
    AlertKind.SILENCE: frozenset(
        {AlertKind.HOST_CLOSED, AlertKind.FORK_LOST, AlertKind.FROZEN, AlertKind.AUDIO_MISSING}
    ),
}
# Signals about the show's own flow; a pause ends them (the root alerts are about the setup and stay).
PAUSE_CLOSES = frozenset({AlertKind.SILENCE, AlertKind.FROZEN, AlertKind.AUDIO_MISSING})
# What the viewer cannot get back without a person: the host tab gone, or the lip-sync fork gone.
_OPERATOR_KINDS = frozenset({AlertKind.HOST_CLOSED, AlertKind.FORK_LOST})

_WATCHED_STATES = frozenset({"running", "closing", "paused"})

# Runbook §4 wording; the operator reads these while talking to the customer, so one short sentence each.
OPERATOR_ACTION = (
    "Cần người vận hành: xem terminal app và mục Lỗi của show; không cứu được trong khoảng 1 phút thì người dẫn "
    "báo khách và phát video dự phòng (runbook §5)"
)
_ACTIONS: dict[AlertKind, str] = {
    AlertKind.HOST_CLOSED: 'Mở lại /host, bấm "Bắt đầu" rồi chia sẻ lại tab vào Meet',
    # 007 T056: pressed before the app saw the new fork, the reconnect failed twice and fell back again.
    AlertKind.FORK_LOST: (
        'Xem terminal fork; fork chết thì chạy lại run.ps1, đợi banner này tắt rồi bấm "Bật lại nhân vật nhép miệng"'
    ),
    AlertKind.STATIC_MODE: 'Xem terminal fork; fork còn chạy thì bấm "Bật lại nhân vật nhép miệng"',
    AlertKind.FALLBACK_MODE: "Để show chạy chế độ dự phòng; nếu kéo dài thì chuyển sang video dự phòng (runbook §5)",
    AlertKind.FROZEN: 'Xem terminal fork; fork còn chạy thì tải lại /host, bấm "Bắt đầu" rồi chia sẻ lại tab vào Meet',
    AlertKind.AUDIO_MISSING: 'Bấm "Bắt đầu" trên /host; kiểm Meet đang chia sẻ tab kèm âm thanh',
}
# 006 contracts/api.md §8: with OUTPUT_MODE=obs the picture and sound leave through the OBS Browser Source.
_OBS_ACTIONS: dict[AlertKind, str] = {
    AlertKind.HOST_CLOSED: (
        "Kiểm OBS còn chạy; chuột phải nguồn AI host → Refresh; đừng để trang /host trên Chrome phát thay"
    ),
    AlertKind.FROZEN: "Xem terminal fork; fork còn chạy thì chuột phải nguồn → Refresh",
    AlertKind.AUDIO_MISSING: 'Kiểm "Control audio via OBS" và thanh âm lượng nguồn trong mixer OBS',
}
_AFTER_SKIP_ACTION = 'Đợi câu kế tiếp; nếu vẫn im thì bấm "Bỏ qua câu đang nói" hoặc "Tạm dừng"'


def _iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _short(text: str | None) -> str | None:
    if text is None:
        return None
    return text if len(text) <= TEXT_MAX_CHARS else text[: TEXT_MAX_CHARS - 1] + "…"


def _secs(value: float) -> int:
    return max(0, round(value))


@dataclass
class Alert:
    alert_id: str
    kind: AlertKind
    level: AlertLevel
    show_id: str
    started_at: str  # ISO, when the threshold was crossed
    ended_at: str | None
    seconds: float | None  # set on close: from when the signal began, not from the threshold
    utterance_id: str | None
    text: str | None
    message: str
    action: str
    auto_action: str | None
    close_reason: str | None  # "cleared" | "covered" | "paused" | "show_ended"

    @property
    def state(self) -> str:
        return "open" if self.ended_at is None else "closed"

    def to_json(self) -> dict[str, Any]:
        """The `alert` object of contracts/api.md §3."""
        body = asdict(self)
        body["kind"] = self.kind.value
        body["level"] = self.level.value
        body["state"] = self.state
        return body


@dataclass(frozen=True)
class AlertChange:
    event: ChangeEvent
    alert: Alert  # a copy taken at the change: later changes never rewrite it

    def record(self, at: str) -> dict[str, Any]:
        """One `alerts.jsonl` line (contracts/files.md §3)."""
        return {"event": self.event, "at": at, "alert": self.alert.to_json()}


@dataclass(frozen=True)
class WatchdogThresholds:
    silence_s: float = 5.0
    frozen_s: float = 3.0
    autoskip_s: float = 15.0
    audio_ack_s: float = 3.0
    # The fork starts a sentence ~3 s after it is handed over (005 sentence gap p95 2.98 s, 007 T054 max 3.16 s),
    # so the still-image deadline raised false alerts in lip-sync mode.
    audio_ack_lipsync_s: float = 6.0
    # 006 FR-010, obs mode only: an OBS source that stops sending heartbeats is as good as gone.
    host_stale_s: float = 10.0

    @classmethod
    def from_settings(cls, settings: Settings) -> WatchdogThresholds:
        return cls(
            silence_s=settings.watchdog_silence_s,
            frozen_s=settings.watchdog_frozen_s,
            autoskip_s=settings.watchdog_autoskip_s,
            audio_ack_s=settings.watchdog_audio_ack_s,
            audio_ack_lipsync_s=settings.watchdog_audio_ack_lipsync_s,
            host_stale_s=settings.watchdog_host_stale_s,
        )


@dataclass
class _Signal:
    since: float
    utterance_id: str | None = None
    text: str | None = None
    detail: str | None = None


class ShowWatchdog:
    """The rules of research R2/R3 over a fake-able clock. Every `on_*` and `tick` returns the alert changes it made."""

    def __init__(
        self,
        thresholds: WatchdogThresholds | None = None,
        *,
        lipsync: bool = False,
        output_mode: str = "meet",
        wall: Callable[[], str] = _iso_now,
    ) -> None:
        self.thresholds = thresholds or WatchdogThresholds()
        self.lipsync = lipsync  # AVATAR_MODE=livetalking: frozen, fork_lost and static_mode only apply then
        self.obs = output_mode == "obs"
        self._wall = wall
        self._show_id: str | None = None
        self._state: str | None = None
        self._mode = "normal"
        self._mode_since = 0.0
        # Setup state, kept across shows. None = not reported yet, which never raises an alert.
        self._host_connected: bool | None = None
        self._host_lost_at = 0.0
        # Last sign of life from the playing connection (connect or heartbeat); only the obs stale rule reads it.
        self._host_seen_at = 0.0
        self._fork_connected: bool | None = None
        self._fork_lost_at = 0.0
        self._avatar_active: str | None = None
        self._static_since = 0.0
        # Flow state of the current show.
        self._playing: set[tuple[str, int]] = set()
        self._started: deque[tuple[str, int]] = deque(maxlen=_STARTED_MEMORY)
        self._silence_mark = 0.0
        self._silence_covered = False
        self._skipped_at: float | None = None
        self._last_utterance: str | None = None
        self._last_text: str | None = None
        self._unacked: _Signal | None = None
        self._last_status: HostStatus | None = None
        self._frames: int | None = None
        self._frames_since: float | None = None
        self._audio_bad_since: float | None = None
        self._open: dict[AlertKind, Alert] = {}
        self._since: dict[AlertKind, float] = {}

    # ---------- reading ----------

    @property
    def open_alerts(self) -> list[Alert]:
        return [replace(alert) for kind in _ORDER if (alert := self._open.get(kind)) is not None]

    @property
    def show_id(self) -> str | None:
        return self._show_id

    @property
    def watching(self) -> bool:
        return self._show_id is not None and self._state in _WATCHED_STATES

    # ---------- inputs ----------

    def on_show_state(self, show_id: str, state: str, mode: str, now: float) -> list[AlertChange]:
        changes: list[AlertChange] = []
        if show_id != self._show_id:
            changes += self._close_all("show_ended", now)
            self._show_id = show_id
            self._state = None
            self._reset_flow(now)
        previous = self._state
        self._state = state
        if mode != self._mode:
            self._mode = mode
            self._mode_since = now
        if state in ("ended", "idle"):
            changes += self._close_all("show_ended", now)
            return changes
        if state == "paused" and previous != "paused":
            for kind in PAUSE_CLOSES:
                changes += self._close(kind, "paused", now)
            self._reset_flow(now, keep_playing=True)
        elif previous in (None, "paused") and state in ("running", "closing"):
            # The silent stretch starts again when the show (re)starts: waiting in pause is not silence.
            self._reset_flow(now, keep_playing=previous == "paused")
        return changes + self._evaluate(now)

    def on_sentence(self, utterance_id: str, seq: int, text: str, now: float) -> list[AlertChange]:
        """A sentence was handed to the renderer: it must be heard within the ack deadline (research R1 b)."""
        key = (utterance_id, seq)
        # The bus may deliver SENTENCE after the renderer already said it is playing.
        if key not in self._started and key not in self._playing and self._unacked is None:
            self._unacked = _Signal(now, utterance_id, _short(text))
        return self._evaluate(now)

    def on_playback_started(self, utterance_id: str, seq: int, text: str, now: float) -> list[AlertChange]:
        key = (utterance_id, seq)
        self._playing.add(key)
        self._started.append(key)
        # Any sentence heard proves the audio path; one never acknowledged before it (a render error) is history.
        self._unacked = None
        self._skipped_at = None
        self._last_utterance = utterance_id
        self._last_text = _short(text) or self._last_text
        return self._evaluate(now)

    def on_playback_ended(self, utterance_id: str, seq: int, now: float) -> list[AlertChange]:
        self._playing.discard((utterance_id, seq))
        if not self._playing:
            self._silence_mark = now
        return self._evaluate(now)

    def on_playback_stopped(self, now: float) -> list[AlertChange]:
        """A skip or interrupt cut the sentence: silence counts from here, and the cut sentence is not "unheard"."""
        self._playing.clear()
        self._unacked = None
        self._silence_mark = now
        return self._evaluate(now)

    def on_host_connection(self, connected: bool, now: float, role: str | None = None) -> list[AlertChange]:
        if self.obs:
            # A Chrome /host tab that got to play in obs mode does not reach the OBS output (contracts §8).
            connected = connected and role == "obs"
        if connected and self._host_connected is not True:
            self._host_seen_at = now
        if not connected and self._host_connected is not False:
            self._host_lost_at = now
            # That tab's heartbeats and its pending sentence went with it.
            self._clear_heartbeat()
            self._playing.clear()
            self._unacked = None
        self._host_connected = connected
        return self._evaluate(now)

    def on_lipsync_health(self, connected: bool, now: float) -> list[AlertChange]:
        if not connected and self._fork_connected is not False:
            self._fork_lost_at = now
        self._fork_connected = connected
        return self._evaluate(now)

    def on_avatar_mode(self, active: str, now: float) -> list[AlertChange]:
        if active == "static" and self._avatar_active != "static":
            self._static_since = now
        self._avatar_active = active
        return self._evaluate(now)

    def on_host_status(self, status: HostStatus) -> list[AlertChange]:
        """One heartbeat; its own `received_at` is the time, so the frozen rule only ever compares two heartbeats."""
        now = status.received_at
        self._last_status = status
        self._host_seen_at = max(self._host_seen_at, now)
        if status.frames is None:
            self._frames = None
            self._frames_since = None
        elif status.frames != self._frames:
            self._frames = status.frames
            self._frames_since = now
        if self._audio_bad(status):
            if self._audio_bad_since is None:
                self._audio_bad_since = now
        else:
            self._audio_bad_since = None
        return self._evaluate(now)

    def tick(self, now: float) -> list[AlertChange]:
        return self._evaluate(now)

    # ---------- rules ----------

    @property
    def _lipsync_active(self) -> bool:
        return self.lipsync and self._avatar_active != "static"

    def _audio_bad(self, status: HostStatus) -> bool:
        # The sound goes out on one path: the WebRTC <video> in lip-sync, the AudioContext with the still image.
        if self._lipsync_active:
            return status.video_muted is True or status.video_paused is True
        return status.audio in ("suspended", "closed")

    def _signals(self, now: float) -> dict[AlertKind, _Signal]:
        t = self.thresholds
        found: dict[AlertKind, _Signal] = {}
        if self._host_connected is False:
            found[AlertKind.HOST_CLOSED] = _Signal(self._host_lost_at)
        elif self.obs and self._host_connected and now - self._host_seen_at > t.host_stale_s:
            # Not in meet mode: Chrome throttles timers in a background tab (Q27), so a shared tab would look stale.
            found[AlertKind.HOST_CLOSED] = _Signal(self._host_seen_at, detail="stale")
        if self.lipsync and self._fork_connected is False:
            found[AlertKind.FORK_LOST] = _Signal(self._fork_lost_at)
        if self.lipsync and self._avatar_active == "static":
            found[AlertKind.STATIC_MODE] = _Signal(self._static_since)
        if self._mode == "fallback":
            found[AlertKind.FALLBACK_MODE] = _Signal(self._mode_since)
        if self._state == "paused":
            return found
        last = self._last_status
        if (
            self._lipsync_active
            and last is not None
            and self._frames_since is not None
            and last.received_at - self._frames_since > t.frozen_s
        ):
            found[AlertKind.FROZEN] = _Signal(self._frames_since, self._last_utterance, self._last_text)
        audio: _Signal | None = None
        if self._audio_bad_since is not None:
            audio = _Signal(self._audio_bad_since, self._last_utterance, self._last_text, "heartbeat")
        ack_s = t.audio_ack_lipsync_s if self._lipsync_active else t.audio_ack_s
        if self._unacked is not None and now - self._unacked.since > ack_s:
            if audio is None or self._unacked.since < audio.since:
                audio = replace(self._unacked, detail="unacked")
        if audio is not None:
            found[AlertKind.AUDIO_MISSING] = audio
        if not self._playing and now - self._silence_mark > t.silence_s:
            found[AlertKind.SILENCE] = _Signal(self._silence_mark, self._last_utterance, self._last_text)
        return found

    def _evaluate(self, now: float) -> list[AlertChange]:
        if not self.watching:
            return []
        signals = self._signals(now)
        active: dict[AlertKind, _Signal] = {}
        for kind in _ORDER:
            signal = signals.get(kind)
            if signal is not None and not (COVERED_BY[kind] & active.keys()):
                active[kind] = signal
        if COVERED_BY[AlertKind.SILENCE] & active.keys():
            # Under a root the gap is the root's problem; once the root clears, silence counts afresh from then.
            self._silence_mark = now
            self._skipped_at = None
            self._silence_covered = True
        elif self._silence_covered:
            self._silence_covered = False
            self._silence_mark = now
            self._skipped_at = None
            active.pop(AlertKind.SILENCE, None)
        if AlertKind.HOST_CLOSED in active:
            self._unacked = None
        changes: list[AlertChange] = []
        for kind in _ORDER:
            if kind in self._open and kind not in active:
                changes += self._close(kind, "covered" if kind in signals else "cleared", now)
        for kind in _ORDER:
            signal = active.get(kind)
            if signal is None:
                continue
            if kind not in self._open:
                changes.append(self._opened(kind, signal, now))
            if kind is AlertKind.SILENCE:
                changes += self._silence_steps(now)
        return changes

    def _silence_steps(self, now: float) -> list[AlertChange]:
        """Research R3: one auto-skip at `autoskip_s`, then `operator` after a further `silence_s` without speech."""
        alert = self._open[AlertKind.SILENCE]
        since = self._since[AlertKind.SILENCE]
        t = self.thresholds
        if self._skipped_at is None and alert.auto_action is None and now - since >= t.autoskip_s:
            self._skipped_at = now
            alert.auto_action = "skip"
            alert.message = f"Host im lặng {_secs(now - since)} giây, đã tự bỏ câu đang kẹt"
            alert.action = _AFTER_SKIP_ACTION
            return [AlertChange("auto_skip", replace(alert))]
        if self._skipped_at is not None and alert.level is AlertLevel.WARNING and now - self._skipped_at >= t.silence_s:
            alert.level = AlertLevel.OPERATOR
            alert.message = f"Host vẫn im lặng {_secs(now - since)} giây dù đã tự bỏ câu"
            alert.action = OPERATOR_ACTION
            return [AlertChange("level", replace(alert))]
        return []

    def _opened(self, kind: AlertKind, signal: _Signal, now: float) -> AlertChange:
        assert self._show_id is not None
        alert = Alert(
            alert_id=uuid.uuid4().hex,
            kind=kind,
            level=AlertLevel.OPERATOR if kind in _OPERATOR_KINDS else AlertLevel.WARNING,
            show_id=self._show_id,
            started_at=self._wall(),
            ended_at=None,
            seconds=None,
            utterance_id=signal.utterance_id,
            text=signal.text,
            message=self._message(kind, signal, now),
            action=self._action(kind),
            auto_action=None,
            close_reason=None,
        )
        self._open[kind] = alert
        self._since[kind] = signal.since
        return AlertChange("open", replace(alert))

    def _message(self, kind: AlertKind, signal: _Signal, now: float) -> str:
        n = _secs(now - signal.since)
        if kind is AlertKind.SILENCE:
            return f"Host im lặng {n} giây"
        if kind is AlertKind.FROZEN:
            return f"Hình trong nguồn OBS đứng {n} giây" if self.obs else f"Hình trên tab host đứng {n} giây"
        if kind is AlertKind.AUDIO_MISSING:
            where = "nguồn OBS" if self.obs else "tab host"
            if signal.detail == "heartbeat":
                return f"Có thể mất tiếng ở {where}: {'nguồn' if self.obs else 'tab'} báo không phát được tiếng"
            return f"Có thể mất tiếng ở {where}: câu đã gửi {n} giây mà chưa phát"
        if kind is AlertKind.FORK_LOST:
            return f"Mất kết nối tới fork nhép miệng ({n} giây)"
        if kind is AlertKind.HOST_CLOSED:
            if not self.obs:
                return "Màn hình host đã đóng"
            if signal.detail == "stale":
                return f"Nguồn OBS đã ngắt: không gửi nhịp trạng thái {n} giây"
            return "Nguồn OBS đã ngắt"
        if kind is AlertKind.FALLBACK_MODE:
            return "Show đang ở chế độ dự phòng: dịch vụ viết kịch bản đang lỗi"
        return "Nhân vật nhép miệng lỗi, đang dùng ảnh tĩnh"

    def _action(self, kind: AlertKind) -> str:
        if kind is AlertKind.SILENCE:
            return f"Đợi vài giây; nếu quá {_secs(self.thresholds.autoskip_s)} giây hệ thống sẽ tự bỏ câu đang kẹt"
        if self.obs and kind in _OBS_ACTIONS:
            return _OBS_ACTIONS[kind]
        return _ACTIONS[kind]

    def _close(self, kind: AlertKind, reason: str, now: float) -> list[AlertChange]:
        alert = self._open.pop(kind, None)
        if alert is None:
            return []
        since = self._since.pop(kind, now)
        alert.ended_at = self._wall()
        alert.seconds = round(max(0.0, now - since), 3)
        alert.close_reason = reason
        return [AlertChange("close", alert)]

    def _close_all(self, reason: str, now: float) -> list[AlertChange]:
        changes: list[AlertChange] = []
        for kind in _ORDER:
            changes += self._close(kind, reason, now)
        return changes

    def _reset_flow(self, now: float, *, keep_playing: bool = False) -> None:
        if not keep_playing:
            self._playing.clear()
        self._silence_mark = now
        self._silence_covered = False
        self._skipped_at = None
        self._unacked = None
        self._frames = None
        self._frames_since = None
        self._audio_bad_since = None

    def _clear_heartbeat(self) -> None:
        self._last_status = None
        self._frames = None
        self._frames_since = None
        self._audio_bad_since = None


class WatchdogService:
    """Runs `ShowWatchdog` in the app: bus events and playback notices in, `ALERT` events and `alerts.jsonl` out.

    Subscribe (`subscription`) before the renderer starts, so its first avatar mode and fork health are seen.
    """

    def __init__(
        self,
        settings: Settings,
        bus: EventBus,
        subscription: Subscription,
        *,
        skip: Callable[[], Any],
        session_log: SessionLog | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.watchdog = ShowWatchdog(
            WatchdogThresholds.from_settings(settings),
            lipsync=settings.avatar_mode == "livetalking",
            output_mode=settings.output_mode,
        )
        self._bus = bus
        self._sub = subscription
        self._skip = skip
        self._log = session_log
        self._clock = clock
        self._tick_s = settings.watchdog_tick_s
        self._skips: set[asyncio.Task[Any]] = set()

    @property
    def open_alerts(self) -> list[Alert]:
        return self.watchdog.open_alerts

    def attach(self, renderer: Any) -> None:
        """Listen to what is really heard, and start from the host connection the renderer has now."""
        add_listener = getattr(renderer, "add_playback_listener", None)
        if add_listener is not None:
            add_listener(self)
        connected = bool(getattr(renderer, "host_ready", False))
        role = getattr(renderer, "host_role", None)
        self._apply(self.watchdog.on_host_connection(connected, self._clock(), role))

    def flush(self) -> None:
        """Apply what is already on the bus, e.g. the show's end at shutdown, before the task is cancelled."""
        self._pump()

    async def run(self) -> None:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(anext(self._sub), self._tick_s)
                except TimeoutError:
                    event = None
                except StopAsyncIteration:
                    return
                if event is not None:
                    self._handle(event)
                self._pump()
                self._apply(self.watchdog.tick(self._clock()))
        finally:
            for task in list(self._skips):
                task.cancel()

    # ---------- PlaybackListener (called on the loop, must return fast; failures are caught by the notifier) ----------

    def playback_started(self, utterance_id: str, seq: int, text: str) -> None:
        self._pump()
        self._apply(self.watchdog.on_playback_started(utterance_id, seq, text, self._clock()))

    def playback_ended(self, utterance_id: str, seq: int) -> None:
        self._pump()
        self._apply(self.watchdog.on_playback_ended(utterance_id, seq, self._clock()))

    def playback_stopped(self) -> None:
        self._pump()
        self._apply(self.watchdog.on_playback_stopped(self._clock()))

    # ---------- internals ----------

    def _pump(self) -> None:
        # Bus events published before this notice are applied first, so a SENTENCE never lands after its own start.
        for event in self._sub.drain():
            self._handle(event)

    def _handle(self, event: Event) -> None:
        payload = event.payload
        now = self._clock()
        w = self.watchdog
        try:
            if event.type is EventType.SHOW_STATE:
                changes = w.on_show_state(
                    str(payload.get("show_id")), str(payload.get("state")), str(payload.get("mode", "normal")), now
                )
            elif event.type is EventType.SENTENCE:
                changes = w.on_sentence(
                    str(payload.get("utterance_id")), int(payload.get("seq", 0)), str(payload.get("text", "")), now
                )
            elif event.type is EventType.HOST_CONNECTION:
                role = payload.get("role")
                changes = w.on_host_connection(bool(payload.get("connected")), now, str(role) if role else None)
            elif event.type is EventType.LIPSYNC_HEALTH:
                changes = w.on_lipsync_health(bool(payload.get("connected")), now)
            elif event.type is EventType.AVATAR_MODE:
                changes = w.on_avatar_mode(str(payload.get("active")), now)
            elif event.type is EventType.HOST_STATUS:
                changes = w.on_host_status(HostStatus.from_message(payload, float(payload.get("received_at", now))))
            else:
                return
        except Exception:
            # A malformed event must not stop the watchdog for the rest of the show.
            logger.exception("watchdog_event_failed")
            return
        self._apply(changes)

    def _apply(self, changes: Iterable[AlertChange]) -> None:
        for change in changes:
            alert = change.alert
            body = alert.to_json()
            self._bus.publish(Event(EventType.ALERT, {"alert": body}))
            if self._log is not None:
                self._log.write_alert(change.record(_iso_now()))
            log_event(
                logger,
                "watchdog_alert",
                change=change.event,
                kind=alert.kind.value,
                alert_level=alert.level.value,
                show_id=alert.show_id,
                alert_id=alert.alert_id,
                seconds=alert.seconds,
                close_reason=alert.close_reason,
            )
            if change.event == "auto_skip":
                log_event(logger, "watchdog_auto_skip", show_id=alert.show_id, alert_id=alert.alert_id)
                task = asyncio.ensure_future(self._auto_skip())
                self._skips.add(task)
                task.add_done_callback(self._skips.discard)

    async def _auto_skip(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            try:
                await self._skip()
            except Exception:
                logger.exception("watchdog_auto_skip_failed")
