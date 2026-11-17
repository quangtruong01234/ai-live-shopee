# Data model: 007 Sẵn sàng cho buổi demo

> Kiểu Python (`dataclass` đóng băng hoặc `StrEnum`) trong `src/ai_live/ops/` trừ khi ghi khác. Thời điểm ghi file là ISO 8601 UTC.

## 1. Kiểm tra trước demo

```python
class CheckStatus(StrEnum):
    OK = "ok"            # Đạt
    WARN = "warn"        # Cảnh báo
    FAIL = "fail"        # Lỗi
    UNKNOWN = "unknown"  # Không kiểm được

@dataclass(frozen=True)
class ReadinessItem:
    id: str          # mã mục, bảng dưới
    label: str       # tên mục tiếng Việt
    status: CheckStatus
    message: str     # tiếng Việt: thấy gì
    action: str | None  # tiếng Việt: làm gì (None khi Đạt)

@dataclass(frozen=True)
class ReadinessResult:
    checked_at: str
    source: Literal["app", "offline"]
    ready: bool                  # không có mục FAIL
    items: tuple[ReadinessItem, ...]
    manual: tuple[str, ...]      # "Việc tự xác nhận" (FR-005)
    duration_ms: int
```

| `id` | Kiểm | Lỗi | Cảnh báo |
|---|---|---|---|
| `app_env` | `APP_ENV` | `dev` | — |
| `reply_engine` | `REPLY_ENGINE` | `fake` | `gemini` (runbook dùng `chain`) |
| `tts_provider` | `TTS_PROVIDER` | `fake` | `gemini` (free chỉ vài câu) |
| `avatar_mode` | `AVATAR_MODE` | — | `static` (hỏi có cố ý không) |
| `recording` | fork `record_enabled` | `true` | — (ảnh tĩnh: Đạt "không dùng fork") |
| `fork` | fork health + `LipsyncHealth` + `AvatarModeState` | không nối được; đang ở ảnh tĩnh do lỗi | nối được nhưng chưa có phiên host |
| `character` | nhân vật đã nạp, `CUSTOMER_ID`/`AVATAR_ID`, `prepare.fork_commit` | thiếu `CUSTOMER_ID` hoặc `AVATAR_ID` | nhân vật chuẩn bị với fork khác fork đang chạy |
| `host` | `renderer.host_ready` + `HostStatus` gần nhất | chưa mở / chưa bấm "Bắt đầu"; tiếng không chạy | chưa nhận nhịp `host_status` |
| `content` | catalog đã nạp, số sản phẩm, file sửa sau khi nạp | không có sản phẩm / file lỗi (offline) | file sản phẩm đổi sau khi nạp |
| `scene` | `SCENE_ENABLED` + cảnh báo `placeholder` | còn ảnh mẫu (nêu sản phẩm) | — |
| `ai_label` | `AI_LABEL_TEXT` | rỗng | — |
| `backup_video` | tờ mô tả mới nhất trong `BACKUP_VIDEO_DIR` | thiếu file, kiểm không đạt (độ dài/tiếng/nhãn) | khác nhân vật/khách/bản nội dung đang nạp |
| `llm_chain` | `ChainReplyEngine.snapshot()` (không gọi) | không entry nào `ready` | có entry đang nghỉ |
| `power` | nguồn điện | — | chạy pin (Không kiểm được ngoài Windows) |
| `disk` | chỗ trống ổ chứa `SESSION_DATA_DIR` | — | < `READINESS_MIN_FREE_GB` |

`character` cảnh báo khi `prepare.fork_commit` trong `character.json` khác `fork_commit` mà `/ailive/health` báo (sửa lỗi
2026-11-17: trước đó chỉ có dòng log `avatar_prepared_with_other_fork`); thiếu một trong hai commit thì không so. Bản offline đọc
`character.json` trong `AVATAR_DIR`.
`reply_engine` khác `chain` thì `llm_chain` là Đạt "không dùng chuỗi model". `AVATAR_MODE=static` thì `fork`, `recording` là Đạt "không
dùng nhép miệng".

## 2. Canh show

```python
class AlertKind(StrEnum):
    SILENCE = "silence"; FROZEN = "frozen"; AUDIO_MISSING = "audio_missing"; FORK_LOST = "fork_lost"
    HOST_CLOSED = "host_closed"; FALLBACK_MODE = "fallback_mode"; STATIC_MODE = "static_mode"

class AlertLevel(StrEnum):
    WARNING = "warning"     # cảnh báo
    OPERATOR = "operator"   # cần người vận hành

@dataclass
class Alert:
    alert_id: str            # uuid hex
    kind: AlertKind
    level: AlertLevel
    show_id: str
    started_at: str          # ISO, thời điểm vượt ngưỡng
    ended_at: str | None
    seconds: float | None    # tổng thời gian khi đóng (tính từ lúc dấu hiệu bắt đầu, không phải lúc vượt ngưỡng)
    utterance_id: str | None # câu liên quan (câu cuối đã phát với silence; câu chưa có xác nhận với audio_missing)
    text: str | None         # câu liền trước (rút gọn 120 ký tự)
    message: str             # tiếng Việt, kèm số giây
    action: str              # tiếng Việt, theo runbook §4
    auto_action: str | None  # "skip" khi đã tự bỏ câu
    close_reason: str | None # "cleared" | "covered" | "paused" | "show_ended"
```

