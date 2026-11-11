# Hợp đồng adapter: 005-lipsync-livetalking

- **Ngày:** 2026-11-06 · Nguồn: [research.md](../research.md) R2, R4, R9, R10, R13 · Mã: `src/ai_live/core/protocols.py`, `src/ai_live/avatar/`

## 1. `AvatarRenderer` (không đổi chữ ký)

Giữ nguyên Protocol hiện có (đã gồm `first_playback_at`, thêm ở 004). Ba lớp mới đều thỏa nó, nên `ShowDirector` và `ScriptRunner` không
đổi cách gọi `speak` / `interrupt`.

```python
class AvatarRenderer(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def speak(self, utterance_id: str, text: str, audio: AsyncIterator[bytes], sample_rate: int) -> None: ...
    async def interrupt(self) -> None: ...
    @property
    def is_speaking(self) -> bool: ...
    def first_playback_at(self, utterance_id: str) -> float | None: ...
```

## 2. Protocol tùy chọn mới (`core/protocols.py`)

```python
@runtime_checkable
class RenderOutcomeSink(Protocol):
    """A renderer that wants to know how each turn's render step ended (FR-022, research R9)."""

    def record_render_outcome(self, utterance_id: str, ok: bool, *, error_kind: str | None = None) -> None: ...


@runtime_checkable
class RenderStatsSource(Protocol):
    """A renderer that measures its own frame rate per turn (FR-020)."""

    def render_stats(self, utterance_id: str) -> RenderTurnStats | None: ...


class RendererError(RuntimeError):
    """Render-step failure reported by the renderer itself; `kind` goes to errors.jsonl (FR-021)."""

    def __init__(self, kind: str, message: str) -> None: ...
    kind: str   # "lipsync_unavailable" | "vram_oom" | "inference_failed" | "bad_audio" | "renderer_restarted"
```

Lõi gọi:
- `ShowDirector._play_all` và `ScriptRunner` (chỗ `check_render` + `speak`): sau bước render của một lượt, nếu `isinstance(renderer,
  RenderOutcomeSink)` thì gọi `record_render_outcome(uid, ok)`. `ok=False` khi bước render ném lỗi (cả `InjectedFault` của
  `check_render`), kèm `error_kind` = `kind` ghi vào `errors.jsonl` (để log `avatar_fallback` có `last_error_kind`, events.md; sửa
  2026-11-11 khi làm T055); `ok=True` khi mọi câu của lượt đã `speak` xong. Lượt bị bỏ qua hoặc dừng trước bước render: không gọi.
- Khi ghi `TurnLatency`, nếu `isinstance(renderer, RenderStatsSource)` thì chép `render_fps`, `infer_fps`, `clips_used` và log
  `render_stats` (events.md §2) khi renderer trả số liệu (lượt `livetalking`). Câu kịch bản không có `TurnLatency` (004 research R2), nên
  `ScriptRunner` chỉ log `render_stats` cho mỗi câu đã nói (sửa 2026-11-11 khi làm T051).
- `_render_error_kind` của `ShowDirector` thêm nhánh `getattr(exc, "kind", ...)` như `_error_kind` của `ScriptRunner`, để `RendererError.kind`
  vào `errors.jsonl`.

## 3. `LiveTalkingRenderer` (`avatar/livetalking_renderer.py`, mới)

```python
class LiveTalkingRenderer:
    def __init__(
        self,
        base_url: str,                      # LIVETALKING_URL
        host: HostLink,                     # §5: send subtitle messages to /host, read lipsync_session
        *,
        first_frame_timeout_s: float = 10.0,
        ack_timeout_s: float = 3.0,
        reconnect_max_s: float = 10.0,
        lead_s: float = 0.0,                # LIVETALKING_LEAD_S: hand back before sentence_played (subtitle_clear later)
        connect: ForkConnector = websockets_connect,   # injected in tests (fake fork)
        bus: EventBus | None = None,
        clock: Callable[[], float] = time.monotonic,
        expected_fork_commit: str | None = None,       # character.prepare.fork_commit; mismatch only warns
    ) -> None: ...

    # AvatarRenderer
    async def start(self) -> None: ...      # starts the background task that (re)connects /ailive/ws when host reports a session
    async def stop(self) -> None: ...
    async def speak(self, utterance_id, text, audio, sample_rate) -> None: ...
    async def interrupt(self) -> None: ...
    is_speaking: bool
    def first_playback_at(self, utterance_id) -> float | None: ...
    # RenderStatsSource
    def render_stats(self, utterance_id) -> RenderTurnStats | None: ...
    # extra
    @property
    def ready(self) -> bool: ...            # fork socket open and hello received for the host's current session
    @property
    def health(self) -> LipsyncHealth: ...
```

