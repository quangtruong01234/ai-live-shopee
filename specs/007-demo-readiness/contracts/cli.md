# Contract: lệnh `python -m ai_live.ops` (007)

## `readiness`

```
uv run python -m ai_live.ops readiness [--url http://127.0.0.1:8000] [--json]
```

- Gọi `GET {url}/api/readiness` (timeout 10 s). Không nối được app: kiểm offline (research R8), `source: "offline"`.
- In bảng tiếng Việt (mỗi mục một dòng: dấu trạng thái, tên, lời nhắn, việc cần làm), rồi "Việc tự xác nhận", rồi kết luận.
- `--json`: in `ReadinessResult` JSON.
- Mã thoát: 0 "Sẵn sàng", 1 "Chưa sẵn sàng".

## `report`

```
uv run python -m ai_live.ops report <session_dir | session_id> [--show <show_id>] [--json]
```

- Không có `--show`: báo cáo show có `segment` cuối cùng trong phiên. `session_id` tìm trong `SESSION_DATA_DIR`.
- Ghi `rehearsal_<show_id>.md/.json` vào thư mục phiên, in bản `.md` (hoặc JSON với `--json`).
- Mã thoát: 0 khi tiêu chí 3 và 4 đều PASS, 1 khi không, 2 khi không tìm thấy phiên/show.

## `backup-video`

```
uv run python -m ai_live.ops backup-video [--seconds 150] [--content verbatim|script] [--url http://127.0.0.1:8000]
```

- `--seconds` trong 120–180 (ngoài khoảng: lỗi 2). `--content script` dùng kịch bản LLM như show thật (tốn hạn mức, chỉ khi người vận
  hành chọn).
- Điều kiện trước (lỗi thì in việc cần làm, mã 2): app chạy, `avatar.active == livetalking`, host sẵn sàng, không có show đang chạy, fork
  `record_enabled`, `customer_id`/`avatar_id` không rỗng.
- In tiến độ mỗi 10 s; xong in đường dẫn video, tờ mô tả và kết quả kiểm. Mã thoát 0 khi `sheet.ok`, 1 khi kiểm không đạt.
- Ctrl+C: kết thúc show, dừng ghi, không viết tờ mô tả.
