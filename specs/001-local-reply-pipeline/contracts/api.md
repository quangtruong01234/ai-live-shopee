# Hợp đồng HTTP / WebSocket: 001-local-reply-pipeline

> App FastAPI bind `APP_HOST=127.0.0.1` (mặc định). Không đăng nhập: một người vận hành trên máy local (spec, Giả định).
> Bind ra ngoài localhost là rủi ro S6 (`docs/RISKS.md`). Lỗi trả JSON `{"error": "<mã>", "message": "<tiếng Việt>", "details": [...]}`.
> Mã lỗi chung: `validation_error` (422, `details` gồm `loc`, `msg`, `type`, không trả lại nội dung gửi lên), `not_found` (404),
> `method_not_allowed` (405), `http_error` (mã khác, ví dụ 400 khi body không phải JSON hợp lệ).

## 1. Trang

| Method | Path | Trả về |
|--------|------|--------|
| GET | `/` | Trang điều khiển: ô gõ comment (tên + nội dung), hàng đợi, comment bị loại kèm lý do, lượt đang nói, nút Tạm dừng/Tiếp tục/Bỏ qua, nạp nội dung, bảng độ trễ |
| GET | `/host` | Trang host: ảnh avatar, nhãn AI (`AI_LABEL_TEXT`, vị trí `AI_LABEL_POSITION`), phụ đề, nút "Bắt đầu" để mở khóa âm thanh |
| GET | `/static/*` | JS/CSS/ảnh placeholder |

Nhãn AI trên `/host` không có tham số nào để ẩn. `AI_LABEL_TEXT` rỗng thì app không khởi động (Điều I).

## 2. API

| Method | Path | Body | Thành công | Lỗi |
|--------|------|------|------------|-----|
| POST | `/api/comments` | `{"author": str, "text": str}` | `202 {"comment_id", "status": "waiting" \| "dropped", "drop_reason"?, "priority"?}` | `422` sai schema |
| POST | `/api/pause` | — | `200 {"state": "paused"}` (idempotent) | |
| POST | `/api/resume` | — | `200 {"state": "running"}` (idempotent) | |
| POST | `/api/skip` | — | `200 {"skipped_utterance_id": str \| null}` | |
| PUT | `/api/content` | raw `.docx`, header `X-Filename` | `200 {"version", "products": [{id, name, is_primary}]}` | `400 content_invalid` + `details: [ContentIssue]`; `413` quá `CONTENT_MAX_BYTES`; `415` không phải docx |
| GET | `/api/state` | — | `200 {session, queue: [QueuedComment], current_utterance, catalog: {version, products}, viewers: [ViewerBlock]}` (`viewers` thêm bởi ADR-078) | |
| POST | `/api/viewers/block` | `{"author_key": str, "author"?: str, "minutes": int (1–240) \| null}` (`null` = cả phiên) | `200 {"viewers": [ViewerBlock], "removed": int}` (`removed`: số comment đang chờ bị bỏ) | `422` sai schema (FR-029, ADR-078) |
| POST | `/api/viewers/unblock` | `{"author_key": str}` | `200 {"viewers": [ViewerBlock]}` (idempotent; gỡ cả tạm bỏ qua tự động) | `422` |
| GET | `/api/latency` | `?idle_only=bool` | `200 LatencySummary` (xem data-model §4) | |
| GET | `/health` | — | `200 {"status": "ok", "host_connected": bool, "catalog_version"}` | |
| GET | `/favicon.ico` | — | `204` rỗng: trình duyệt tự hỏi biểu tượng; trả rỗng để log và console không có 404 giả (sửa lỗi 2026-11-17) | |
| POST | `/api/debug/fault` | `{"step": "llm" \| "tts" \| "render", "mode": "error" \| "timeout", "count": int}` | `200` | `404` khi `APP_ENV != dev` |
| POST | `/api/debug/speak` | `{"text": str}` (1–300 ký tự) | `200 {"utterance_id"}` sau khi phát xong | `404` khi `APP_ENV != dev`; `409 busy` khi đang có lượt nói; `503 host_unavailable` khi chưa mở `/host` (chưa `ready`) hoặc host không ack kịp. Chạy TTS + renderer, bỏ qua LLM và hàng đợi (Điều IV: chạy riêng khâu renderer) |

Ghi chú:
- `POST /api/comments` trả `202` cả khi comment bị lọc, để trang điều khiển hiện lý do ngay (US2 #4).
- Upload dùng raw body thay vì multipart để khỏi thêm `python-multipart` (research R13). Kiểm tra docx bằng chữ ký zip + `python-docx` mở được.
- `X-Filename` chỉ để ghi `source_name`; server không dùng nó làm đường dẫn ghi file.

## 3. WebSocket `/ws/control` (server → trang điều khiển)

Mỗi message là JSON `{"type": <EventType>, "ts": <ISO8601>, ...}`, đúng các sự kiện EventBus ở [`events.md`](./events.md).
Khi kết nối, server gửi ngay một `state` (cùng nội dung `GET /api/state`). Client không gửi gì (thao tác đi qua HTTP).

## 4. WebSocket `/ws/host` (hai chiều với trang host)

Chỉ một kết nối host tại một thời điểm; kết nối mới thay kết nối cũ (đóng cũ với code `4000`).

> Đổi bởi 006 (ADR-058): `/ws/host?role=obs|host`, vai `obs` thắng `host` (mã đóng `4001` `obs_active`); cùng vai vẫn là `4000`.
> Xem `specs/006-obs-output/contracts/api.md` §2.

**Server → host**

| Message | Dạng | Nội dung |
|---------|------|----------|
| `sentence_start` | JSON | `{"type", "utterance_id", "seq": int, "text", "sample_rate"}` |
| (audio) | binary | PCM16 LE mono, nhiều frame |
| `sentence_end` | JSON | `{"type", "utterance_id", "seq"}` |
| `stop` | JSON | `{"type", "utterance_id"}`: dừng phát ngay, xóa buffer |

**Host → server**

| Message | Nội dung | Ý nghĩa |
|---------|----------|---------|
| `ready` | `{"type"}` | người dùng đã bấm "Bắt đầu", AudioContext chạy |
| `playback_started` | `{"type", "utterance_id", "seq"}` | đã bắt đầu phát câu; câu `seq=0` là mốc `avatar_first_frame` |
| `sentence_played` | `{"type", "utterance_id", "seq"}` | phát xong câu |

Chưa nhận `ready` thì coi như host chưa kết nối (`RendererUnavailable`), để không mất tiếng vì Chrome chặn autoplay (rủi ro Q10).
