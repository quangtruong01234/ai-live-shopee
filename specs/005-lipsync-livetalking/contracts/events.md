# Sự kiện, log và cấu hình: 005-lipsync-livetalking

- **Ngày:** 2026-11-06 · Nguồn: [research.md](../research.md) R6, R9, R10, R13 · [data-model.md](../data-model.md)

## 1. Sự kiện trên bus (`core/events.py`, phát ra `/ws/control`)

| `EventType` | Payload | Khi nào |
|-------------|---------|---------|
| `AVATAR_MODE = "avatar_mode"` (mới) | `{"configured", "active", "reason", "consecutive_errors", "changed_at"}` | Tự về ảnh tĩnh, bật lại, và một lần lúc mở app |
| `LIPSYNC_HEALTH = "lipsync_health"` (mới) | `LipsyncHealth` (data-model §6) | Nối / mất nối fork, `hello`, mỗi tin `health` (5 s), `error` |
| `LATENCY` (đổi) | thêm `render_fps`, `infer_fps`, `clips_used` | Như cũ, cuối lượt |
| `HOST_CONNECTION` | không đổi | |

## 2. Log có cấu trúc (`log_event`)

Mọi dòng có `utterance_id` khi gắn với lượt (Điều VIII). Không ghi nội dung tiếng, không ghi `sessionid` vào chỗ công khai (chỉ log local).

| Sự kiện | Trường | Ghi chú |
|---------|--------|---------|
| `avatar_first_frame` | `utterance_id`, `mode` | Mốc đã có; ở `livetalking` = nhận `playback_started` câu đầu từ fork (R6) |
| `render_stats` | `utterance_id`, `frames`, `render_fps`, `infer_fps`, `clips_used` | Cuối lượt `livetalking` (FR-020). Với `LIVETALKING_LEAD_S > 0`, dòng này được ghi sau khi câu cuối của lượt đã phát (≤ 30 s), muộn hơn lúc `speak` trả về (sửa 2026-11-12, T075; contracts/adapters.md §2) |
| `avatar_fallback` | `utterance_id` (lượt lỗi cuối), `consecutive_errors`, `last_error_kind` | FR-022 |
| `avatar_lipsync_enabled` | `by: "operator"` | FR-022 |
| `lipsync_connected` / `lipsync_disconnected` | `boot_id`, `fork_commit`, `session_id` / `reason` | |
| `renderer_restarted` | `old_boot_id`, `new_boot_id` | FR-021 |
| `lipsync_vram_oom` | `utterance_id?`, `vram_peak_mb` | FR-021, cùng `kind=vram_oom` trong `errors.jsonl` |
| `avatar_prepared_with_other_fork` | `prepared_commit`, `running_commit` | Cảnh báo, data-model §2 |
| `lipsync_connect_failed` | `session_id`, `error` | Thêm lúc implement: không nối được `/ailive/ws`, thử lại với backoff |
| `lipsync_error` | `kind`, `utterance_id?` | Thêm lúc implement: tin `error` từ fork khác `vram_oom` |
| `lipsync_sentence_unfinished` | `utterance_id`, `seq`, `error` | Thêm lúc implement: với `LIVETALKING_LEAD_S`, câu đã trả về sớm nhưng fork không báo phát xong |

## 3. `errors.jsonl` (đã có): `kind` mới ở bước `render`

`lipsync_unavailable`, `vram_oom`, `inference_failed`, `bad_audio`, `renderer_restarted`. Giữ `timeout`, `host_unavailable`, `injected_*`.

## 4. Thư mục phiên

- `latency.jsonl` (đã có): mỗi dòng thêm `render_fps`, `infer_fps`, `clips_used`.
- `avatar.jsonl` (mới): mỗi lần đổi chế độ và mỗi `health` (để vẽ VRAM / fps theo thời gian cho lần chạy 30 phút, SC-006).
  Thêm (sửa lỗi 2026-11-17): một dòng `kind: "render"` cho mỗi lượt hoặc câu kịch bản có khung hình; báo cáo tổng duyệt 007
  đọc `render_fps` và `mouth_method` ở đây:
  `{"ts", "kind": "render", "utterance_id", "show_id", "frames", "render_fps", "infer_fps", "clips_used", "scene_ms", "mouth_method"}`.
  `show_id` là `null` với lượt trả lời ngoài show. Với `LIVETALKING_LEAD_S`, dòng được ghi khi câu phát xong, nên có thể nằm sau
  dòng của câu kế tiếp.