Hành vi `speak` (giống `StaticRenderer`, khác đích gửi):
1. Không `ready` → `RendererError("lipsync_unavailable", "Chưa nối được phần nhép miệng (LiveTalking)")`.
2. Gửi `sentence_start`, các chunk PCM, `sentence_end` qua `/ailive/ws` (contracts/fork-protocol.md §2).
3. Chờ `playback_started` ≤ `first_frame_timeout_s` (quá hạn → `RendererError("timeout")`, để route và bộ đếm lỗi lượt đọc được
   `kind`; bản thiết kế ghi `TimeoutError`); câu `seq == 0` ghi `first_playback_at`. Ngay khi có ack, gửi
   `{"type":"subtitle", utterance_id, seq, text}` tới trang host.
4. Chờ `sentence_played` ≤ thời lượng tiếng + `ack_timeout_s`; xong gửi `{"type":"subtitle_clear", utterance_id, seq}`. Với
   `lead_s > 0`, `speak` trả về sớm `lead_s` giây trước khi câu phát xong; một tác vụ nền chờ `sentence_played` rồi mới gửi `subtitle_clear`.
5. Tin `error` từ fork khi đang chờ → `RendererError(kind, message)`. Mất kết nối khi đang chờ → `RendererError("lipsync_unavailable")`.
   `hello` với `boot_id` khác lần trước → log `renderer_restarted`, các câu đang chờ lỗi `RendererError("renderer_restarted")`.

`interrupt`: gửi `stop` tới fork và `{"type":"stop"}` tới trang host (xóa phụ đề), giải phóng các ack đang chờ như `StaticRenderer`.

## 4. `SwitchingRenderer` (`avatar/switching_renderer.py`, mới)

```python
class SwitchingRenderer:
    def __init__(
        self,
        lipsync: LipsyncRenderer,           # LiveTalkingRenderer (Protocol in switching_renderer.py; a fake in tests)
        static: StaticRenderer,             # image = AVATAR_DIR/face.png
        *,
        fallback_after: int = 2,            # AVATAR_FALLBACK_AFTER
        configured: AvatarMode = "livetalking",
        bus: EventBus | None = None,
        clock: Callable[[], datetime] = ...,
    ) -> None: ...
    lipsync: LipsyncRenderer; static: StaticRenderer           # public: routes read lipsync.health / ready
    # AvatarRenderer + RenderOutcomeSink + RenderStatsSource: delegate to the renderer chosen for the turn
    @property
    def mode(self) -> AvatarModeState: ...
    async def enable_lipsync(self) -> AvatarModeState: ...   # POST /api/avatar/lipsync
    # /ws/host passthrough (the route only knows this object)
    async def attach(self, conn: HostConnection) -> None: ...
    def detach(self, conn: HostConnection) -> None: ...
    def handle_message(self, conn: HostConnection, message: dict) -> None: ...
    @property
    def host_ready(self) -> bool: ...
    @property
    def ack_timeout_s(self) -> float: ...                     # the active renderer's value (faults.check_render uses it)
```

- Renderer của một lượt chọn lúc `speak(seq=0)` đầu tiên của `utterance_id` và giữ tới hết lượt (data-model §4).
- `record_render_outcome`: đếm theo data-model §4; đạt ngưỡng → `active = static`, gửi `{"type":"mode","mode":"static","reason":"render_errors"}`
  tới trang host, phát `EventType.AVATAR_MODE`, log `avatar_fallback`.
- `enable_lipsync`: `active = livetalking`, bộ đếm 0, gửi `{"type":"mode","mode":"livetalking"}` (trang host gọi lại `/offer` nếu kết
  nối WebRTC đã đóng), phát `AVATAR_MODE`, log `avatar_lipsync_enabled`. Gọi khi `configured = static` → `ValueError` (route trả 409).
- `/ws/host` luôn do `StaticRenderer` giữ (một kết nối trang host duy nhất, ADR-016). `handle_message` chuyển tiếp cho `StaticRenderer`, và
  khi tin `ready` có `lipsync_session` thì báo cho `LiveTalkingRenderer` qua `HostLink`.
- `host_ready` = trang host đã `ready` (bấm "Bắt đầu"). Không kiểm fork ở đây: thiếu fork thì `speak` lỗi, lượt lỗi được đếm và tự về ảnh
  tĩnh (đúng FR-022 khi fork chết lúc mở phiên).

Khi `AVATAR_MODE=static`, `create_renderer()` trả thẳng `StaticRenderer` như hiện nay (không bọc), giữ nguyên hành vi 001/004 (FR-014).

## 5. `HostLink` (`avatar/static_renderer.py`)

```python
class HostLink(Protocol):
    @property
    def host_ready(self) -> bool: ...                # host page attached and "ready" (added 2026-11-11, T050)
    @property
    def lipsync_session(self) -> str | None: ...     # from the host's "ready" message; None until reported
    async def send_to_host(self, message: dict[str, Any]) -> bool: ...   # False when no host is attached
    def on_session_change(self, callback: Callable[[int | None], None]) -> None: ...
```

`StaticRenderer` thỏa `HostLink`: thêm thuộc tính `lipsync_session`, phương thức `send_to_host` (gửi JSON qua kết nối hiện tại) và
callback khi phiên đổi (trang host nối lại hoặc gọi lại `/offer`). Không đổi hành vi static hiện có.

