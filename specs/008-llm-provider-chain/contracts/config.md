# Hợp đồng cấu hình: 008-llm-provider-chain

> Cấu hình chỉ đọc từ biến môi trường / `.env` qua `pydantic-settings` (ADR-015). Mặc định trong `Settings` và `.env.example` phải khớp
> (`tests/unit/test_config.py`). Quyết định ở `research.md` R2, R4, R5, R9; ràng buộc ở `data-model.md` §1.
> Sửa 2026-11-03 (làm rõ sau plan): thêm trường `platform`, lần kiểm qua mạng lúc khởi động (§4); bỏ việc tắt mục khi lỗi cấu hình.

## 1. Biến mới hoặc đổi

| Biến | Kiểu | Mặc định | Ghi chú |
|------|------|----------|---------|
| `REPLY_ENGINE` | `chain \| gemini \| fake` | **`chain`** (trước là `gemini`) | spec "Giả định"; `gemini` và `fake` vẫn chọn được (FR-001) |
| `LLM_CHAIN` | mảng JSON một dòng | 3 mục của ADR-035 (bên dưới) | FR-003 |
| `LLM_CHAIN_COOLDOWN_S` | float ≥ 0 | `60` | FR-010; thời gian nghỉ cố định cho mọi lỗi trước câu đầu (trừ `blocked`) |
| `FREELLMAPI_KEY` | secret | trống | key thống nhất của freellmapi (ADR-034), dạng `freellmapi-…` |
| `GROQ_API_KEY` | secret | trống | key Groq gọi thẳng, dạng `gsk_…` |

Biến giữ nguyên nhưng được dùng thêm:
- `GEMINI_API_KEY`: được tham chiếu khi một mục có `key_env = GEMINI_API_KEY`.
- `LLM_MAX_TOKENS` (300), `SCRIPT_MAX_TOKENS` (600): gửi thành `max_tokens` cho `reply()` / `narrate()`.
- `LLM_TIMEOUT_S` (8), `SCRIPT_LLM_TIMEOUT_S` (10): chặn trên của tổng `first_sentence_timeout_s`.
- `LLM_MODEL`, `LLM_THINKING_LEVEL`: chỉ dùng khi `REPLY_ENGINE=gemini`. Tham số suy luận của chuỗi nằm trong `params` từng mục.

Khi `REPLY_ENGINE=chain`, key không được mục nào tham chiếu có thể để trống.

**Hệ quả với test:** đổi mặc định sang `chain` làm app cần `FREELLMAPI_KEY` và `GROQ_API_KEY` để khởi động. Test và fixture hiện đặt
`REPLY_ENGINE=fake` hoặc truyền engine vào thẳng; `/sdd.tasks` phải có một task rà lại mọi nơi tạo `Settings()` mặc định trong test.

## 2. Giá trị mặc định của `LLM_CHAIN`

```
LLM_CHAIN=[{"label":"sealion","base_url":"http://127.0.0.1:3001/v1","model":"gemma-sea-lion-v4-27b","key_env":"FREELLMAPI_KEY","platform":"cloudflare","first_sentence_timeout_s":2.5},{"label":"qwen","base_url":"https://api.groq.com/openai/v1","model":"qwen/qwen3.8-27b","key_env":"GROQ_API_KEY","first_sentence_timeout_s":2.0,"params":{"reasoning_effort":"none"}},{"label":"gemini","base_url":"https://generativelanguage.googleapis.com/v1beta/openai","model":"models/gemini-3.5-flash-lite","key_env":"GEMINI_API_KEY","first_sentence_timeout_s":2.0,"params":{"reasoning_effort":"low"}}]
```

Chuỗi theo ADR-040: `gptoss` bị bỏ vì không đạt SC-001 ở T055; giờ chờ SEA-LION hạ từ 3,5 s xuống 2,5 s (cổng Q18). `.env.example` giữ
mục `gptoss` cũ thành dòng chú thích. ADR-073 (2026-11-20) thêm mục cuối `gemini`: `models/gemini-3.5-flash-lite` gọi thẳng endpoint
OpenAI của Google (không qua freellmapi, không khai `platform`), chờ câu đầu 2,0 s; tổng ba mục 6,5 s ≤ 8 s.
Các ví dụ thông báo lỗi ở §3–§4 vẫn dùng chuỗi 3 mục cũ (mục 2 `gptoss`) để minh họa hai mục chung một `base_url`.

