# Mô hình dữ liệu (Phase 1): 005-lipsync-livetalking

- **Ngày:** 2026-11-06 · **Plan:** [plan.md](./plan.md) · **Research:** [research.md](./research.md)
- Lấy từ "Thực thể chính" của spec: Nhân vật, Clip nền, Lượt tạo hình, Số đo tạo hình. Thêm cấu hình và trạng thái chế độ hiển thị (FR-022).

## 1. Cấu hình (biến môi trường, `core/config.py`)

| Biến | Kiểu, mặc định | Kiểm tra | Ghi chú |
|------|----------------|----------|---------|
| `AVATAR_MODE` | `static \| livetalking`, `static` | đã có | Comment `.env.example` sửa: `livetalking` chạy trên GPU laptop (ADR-023), RunPod là dự phòng |
| `CUSTOMER_ID` | `str`, rỗng | bắt buộc khi `livetalking`; `[a-z0-9_-]{1,64}` | Mới (R13). Mã khách của phiên |
| `AVATAR_ID` | `str`, rỗng | bắt buộc khi `livetalking`; phải trùng `character_id` | Đã có |
| `AVATAR_DIR` | `Path`, `assets/avatars/demo_host_01` | khi `livetalking`: thư mục có `character.json` trạng thái `ready` | Mới. Thư mục đã gitignore |
| `AVATAR_STATIC_IMAGE` | `Path`, đã có | | Dùng ở `static`. Ở `livetalking`, ảnh dự phòng là `AVATAR_DIR/face.png`, bỏ qua biến này |
| `LIVETALKING_URL` | `AnyHttpUrl`, `http://127.0.0.1:8010` | host phải là `127.0.0.1` hoặc `localhost` | Đã có trong `.env.example`, thêm vào config. Cổng 8010 là `listenport` mặc định của LiveTalking (bỏ TODO cũ) |
| `LIVETALKING_PYTHON` | `Path`, `vendor/livetalking/.venv/Scripts/python.exe` | file tồn tại (chỉ kiểm khi chạy `prepare`) | Mới. Python của venv fork, chỉ CLI `prepare` dùng |
| `LIVETALKING_FIRST_FRAME_TIMEOUT_S` | `float`, `10.0` | `> 0` | Mới (R10) |
| `LIVETALKING_RECONNECT_MAX_S` | `float`, `10.0` | `> 0` | Mới (R10) |
| `LIVETALKING_LEAD_S` | `float`, `0.0` | `≥ 0`; `0` = tắt | Mới (R15). `speak` trả về sớm khi phần tiếng còn lại của câu ≤ giá trị này |
| `AVATAR_FALLBACK_AFTER` | `int`, `2` | `≥ 1` | Mới. Số lượt lỗi render liền nhau trước khi về ảnh tĩnh (FR-022: 2) |
| `AI_LABEL_TEXT` | `str`, `AI` | không rỗng; ở `livetalking` chỉ ASCII in được | Đã có (R5) |
| `AI_LABEL_POSITION` | `top-left \| top-right \| bottom-left \| bottom-right`, `top-right` | | Đã có |
| `RENDERER_ACK_TIMEOUT_S` | `float`, `3` | | Đã có; dùng cho phần sau `playback_started` |

Biến chỉ fork đọc (đặt trong `scripts/livetalking/run.ps1`, không vào config của app): `LIVETALKING_BATCH_SIZE` (mặc định 16, R6),
`LIVETALKING_LIP_EVERY_N` (1, R8), `LIVETALKING_TRANSITION_S` (0,3, R7), `LIVETALKING_HOLD_S` (2,5, R7: giữ clip nói sau mỗi câu; 1,5 trước T067), cùng `AI_LABEL_TEXT`, `AI_LABEL_POSITION`, `AVATAR_DIR`.
Script đọc chúng từ `.env` của repo để chỉ có một nguồn (contracts/fork-protocol.md §5).

## 2. Nhân vật (`AvatarCharacter`): `AVATAR_DIR/character.json`

Một file JSON viết tay lúc tạo nhân vật; lệnh `prepare` ghi thêm phần `prepare`. Đã gitignore cùng thư mục (chứa tên khách, ảnh).

```json
{
  "schema_version": 1,
  "character_id": "demo_host_01",
  "customer_id": "demo_customer_01",
  "face": "face.png",
  "provenance": "provenance.json",
  "clips": [
    {"clip_id": "idle_01", "file": "clips/idle_01.mp4", "kind": "idle"},
    {"clip_id": "idle_02", "file": "clips/idle_02.mp4", "kind": "idle"},
    {"clip_id": "talk_01", "file": "clips/talk_01.mp4", "kind": "talk"},
    {"clip_id": "talk_02", "file": "clips/talk_02.mp4", "kind": "talk"}
  ],
  "prepare": {
    "status": "ready",
    "prepared_at": "2026-11-07T10:00:00+07:00",
    "fork_commit": "<sha>",
    "frame_size": [480, 832],
    "clips": {"idle_01": {"frames": 121, "fps": 24.0, "avatar_dir": "vendor/livetalking/data/avatars/demo_host_01__idle_01"}},
    "errors": []
  }
}
```