## 5. `.env.example` (khối Avatar / LiveTalking sau khi sửa)

```dotenv
AVATAR_MODE=static              # static (ảnh tĩnh) | livetalking (nhép miệng trên GPU laptop, ADR-023; RunPod là dự phòng)
# ---------- Avatar / LiveTalking ----------
CUSTOMER_ID=                    # mã khách của phiên; nhân vật của khách khác bị từ chối (FR-004)
AVATAR_ID=                      # mỗi avatar chỉ gán cho đúng 1 tài khoản/khách; phải trùng character_id
AVATAR_DIR=assets/avatars/demo_host_01   # thư mục nhân vật (character.json, face.png, clips/); đã gitignore
AVATAR_STATIC_IMAGE=assets/avatars/demo/idle.png   # chỉ dùng ở AVATAR_MODE=static
AVATAR_FALLBACK_AFTER=2         # số lượt lỗi tạo hình liền nhau trước khi tự về ảnh tĩnh
LIVETALKING_URL=http://127.0.0.1:8010    # cổng mặc định listenport của LiveTalking
LIVETALKING_PYTHON=vendor/livetalking/.venv/Scripts/python.exe   # Python của venv fork, cho lệnh prepare
LIVETALKING_FIRST_FRAME_TIMEOUT_S=10
LIVETALKING_RECONNECT_MAX_S=10
LIVETALKING_LEAD_S=0            # >0: speak trả về sớm chừng ấy giây trước khi câu phát xong, giảm khoảng lặng giữa câu (R15)
LIVETALKING_BATCH_SIZE=16       # fork đọc; nhỏ hơn thì khung đầu sớm hơn, thông lượng thấp hơn
LIVETALKING_LIP_EVERY_N=1       # fork đọc; 2 = suy luận miệng mỗi khung thứ 2 khi máy không kịp
LIVETALKING_MOUTH_METHOD=w2l    # fork đọc (010); cách tạo miệng, sai thì fork dùng w2l
LIVETALKING_TRANSITION_S=0.3    # fork đọc; thời gian trộn khi đổi clip
LIVETALKING_HOLD_S=2.5          # fork đọc; giữ clip nói (miệng khép) chừng ấy giây sau câu rồi mới về clip chờ
AILIVE_RECORD_DIR=              # fork đọc; tự kiểm: ghi luồng ra mp4/wav/jsonl vào đây (vd out/selfcheck, ngoài git); trống = tắt
AILIVE_RECORD_MAX_S=600         # fork đọc; mỗi bản ghi tự dừng sau chừng ấy giây
AI_LABEL_TEXT=AI-GENERATED CONTENT  # đổi bởi ADR-065 (trước là AI); ở livetalking chỉ dùng chữ ASCII
AI_LABEL_POSITION=top-right
RENDERER_ACK_TIMEOUT_S=3
```

Các biến `LIVETALKING_BATCH_SIZE`, `LIVETALKING_LIP_EVERY_N`, `LIVETALKING_MOUTH_METHOD` (010, thêm 2026-11-13), `LIVETALKING_TRANSITION_S`, `LIVETALKING_HOLD_S`, `AILIVE_RECORD_DIR`, `AILIVE_RECORD_MAX_S` chỉ fork đọc (qua `run.ps1`; hai biến ghi luồng là công cụ tự kiểm, xem quickstart §11). `test_config` hiện
kiểm `.env.example` khớp `Settings`: thêm danh sách biến "chỉ fork đọc" được miễn, thay vì thêm trường không dùng vào `Settings`.

## 6. CLI

| Lệnh | Mục đích |
|------|----------|
| `uv run python -m ai_live.avatar prepare <AVATAR_DIR>` | Chuẩn bị nhân vật (FR-001–005); in bảng kết quả, mã thoát 0 khi `ready` |
| `uv run python -m ai_live.avatar check <AVATAR_DIR>` | Chỉ kiểm `character.json` + hồ sơ nguồn gốc (không gọi fork, không GPU) |
| `powershell scripts/livetalking/setup.ps1` | Dựng fork + venv (một lần) |
| `powershell scripts/livetalking/run.ps1` | Bật fork ở terminal riêng |
