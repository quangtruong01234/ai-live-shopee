# Mô hình dữ liệu (Phase 1): Chuỗi model LLM

- **Feature:** `008-llm-provider-chain` · **Ngày:** 2026-11-03 · Nguồn quyết định: [research.md](./research.md)
- Mọi thực thể sống trong bộ nhớ của một phiên chạy app; không có DB. Thứ được ghi xuống đĩa là log JSON và phần `llm_chain` của
  `show_summary_<show_id>.json` (thư mục phiên, gitignore).
- Sửa 2026-11-03 (làm rõ sau plan): bỏ trạng thái `disabled`, bỏ `retry_after_s`, `local_gateways`, request và token trong bản tổng hợp;
  thêm trường `platform` và kết quả kiểm lúc khởi động (§9).

## 1. `ChainEntryConfig` (cấu hình, `core/config.py`)

Một mục trong `LLM_CHAIN` (R2). Model pydantic, `extra="forbid"`.

| Trường | Kiểu | Ràng buộc |
|--------|------|-----------|
| `label` | `str` | 1–24 ký tự, `[a-z0-9_-]`; duy nhất trong chuỗi |
| `base_url` | `str` | không rỗng; `http://` hoặc `https://`; bỏ `/` cuối khi dùng |
| `model` | `str` | không rỗng; không là `auto` hay `fusion`, không bắt đầu bằng `auto:` (so không phân biệt hoa thường) |
| `key_env` | `str` | một trong `GEMINI_API_KEY`, `FREELLMAPI_KEY`, `GROQ_API_KEY`; trường tương ứng của `Settings` phải có giá trị |
| `first_sentence_timeout_s` | `float` | > 0 |
| `platform` | `str \| None` | mặc định `None`; 1–32 ký tự `[a-z0-9_-]`; **bắt buộc** khi `local` (R2, FR-024) |
| `params` | `dict[str, Any]` | mặc định `{}`; không chứa `model`, `messages`, `stream`, `stream_options` |

Thuộc tính suy ra (không cấu hình): `position` (1-based theo thứ tự), `local` (`base_url` trỏ tới `127.0.0.1`, `localhost` hoặc `::1`).

Ràng buộc cả chuỗi (kiểm ở `ChainReplyEngine.from_settings`, lỗi là `ReplyEngineError("config_error")`):
- ít nhất 1 mục khi `REPLY_ENGINE=chain`;
- tổng `first_sentence_timeout_s` ≤ min(`LLM_TIMEOUT_S`, `SCRIPT_LLM_TIMEOUT_S`).

Biến mới của `Settings`: `llm_chain: list[ChainEntryConfig]`, `llm_chain_cooldown_s: float = 60` (≥ 0), `freellmapi_key: SecretStr | None`,
`groq_api_key: SecretStr | None`. `reply_engine` thêm giá trị `chain` và đổi mặc định thành `chain`.

## 2. `EntryState` (lúc chạy, `brain/chain_state.py`)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `label` | `str` | khóa |
| `status` | `Literal["ready", "resting"]` | |
| `reason` | `AttemptReason \| None` | lý do nghỉ, chỉ khi `resting` |
| `retry_at` | `datetime \| None` | chỉ khi `resting` |

Chuyển trạng thái:

```
         mọi lỗi trừ blocked (rate_limited, overloaded, empty, connection, timeout,
                              rejected, wrong_platform, interrupted)
  ready ───────────────────────────────────────────────────────────────────► resting(until)
    ▲                                                                           │
    └─────────────────────── đồng hồ ≥ until (đọc lại mỗi lượt) ─────────────────┘
  ready ──── blocked, hủy (CancelledError) ────► ready  (không đổi)
```

`until = now + LLM_CHAIN_COOLDOWN_S` (cố định, không đọc thời gian chờ của nhà cung cấp).

## 3. `AttemptReason` (enum, `brain/chain_state.py`)

`rate_limited` · `overloaded` · `empty` · `connection` · `timeout` · `rejected` · `wrong_platform` · `blocked` · `interrupted`. Ánh xạ từ
HTTP, header và luồng ở `research.md` R3. Hủy không phải một `AttemptReason`: lần thử bị hủy không được ghi là lỗi.

## 4. `Attempt` (một lần thử một mục trong một lượt)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `label` | `str` | |
| `outcome` | `Literal["ok", "failed", "skipped", "cancelled"]` | `skipped`: mục đang nghỉ, không gọi mạng |
| `reason` | `AttemptReason \| None` | khi `failed` hoặc `skipped` |
| `routed_via` | `str \| None` | giá trị `X-Routed-Via` đầy đủ nếu có (log, kể cả khi `wrong_platform`) |
| `elapsed_s` | `float` | tới câu đầu (`ok`) hoặc tới lỗi |
| `injected` | `bool` | lỗi đến từ giả lập (R8) |