| Trường | Kiểu | Kiểm tra |
|--------|------|----------|
| `schema_version` | `int` | `== 1` |
| `character_id` | `str` | `[a-z0-9_-]{1,64}`; trùng tên thư mục và `AVATAR_ID` |
| `customer_id` | `str` | bắt buộc (FR-004); trùng `CUSTOMER_ID` khi mở phiên |
| `face` | `str` (đường dẫn tương đối) | file tồn tại, PNG/JPG |
| `provenance` | `str` | file tồn tại, hợp lệ theo §3 |
| `clips[]` | `list[BaseClip]` | ≥ 1 `idle` và ≥ 1 `talk` (FR-002); `clip_id` không trùng; file nằm trong `AVATAR_DIR` (không `..`) |
| `prepare` | `PrepareResult \| null` | do lệnh `prepare` ghi; người không sửa tay |

`BaseClip`: `clip_id` (`[a-z0-9_-]{1,64}`), `file` (`.mp4`), `kind` (`idle | talk`, FR-012). Không dùng bản `_pingpong` (R7); nếu khai báo
file có hậu tố `_pingpong` thì `prepare` cảnh báo nhưng không chặn.

**Trạng thái chuẩn bị** (`prepare.status`, spec "Nhân vật: trạng thái chuẩn bị"):

```
(chưa có prepare) ──prepare──▶ preparing ──hết lỗi──▶ ready
                                   │
                                   └──có lỗi──▶ failed (errors[] ghi lý do)
ready/failed ──prepare lại──▶ preparing
```

`preparing` chỉ tồn tại trong lúc lệnh chạy; lệnh bị ngắt giữa chừng để lại `preparing`, app coi như chưa sẵn sàng. App chỉ mở phiên
`livetalking` khi `ready` **và** `prepare.fork_commit` trùng commit fork đang chạy (fork báo trong `hello`, contracts/fork-protocol.md §3);
khác commit thì cảnh báo trong log (`avatar_prepared_with_other_fork`), không chặn.

`PrepareError`: `{"code": "...", "clip_id": "talk_01" | null, "frame": 84 | null, "message": "<tiếng Việt>"}`. Mã lỗi:
`face_count` (khác đúng 1 mặt, FR-003), `missing_file`, `bad_video` (không đọc được, 0 khung), `size_mismatch` (clip khác kích thước nhau),
`missing_provenance`, `provenance_incomplete`, `missing_customer`, `kind_missing` (thiếu loại idle hoặc talk), `fork_failed` (script fork lỗi khác),
`bad_character` (thêm lúc implement: `character.json` sai cấu trúc, ví dụ `character_id` khác tên thư mục, `kind` lạ, `file` không phải
`.mp4` trong thư mục nhân vật).

## 3. Hồ sơ nguồn gốc (`provenance.json`)

File đã có cho `demo_host_01` (tạo ở notebook Kaggle). `prepare` kiểm các trường tối thiểu, không đổi file:

| Trường | Bắt buộc | Kiểm tra |
|--------|----------|----------|
| `character_id` | có | trùng `character.json` |
| `kind` | có | `ai_generated_fictional_face` (FR-001; giá trị khác bị từ chối cho tới khi có quy trình đồng ý cho người thật, Điều II) |
| `created_by`, `created_at`, `platform` | có | không rỗng |
| `models` | có | danh sách, hoặc object theo vai trò (file thật của `demo_host_01`); mỗi phần tử có `name` (file thật dùng `repo`) và `license` |
| `clips` hoặc `assets` | có | mỗi clip trong `character.json` có một mục nguồn gốc (FR-004: "từng clip nền"); một mục khớp clip khi `clip_id` hoặc `name` bằng `clip_id`, hoặc tên file trong `file` / `files[]` bằng tên file clip |
| `adult_fictional_confirmed` | có | `true` (FR-005; người tạo xác nhận, không tự kiểm bằng máy) |

TODO: `provenance.json` của `demo_host_01` hiện chưa có `adult_fictional_confirmed` và chưa có mục riêng từng clip; bổ sung bằng tay
trước khi `prepare` (quickstart bước 2). Luật khớp mục clip ở bảng trên được viết rộng để chấp nhận file hiện có; T043 (người dùng)
xác nhận lại bằng `uv run python -m ai_live.avatar check`.

