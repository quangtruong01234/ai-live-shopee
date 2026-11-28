# Contract: API, sự kiện và tin WebSocket (007)

> Bổ sung cho contracts của 001/004/005/009; phần không nhắc tới giữ nguyên.

## 1. `GET /api/readiness`

Chạy kiểm tra trước demo (FR-001…FR-006). Chỉ đọc trạng thái; không gọi LLM, không phát tiếng/hình, không đổi show. Mỗi lần gọi ghi
một dòng `readiness.jsonl`. Có ở mọi `APP_ENV`.

```json
{
  "checked_at": "2026-11-13T10:00:00+00:00",
  "source": "app",
  "ready": false,
  "duration_ms": 412,
  "items": [
    {"id": "reply_engine", "label": "Bộ trả lời", "status": "fail",
     "message": "REPLY_ENGINE=fake (câu nói vô nghĩa)", "action": "Đặt REPLY_ENGINE=chain trong .env rồi bật lại app"}
  ],
  "manual": ["Văn bản đồng ý (hình + giọng) của người mẫu đã ký, bản ký lưu ngoài git", "..."]
}
```

`status` ∈ `ok | warn | fail | unknown`. Thứ tự `items` cố định theo data-model §1.

## 2. `POST /api/show/start` (thêm thân tùy chọn)

```json
{"content": "verbatim"}
```

- Không có thân (hoặc thân không có `content`): dùng `SHOW_CONTENT` trong `.env`, mặc định `"loop"` (ADR-088). `"script"`: như 004.
- `"loop"` (ADR-088): lặp một đoạn cố định dựng từ file (giới thiệu, mô tả, giá, khuyến mãi) kèm câu mời hỏi tư vấn, không gọi engine;
  comment vẫn trả lời bằng LLM. Trả lời thêm `"content": "loop"`.
- `"verbatim"`: show đọc nguyên văn giới thiệu + mô tả trong file sản phẩm, không gọi engine (research R6). Trả lời thêm
  `"content": "verbatim"`. Show đang chạy thì trả show đó với `already_running: true` (không đổi nguồn nội dung).
- Giá trị khác (kể cả `null` ghi rõ): 422.

`GET /api/show` (`ShowSnapshot`) thêm `content_source`.

## 3. Sự kiện `alert` (WebSocket điều khiển `/ws/control`)

Mỗi lần cảnh báo mở, đổi mức, tự gỡ hoặc đóng:

```json
{"type": "alert", "alert": {"alert_id": "…", "kind": "silence", "level": "warning", "state": "open",
  "show_id": "…", "started_at": "…", "ended_at": null, "seconds": null,
  "message": "Host im lặng 6 giây", "action": "Đợi vài giây; nếu quá 15 giây hệ thống sẽ tự bỏ câu đang kẹt",
  "auto_action": null, "close_reason": null}}
```

`state` ∈ `open | closed`. `GET /api/state` thêm `alerts`: danh sách cảnh báo đang mở (trang tải lại vẫn thấy).

Trang điều khiển: banner cảnh báo trên cùng, màu vàng (`warning`) hoặc đỏ (`operator`), một dòng mỗi cảnh báo đang mở; tự ẩn khi đóng.
Không phát âm thanh.

## 4. Tin `host_status` (tab host → app, `/ws/host`)

Mỗi 1 giây sau khi bấm "Bắt đầu":

```json
{"type": "host_status", "frames": 1834, "audio": "running", "video_muted": false, "video_paused": false, "visible": false}
```

Renderer chỉ nhận từ kết nối hiện tại, phát `EventType.HOST_STATUS` với `HostStatus` (data-model §2); không trả lời tab host. Trường thiếu
hoặc sai kiểu thì coi là `null`.

## 5. `GET /health` (thêm trường)

`customer_id`, `avatar_id` (chuỗi, có thể rỗng), `show_active` (bool). Lệnh làm video dự phòng đọc ở đây.

## 6. Fork `GET /ailive/health` (thêm trường)

`record_enabled`: `true` khi fork bật với `AILIVE_RECORD_DIR`. App không đọc biến môi trường của fork, nên readiness lấy ở đây.
