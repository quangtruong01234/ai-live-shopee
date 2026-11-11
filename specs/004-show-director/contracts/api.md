# Hợp đồng HTTP / WebSocket: 004-show-director

> Mở rộng hợp đồng của `specs/001-local-reply-pipeline/contracts/api.md`; mọi quy ước chung giữ nguyên: bind `127.0.0.1`, lỗi dạng
> `{"error", "message", "details"}`, `message` tiếng Việt.
> **WebSocket `/ws/host` không đổi**: mỗi câu kịch bản là một `sentence_start` (`seq = 0`) với `utterance_id` riêng.

## 1. Trang điều khiển `/` (thêm khu "Show", FR-019)

- Các nút: **Bắt đầu show**, **Kết thúc**. Ba nút Tạm dừng, Tiếp tục, Bỏ qua của 001 dùng chung. Tên "Bắt đầu show" để khỏi nhầm với nút
  "Bắt đầu" mở khóa âm thanh trên trang host.
- Hiển thị:
  - trạng thái (chưa chạy / đang chạy / tạm dừng / đang chào kết / đã kết thúc);
  - chế độ, với dải cảnh báo "Đang ở chế độ dự phòng" khi `mode = fallback`;
  - phân đoạn đang nói (sản phẩm, chủ đề, câu đang nói) và phân đoạn kế tiếp;
  - 10 câu bị chặn gần nhất kèm lý do; 10 lỗi gần nhất;
  - số khoảng lặng p95/max (cập nhật theo `show_stats`).
- Bộ chọn "phân đoạn kế tiếp" (FR-018): danh sách sản phẩm, rồi chỉ những chủ đề có dữ liệu cho sản phẩm đó (từ `available_topics`).
  Tổ hợp không có dữ liệu không hiện (US5 #2).
- Ô gửi comment mock của 001 giữ nguyên (US6).

## 2. API mới

| Method | Path | Body | Thành công | Lỗi |
|--------|------|------|------------|-----|
| POST | `/api/show/start` | — | `200 {"show_id", "state", "already_running": bool}` | `409 host_unavailable` (host chưa `ready`, chỉ khi chưa có show đang chạy); `409 no_content` (chưa nạp nội dung hợp lệ) |
| POST | `/api/show/end` | — | `200 {"show_id" \| null, "state"}` (idempotent: `idle`/`ended` trả trạng thái hiện tại) | |
| POST | `/api/show/next` | `{"product_id"?: str, "topic"?: Topic}` (ít nhất một trường) | `200 {"product_id", "topic", "origin": "operator"}` | `409 show_not_running` (state ∉ `running`, `paused`); `422 topic_unavailable` (tổ hợp không có dữ liệu hoặc `product_id` không có); `422 validation_error` |
| GET | `/api/show` | — | `200 ShowSnapshot` (§4); `200 null` trước lần bắt đầu show đầu tiên | |

Thông báo lỗi (tiếng Việt):
- `host_unavailable`: "Màn hình host chưa sẵn sàng. Mở /host và bấm Bắt đầu."
- `no_content`: "Chưa nạp file nội dung sản phẩm hợp lệ."
- `show_not_running`: "Show chưa chạy."
- `topic_unavailable`: "Sản phẩm này không có dữ liệu cho chủ đề đã chọn."

## 3. API của 001 thay đổi hành vi

| Path | Thay đổi |
|------|----------|
| `POST /api/pause` | Khi show `running`: show chuyển sang `paused` ở cuối câu đang nói (FR-015). Trả `200 {"state": "paused", "show_state"?}` |
| `POST /api/resume` | Khi show `paused`: chuyển sang `running`, câu kế được tạo tiếng lại (research R7). Trả `200 {"state": "running", "show_state"?}` |
| `POST /api/skip` | Đang trả lời comment: như 001. Đang nói kịch bản: bỏ phần còn lại của phân đoạn. Đang `closing`: dừng ngay và sang `ended`. Trả `200 {"skipped_utterance_id", "skipped_segment_id"?}` |
| `GET /api/state` | Thêm `"show": ShowSnapshot \| null` |
| `PUT /api/content` | Khi show đang chạy: thay nội dung như 001, gọi `on_catalog_replaced` (research R7). Phân đoạn đang nói được nói hết |
| `POST /api/comments` | Khi show `closing`/`ended`: comment vẫn qua bộ lọc nhưng bị ghi `dropped` với `drop_reason: "show_ended"`. Trả `202` như 001 |
| `POST /api/debug/fault` | `step: "llm"` áp dụng cho cả `narrate()` (FR-024). Không thêm bước mới |
| `POST /api/debug/speak` | Khi show `running`/`paused`/`closing`: `409 busy` |

`show_state` chỉ có trong body khi đang có show.

## 4. `ShowSnapshot`

```json
{
  "show_id": "…", "state": "running", "mode": "normal",
  "started_at": "…",
  "current": {"segment_id": "…", "product_id": "p1", "product_name": "…", "topic": "price", "topic_label": "Giá và phân loại",
              "origin": "rotation", "sentence": "…", "seq": 1},
  "next": {"segment_id": "…", "product_id": "p2", "product_name": "…", "topic": "intro", "topic_label": "Giới thiệu chung", "origin": "operator", "status": "ready"},
  "recent_blocked": [{"segment_id": "…", "text": "…", "reason": "unknown_amount", "reason_label": "số tiền không có trong dữ liệu", "at": "…"}],
  "recent_errors": [{"segment_id": "…", "step": "llm", "kind": "rate_limited", "message": "…", "at": "…"}],
  "available_topics": {"p1": ["intro", "highlights", "specs", "price", "promotion", "faq", "call_to_action"], "p2": ["intro", "price", "call_to_action"]},
  "stats": {"segments": 12, "gap_p95_s": null, "gap_max_s": 0.6, "primary_share": 0.5}
}
```
- `recent_blocked[].text` là câu bị chặn. Câu này chỉ hiện trên trang điều khiển local và trong file phiên, không ghi vào log INFO
  (giống `sentence_hash` của 001).
- `message` của lỗi đã qua `redact`.
- `next.status`: `planned` (chưa sinh), `ready` (đã soạn xong), `discarded` (bị bỏ). Trang điều khiển hiện "đã soạn xong" khi `ready`.
- Thứ tự kiểm của `POST /api/show/start`: show đang chạy → `already_running: true`; rồi host (`host_unavailable`); rồi nội dung (`no_content`) (ADR-033).
