# Tasks: Chuỗi model LLM miễn phí, tự chuyển model khi lỗi

- **Feature ID:** 008-llm-provider-chain · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`
- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong).
- **[GPU]**: cần GPU (laptop trước theo ADR-023, RunPod chỉ dự phòng); gom vào "Đợt GPU" ở cuối. Feature này **không có** task GPU.
- **[US#]**: thuộc user story nào trong spec.
- Mỗi task ghi **đường dẫn file cụ thể**. Đường dẫn mã nguồn tính từ `src/ai_live/`.
- Mọi test chạy không mạng, không key: dùng nhà cung cấp giả `tests/fixtures/fake_openai.py` (`httpx.MockTransport`, FR-023), trừ
  `tests/live/` (marker `live_llm`, cần người dùng đồng ý trước khi chạy).
- Quyết định lúc tạo tasks: `tests/fixtures/fake_openai.py` **không** có chế độ server riêng (Điều VII); các bước bằng tay ở quickstart US2
  chạy với chuỗi thật và đánh dấu **[mạng + hạn mức]**.

## Phase 1: Setup

- [x] T001 `pyproject.toml`: chuyển `"httpx>=0.28.1"` từ nhóm `dev` sang `dependencies` (giữ nguyên version, không thêm package; ADR-035,
  người dùng duyệt 2026-11-03); đổi mô tả marker `live_llm` thành "gọi LLM thật (Gemini hoặc chuỗi model)"; chạy `uv sync` và kiểm
  `uv.lock` không đổi version nào.
- [x] T002 [P] `.env.example`: `REPLY_ENGINE=chain`; dòng `LLM_CHAIN=` đúng giá trị mặc định ở contracts/config.md §2;
  `LLM_CHAIN_COOLDOWN_S=60`; `FREELLMAPI_KEY=`, `GROQ_API_KEY=` để trống; một dòng ví dụ đã comment cho mục 4 (Gemini qua freellmapi, ghi
  rõ chỉ bật sau khi qua bộ kiểm US4).

---

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

- [x] T003 [P] `tests/conftest.py`: thêm `"FREELLMAPI_"` và `"GROQ_"` vào `_ENV_PREFIXES` để key thật trong môi trường không lọt vào test
  (`LLM_CHAIN*` đã nằm trong `"LLM_"`); fixture `settings` giữ `reply_engine="fake"`.
- [x] T004 [P] `tests/unit/test_config.py` (viết trước, phải FAIL): mặc định `reply_engine == "chain"`; `llm_chain` mặc định parse ra
  đúng 3 mục của contracts/config.md §2 (label, base_url, model, key_env, platform, first_sentence_timeout_s, params);
  `llm_chain_cooldown_s == 60`; `freellmapi_key`, `groq_api_key` mặc định `None` (kiểu `SecretStr | None` như `gemini_api_key`, data-model §1); `ChainEntryConfig` theo data-model §1: label
  1–24 ký tự `[a-z0-9_-]`, `base_url` phải http(s), `first_sentence_timeout_s > 0`, `platform` 1–32 ký tự `[a-z0-9_-]`, `extra=forbid`,
  `position` suy ra theo thứ tự; JSON `LLM_CHAIN` sai báo lỗi nêu tên biến; test so mặc định với `.env.example` vẫn qua với 5 biến mới.
- [x] T005 `core/config.py`: `ChainEntryConfig` (pydantic, data-model §1); `reply_engine: Literal["chain", "gemini", "fake"] = "chain"`;
  `llm_chain: list[ChainEntryConfig]` với mặc định ở contracts/config.md §2; `llm_chain_cooldown_s: float = 60` (≥ 0);
  `freellmapi_key`, `groq_api_key: SecretStr | None = None`. Phụ thuộc T004.
- [x] T006 Rà mọi nơi tạo `Settings()` mặc định trong test (tìm `Settings(` trong `tests/`) sau khi mặc định đổi sang `chain`:
  `tests/unit/test_cli.py:51` và `tests/unit/test_gemini_engine.py:250` đặt `reply_engine` rõ ràng (`fake` hoặc `gemini` theo ý test);
  `tests/live/test_gemini_engine.py:31`, `tests/live/test_gemini_narrate.py:29` đặt `reply_engine="gemini"`. `uv run pytest` vẫn xanh.
  Phụ thuộc T005.
- [x] T007 [P] `tests/unit/test_events.py`: thêm `LLM_CHAIN` (`"llm_chain"`) vào danh sách giá trị `EventType` mong đợi (contracts/events.md §2).
- [x] T008 `core/events.py`: `EventType.LLM_CHAIN`. Phụ thuộc T007.
- [x] T009 [P] `tests/unit/test_redact.py`: che mẫu `gsk_…`, `freellmapi-…`, `sk-…`; che theo chính giá trị key truyền vào (kể cả key
  không theo mẫu nào); chuỗi không có key giữ nguyên (research R12, SC-008).
- [x] T010 `security/redact.py`: thêm ba mẫu và hàm che theo danh sách giá trị secret. Phụ thuộc T009.
- [x] T011 [P] `tests/unit/test_chain_state.py` (đồng hồ giả): mục mới là `ready`; `rest(label, 60, reason)` trả `retry_at = now + 60`, mục
  thành `resting` có lý do; qua `retry_at` thì `status()` đọc là `ready` mà không cần gọi gì thêm; `RESTING_REASONS` gồm mọi
  `AttemptReason` trừ `BLOCKED`; `snapshot()` giữ thứ tự mục; nhãn lạ báo lỗi (data-model §2, §3; contracts/adapters.md §4).
- [x] T012 `brain/chain_state.py`: `AttemptReason` (StrEnum, 9 giá trị), `RESTING_REASONS`, `EntryState`, `ChainState` thuần (không I/O, không
  asyncio). Phụ thuộc T011.
- [x] T013 [P] `tests/fixtures/fake_openai.py`: nhà cung cấp OpenAI-compatible giả dựng trên `httpx.MockTransport`, kịch bản theo
  (`base_url`, `model`):
  - `POST /chat/completions` stream SSE: các khúc chữ (có thể chèn trễ), dòng keepalive `:`, trường suy luận cần bỏ qua, khúc `usage`
    (có `cached_tokens`), `finish_reason` (kể cả `content_filter`), `[DONE]`; frame `{"error":…}` trước hoặc sau câu đầu; luồng rỗng;
  - status HTTP kèm body lỗi (`error.code` kiểu freellmapi hoặc `error.type`); lỗi kết nối; treo không trả chữ (để thử hết giờ chờ);
  - header `X-Routed-Via` tùy chọn: thiếu, `cache`, `idempotency`, `cloudflare/<model>`, `Groq/<model>`, …;
  - `GET /models`: danh sách `data[].id` có `available`, `unavailable_reason`, `execution_status`; 401/403; status khác; lỗi kết nối;
  - ghi lại mọi request (path, header, body) và số dòng SSE client đã đọc, để test kiểm "0 request" và "không đọc dòng SSE nào".
- [x] T014 [P] `docs/ARCHITECTURE.md` §3: thêm `REPLY_ENGINE` (`chain | gemini | fake`) vào danh sách biến chọn adapter; §1 (sơ đồ,
  bước 4) đổi "Gemini API" thành chuỗi model theo ADR-035/037, ghi "chưa code" tới khi feature xong. `src/README.md`: dòng `brain/`
  thêm `chain_engine.py`, `chain_state.py`, `openai_compat.py` (contracts/adapters.md §1).
- [x] T015 [P] `core/protocols.py`: docstring `ReplyEngine` thêm "Implementations: ChainReplyEngine (OpenAI-compatible model chain,
  ADR-035/037), GeminiReplyEngine, FakeReplyEngine." Protocol không đổi.

**Checkpoint:** nền tảng sẵn sàng, các story bắt đầu được.

---

## Phase 3: User Story 1: Host nói bằng model đầu chuỗi (P1) 🎯 MVP

**Mục tiêu:** với `REPLY_ENGINE=chain`, show 004 và đường comment 001 nói bằng mục 1 của chuỗi, cùng prompt và guard; mỗi lượt ghi model,
nhà cung cấp, nhãn mục; cấu hình sai hoặc key/model/dịch vụ gom key hỏng thì app không khởi động.

**Kiểm thử độc lập:** quickstart US1 phần "Không mạng" và "Từ chối cấu hình sai" bước 1–4; chuỗi một mục với nhà cung cấp giả.

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [x] T016 [P] [US1] `tests/unit/test_openai_compat.py`: body request đúng
  `{"model","messages","stream":true,"stream_options":{"include_usage":true},"max_tokens",**params}`; header `Authorization: Bearer`,
  thêm `X-FreeLLM-Cache: off` chỉ khi mục có `platform`; parse SSE: bỏ dòng `:`, dừng ở `data: [DONE]`, lấy chữ từ
  `choices[0].delta.content`, bỏ trường suy luận, đọc `finish_reason`, `model`, `usage` vào `StreamMeta`; `list_models` đọc `data[].id`,
  `available`, `unavailable_reason`, `execution_status`, 401 → `ProviderFailure(REJECTED, 401)`, lỗi kết nối → `CONNECTION`; thông báo
  lỗi đã che key (contracts/adapters.md §3).
- [x] T017 [P] [US1] `tests/unit/test_chain_engine.py` (phần US1):
  - chuỗi một mục: `reply()` và `narrate()` yield từng câu hoàn chỉnh qua `SentenceSplitter`, có `flush()` cuối luồng; `messages` dựng từ
    `build_system_prompt`/`build_user_message` và `build_script_system_prompt`/`build_segment_message` như Gemini (FR-002); `max_tokens`
    là `LLM_MAX_TOKENS` cho `reply()`, `SCRIPT_MAX_TOKENS` cho `narrate()`;
  - turn observer nhận `TurnRecord` `outcome="ok"` có `label`, `model`, `provider` (lấy từ `X-Routed-Via`, không có thì host của
    `base_url`), `usage`; log `llm_attempt` và `llm_usage` có `label`, `model`, `provider` và `comment_id` hoặc `segment_id` + `topic`
    (FR-005); không dòng log nào chứa header `Authorization`, body request hay giá trị key;
  - `from_settings`: mỗi dòng bảng contracts/config.md §3 ném `ReplyEngineError("config_error")` đúng thông báo tiếng Việt, không chứa
    key (FR-004); `only="gptoss"` ra chuỗi một mục, nghỉ 0 s; `only` nhãn lạ là `config_error`;
  - `preflight()`: một `GET /models` cho mỗi cặp (`base_url`, `key_env`) (chuỗi mặc định → 2 request); mỗi `problem` ở contracts/config.md
    §4 (`unreachable`, `auth`, `model_missing`, `model_unavailable`, `http_error`) ném `config_error` liệt kê mọi mục lỗi theo số thứ tự
    và nhãn; `execution_status: exhausted` chỉ ghi WARNING; log `llm_preflight` mỗi mục (FR-011, SC-009).
- [x] T018 [P] [US1] `tests/contract/conftest.py`, `tests/contract/test_reply_engine_contract.py`: thêm `ChainReplyEngine` (nhà cung cấp
  giả) vào các engine chạy contract test `ReplyEngine`: câu hoàn chỉnh không rỗng, chỉ ném `ReplyEngineError` với `kind` hợp lệ, không
  đổi `catalog` (contracts/adapters.md §1).
- [x] T019 [P] [US1] `tests/integration/test_show_api.py`: app tạo bằng `create_app(reply_engine=<ChainReplyEngine với transport giả>)`:
  `preflight()` lỗi thì lifespan ném `ReplyEngineError("config_error")`, app không nhận request, thông báo không chứa key (US1 #6);
  `preflight()` qua thì show chạy, phân đoạn đầu nói bằng mục 1 và vẫn có mốc `segment_requested`, `llm_first_sentence` (FR-006);
  `aclose()` được gọi lúc tắt app.
- [x] T020 [P] [US1] `tests/integration/test_show_director.py`: với `ChainReplyEngine` giả, mỗi câu trả lời comment ghi `llm_turn`
  (logger `ai_live.director`) có `utterance_id`, `comment_id`, `label`, `model`, `provider`, `attempts`, `outcome` (FR-005, US1 #3);
  câu có giá lạ do model giả sinh vẫn bị guard chặn như với Gemini (US1 #4, FR-002); trả lời comment xong thì phân đoạn kế của kịch
  bản vẫn chạy bằng chuỗi, đúng chủ đề kế tiếp (US1 #2).

### Implement US1

- [x] T021 [US1] `brain/openai_compat.py`: `ProviderFailure`, `StreamMeta`, `ModelListing`/`ModelRow`, `OpenAICompatClient(client, secrets)`
  với `stream_chat()` (stream SSE bằng `aiter_lines`, header, body, `X-FreeLLM-Cache: off` khi có `platform`) và `list_models()` (giới hạn
  5 s); `httpx.Timeout(connect=2.0, read=None, write=5.0, pool=2.0)`; mọi thông báo qua `security/redact.py` với giá trị key.
  Phụ thuộc T010, T012, T013, T016.
- [x] T022 [US1] `brain/chain_engine.py`: `Usage`, `Attempt`, `TurnRecord`, `PreflightResult`, `ResolvedEntry`, `FaultHook`;
  `ChainReplyEngine` với `from_settings(settings, *, only=None, fault_hook=None)` (mọi luật ở contracts/config.md §3, gồm tổng
  `first_sentence_timeout_s` ≤ min(`LLM_TIMEOUT_S`, `SCRIPT_LLM_TIMEOUT_S`)), `preflight()`, `reply()`, `narrate()` đường một mục: lấy câu
  đầu trong `asyncio.timeout(first_sentence_timeout_s)` rồi **ra khỏi khối timeout mới `yield`** (research R1), yield các câu còn lại,
  `finally` đóng response và gửi `TurnRecord`; `add_turn_observer`, `entries`, `aclose()`; log `llm_attempt`, `llm_usage`, `llm_preflight`
  (contracts/events.md §1). Phụ thuộc T005, T012, T017, T021.
- [x] T023 [US1] `brain/factory.py`: nhánh `chain` → `ChainReplyEngine.from_settings(settings, only=..., fault_hook=...)` (import muộn
  như Gemini); `create_reply_engine` nhận thêm `only` và `fault_hook` tùy chọn. Phụ thuộc T022.
- [x] T024 [US1] `app/main.py`: lifespan gọi `await engine.preflight()` khi engine là `ChainReplyEngine`, trước khi nhận request (lỗi thì
  app không khởi động); `await engine.aclose()` lúc tắt; nhãn `llm_model` truyền cho `ShowDirector` (dòng 104) và health/state
  (dòng 125–126) là `"chain"` khi `REPLY_ENGINE=chain`. Phụ thuộc T019, T023.
- [x] T025 [US1] `director/show_director.py`: khi engine có `add_turn_observer`, đăng ký observer ghi `llm_turn` cho lượt trả lời comment,
  nối `turn_key` (= `comment.id`) với `utterance_id`. Phụ thuộc T020, T022.
- [x] T058 [P] [US1] `tests/unit/test_cli.py` (viết trước, phải FAIL): `python -m ai_live.brain ask` và `narrate` với
  `REPLY_ENGINE=chain` (nhà cung cấp giả `tests/fixtures/fake_openai.py`) gọi `preflight()` trước lượt đầu; `preflight()` lỗi thì in
  thông báo tiếng Việt không chứa key, thoát mã 1 và không gọi `/chat/completions`; `aclose()` được gọi cả khi lỗi (FR-011, US1 #6;
  thêm sau phân tích 2026-11-04).
- [x] T059 [US1] `brain/__main__.py`: khi engine là `ChainReplyEngine`, chạy `preflight()`, lượt `ask`/`narrate` và `aclose()` trong
  cùng một `asyncio.run` (client httpx gắn với một event loop); `ReplyEngineError("config_error")` in thông báo và thoát mã 1 như lỗi
  cấu hình hiện có; cập nhật docstring đầu file. Phụ thuộc T022, T023, T058.

**Checkpoint:** US1 chạy và test độc lập được (T016–T020, T058 xanh; quickstart US1 "Từ chối cấu hình sai" bước 1–4). Dừng lại, báo người dùng,
demo. Bảng a–f và show 5 phút của quickstart US1 cần **[mạng]** / **[mạng + hạn mức]**, làm ở T055.

---

## Phase 4: User Story 2: Tự chuyển model khi lỗi (P1)

**Mục tiêu:** lỗi trước câu đầu thì chuyển mục kế và cho mục lỗi nghỉ cố định; lỗi sau câu đầu thì dừng, không trộn câu hai model; mục
đang nghỉ bị bỏ qua không tốn request; hết chuỗi báo lỗi nhanh để show vào chế độ dự phòng của 004; sai nền tảng thì từ chối.

**Kiểm thử độc lập:** test không mạng của phase này; quickstart US2 bước 1–8 **[mạng + hạn mức]** với giả lập lỗi theo mục.

### Test cho US2 (viết trước, phải FAIL trước khi implement)

- [x] T026 [P] [US2] `tests/unit/test_openai_compat.py` (phần US2): mỗi dòng bảng research R3 ra đúng `reason`: 429 → `rate_limited`;
  500/502/503/504 và frame lỗi SSE → `overloaded`; 502 `empty_completion` → `empty`; `ConnectError`/`ReadError`/`RemoteProtocolError` →
  `connection`; 400/401/403/404 `model_not_found`/422/4xx khác, 502 `provider_authentication_failed`, 502 `provider_error`, 503
  `no_providers_configured` → `rejected`; đọc cả `error.code` và `error.type`; không đọc `Retry-After`. Kiểm nền tảng (FR-024): mục có
  `platform`, `X-Routed-Via` thiếu / `cache` / `idempotency` / nền tảng khác → `wrong_platform`, response đóng và **0 dòng SSE** đã đọc;
  `Cloudflare/gemma…` khớp `cloudflare` (không phân biệt hoa thường, chỉ phần trước `/` đầu tiên); mục không có `platform` không kiểm.
- [x] T027 [P] [US2] `tests/unit/test_chain_engine.py` (phần US2, đồng hồ giả, chuỗi 3 mục):
  - mỗi lý do trước câu đầu (trừ `blocked`) chuyển sang mục kế, mục lỗi nghỉ `cooldown_s`, log `llm_switch` + `llm_entry_rest` (FR-007,
    FR-010); mục treo bị bỏ sau `first_sentence_timeout_s` của chính nó (FR-009);
  - lỗi sau câu đầu → `interrupted`: ném `ReplyEngineError("api_error")`, mục nghỉ, không chuyển, không câu nào của mục 2 trong lượt đó
    (FR-008, US2 #3);
  - mục đang nghỉ: `Attempt(skipped)`, **0 request** tới mục đó (SC-004); hết `retry_at` thì lượt kế bắt đầu lại từ mục 1 (FR-015, US2 #6);
  - `content_filter` không có chữ → `blocked`: chuyển, không nghỉ;
  - hủy lượt (`aclose()` generator hoặc `CancelledError`) trước và sau câu đầu: không nghỉ, không chuyển, `TurnRecord.outcome="cancelled"`
    (FR-013);
  - hết chuỗi: mọi lý do `rate_limited` → `kind="rate_limited"`, lẫn lý do → `api_error`; thông báo liệt kê lý do từng mục đã che key;
    log `llm_chain_exhausted`; khi mọi mục đang nghỉ, lỗi ném ra trong ≤ 1 s và 0 request (FR-012, SC-006);
  - `reply()` và `narrate()` chạy đồng thời dùng chung một `ChainState`;
  - `fault_hook` trả từng mode của `ENTRY_FAULT_MODES` ra đúng `reason`, `Attempt.injected=True`; `interrupted` giả lập lỗi sau câu đầu;
    lỗi giả lập ngay ở mục 1 chỉ cộng ≤ 1 s vào thời gian tới câu đầu với nhà cung cấp giả (SC-003).
- [x] T028 [P] [US2] `tests/unit/test_faults.py` (mới): `inject("llm", mode, count, entry="sealion")` xếp hàng theo nhãn; `take_entry`
  lấy từng mode rồi trả `None`; `pending_entry` đếm đúng; `entry` với `step` khác `llm` hoặc mode ngoài `ENTRY_FAULT_MODES` báo lỗi; lỗi
  theo bước của 004 không đổi (contracts/adapters.md §5).
- [x] T029 [P] [US2] `tests/integration/test_show_director.py` (phần US2): show với chuỗi giả mà mọi mục lỗi vào chế độ dự phòng sau đúng
  `SCRIPT_FALLBACK_AFTER` lần lỗi liên tiếp như Gemini (SC-006); mục 1 lỗi giữa phân đoạn thì phân đoạn dừng ở câu cuối đã nhận và phân
  đoạn kế nói bằng mục 2, không phân đoạn nào có câu của hai mục (US2 #3, SC-005); câu bị guard chặn không làm chuyển mục (FR-014, US2 #7);
  `errors.jsonl` ghi `type` = `kind` của lượt hết chuỗi và `message` liệt kê lý do từng mục (contracts/events.md §3).
- [x] T030 [P] [US2] `tests/integration/test_show_api.py` (phần US2): `POST /api/debug/fault` có `entry` trả `200` với `entry`, `pending`;
  `422` khi `entry` không có trong chuỗi, khi mode theo mục thiếu `entry`, khi có `entry` mà `REPLY_ENGINE` khác `chain`; `404` khi
  `APP_ENV != dev`; lỗi đã xếp hàng làm lượt kế chuyển mục (FR-016, contracts/api.md §1).

### Implement US2

- [x] T031 [US2] `brain/openai_compat.py`: phân loại lỗi theo bảng research R3; kiểm nền tảng `X-Routed-Via` ngay sau status line, trước
  dòng SSE đầu, sai thì đóng response và ném `ProviderFailure(WRONG_PLATFORM)` có `routed_via`. Phụ thuộc T026.
- [x] T032 [US2] `brain/chain_engine.py`: vòng thử nhiều mục (bỏ mục nghỉ, chuyển trước câu đầu, `interrupted` sau câu đầu, `blocked` không
  nghỉ, hủy không đổi `ChainState`), hết chuỗi theo research R7, gọi `fault_hook(label)` trước mỗi lần thử, log `llm_switch`,
  `llm_entry_rest`, `llm_chain_exhausted`. Phụ thuộc T027, T031.
- [x] T033 [US2] `director/faults.py`: `ENTRY_FAULT_MODES`, `inject(..., entry=None)`, `take_entry(label)`, `pending_entry(label)`.
  Phụ thuộc T028.
- [x] T034 [US2] `app/routes.py`: `FaultIn.entry: str | None`, mode mới, kiểm `422` theo contracts/api.md §1, response có `entry` và
  `pending`. Phụ thuộc T030, T033.
- [x] T035 [US2] `app/main.py`: truyền `faults.take_entry` làm `fault_hook` cho `create_reply_engine` **chỉ khi** `APP_ENV=dev`; đưa danh
  sách nhãn mục cho route kiểm `entry`. Phụ thuộc T024, T032, T033.
- [x] T036 [US2] `director/show_director.py`: lỗi `llm` hết chuỗi ghi `errors.jsonl` với `type` = `kind` và `message` đã che; vẫn tính vào
  bộ đếm lỗi liên tiếp của chế độ dự phòng như lỗi Gemini. Phụ thuộc T029, T032.

**Checkpoint:** US2 chạy và test độc lập được (T026–T030 xanh). Dừng lại, báo người dùng, demo. Quickstart US2 bước 1–10 **[mạng + hạn mức]**
làm ở T055.

---

## Phase 5: User Story 3: Theo dõi model đang nói (P2)

**Mục tiêu:** trang điều khiển hiện mục đang nói, cảnh báo khi dùng model dự phòng trong ≤ 2 s, bảng trạng thái mục; bản tổng hợp show
có phần `llm_chain`.

**Kiểm thử độc lập:** test không mạng của phase này; quickstart US3 bước 1–4.

### Test cho US3 (viết trước, phải FAIL trước khi implement)

- [x] T037 [P] [US3] `tests/unit/test_chain_engine.py` (phần US3): `snapshot()` đúng data-model §6 (`entries` với `label`, `model`,
  `platform`, `position`, `status`, `reason`, `retry_at`; `last_entry`; `using_backup`); state observer được gọi khi chuyển mục, khi mục
  nghỉ và ở lượt đầu tiên của một mục khác `last_entry`; mục nghỉ quá `retry_at` hiện `ready` (FR-019); khi mọi mục đang nghỉ, mọi
  `entries[].status` là `resting` để trang điều khiển hiện cảnh báo đỏ (trường hợp biên "toàn bộ chuỗi đang nghỉ lúc bắt đầu show").
- [x] T038 [P] [US3] `tests/unit/test_show_stats.py`: phần `llm_chain` của bản tổng hợp theo data-model §7: `segments`, `replies` theo mục,
  `failures` theo lý do (tính cả lỗi giả lập, không tính `skipped`), `switches` theo lý do, `exhausted`; `null` khi `REPLY_ENGINE` khác
  `chain`; không có request hay token (FR-018).
- [x] T039 [P] [US3] `tests/integration/test_show_api.py` (phần US3): `/api/state` có `llm_chain` (là `null` với engine giả cũ); `/health`
  có `reply_engine` và, khi `chain`, `llm_ready` (vẫn `200` khi `false`); sau một lần chuyển mục, `/ws/control` nhận message
  `{"type":"llm_chain",…}` trong ≤ 2 s; message `state` lúc kết nối có `llm_chain` (FR-017, SC-007, contracts/api.md §2); mọi mục
  đang nghỉ thì bắt đầu show vẫn thành công, show vào chế độ dự phòng như 004 và `/health` có `llm_ready = false` (trường hợp biên).

### Implement US3

- [x] T040 [US3] `brain/chain_engine.py`: `snapshot()`, `add_state_observer()`, gọi state observer theo contracts/api.md §2. Phụ thuộc T032,
  T037.
- [x] T041 [US3] `director/show_stats.py`: gom `TurnRecord` thành phần `llm_chain` của bản tổng hợp (data-model §7). Phụ thuộc T038.
- [x] T042 [US3] `director/show_director.py`: turn observer đưa `TurnRecord` của cả phân đoạn và câu trả lời vào `ShowStats`; bản tổng hợp
  `show_summary_<show_id>.json` có khóa `llm_chain`. Phụ thuộc T025, T036, T041.
- [x] T043 [US3] `app/main.py`: đăng ký state observer phát `EventType.LLM_CHAIN` lên EventBus; giữ tham chiếu engine chuỗi cho state và
  health. Phụ thuộc T008, T035, T040.
- [x] T044 [US3] `app/context.py`: `build_state` thêm `llm_chain` (`ChainSnapshot` hoặc `null`). Phụ thuộc T043.
- [x] T045 [US3] `app/routes.py`: `/health` thêm `reply_engine` và `llm_ready` (có ít nhất một mục sẵn sàng). Phụ thuộc T034, T043.
- [x] T046 [US3] `app/static/control.html`, `app/static/control.js`: khu "Model LLM" theo contracts/api.md §3 (chỉ hiện khi `llm_chain`
  khác `null`, **không có nút**, FR-020): dòng "Đang nói bằng: `<label>` (`<model>`)", cảnh báo vàng "Đang dùng model dự phòng" kèm lý do
  và giờ thử lại, bảng mục (thứ tự, nhãn, model, nền tảng, trạng thái; mục quá `retry_at` hiện "sẵn sàng" không cần sự kiện mới), cảnh báo
  đỏ khi không mục nào sẵn sàng, nhãn lý do tiếng Việt; khu giả lập lỗi (dev) thêm ô chọn mục và mode theo mục. Phụ thuộc T044.

**Checkpoint:** US3 chạy và test độc lập được (T037–T039 xanh; quickstart US3 bước 1–3 với giả lập lỗi, bước 4 tìm chuỗi key). Dừng lại,
báo người dùng, demo.

---

## Phase 6: User Story 4: Kiểm từng model (P3)

**Mục tiêu:** bộ câu hỏi mẫu (001) và bộ tự kiểm tra kịch bản (004) chạy với cả chuỗi hoặc ghim một mục; báo cáo ghi model và nền tảng;
phần so với lần trước hiện engine của hai lần.

**Kiểm thử độc lập:** test không mạng của phase này; quickstart US4 **[mạng + hạn mức]**.

### Test cho US4 (viết trước, phải FAIL trước khi implement)

- [x] T047 [P] [US4] `tests/unit/test_qa_eval_script_cli.py`: `script --entry gptoss` chạy chuỗi một mục; `--entry` khi `REPLY_ENGINE`
  khác `chain` là lỗi cấu hình; `preflight()` chạy trước phân đoạn đầu, lỗi thì thoát với mã lỗi cấu hình và không sinh phân đoạn nào;
  nhãn engine `chain` hoặc `chain:<label>` (FR-021, contracts/adapters.md §6); mục ghim lỗi (nhà cung cấp giả trả `429`) thì phân
  đoạn đó ghi lỗi dịch vụ, không gọi mục khác, không tính vi phạm, và lệnh thoát với `EXIT_INCOMPLETE` (3) (FR-021).
- [x] T048 [P] [US4] `tests/unit/test_cli.py`: như T047 cho `qa_eval run --entry`; runner ghi `model_label`, `model`, `provider` cho mỗi câu
  hỏi, file kết quả có `engine`, phần so với lần trước in `engine` của cả hai lần (FR-022, data-model §8); mục ghim lỗi thì câu hỏi đó
  ghi lỗi dịch vụ, không gọi mục khác và không tính điểm (FR-021).
- [x] T049 [P] [US4] `tests/unit/test_script_eval.py`: mỗi kết quả phân đoạn ghi `model_label`, `model`, `provider`; file kết quả có `engine`;
  phần so với lần trước in `engine` của hai lần (FR-022).

### Implement US4

- [x] T050 [US4] `qa_eval/runner.py`: đăng ký turn observer, ghi `model_label`, `model`, `provider` mỗi câu hỏi; `engine` thay cho
  `llm_model` trong file chạy và tiêu đề so sánh (dòng 60, 257, 348). Phụ thuộc T022, T048.
- [x] T051 [US4] `qa_eval/script_eval.py`: như T050 cho phân đoạn; nhánh chọn engine (dòng 620 `gemini = settings.reply_engine == "gemini"`)
  chạy đúng với `chain`. Phụ thuộc T022, T049.
- [x] T052 [US4] `qa_eval/__main__.py`: cờ `--entry LABEL` cho `run` và `script` (gọi `create_reply_engine(settings, only=LABEL)`); chạy
  `preflight()` trước câu hỏi đầu, lỗi thì thoát mã lỗi cấu hình; nhãn engine `chain` / `chain:<label>` (dòng 161, 255); `aclose()` cuối
  lần chạy. Phụ thuộc T023, T047, T050, T051.

**Checkpoint:** US4 chạy và test độc lập được (T047–T049 xanh). Dừng lại, báo người dùng, demo.

---

## Phase 7: Hoàn thiện và việc chung

- [x] T053 [P] `tests/live/test_chain_engine.py` (mới, marker `live_llm`): với mỗi mục ghim bằng `only=`, một `reply()` và một `narrate()`
  thật ra ≥ 1 câu, `provider` khớp `platform` của mục; `preflight()` thật qua. **Chạy cần người dùng đồng ý** (tốn hạn mức free).
- [x] T054 Chạy `uv run pytest` (bỏ `live_llm`) và `uv run ruff check . && uv run ruff format --check .`: sạch.
- [x] T055 Chạy quickstart (`specs/008-llm-provider-chain/quickstart.md`) **cùng người dùng** (bước **[mạng]** / **[mạng + hạn mức]** cần đồng
  ý): US1 bảng a–f và show 5 phút; US2 bước 1–10; US3 bước 1–4; US4 cho từng mục. Điền bảng "Kết quả kiểm chứng" với số đo thật:
  SC-001 (bộ câu hỏi ≥ 8/10, kịch bản 0 vi phạm, từng mục), SC-002, SC-003, SC-005, SC-007, SC-008, SC-009; thay số "ước tính" trong bảng
  độ trễ của `plan.md` bằng số đo. Chạy app với stdout chuyển vào `logs/` như quickstart US3 bước 4 để kiểm SC-008. **Cổng Q18:** đếm
  số câu chào mở màn có câu đầu > 5 s; nếu quá 1/10 lần thì dừng và hỏi người dùng có hạ `first_sentence_timeout_s` của `sealion`
  không (research R4, plan "Theo dõi độ phức tạp").
- [x] T056 `docs/ARCHITECTURE.md` §1 bỏ ghi "chưa code" và ghi số đo độ trễ của T055; `specs/004-show-director/tasks.md`: ghi chú ở
  T075–T079 rằng adapter chuỗi đã xong (G1 dùng `tests/live/test_chain_engine.py`).
- [x] T057 `/update-context` (CLAUDE.md, `docs/DECISIONS.md`, `docs/ROADMAP.md`, `progress/`).

---

## Phụ thuộc và thứ tự

- Setup (T001–T002) → Foundational (T003–T015) → US1 → US2 → US3 → US4 → Polish.
- Trong Foundational: T004 → T005 → T006; T007 → T008; T009 → T010; T011 → T012. T003, T013, T014, T015 độc lập.
- US1: T016 → T021 → T022 → T023 → T024; T017 → T022; T019 → T024; T020 + T022 → T025; T058 → T059 (cần T022, T023). T018 xanh khi T022 xong.
- US2 cần US1 xong (cùng file `openai_compat.py`, `chain_engine.py`, `app/main.py`): T026 → T031 → T032; T027 → T032; T028 → T033 → T034;
  T030 → T034; T032 + T033 → T035; T029 + T032 → T036.
- US3 cần US2 (state observer dựa trên chuyển và nghỉ; `routes.py`, `main.py` nối tiếp T034, T035): T037 → T040 → T043 → T044 → T046;
  T038 → T041 → T042; T043 → T045.
- US4 cần T022, T023 (US1); không cần US2, US3: có thể làm song song với US2/US3 nếu khác người làm.
- Polish cần mọi story xong; T055 cần T053 và người dùng.

## Chạy song song

- Foundational đợt 1: T003, T004, T007, T009, T011, T013, T014, T015 (8 file khác nhau).
- US1 test: T016, T017, T018, T019, T020, T058 cùng lúc.
- US2 test: T026, T027, T028, T029, T030 cùng lúc; T033 làm song song với T031–T032 khi T028 đã viết (không gắn `[P]` vì phụ thuộc T028).
- US3 test: T037, T038, T039 cùng lúc; T041 làm song song với T040 khi T038 đã viết (không gắn `[P]` vì phụ thuộc T038).
- US4 test: T047, T048, T049 cùng lúc.
- Chủ file theo `/sdd.dispatch` §2: `brain/`, `qa_eval/`, `tests/live/`, `test_openai_compat.py`, `test_chain_engine.py`,
  `test_chain_state.py` → ai-brain; `core/`, `director/`, `security/`, `app/`, `test_show_*.py`, `test_faults.py` → ai-orchestrator;
  `tests/contract/`, `tests/conftest.py`, `tests/fixtures/`, `test_cli.py` → ai-qa; `docs/`, quickstart → phiên chính.

## Đợt GPU

Không có. Feature chỉ đổi bộ sinh lời thoại; mọi test chạy với `AVATAR_MODE=static` và `TTS_PROVIDER=fake`.

## Chiến lược MVP

1. Setup + Foundational → 2. US1 → **dừng, kiểm chứng, demo** → 3. thêm US2, US3, US4 từng bước một.

US1 một mình đã thay được Gemini bằng mục 1 của chuỗi; US2 mới làm chuỗi chịu được lỗi, nên **không lên demo thật trước khi US2 xong**.

## Đối chiếu FR / SC → task

| Yêu cầu | Task |
|---------|------|
| FR-001 | T005, T023, T024 |
| FR-002 | T017, T018, T020 |
| FR-003 | T004, T005 |
| FR-004 | T017, T022 |
| FR-005 | T017, T020, T025 |
| FR-006 | T019 |
| FR-007 | T026, T027, T031, T032 |
| FR-008 | T027, T029, T032 |
| FR-009 | T017 (tổng giờ chờ), T027, T022 |
| FR-010 | T011, T012, T027, T032 |
| FR-011 | T017, T019, T022, T024, T058, T059 |
| FR-012 | T027, T029, T032 |
| FR-013 | T027, T032 |
| FR-014 | T029 |
| FR-015 | T027, T032 |
| FR-016 | T027, T028, T030, T033–T035, T046 |
| FR-017 | T039, T046 |
| FR-018 | T038, T041, T042 |
| FR-019 | T037, T046 |
| FR-020 | T005, T046 |
| FR-021 | T047, T048, T052 |
| FR-022 | T048, T049, T050, T051 |
| FR-023 | T013, T053 |
| FR-024 | T026, T031 |
| SC-001 | T055 |
| SC-002 | T027, T055 |
| SC-003 | T027, T055 |
| SC-004 | T027 |
| SC-005 | T026, T029, T055 |
| SC-006 | T027, T029 |
| SC-007 | T039, T055 |
| SC-008 | T009, T017, T055 |
| SC-009 | T017, T019, T055 |

Không còn FR hay SC nào chưa có task.

## Nhật ký lỗi gặp khi implement

- 2026-11-04 (Foundational): sau T005 mặc định `REPLY_ENGINE=chain` nhưng `brain/factory.py` `create_reply_engine` coi mọi giá trị khác `fake` là Gemini, nên tới khi US1 nối `ChainReplyEngine` thì `chain` lặng lẽ dựng `GeminiReplyEngine`. US1 (T022/T023) phải thêm nhánh `chain` rõ ràng và báo lỗi với giá trị lạ.
- 2026-11-04 (Foundational): `ChainEntryConfig` kiểm `base_url` http(s) và `model` bắt buộc ở mức trường, nên thông báo "thiếu base_url" / "thiếu model" của contracts/config.md §3 do pydantic báo (nêu `LLM_CHAIN`), `from_settings` chỉ còn gặp model rỗng; `key_env` để `str` để `from_settings` báo lỗi kèm số mục.
- 2026-11-04 (Foundational): `ChainState.rest(..., BLOCKED)` ném `ValueError`; `ChainReplyEngine` phải kiểm `reason in RESTING_REASONS` trước khi gọi. research.md R1 còn mô tả API cũ (`resting(until, reason)`, `next_ready`), code theo contracts/adapters.md §4.
- 2026-11-04 (Foundational): `fake_openai` đếm `lines_read` ngay khi client kéo khúc đầu, nên `OpenAICompatClient` phải kiểm `X-Routed-Via` trước `aiter_lines()`; `hang_without_text()` gửi một khúc `Role` (lines_read = 1), muốn 0 dòng thì dùng `ChatReply(events=[Hang()])`.
- 2026-11-04 (US1): T018 có ca `wrong-platform` nhưng kiểm nền tảng nằm ở T031 (US2); ai-brain làm trước phần kiểm `X-Routed-Via` trong `openai_compat.stream_chat` (sau dòng trạng thái, trước dòng SSE đầu; so không phân biệt hoa thường phần trước dấu `/`; mục không khai `platform` thì không kiểm). Phân loại mã lỗi đầy đủ theo research R3 vẫn là T031 (hiện: 429 → rate_limited, 5xx → overloaded, còn lại → rejected).
- 2026-11-04 (US1): guard chặn câu hoặc bỏ lượt thì đóng stream, engine nhận `GeneratorExit` nên `llm_turn` ra `outcome="cancelled"`; contracts/events.md chưa ghi trường hợp này. Engine log lỗi observer bằng `turn observer failed`, tên này chưa có trong events.md §1.
- 2026-11-04 (US1): `/health` chưa hiện `reply_engine`/chuỗi (là T045, US3); T024 chỉ đổi nhãn `llm_model="chain"` cho `ShowDirector` và log `app_started`. Lỗi `SessionLog.open`/`renderer.start()` sau khi preflight đạt thì client httpx chưa được đóng (tiến trình đang thoát).
- 2026-11-04 (US2): test tích hợp mở `TestClient(app)` sau khi fixture `json_log_lines` gắn bộ gom log thì `configure_logging` lúc khởi động app xóa bộ gom (`root.handlers[:] = [handler]`) và test thấy 0 dòng log. Dựng client trong fixture được yêu cầu **trước** `json_log_lines` (như `wired_chain_client`, `closing_client`).
- 2026-11-04 (US2): ai-brain chọn: 5xx ngoài bảng R3 (501, 505…) → `overloaded`; hook trả mode lạ hoặc ném lỗi thì log `fault hook failed` / `unknown entry fault mode` và thử mục bình thường (hai tên log chưa có trong events.md); giả lập `interrupted` vẫn mở stream thật (research R8), các mode khác không gửi request; giả lập `timeout` chờ đủ giới hạn của mục. ai-orchestrator đặt mã `422` `chain_not_active`, `unknown_entry` (contracts/api.md §1 chưa ghi tên mã).
- 2026-11-04 (US2): wave-check 2/4 lần chạy liền nhau gặp `OSError: [WinError 10055]` ở `socket.socketpair()` của asyncio (Windows hết socket loopback), chạy lại thì xanh; không phải lỗi code.
- 2026-11-04 (US3/US4): phiên API hết giới hạn giữa đợt (ai-brain US4, ai-orchestrator US3 đợt 1); tiếp tục bằng cách gửi lại cho đúng agent sau khi giới hạn đặt lại, agent đọc lại file trước khi sửa tiếp.
- 2026-11-04 (US3): ai-orchestrator chọn (data-model §7 để ngỏ): `segments`/`replies` chỉ đếm lượt `ok`; lượt `interrupted` tính 1 lỗi lý do `interrupted`; lượt `cancelled` không đếm nhưng các lần thử hỏng trước đó vẫn tính; lần thử bị bỏ qua vì mục đang nghỉ không tính lỗi. Director nhận ra engine chuỗi bằng `add_turn_observer` (không theo `settings.reply_engine`, vì Settings mặc định là `chain` mà test dùng engine giả).
- 2026-11-04 (US3): trang điều khiển của 004 chưa có khu giả lập lỗi; T046 làm mới form "Giả lập lỗi (dev)", hiện khi `GET /api/debug/fault` trả 405 (route chỉ có ở `APP_ENV=dev`, ngoài dev là 404). Muốn cờ rõ ràng trong `/health` hoặc `/api/state` thì phải sửa contracts/api.md trước. Khu "Model LLM" mới kiểm bằng test tĩnh, chưa mở trình duyệt.
- 2026-11-04 (US4): ai-brain chọn mã thoát `qa_eval run`: 2 khi `điểm + số câu lỗi dịch vụ < ngưỡng`; còn lại 3 nếu có câu lỗi dịch vụ; còn lại 0 (7 đúng + 1 lỗi /10 trước thoát 2, nay thoát 3). File kết quả câu hỏi đổi `llm_model` → `engine`, thêm `previous_engine` (vẫn đọc file cũ); `previous` của bộ kiểm kịch bản thêm `engine`, `model` (khác data-model §10 của 004). Chạy cả chuỗi lưu `model` là danh sách model nối bằng dấu phẩy.
- 2026-11-04 (Polish): T053 viết xong nhưng chưa chạy (cần người dùng đồng ý, mỗi lần 3 `GET /models` + 6 lượt chat; `sealion`, `gptoss` cần freellmapi đang chạy). Nhãn test đọc lúc collect; `LLM_CHAIN` hỏng thì ra 1 test bỏ qua `no-chain`, nên khi chạy ở T055 phải thấy "9 passed" chứ không phải "1 skipped"; chạy từ thư mục gốc repo (`data/products/demo.docx` là đường dẫn tương đối). T056: phần ghi chú đã sửa (ARCHITECTURE §1, ghi chú T075–T079 của 004), số đo độ trễ còn `TODO:` chờ T055 nên chưa tick.
- 2026-11-04 (T055): kiểm "`GROQ_API_KEY=` trống" bằng biến môi trường shell không làm app từ chối, vì `Settings` có `env_ignore_empty=True` nên biến trống rơi về giá trị trong `.env`; không phải lỗi app. Kiểm lại bằng `Settings(_env_file=None)` (nạp `.env` trừ `GROQ_API_KEY`) thì ra đúng thông báo. Bảng a–f lần e giả lập bằng `base_url` `127.0.0.1:3999`, chưa tắt freellmapi thật.
- 2026-11-04 (T055): "Bỏ qua" bằng `POST /api/show/next` không hủy lần thử đang chạy (route chờ phân đoạn đang chuẩn bị); kiểm FR-013 bằng comment + `POST /api/skip` thì đạt (`llm_turn outcome=cancelled`, không có `llm_entry_rest`).
- 2026-11-04 (T055): `qa_eval` không bật log INFO, nên đầu ra không có `llm_preflight` / `llm_attempt` như quickstart US4 mong đợi; nhãn mục đọc từ báo cáo. `qa_eval script` không có `--pace` (cố định 6 s), với hạn mức free của Groq gần nửa số phân đoạn lỗi dịch vụ (qwen 10/21 `rate_limited`); lần chấm lại nhịp 30 s dùng script tạm gọi `run_script_check(pace_s=30)`.
- 2026-11-05 (T055): người dùng chọn hạ giờ chờ `sealion` và nhờ chọn cách xử lý `gptoss` → ADR-040: chuỗi mặc định còn `sealion` 2,5 s
  → `qwen`. Sửa `DEFAULT_LLM_CHAIN`, `.env.example`, test chuỗi mặc định (test luật cấu hình / preflight dùng `RULES_CHAIN` 3 mục
  riêng trong `test_chain_engine.py`); 1372 test pass. Đo lại: Q18 0/10 câu chào > 5 s (lớn nhất 3,31 s); `qwen` kịch bản 21/21,
  0 vi phạm. SC-009 d đạt (người dùng tắt key SEA-LION). US2 bước 9 đạt (người dùng tắt / bật Cloudflare giữa show, lỗi 503
  `rejected` chứ không phải `connection`); US3 người dùng xem bằng trình duyệt, đạt; bước 10 bỏ qua (không còn `gptoss`). Người dùng
  chấp nhận SC-007 ("ok chạy đi"); tick T055.
- 2026-11-04 (T055): `gptoss` không đạt SC-001 (bộ câu hỏi 6/8 câu chấm được; kịch bản 2–4 vi phạm `bad_pronoun` / `platform_phrase`); cổng Q18 chạm ngưỡng (câu chào khi `sealion` hết giờ: 1/5 lần 7,08 s). Cả hai chờ người dùng quyết định, T055 chưa tick.
