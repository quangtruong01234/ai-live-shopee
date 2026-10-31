# Hợp đồng sự kiện và log: 001-local-reply-pipeline

## 1. Log JSON (stdout, stdlib `logging` + formatter JSON)

Mọi dòng có: `ts` (ISO8601 UTC), `level`, `logger`, `event`, `session_id`. Dòng thuộc một lượt nói có thêm `utterance_id`.
Mốc độ trễ ghi `event` = tên mốc và `t_mono` (giây, `time.monotonic()`).

| `event` | Trường thêm |
|---------|-------------|
| `comment_received` | `comment_id`, `utterance_id`? (chưa có ở lúc nhận, ghi lại khi lượt bắt đầu) |
| `turn_started` | `utterance_id`, `comment_id`, `priority`, `queue_wait_s` |
| `llm_first_sentence` | `utterance_id`, `t_mono` |
| `tts_first_chunk` | `utterance_id`, `t_mono` |
| `avatar_first_frame` | `utterance_id`, `t_mono` |
| `turn_finished` | `utterance_id`, `outcome`, `error_step`?, `total_s`? |
| `guard_blocked` | `utterance_id`, `reason`, `sentence_hash` (không log nguyên câu bị chặn ở mức INFO) |
| `comment_dropped` | `comment_id`, `reason` |
| `content_replaced` / `content_rejected` | `version` / `issue_count` |
| `control_command` | `command` (`pause` \| `resume` \| `skip`), `t_mono`: lúc server nhận lệnh |
| `control_applied` | `command`, `latency_ms`, `utterance_id`? (skip): lúc gửi `stop` tới trang host (skip) hoặc phát `session_state` (pause/resume) |

**Che secret:** mọi formatter đi qua `security/redact.py`: che giá trị của các biến `*_KEY`, `*_TOKEN`, `*_SECRET` trong cấu hình và chuỗi
dạng key Google `AIza...`. Nội dung comment chỉ log ở mức DEBUG (dữ liệu người xem).

## 2. File phiên `data/sessions/<session_id>/` (JSONL, nằm trong `.gitignore`)

**`comments.jsonl`**, một dòng khi comment có trạng thái cuối:
```json
{"comment_id": "…", "received_at": "2026-10-30T10:00:00Z", "author": "Lan", "text": "…", "truncated": false,
 "status": "answered|skipped|error|dropped", "drop_reason": null, "priority": "HIGH", "utterance_id": "…"}
```

**`utterances.jsonl`**, một dòng khi lượt kết thúc:
```json
{"utterance_id": "…", "comment_id": "…", "catalog_version": "a1b2c3d4e5f6", "llm_model": "gemini-3.8-flash",
 "sentences": ["…"], "outcome": "completed|skipped|error", "error_step": null, "guard_reason": null,
 "marks": {"comment_received": 0.0, "turn_started": 0.01, "llm_first_sentence": 1.12, "tts_first_chunk": 1.15, "avatar_first_frame": 1.31},
 "total_s": 1.31, "queue_wait_s": 0.01}
```
`marks` lưu tương đối so với `comment_received` (giây) để đọc dễ.

**`errors.jsonl`**: `{"ts", "utterance_id"?, "step", "type", "message"}` (đã che secret).

**`latency_summary.json`**: ghi một lần khi app tắt (lifespan shutdown), nội dung là `LatencySummary` của cả phiên, cả hai chế độ
`idle_only` (FR-019).

`GET /api/latency` đọc từ bộ nhớ của phiên hiện tại; file JSONL và `latency_summary.json` dùng để xem lại sau phiên. Ghi file chạy ở executor để không chặn event loop.

## 3. Sự kiện EventBus (đẩy ra `/ws/control`)

| `type` | Payload |
|--------|---------|
| `state` | như `GET /api/state` (chỉ gửi lúc mới kết nối) |
| `comment_accepted` | `{comment_id, author, text, priority}` |
| `comment_dropped` | `{comment_id, author, text, reason}` |
| `queue_changed` | `{queue: [{comment_id, author, text, priority, status}]}` (theo thứ tự `snapshot()`) |
| `turn_started` | `{utterance_id, comment_id, author, text}` |
| `sentence` | `{utterance_id, seq, text}` (câu đã qua guard, sắp phát) |
| `guard_blocked` | `{utterance_id, reason}` |
| `turn_finished` | `{utterance_id, outcome, error_step?, total_s?}` |
| `session_state` | `{state: "running" \| "paused"}` |
| `content_replaced` | `{version, products: [{id, name, is_primary}]}` |
| `host_connection` | `{connected: bool}` |
| `latency` | `LatencySummary`, gửi sau mỗi `turn_finished` |
