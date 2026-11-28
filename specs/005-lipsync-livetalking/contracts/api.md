# Hợp đồng API: 005-lipsync-livetalking

- **Ngày:** 2026-11-06 · Nguồn: [research.md](../research.md) R4, R9, R12 · App vẫn chỉ nghe `127.0.0.1:8000`.
- Lỗi theo dạng chung `{"error": "<mã>", "message": "<tiếng Việt>", "details": {...}}` như 001/004.

## 1. HTTP mới

### `POST /api/avatar/lipsync`: bật lại nhân vật nhép miệng (FR-022, US2 #6)

- Thân: không có. Trả `200`:
  ```json
  {"configured": "livetalking", "active": "livetalking", "reason": null, "consecutive_errors": 0, "changed_at": "2026-11-07T10:05:00+07:00"}
  ```
- Có hiệu lực từ lượt kế tiếp; lượt đang nói không đổi.
- `409 not_lipsync_mode`: "Phiên đang chạy chế độ ảnh tĩnh theo cấu hình, không có nhân vật nhép miệng để bật lại."
- Không kiểm fork còn sống trước khi bật: nếu fork vẫn chết, 2 lượt sau lại tự về ảnh tĩnh (trang điều khiển hiện `health.connected`).

### `GET /api/avatar`: trạng thái hiển thị

```json
{
  "mode": {"configured": "livetalking", "active": "static", "reason": "render_errors", "consecutive_errors": 2, "changed_at": "..."},
  "character": {"character_id": "demo_host_01", "customer_id": "demo_customer_01", "clips": {"idle": 2, "talk": 2}},
  "lipsync": {"connected": false, "boot_id": "…", "fork_commit": "…", "session_id": null, "vram_used_mb": null, "infer_fps": null,
              "last_error": "lipsync_unavailable", "updated_at": "..."}
}
```

Ở `static`: `mode.configured = "static"`, `character` và `lipsync` là `null`.

### `POST /api/debug/speak-audio`: thử nhân vật bằng tiếng có sẵn (FR-011, R12)

- Chỉ có khi router debug bật (như `/api/debug/speak`). Thân request là **byte WAV thô** (`Content-Type: audio/wav`), tên file trong header
  `X-Filename` (mã hóa URL, tùy chọn), tối đa 5 MB (khoảng 160 s ở 16 kHz). Lúc implement đổi từ `multipart/form-data` sang thân thô để
  khỏi thêm `python-multipart` (không có ADR); trang điều khiển gửi thẳng `File` bằng `fetch`.
- Kiểm bằng `wave`: PCM16, mono, 16 000 Hz. Sai → `422 bad_audio`: "File phải là WAV PCM 16-bit, mono, 16 kHz. Đổi bằng lệnh trong
  quickstart bước 6." kèm `details`: định dạng đọc được `{sample_rate, channels, sample_width_bits}`; file không đọc được như WAV →
  `{reason: "not_wav"}`; quá 5 MB → `{size_bytes}`.
- Gửi tiếng vào renderer đang dùng bằng `utterance_id = "dbg-audio-<uuid8>"`, chữ phụ đề = tên file. Trả `200` sau khi phát xong:
  `{"utterance_id": "...", "duration_s": 4.2, "first_frame_s": 1.9, "render_fps": 23.8}`.
- Đang có lượt nói (show chạy) → `409 busy`: "Đang có lượt nói, tạm dừng show rồi thử lại."
- Lỗi renderer → `503` với `error` = `kind` (`host_unavailable`, `lipsync_unavailable`, `timeout`, `vram_oom`), lời tiếng Việt.
- Không lưu file lên đĩa; không ghi nội dung tiếng vào log.

## 2. HTTP đổi

| Endpoint | Đổi |
|----------|-----|
| `GET /avatar-image` | `livetalking`: trả `AVATAR_DIR/face.png` (ảnh dự phòng của chính nhân vật, FR-022) |
| `GET /api/latency` | Thêm `turns`: 20 lượt gần nhất, mới nhất trước, mỗi lượt `{utterance_id, outcome, total_s, render_fps, infer_fps, clips_used}` (ba trường cuối `null` ở `static`); thêm `render_fps` và `infer_fps` dạng `StepStats` (p50/p95, chỉ tính lượt có số) cạnh `steps`, không nằm trong `steps` vì là tốc độ chứ không phải số giây (FR-020; lúc implement T070) |
| `GET /health` | Thêm `avatar: {"configured", "active", "lipsync_connected"}` |
| `GET /host` | Trang host đọc `AVATAR_MODE` và `LIVETALKING_URL` qua `GET /api/host-config` (§3) |