## 4. Chế độ hiển thị (`AvatarModeState`, trong `SwitchingRenderer`)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `configured` | `static \| livetalking` | từ `AVATAR_MODE`, không đổi trong phiên |
| `active` | `static \| livetalking` | đang dùng; chỉ khác `configured` sau tự chuyển |
| `reason` | `str \| None` | `render_errors` khi tự chuyển; `None` khi đúng cấu hình |
| `consecutive_errors` | `int` | lượt lỗi render liền nhau (R9) |
| `last_utterance_id` | `str \| None` | lượt cuối đã đếm, để một lượt nhiều câu chỉ đếm một lần |
| `changed_at` | `datetime \| None` | |

Chuyển trạng thái (chỉ khi `configured = livetalking`; ở `static` lớp bọc không đếm):

```
livetalking ──lượt lỗi render, consecutive_errors đạt AVATAR_FALLBACK_AFTER──▶ static (reason=render_errors)
static ──POST /api/avatar/lipsync──▶ livetalking (consecutive_errors = 0)
```

Quy tắc đếm: `record_render_outcome(uid, ok=False)` tăng bộ đếm một lần cho mỗi `uid`; `ok=True` đặt về 0. Lượt không tới bước render
(lỗi LLM, guard, TTS, bỏ qua) không gọi hàm này nên không đổi bộ đếm. Lỗi `host_unavailable` (trang host đóng, nhân vật không hỏng)
cũng không đổi bộ đếm: nếu không, đóng trang host hai lượt sẽ về ảnh tĩnh dù fork vẫn chạy tốt (thêm 2026-11-11 khi làm T050). Đang ở `static` sau tự chuyển thì lỗi render của `StaticRenderer`
không đếm thêm (không có chế độ nào thấp hơn). Đổi chế độ chỉ có hiệu lực từ lượt **kế tiếp**: lượt đang nói giữ renderer đã chọn lúc
gọi `speak` câu đầu.

## 5. Lượt tạo hình và số đo (`RenderTurnStats`)

Gắn với `utterance_id` (spec "Lượt tạo hình", "Số đo tạo hình"). Fork gửi `stats` cuối mỗi câu; `LiveTalkingRenderer` cộng dồn theo lượt.

| Trường | Kiểu | Nguồn |
|--------|------|-------|
| `utterance_id` | `str` | |
| `mode` | `static \| livetalking` | renderer đã dùng cho lượt |
| `clips_used` | `list[str]` | `clip_id` của clip nói đã dùng (FR-013, kiểm không lặp) |
| `frames` | `int` | tổng khung hình đã gửi trong các câu |
| `render_fps` | `float \| None` | khung đã gửi / thời gian từ `playback_started` câu đầu tới `sentence_played` câu cuối |
| `infer_fps` | `float \| None` | trung bình fork báo (`infer_fps` của LiveTalking) |
| `first_frame_at` | `float \| None` | `time.monotonic()` lúc nhận `playback_started` câu đầu = mốc `avatar_first_frame` |
| `last_played_at` | `float \| None` | `time.monotonic()` lúc nhận `sentence_played` câu cuối đã phát; `ScriptRunner` tính `sentence_gap` từ số này (thêm 2026-11-12, T075) |
| `error_kind` | `str \| None` | `timeout`, `host_unavailable`, `lipsync_unavailable`, `vram_oom`, `renderer_restarted`, `injected_*` |

`TurnLatency` (004, `core/models.py`) thêm ba trường tùy chọn `render_fps`, `infer_fps`, `clips_used`, mặc định `None`, để bảng độ trễ
(`GET /api/latency`, trang điều khiển) hiện thêm cột (FR-020). Ở `static` các trường này `None`. `LatencySummary` thêm `render_fps` và `infer_fps` p50/p95
(chỉ tính lượt có số) và `turns` (20 lượt gần nhất, `TurnLatency.to_row()`; contracts/api.md §2).

## 6. Sức khỏe phần tạo hình (`LipsyncHealth`)

Trạng thái mới nhất fork báo, để trang điều khiển và `GET /health` hiện:

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `connected` | `bool` | `/ailive/ws` đang mở |
| `boot_id` | `str \| None` | đổi giữa hai lần nối = fork khởi động lại (FR-021) |
| `fork_commit` | `str \| None` | |
| `session_id` | `str \| None` | `sessionid` WebRTC của trang host |
| `vram_used_mb` | `int \| None` | `torch.cuda.memory_allocated` / `max_memory_allocated` lúc báo |
| `infer_fps` | `float \| None` | |
| `last_error` | `str \| None` | `kind` gần nhất |
| `updated_at` | `datetime` | |