## 5. `TurnRecord` (gửi tới turn observer khi một lượt kết thúc)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `turn_key` | `str` | `comment.id` (trả lời) hoặc `segment_id` (kịch bản) |
| `kind` | `Literal["reply", "segment"]` | |
| `label` | `str \| None` | mục đã ra câu; `None` khi hết chuỗi |
| `model` | `str \| None` | trường `model` của response, nếu không có thì `model` của mục |
| `provider` | `str \| None` | `X-Routed-Via` hoặc host của `base_url` (R6) |
| `attempts` | `list[Attempt]` | theo thứ tự đã thử |
| `outcome` | `Literal["ok", "interrupted", "exhausted", "cancelled"]` | |
| `usage` | `Usage \| None` | `prompt_tokens`, `completion_tokens`, `cached_tokens` (mỗi trường có thể `None`); chỉ để ghi `llm_usage` |

Bất biến: mọi câu của một lượt đến từ đúng một `label` (FR-008, SC-005). Với mục có `platform`, lượt `ok` hoặc `interrupted` luôn có phần
nền tảng của `provider` bằng `platform` (FR-024). Chỉ lần thử cuối có `outcome = ok` hoặc `interrupted`.

## 6. `ChainSnapshot` (trạng thái gửi trang điều khiển)

```json
{
  "entries": [
    {"label": "sealion", "model": "gemma-sea-lion-v4-27b", "platform": "cloudflare", "position": 1, "status": "resting",
     "reason": "rate_limited", "retry_at": "2026-11-03T10:42:05+07:00"}
  ],
  "last_entry": "gptoss",
  "using_backup": true
}
```

- `using_backup` = `last_entry` không phải mục ở vị trí 1.
- Khi `REPLY_ENGINE` khác `chain`, `build_state` trả `llm_chain: null`.

## 7. Phần `llm_chain` của bản tổng hợp show (`ShowStats`)

```json
"llm_chain": {
  "entries": {
    "sealion": {"model": "gemma-sea-lion-v4-27b", "segments": 21, "replies": 3,
                "failures": {"rate_limited": 1, "timeout": 1}}
  },
  "switches": {"rate_limited": 1, "timeout": 1},
  "exhausted": 0
}
```

- `failures` đếm lần thử `failed` của mục theo lý do (kể cả lỗi giả lập); `skipped` không tính.
- `segments` và `replies` là số lượt engine đã trả xong (có thể lệch nhẹ với số lượt đã nói khi bỏ qua; R9).
- Không có request hay token (làm rõ 2026-11-03); token từng lượt nằm trong log `llm_usage`.

## 8. Kết quả bộ kiểm (US4)

Mỗi mục kết quả của `qa_eval run` và `qa_eval script` thêm `model_label`, `model` và `provider` (từ `TurnRecord`). File kết quả thêm
`engine` (`chain` hoặc `chain:<label>`). Phần so với lần trước hiện `engine` của cả hai lần.

## 9. `PreflightResult` (lần kiểm lúc khởi động, R9)

Một dòng cho mỗi mục, ghi vào log `llm_preflight`; không lưu sau khởi động.

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `label` | `str` | |
| `position` | `int` | |
| `ok` | `bool` | |
| `problem` | `Literal["unreachable", "auth", "model_missing", "model_unavailable", "http_error"] \| None` | khi `ok = false` |
| `detail` | `str \| None` | đã che key; ví dụ `unavailable_reason=no_key`, `status=500` |
| `execution_status` | `str \| None` | của freellmapi nếu có (`ready` / `needsKey` / `exhausted`); `exhausted` chỉ là cảnh báo |

Một dòng `ok = false` bất kỳ → `ReplyEngineError("config_error")`, app không khởi động.

## 10. Kiểu nội bộ của engine (`brain/chain_engine.py`, `brain/openai_compat.py`)

Không ra ngoài engine, không ghi xuống đĩa.

`ResolvedEntry` (do `ChainReplyEngine.from_settings` tạo, một cho mỗi mục):

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `config` | `ChainEntryConfig` | §1 |
| `position` | `int` | 1-based |
| `local` | `bool` | suy ra từ `base_url` (§1) |
| `key` | `SecretStr` | giá trị của biến `key_env`; không bao giờ log |

`ModelListing` = `dict[str, ModelRow]`, khóa là `id` của model trong `GET /models`. `ModelRow`:

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `available` | `bool \| None` | freellmapi trả trường này, Groq không trả; chỉ `false` mới là `model_unavailable` (contracts/config.md §4) |
| `unavailable_reason` | `str \| None` | freellmapi, ví dụ `no_key` |
| `execution_status` | `str \| None` | freellmapi (`ready` / `needsKey` / `exhausted`) |