`platform` là id nền tảng của freellmapi mà benchmark ADR-035 đã chạy (`cloudflare` cho SEA-LION, `groq` cho gpt-oss-120b trước ADR-040; research R2,
R6). Mục `qwen` gọi thẳng Groq nên không khai `platform`.

- Mục Gemini qua freellmapi (mục 4 cũ) đã chốt ở ADR-073 thành gọi thẳng Google, 2,0 s.
- `TODO:` xác nhận ba tên model bằng `GET /v1/models` (research R2); lần kiểm lúc khởi động (§4) cũng báo sai ngay.

## 3. Lỗi cấu hình lúc khởi động (FR-004)

`ChainReplyEngine.from_settings()` ném `ReplyEngineError("config_error", <thông báo tiếng Việt>)`; app không khởi động (như thiếu
`GEMINI_API_KEY` ở 001). Mẫu thông báo (không bao giờ chứa giá trị key):

| Lỗi | Thông báo |
|-----|-----------|
| chuỗi rỗng | `LLM_CHAIN trống: cần ít nhất một mục khi REPLY_ENGINE=chain` |
| JSON sai | lỗi validation của pydantic-settings (nêu tên biến `LLM_CHAIN`) |
| model `auto`, `auto:*`, `fusion` | `LLM_CHAIN mục 2 (gptoss): không được dùng model "auto"; ghi tên model cụ thể (ADR-035)` |
| loopback thiếu `platform` | `LLM_CHAIN mục 1 (sealion): base_url trỏ tới dịch vụ gom key nên phải khai platform (ví dụ "cloudflare")` |
| thiếu model / URL | `LLM_CHAIN mục 1 (sealion): thiếu model` / `... thiếu base_url` |
| key_env lạ | `LLM_CHAIN mục 3 (qwen): key_env "FOO_KEY" không hợp lệ; dùng GEMINI_API_KEY, FREELLMAPI_KEY hoặc GROQ_API_KEY` |
| key trống | `LLM_CHAIN mục 3 (qwen): GROQ_API_KEY chưa có giá trị trong .env` |
| trùng label | `LLM_CHAIN: nhãn "sealion" bị trùng` |
| params cấm | `LLM_CHAIN mục 2 (gptoss): params không được đặt "model"` |
| tổng giờ chờ | `LLM_CHAIN: tổng first_sentence_timeout_s là 9.0 s, vượt 8.0 s (min của LLM_TIMEOUT_S và SCRIPT_LLM_TIMEOUT_S)` |

## 4. Lỗi của lần kiểm lúc khởi động (FR-011, SC-009)

Sau §3, lifespan gọi `await engine.preflight()` (research R9): một `GET {base_url}/models` cho mỗi cặp (`base_url`, `key_env`), giới hạn
5 s. Một dòng lỗi bất kỳ → `ReplyEngineError("config_error")`, app không khởi động. Thông báo liệt kê mọi mục lỗi, không chứa key:

| `problem` | Khi | Thông báo |
|-----------|-----|-----------|
| `unreachable` | lỗi kết nối hoặc quá 5 s | `LLM_CHAIN mục 1 (sealion): không kết nối được http://127.0.0.1:3001/v1; dịch vụ gom key đã chạy chưa?` |
| `auth` | 401 / 403 | `LLM_CHAIN mục 3 (qwen): GROQ_API_KEY bị từ chối (401)` |
| `model_missing` | 200 nhưng không có `data[].id` bằng `model` | `LLM_CHAIN mục 2 (gptoss): không có model "gpt-oss-120b" ở http://127.0.0.1:3001/v1` |
| `model_unavailable` | có model nhưng `available: false` | `LLM_CHAIN mục 1 (sealion): model "gemma-sea-lion-v4-27b" chưa dùng được (unavailable_reason=no_key)` |
| `http_error` | status khác | `LLM_CHAIN mục 1 (sealion): kiểm model trả status 500` |

- `execution_status: exhausted` của freellmapi chỉ ghi cảnh báo vào `llm_preflight`, không chặn khởi động.
- Lần kiểm không xác nhận được nền tảng mong đợi còn key; lỗi đó lộ ra ở lượt đầu thành `wrong_platform` (research R9).

Lỗi cấu hình chỉ lộ ra giữa show (key bị thu hồi, model bị tắt trên dashboard) không có trạng thái riêng: lần thử thành `rejected`, mục
nghỉ `LLM_CHAIN_COOLDOWN_S` rồi được thử lại như mọi lỗi khác (research R3).
