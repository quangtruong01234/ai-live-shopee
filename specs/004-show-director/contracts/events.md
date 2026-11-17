# Hợp đồng sự kiện và log: 004-show-director

> Mở rộng `specs/001-local-reply-pipeline/contracts/events.md`. Quy ước chung giữ nguyên: log JSON có `ts`, `level`, `logger`, `event`,
> `session_id`; mốc có `t_mono`; mọi formatter và mọi dòng ghi file đi qua `security/redact.py`; ghi file chạy ở worker thread.

## 1. Log JSON mới

Mọi dòng thuộc show có `show_id`. Dòng thuộc một câu kịch bản có thêm `segment_id` và `utterance_id`.

| `event` | Trường thêm |
|---------|-------------|
| `show_state` | `state`, `mode`, `reason`? (`operator`, `fallback_after_failures`, `retry_succeeded`, `shutdown`) |
| `segment_requested` | `segment_id`, `product_id`?, `topic`, `origin`, `mode`, `t_mono` (mốc Điều VIII, thay `comment_received`) |
| `segment_ready` | `segment_id`, `first_sentence_s` (từ `segment_requested`) |
| `segment_started` / `segment_finished` | `segment_id`, `status`, `spoken`, `blocked`, `dropped` |
| `llm_first_sentence` / `tts_first_chunk` / `avatar_first_frame` | `utterance_id`, `segment_id`, `t_mono` (cùng tên với 001) |
| `sentence_played` | `utterance_id`, `segment_id`, `t_mono` |
| `sentence_gap` | `from_utterance_id`, `to_utterance_id`, `seconds`, `kind` |
| `sentence_dropped` | `utterance_id`, `segment_id`, `reason` (`duplicate`, `empty_after_clean`, `sentence_count_exceeded`, `paused_discard`, `segment_discarded`) |
| `guard_blocked` | như 001, thêm `segment_id`? và `detail_hash` |
| `mode_changed` | `from`, `to`, `consecutive_failures` |
| `rotation_repeat` | `product_id`, `topic` (chỉ khi catalog có đúng một tổ hợp) |
| `control_command` / `control_applied` | như 001; `command` thêm `show_start`, `show_end`, `show_next` |
| `llm_usage` | như 001, thêm `segment_id`? |

## 2. File trong `data/sessions/<session_id>/` (gitignore)

**`segments.jsonl`**: một dòng khi phân đoạn có trạng thái cuối (`done`, `skipped`, `failed`, `blocked`, `discarded`).
```json
{"segment_id": "…", "show_id": "…", "index": 7, "product_id": "p2", "topic": "promotion", "origin": "rotation", "mode": "normal",
 "catalog_version": "a1b2…", "status": "done", "requested_at": "…", "started_at": "…", "finished_at": "…",
 "sentences": {"spoken": 4, "blocked": 1, "dropped": 0, "tts_error": 0}, "error_step": null, "error_kind": null}
```

**`script_sentences.jsonl`**: một dòng mỗi câu kịch bản ra khỏi LLM (hoặc từ nguồn dự phòng).
```json
{"utterance_id": "…", "segment_id": "…", "seq": 2, "source": "script|fallback|verbatim", "text": "…", "raw_text": "…",
 "status": "spoken|blocked|dropped|tts_error|render_error|interrupted", "guard_reason": null, "guard_detail": null, "drop_reason": null,
 "marks": {"segment_requested": 0.0, "llm_first_sentence": 1.4, "tts_first_chunk": 1.41, "avatar_first_frame": 22.8},
 "played_at": 27.1}
```
`source: "verbatim"`: câu của show đọc nguyên văn (007 R6), đi theo đường dự phòng nhưng không phải sự cố (sửa lỗi
2026-11-17). `marks` và `played_at` lưu tương đối so với `segment_requested` (giây). Câu ở cuối phân đoạn có `avatar_first_frame` lớn, vì nó chờ
các câu trước phát xong. Cách tính khoảng lặng nằm ở `sentence_gap`, không suy ra từ `marks`.

**`show_summary_<show_id>.json`**: `ShowSummary` (data-model §9), ghi khi sang `ended` hoặc khi app tắt giữa show (`ended_by: "shutdown"`).

**Của 001, thêm trường:** `utterances.jsonl` và `comments.jsonl` có `show_id`? (lời trả lời chen vào show). `errors.jsonl` có
`segment_id`?. `latency_summary.json` vẫn chỉ gồm lời trả lời comment.

## 3. Sự kiện EventBus mới (đẩy ra `/ws/control`)

| `type` | Payload |
|--------|---------|
| `show_state` | `{show_id, state, mode}` |
| `segment_started` | `{segment_id, product_id?, product_name?, topic, topic_label, origin, mode}` |
| `segment_finished` | `{segment_id, status}` |
| `segment_next` | `{segment_id?, product_id?, topic, origin, status}` (khi slot kế đổi: sinh xong, người vận hành chọn, hoặc bị bỏ; `status` ∈ `planned`, `ready`, `discarded`, khớp `next.status` ở api.md §4; `planned` = người vận hành vừa chọn, chưa có `segment_id`) |
| `show_stats` | `ShowSnapshot.stats` (sau mỗi phân đoạn kết thúc) |
| `show_error` | `{segment_id?, step, kind, message}` (đã redact) |

Sự kiện của 001 thay đổi:
- `sentence` thêm `segment_id?`.
- `guard_blocked` thêm `segment_id?`, `text`, `reason_label`. `text` chỉ đi qua WebSocket localhost, không vào log INFO.
- `comment_dropped.reason` có thể là `show_ended`; khi đó payload có thêm `show_id` (các lý do khác giữ payload 001).
- `state` (lúc mới kết nối) có thêm `show`.
- `turn_started` / `turn_finished` không phát cho câu kịch bản (chỉ cho lượt trả lời comment), để bảng độ trễ 001 giữ nguyên ý nghĩa.
