# Hợp đồng sự kiện và log: 008-llm-provider-chain

> Mở rộng `specs/001-local-reply-pipeline/contracts/events.md` và `specs/004-show-director/contracts/events.md`. Quy ước chung giữ nguyên:
> log JSON có `ts`, `level`, `logger`, `event`, `session_id`; mọi formatter và mọi dòng ghi file đi qua `security/redact.py`.

## 1. Log JSON mới (logger `ai_live.brain`, trừ `llm_turn`)

Mọi dòng (trừ `llm_preflight`) có `comment_id` (lượt trả lời) hoặc `segment_id` + `topic` (phân đoạn), như `llm_usage` hiện có.
Sửa 2026-11-03 (làm rõ sau plan): thêm `llm_preflight`; bỏ `llm_entry_disabled`, `llm_gateway` và `retry_after_s`.

| `event` | Level | Trường thêm |
|---------|-------|-------------|
| `llm_preflight` | INFO khi `ok`, ERROR khi lỗi, WARNING khi `execution_status=exhausted` | `label`, `position`, `ok`, `problem`?, `detail`? (đã che), `execution_status`? (data-model §9); ghi một lần lúc khởi động, không có `comment_id` / `segment_id` |
| `llm_attempt` | INFO | `label`, `model`, `provider`?, `routed_via`?, `outcome` (`ok`, `failed`, `skipped`), `reason`?, `elapsed_s`, `status`?, `injected` |
| `llm_switch` | WARNING | `from_label`, `to_label`, `reason` |
| `llm_entry_rest` | WARNING | `label`, `reason`, `seconds` (= `LLM_CHAIN_COOLDOWN_S`), `retry_at` |
| `llm_chain_exhausted` | ERROR | `kind` (`rate_limited`, `api_error`), `entries`: `[{label, reason}]` |
| `llm_usage` | INFO | như Gemini (`prompt_tokens`, `output_tokens`, `cached_tokens`), thêm `label`, `model`, `provider`; `output_tokens` lấy từ `usage.completion_tokens` của API (giữ tên trường cũ để log Gemini và chuỗi cùng dạng) |
| `llm_turn` | INFO | logger `ai_live.director`: `utterance_id`, `comment_id`, `label`, `model`, `provider`, `attempts` (số lần thử), `outcome` (FR-005 cho đường comment) |

Không log: header `Authorization`, body request, chữ thô của model (chữ đã nói vẫn ghi ở file lịch sử của 001/004 như cũ).

## 2. Sự kiện EventBus

| `EventType` | Payload | Khi nào |
|-------------|---------|---------|
| `llm_chain` (mới) | `ChainSnapshot` (data-model §6) | trạng thái chuỗi đổi (api.md §2) |

`tests/unit/test_events.py` thêm `LLM_CHAIN` vào danh sách giá trị mong đợi.

## 3. File trong `data/sessions/<session_id>/` (gitignore)

- `show_summary_<show_id>.json`: thêm khóa `llm_chain` (data-model §7); `null` khi `REPLY_ENGINE` khác `chain`.
- `errors.jsonl`: lỗi `llm` hết chuỗi ghi `type` = `kind` của R7, `message` liệt kê lý do từng mục (đã che).
- Không thêm file mới.

## 4. Bộ kiểm (`data/eval/runs/`, `data/eval/script_runs/`, gitignore)

- Mỗi kết quả câu hỏi hoặc phân đoạn thêm `model_label`, `model`, `provider`.
- File chạy thêm `engine` (`chain` hoặc `chain:<label>`); phần so với lần trước in `engine` của hai lần.