`LiveTalkingRenderer.speak` đọc `host_ready` để báo đúng lỗi theo research R10: trang host chưa `ready`, hoặc đóng giữa câu (phiên WebRTC
mất theo trang nên kết nối fork cũng đóng), thì ném `RendererUnavailable` (`kind = host_unavailable`) như 001, không phải
`lipsync_unavailable` (thêm 2026-11-11 khi làm T050, trường hợp biên "đóng màn hình host giữa lúc nói").

## 6. `create_renderer()` (`avatar/factory.py`, mới) và `AppContext`

```python
def load_session_character(settings: Settings) -> AvatarCharacter | None: ...   # None in static; reads files (call via to_thread)
def avatar_image_path(settings: Settings, character: AvatarCharacter | None) -> Path: ...
def create_renderer(
    settings: Settings, *, bus: EventBus, character: AvatarCharacter | None = None
) -> StaticRenderer | SwitchingRenderer: ...
```

`app/main.py` gọi `load_session_character` ngoài event loop (`asyncio.to_thread`) rồi đưa kết quả vào `create_renderer(character=...)`, để
không đọc file nhân vật hai lần và không chặn event loop lúc mở app. `AvatarModeError` chuyển về `avatar/character.py` (`main.py` vẫn
xuất lại tên này).

- `static` → `StaticRenderer(settings.renderer_ack_timeout_s, bus=bus)`.
- `livetalking` → kiểm nhân vật (`load_character(settings)`: `ready`, `customer_id == CUSTOMER_ID`, `character_id == AVATAR_ID`; lỗi →
  `AvatarModeError` với lời tiếng Việt, app không mở), rồi `SwitchingRenderer(LiveTalkingRenderer(...), StaticRenderer(...))`.
- `app/main.py` thay chỗ đang ném `AvatarModeError` cho mọi chế độ khác `static` bằng `create_renderer()`.
- `AppContext.renderer` đổi kiểu từ `StaticRenderer` sang `HostRenderer` (Protocol = `AvatarRenderer` + `attach` / `detach` /
  `handle_message` / `host_ready`), để route `/ws/host` dùng chung cho hai chế độ.
- `/avatar-image` trả `face.png` của nhân vật khi `livetalking`, `AVATAR_STATIC_IMAGE` khi `static`: đường dẫn nằm ở trường mới
  `AppContext.avatar_image: Path | None` (`None` = dùng `AVATAR_STATIC_IMAGE`), do `avatar_image_path` tính lúc mở app.
- `ShowDirector.speak_audio(pcm, sample_rate, text) -> utterance_id` (mới): phát PCM có sẵn qua renderer, bỏ qua LLM và TTS, cùng luật
  bận (`DirectorBusy`) như `speak_text`; route `/api/debug/speak-audio` gọi hàm này.

## 7. Nhân vật (`avatar/character.py`, mới) và CLI `prepare`

```python
def load_character(avatar_dir: Path) -> AvatarCharacter: ...                 # parse + validate (data-model §2, §3), pure
def validate_for_session(character: AvatarCharacter, settings: Settings) -> None: ...   # raises AvatarModeError
async def prepare_character(avatar_dir: Path, fork_python: Path, *, run=..., fork_dir=None) -> PrepareResult: ...
```

`uv run python -m ai_live.avatar prepare <AVATAR_DIR>`: `load_character` (lỗi hồ sơ / khách / loại clip → in lỗi, mã thoát 1, không gọi
fork) → chạy `LIVETALKING_PYTHON -m ailive_ext.prepare <dir> --json` (cwd `vendor/livetalking`) → ghi `prepare` vào `character.json` → in
bảng kết quả tiếng Việt. `run` tiêm được để test không cần fork.

## 8. Khác biệt so với ARCHITECTURE §3

| # | ARCHITECTURE §3 hiện tại | 005 | Xử lý |
|---|--------------------------|-----|-------|
| 1 | Ghi chú tích hợp: TODO chọn (a) hay (b) | Chọn (b): TTS của mình đẩy PCM vào fork qua `/ailive/ws` | ADR-042, ADR-043; sửa ghi chú khi chốt |
| 2 | `OutputSink` "làm ở 005" | **Không làm.** LiveTalking tự xuất WebRTC tới trang host; nhãn AI cũng nằm trong fork | ADR-043, ADR-044; ghi lại `OutputSink` để feature OBS/RTMP |
| 3 | `AvatarRenderer` không có `first_playback_at` | Đã có trong code từ 004, ARCHITECTURE chưa ghi | Bổ sung vào ARCHITECTURE §3 lúc implement (sửa tài liệu cho khớp code) |
| 4 | Không có | Protocol tùy chọn `RenderOutcomeSink`, `RenderStatsSource`, lỗi `RendererError` | ADR-046 |
| 5 | Implementations: `StaticRenderer`, `LiveTalkingRenderer` | Thêm `SwitchingRenderer` (lớp bọc chọn renderer theo lượt) | ADR-046 |
| 6 | Bảng biến chọn adapter có `OUTPUT_MODE` | Không dùng ở 005 | Không đổi |