## 3. `GET /api/host-config` (mới, trang host đọc lúc mở)

```json
{"mode": "livetalking", "active": "livetalking", "livetalking_url": "http://127.0.0.1:8010",
 "ai_label": {"text": "AI", "position": "top-right"}}
```

Thêm 2026-11-25 (ADR-092): `"subtitles": bool` = `HOST_SUBTITLES`, mặc định `false`. Trang host chỉ hiện chữ câu đang nói khi
giá trị là `true`; tin `subtitle`/`subtitle_clear` và ack vẫn gửi như cũ.

## 4. `/ws/host`: tin mới và đổi

Giữ toàn bộ tin của ADR-016. (006 thêm vai `?role=obs|host` và mã đóng `4001`: `specs/006-obs-output/contracts/api.md` §2.) Thêm:

| Hướng | Tin | Trường | Ý nghĩa |
|-------|-----|--------|---------|
| host → server | `ready` (đổi) | thêm `lipsync_session: str \| null` | `sessionid` trả từ `POST {livetalking_url}/offer`; `null` ở `static` hoặc khi `/offer` lỗi |
| host → server | `lipsync_session` | `session: str \| null` | Trang host gọi lại `/offer` (sau `mode` hoặc mất WebRTC) và báo phiên mới |
| server → host | `subtitle` | `utterance_id`, `seq`, `text` | Hiện phụ đề câu đang nói ở `livetalking` (ở `static` vẫn dùng `sentence_start`) |
| server → host | `subtitle_clear` | `utterance_id`, `seq` | Xóa phụ đề sau câu |
| server → host | `mode` | `mode: "static" \| "livetalking"`, `reason: str \| null` | Đổi hiển thị: `static` → ẩn `<video>`, hiện `face.png`, nhãn AI bằng CSS, phát tiếng bằng Web Audio; `livetalking` → hiện `<video>`, gọi lại `/offer` nếu cần |

Trang host ở `livetalking` (`host.js`):
- Bấm "Bắt đầu" (bắt buộc vì chính sách tự phát của Chrome): mở AudioContext (cho lúc tự về ảnh tĩnh), gọi `/offer` bằng `RTCPeerConnection`
  (recvonly audio + video), gắn luồng vào `<video autoplay playsinline>`, rồi gửi `ready` kèm `lipsync_session`.
- `/offer` lỗi (fork chưa chạy): vẫn gửi `ready` với `lipsync_session: null`, hiện "Chưa nối được phần nhép miệng"; app sẽ lỗi ở lượt đầu và
  tự về ảnh tĩnh sau 2 lượt.
- Nhãn AI bằng CSS ẩn khi `<video>` đang phát (nhãn đã nằm trong khung), hiện lại ở `static` hoặc khi video chưa có khung.

## 5. Trang điều khiển

- Dải cảnh báo khi `active != configured`: "Nhân vật nhép miệng lỗi 2 lượt liền, đang dùng ảnh tĩnh." + nút "Bật lại nhân vật nhép miệng"
  (`POST /api/avatar/lipsync`). Cập nhật theo sự kiện `avatar_mode` trên `/ws/control`.
- Ô trạng thái nhỏ: "Nhép miệng: đã nối / mất nối · VRAM … MB · … fps" từ sự kiện `lipsync_health`.
- Khu debug: chọn file WAV + nút "Thử bằng tiếng có sẵn" (`POST /api/debug/speak-audio`).
- Bảng độ trễ: thêm hai dòng "fps tạo hình" và "fps suy luận" (số mẫu, trung vị, p95) và bảng "Lượt gần nhất" với cột Tổng (s), fps tạo hình, fps suy luận, Clip (`ảnh tĩnh` khi lượt chạy ở `static`).