```python
@dataclass(frozen=True)
class HostStatus:   # tin `host_status` từ tab host, phát lên bus dạng EventType.HOST_STATUS
    frames: int | None       # framesDecoded của video WebRTC; None ở ảnh tĩnh hoặc chưa có
    audio: Literal["running", "suspended", "closed"] | None
    video_muted: bool | None
    video_paused: bool | None
    visible: bool | None
    received_at: float       # monotonic phía app
```

Cấu hình (`Settings`): `watchdog_enabled: bool = True`, `watchdog_silence_s = 5`, `watchdog_frozen_s = 3`, `watchdog_autoskip_s = 15`,
`watchdog_audio_ack_s = 3`, `watchdog_audio_ack_lipsync_s = 6` (thay `watchdog_audio_ack_s` khi đang nhép miệng, thêm sau T054),
`watchdog_tick_s = 0.25` (có trong `.env.example` vì test cấu hình đòi mọi biến, ghi chú "chỉ để test").
Ràng buộc: `watchdog_autoskip_s > watchdog_silence_s`.

## 3. Log phiên mới

- `GapRecord`: `{show_id, kind, seconds, from_id, to_id, at}` (`kind` = `GapKind`, `counted` = thuộc `COUNTED_GAP_KINDS`).
- `SessionInfo` (`session.json`): `{session_id, started_at, app_env, reply_engine, tts_provider, avatar_mode, scene_enabled, customer_id,
  avatar_id, catalog_version, power: "ac" | "battery" | null, watchdog: {enabled, silence_s, frozen_s, autoskip_s}}`.

## 4. Báo cáo tổng duyệt

```python
class Verdict(StrEnum):
    PASS = "pass"; FAIL = "fail"; SHORT = "short"   # SHORT: chưa đủ 30 phút (tiêu chí 4)

@dataclass(frozen=True)
class RehearsalReport:
    show_id: str
    session_id: str
    conditions: dict          # SessionInfo + mouth_method (dòng `render` của avatar.jsonl) + fake_run: bool
    started_at: str | None
    ended_at: str | None      # cuối cùng thấy được khi không có summary
    duration_s: float
    ended_normally: bool      # có show_summary và ended_by == "operator"
    gaps: dict                # {counted: n, p95_s, max_s, over_5s: [{at, seconds, kind, before_text}]}
    excluded_gaps: dict       # theo kind: paused/fault/comment
    sentences: dict           # spoken, tts_error, render_error, fallback_spoken, verbatim_spoken (câu `source: "verbatim"`)
    alerts: dict              # theo kind: {count, total_s}; list: mọi cảnh báo theo thời điểm
    modes: dict               # fallback_s, static_s
    render_fps: dict | None   # p50, min từ các dòng `render` của avatar.jsonl (nhép miệng; 005 contracts/events.md §4)
    criterion_3: Verdict
    criterion_4: Verdict
    notes: tuple[str, ...]    # "chạy với bộ trả lời giả, chưa phải tổng duyệt thật", ...
```

- Tiêu chí 3 PASS khi `gaps.p95_s ≤ 1.5` và không khoảng đếm được nào > 5 s; không có khoảng nào → FAIL kèm ghi chú "không đủ dữ liệu".
- Tiêu chí 4: không kết thúc bình thường → FAIL; `duration_s < 1800` → SHORT; có cảnh báo `frozen`, `audio_missing`, `host_closed`,
  `fork_lost` hoặc câu `tts_error`/`render_error` → FAIL; còn lại PASS.
- `fake_run` khi `reply_engine == "fake"` hoặc `tts_provider == "fake"`; tiêu chí 2 không chấm (ghi chú).
- Khi cùng lúc có lỗi và thiếu thời lượng, tiêu chí 4 ghi FAIL (show 10 phút mà đứng hình không được ghi là "chưa đủ 30 phút").
- Dưới 20 khoảng lặng: `p95_s` lấy bằng khoảng dài nhất (không bao giờ đánh giá tốt hơn thực tế), kèm ghi chú; từ 20 khoảng trở
  lên tính như `show_summary` (`quantiles(n=20)[18]`).
- Câu liền trước một cảnh báo: câu bắt đầu bởi khoảng lặng cuối cùng trước lúc cảnh báo mở (`gaps.jsonl.to_id`); cảnh báo `silence`
  dùng luôn `text` của nó.

## 5. Video dự phòng

```python
@dataclass(frozen=True)
class BackupVideoSheet:
    name: str                 # backup_<YYYYmmdd-HHMM>_<customer>
    video: str                # đường dẫn mp4 trong BACKUP_VIDEO_DIR
    made_at: str
    customer_id: str
    avatar_id: str
    catalog_version: str
    content_source: Literal["verbatim", "script"]
    show_id: str
    seconds: float
    has_audio: bool
    label_ok: bool
    label_frames_missing: int
    ok: bool                  # 120 ≤ seconds ≤ 180 và has_audio và label_ok
    problems: tuple[str, ...] # tiếng Việt
    note: str                 # "Chỉ dùng cho demo Meet/YouTube, không phát trên Shopee Live"
```
