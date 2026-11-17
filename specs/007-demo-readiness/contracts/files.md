# Contract: file log phiên và file ra (007)

> Thư mục phiên: `SESSION_DATA_DIR/<session_id>/` (ngoài git). Mọi dòng JSON qua `redact`, ghi trên worker của `SessionLog`.

## 1. `session.json` (một lần lúc mở phiên)

`SessionInfo` (data-model §3). Không có khóa, URL có khóa hay đường dẫn ảnh người mẫu.

## 2. `gaps.jsonl`

```json
{"show_id": "…", "kind": "script", "counted": true, "seconds": 0.84, "from_id": "…", "to_id": "…", "at": "2026-11-13T10:00:03.120Z"}
```

`at` = lúc câu sau bắt đầu phát. `from_id`/`to_id` là `sentence_id` trong `script_sentences.jsonl` (hoặc `utterance_id` với lượt bình luận).

## 3. `alerts.jsonl`

Một dòng mỗi lần đổi trạng thái: `{"event": "open" | "level" | "auto_skip" | "close", "at": "…", "alert": {…như contracts/api.md §3…}}`.

## 4. `readiness.jsonl`

Một dòng mỗi lần kiểm: `ReadinessResult` (contracts/api.md §1). Lệnh CLI chạy offline không ghi (không có phiên).

## 5. `rehearsal_<show_id>.json` và `.md`

`RehearsalReport` (data-model §4). Bản `.md` tiếng Việt: dòng kết luận tiêu chí 3, 4; điều kiện chạy; bảng số liệu; danh sách khoảng lặng
> 5 s và cảnh báo theo thời điểm kèm câu liền trước; ghi chú.

## 6. Video dự phòng: `BACKUP_VIDEO_DIR/<tên>.*` (mặc định `out/backup_video/`)

- `<tên>.mp4`: chép nguyên từ recorder của fork, không cắt ghép.
- `<tên>.sheet.json`: `BackupVideoSheet` (data-model §5).
- `<tên>.sheet.md`: tờ mô tả tiếng Việt cho người vận hành (nhân vật, khách, bản nội dung, nguồn nội dung, ngày làm, kết quả kiểm, cảnh báo
  chỉ dùng ngoài Shopee).

Bản ghi gốc của recorder (`.wav`, `.jsonl`, `.report.json`, ảnh soi) giữ ở `AILIVE_RECORD_DIR`.
