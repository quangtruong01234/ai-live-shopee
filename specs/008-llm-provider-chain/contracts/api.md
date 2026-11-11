# Hợp đồng HTTP và WebSocket: 008-llm-provider-chain

> Mở rộng `specs/001-local-reply-pipeline/contracts/api.md` và `specs/004-show-director/contracts/api.md`. Không thêm endpoint mới.
> App vẫn chỉ bind `127.0.0.1`.

## 1. Endpoint thay đổi

| Method | Path | Thay đổi | Lỗi mới |
|--------|------|----------|---------|
| GET | `/api/state` | thêm khóa `llm_chain`: `ChainSnapshot` (data-model §6), hoặc `null` khi `REPLY_ENGINE` khác `chain` | |
| GET | `/health` | thêm `reply_engine`; khi `chain` thêm `llm_ready: bool` (có ít nhất một mục sẵn sàng). Vẫn trả `200` khi `llm_ready=false` | |
| POST | `/api/debug/fault` | body thêm `entry: str \| null`. `mode` thêm `rate_limited`, `overloaded`, `empty`, `wrong_platform`, `interrupted`. Có `entry` thì `step` phải là `llm` và `mode` thuộc `ENTRY_FAULT_MODES` (`timeout` dùng được cho cả hai dạng) | `422` khi `entry` không có trong chuỗi, khi mode theo mục thiếu `entry`, hoặc khi có `entry` mà `REPLY_ENGINE` khác `chain`. Vẫn `404` khi `APP_ENV != dev` |

Ví dụ:

```json
POST /api/debug/fault
{"step": "llm", "mode": "rate_limited", "count": 3, "entry": "sealion"}
→ 200 {"step": "llm", "mode": "rate_limited", "count": 3, "entry": "sealion", "pending": 3}
```

## 2. WebSocket `/ws/control`

- Message mới `{"type": "llm_chain", "ts": …, …ChainSnapshot}`: gửi mỗi khi trạng thái chuỗi đổi (chuyển mục, nghỉ, lượt đầu tiên
  của một mục khác `last_entry`). FR-017, SC-007: tới trang trong ≤ 2 s sau lần chuyển.
- Message `state` lúc mới kết nối có `llm_chain` như `GET /api/state`.

## 3. Trang điều khiển (`app/static/control.{html,js}`)

Khu "Model LLM" (chỉ hiện khi `llm_chain` khác `null`), không có nút nào (FR-020):
- Dòng chính: "Đang nói bằng: `<label>` (`<model>`)" theo `last_entry`.
- Cảnh báo vàng "Đang dùng model dự phòng" khi `using_backup`, kèm lý do và giờ thử lại của các mục đứng trước (US3 #2).
- Bảng mục: thứ tự, nhãn, model, nền tảng (nếu có), trạng thái (`sẵn sàng` / `nghỉ tới HH:MM:SS (lý do)`). Mục `resting` có `retry_at`
  đã qua hiện là `sẵn sàng` mà không cần sự kiện mới (research R9).
- Cảnh báo đỏ khi mọi mục đều không sẵn sàng: "Không có model nào sẵn sàng; show sẽ vào chế độ dự phòng" (trường hợp biên của spec).
  Dịch vụ gom key tắt giữa show hiện như các mục loopback nghỉ với lý do `lỗi kết nối` (FR-019); không có cảnh báo gateway riêng.
- Khu giả lập lỗi (chỉ dev) thêm ô chọn mục và các mode theo mục.

Nhãn lý do tiếng Việt: `rate_limited` "hết hạn mức", `overloaded` "quá tải / lỗi máy chủ", `empty` "trả về rỗng", `connection` "lỗi kết nối",
`timeout` "quá giờ chờ câu đầu", `rejected` "bị từ chối (key/model)", `wrong_platform` "sai nền tảng", `blocked` "bị bộ lọc nội dung
chặn", `interrupted` "đứt giữa chừng".
