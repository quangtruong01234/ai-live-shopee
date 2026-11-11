# Kế hoạch triển khai: Chuỗi model LLM miễn phí, tự chuyển model khi lỗi

- **Feature ID:** `008-llm-provider-chain` · **Ngày:** 2026-11-03 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ (Planned 2026-11-03, 4 user story, 24 FR, 9 SC). Hiến pháp 1.2.0. ADR-034 (freellmapi), ADR-035 (thứ tự
  model và hướng adapter).
- **Sửa 2026-11-03 (làm rõ sau plan):** freellmapi và chuỗi model miễn phí chỉ dùng cho **một ngày demo**; nếu demo đạt thì đổi sang dịch
  vụ khác (ADR mới). Plan ưu tiên **sự chính xác** (đúng model, đúng nền tảng đã benchmark, đúng cấu hình) hơn khả năng chạy dài:
  - bỏ: nghỉ theo `Retry-After`, trạng thái tắt mục, kiểm gateway mỗi 15 s, request/token trong bản tổng hợp;
  - thêm: kiểm key và tên model một lần lúc khởi động (sai thì không khởi động), kiểm nền tảng thật theo `X-Routed-Via` trước chữ đầu.

## Tóm tắt

Thêm `ChainReplyEngine`, một implementation mới của `ReplyEngine` (Protocol không đổi), gọi API Chat Completions kiểu OpenAI bằng `httpx`
stream SSE. Engine đi qua một chuỗi model ghim tên trong `LLM_CHAIN` (mặc định: SEA-LION v4 27B trên Cloudflare và gpt-oss-120b trên Groq
qua freellmapi, Qwen3.8 27B gọi thẳng Groq; ADR-040 sau T055 bỏ gpt-oss-120b và hạ giờ chờ SEA-LION xuống 2,5 s).

- **Lúc khởi động:** kiểm cấu hình (R2), rồi gọi `GET /models` một lần cho mỗi dịch vụ để xác nhận key và tên model (R9). Lỗi bất kỳ thì
  app không khởi động, thông báo nêu mục lỗi, không in key.
- **Mỗi lượt** (một câu trả lời hoặc một phân đoạn) bắt đầu từ mục cao nhất đang sẵn sàng. Mục đi qua freellmapi khai `platform`; nếu
  `X-Routed-Via` báo nền tảng khác thì lần thử bị từ chối trước chữ đầu (R6).
- **Mọi lỗi trước câu đầu** (429, 5xx, kết nối, quá giờ chờ câu đầu, luồng rỗng, bị từ chối, sai nền tảng): chuyển sang mục kế, mục lỗi nghỉ
  cố định `LLM_CHAIN_COOLDOWN_S` (60 s). Riêng bị bộ lọc nội dung chặn thì chuyển mà không nghỉ.
- **Sau câu đầu** thì không chuyển: lỗi giữa chừng dừng lượt ở câu cuối đã nhận, mục nghỉ. Hết chuỗi thì ném `ReplyEngineError`
  (`rate_limited` hoặc `api_error`) đúng loại mà 004 đang đếm, nên chế độ dự phòng hoạt động như cũ.
- Prompt, `SentenceSplitter`, `clean_spoken`, guard và luồng show giữ nguyên.

Phần quan sát:
- log kết quả kiểm lúc khởi động, mỗi lần thử, chuyển, nghỉ kèm model và nhà cung cấp thật (`X-Routed-Via`);
- khu "Model LLM" trên trang điều khiển nhận sự kiện `llm_chain`;
- phần `llm_chain` trong bản tổng hợp show (lượt và lỗi theo mục, không có token);
- giả lập lỗi theo từng mục (chỉ dev);
- `qa_eval run/script --entry LABEL` để benchmark từng model.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, ADR-020).
- **Phụ thuộc chính:** FastAPI, uvicorn, `pydantic-settings`, `google-genai` (giữ cho `REPLY_ENGINE=gemini`), `httpx`.
  - **Phụ thuộc MỚI cần duyệt: không có package mới.**
  - **Đã duyệt 2026-11-03:** `httpx` chuyển từ nhóm `dev` sang `dependencies` runtime trong `pyproject.toml`. Đã có trong `uv.lock` (`>=0.28.1`),
    không đổi version, ADR-035 đã ghi (research R13).
- **Dịch vụ ngoài:** freellmapi chạy local `127.0.0.1:3001` (ADR-034, ngoài repo); Groq API free tier. Cả hai miễn phí; không bật gói trả phí
  (ADR-019). Chỉ dùng cho một ngày demo (memory, spec "Phạm vi dùng").
- **Lưu trữ:** không DB. Trạng thái nghỉ của chuỗi trong bộ nhớ, mất khi app khởi động lại.
- **Kiểm thử:**
  - pytest + `anyio`. `ChainReplyEngine` chạy với `httpx.MockTransport` qua nhà cung cấp giả `tests/fixtures/fake_openai.py`, mô phỏng
    luồng câu bình thường, mọi dòng của bảng lỗi R3, `X-Routed-Via` (khớp, khác, thiếu, `cache`), `/models` (đủ dạng của R9), `usage`,
    keepalive. Không cần mạng hay key (FR-023).
  - `ChainState` test bằng đồng hồ giả.
  - Test nhà cung cấp thật: `tests/live/test_chain_engine.py`, marker `live_llm`, không chạy mặc định.
- **Nơi chạy:** laptop dev, `AVATAR_MODE=static`, `TTS_PROVIDER=fake`. **Không bước nào cần GPU hay RunPod.**
- **Adapter liên quan:**
  - `ReplyEngine`: thêm `ChainReplyEngine`; `GeminiReplyEngine`, `FakeReplyEngine` giữ nguyên. Chọn bằng `REPLY_ENGINE` qua
    `brain/factory.py`.
  - Không đụng `CommentSource`, `CommentQueue`, `ProductStore`, `TTSEngine`, `AvatarRenderer`, `OutputSink`.
- **Mục tiêu hiệu năng:**
  - Điều VI giữ nguyên: câu đầu của show ≤ 5 s; khoảng lặng p95 ≤ 1,5 s; comment → miệng bắt đầu nói < 5 s p95.
  - Riêng feature: chuyển do lỗi ngay thêm ≤ 1 s (SC-003); lượt hết chuỗi khi mọi mục nghỉ báo lỗi ≤ 1 s (SC-006); cảnh báo trên trang
    điều khiển ≤ 2 s (SC-007). Lần kiểm lúc khởi động chạy trước khi nhận request nên không cộng vào câu chào (SC-009).
- **Ràng buộc khác:**
  - Key chỉ ở `.env`. Cấu hình chuỗi chỉ chứa tên biến key.
  - Mọi thông báo lỗi (cả lúc khởi động) che mẫu key và chính giá trị key (R12).
  - Chỉ gửi dữ liệu sản phẩm mẫu và comment mock tới nhà cung cấp chưa kiểm điều khoản (ràng buộc 5, ADR-034).

## Kiểm tra Constitution (cổng)

### Lần 1 (trước Phase 0)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt (kế thừa lệch có theo dõi của 001) | Lời thoại vẫn sinh từng lượt trong phiên, không lưu sẵn câu để phát lại; lượt trúng cache của freellmapi bị từ chối (FR-024). Không đụng nhãn AI (lệch "nhãn chưa nằm trong frame ở static" giải ở 005). 1 host 1 tài khoản: N/A. |
| II. Đồng ý và bảo mật | Đạt | Không có nhân vật hay giọng mới. Key chỉ từ `.env`; cấu hình chỉ chứa tên biến. Log, trang điều khiển và thông báo lỗi khởi động không hiện key (FR-004, FR-011, SC-008). Dữ liệu gửi đi: sản phẩm mẫu và comment mock (ADR-034). |
| III. Trả lời có căn cứ | Đạt | Cùng prompt và guard cho mọi model. Mỗi model phải qua bộ câu hỏi (≥ 8/10) và bộ tự kiểm tra kịch bản (0 vi phạm) trước khi lên live (US4, SC-001). Kiểm nền tảng bảo đảm câu được nói đến từ đúng nền tảng đã chấm (FR-024). |
| IV. Adapter trước | Đạt | Một implementation mới của `ReplyEngine`, chọn bằng biến môi trường. Lõi pipeline, `ShowDirector`, guard không đổi cách làm việc. |
| V. Test trước | Đạt | Chuyển, nghỉ, sai nền tảng, kiểm lúc khởi động, hết chuỗi test được bằng nhà cung cấp giả, không mạng (FR-023). Test thật tách bằng `live_llm`. |
| VI. Ngân sách độ trễ | Đạt, có rủi ro | Giới hạn chờ câu đầu là một phần ngân sách (bảng bên dưới). Trường hợp mục 1 hết giờ chờ ngay câu chào có thể vượt 5 s (Q18); đo ở T055: 1/5 lần vượt (7,08 s). |
| VII. Đơn giản trước | Đạt | Không thêm package, không thêm hạ tầng trong repo. Không dự đoán hạn mức, chỉ phản ứng khi bị từ chối; một khoảng nghỉ cố định, hai trạng thái, không tác vụ nền. |
| VIII. Quan sát được | Đạt | Log model / nhà cung cấp mỗi lượt và mỗi lần chuyển; giới hạn chờ theo mục; một mục lỗi không làm đứng show. |
| IX. Ngôn ngữ và tài liệu | Đạt | Định danh và comment tiếng Anh; thông báo lỗi, nhãn trang điều khiển tiếng Việt. |

### Lần 2 (sau Phase 1)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I | Đạt (kế thừa lệch của 001) | Không có cache câu trả lời: mục có `platform` gửi `X-FreeLLM-Cache: off` và từ chối `X-Routed-Via: cache` / `idempotency` (R2, R6). Engine chỉ sinh khi `ScriptRunner` hay `ShowDirector` gọi (contracts/adapters.md §2). |
| II | Đạt | R12: mẫu `gsk_…`, `freellmapi-…`, `sk-…` trong `security/redact.py` và che theo giá trị key, áp dụng cả cho thông báo của lần kiểm lúc khởi động. Không log header `Authorization` hay body request (contracts/events.md §1). Quickstart US1 (bảng a–f) và US3 bước 4 kiểm SC-008 bằng tìm chuỗi key. |
| III | Đạt | Engine chỉ trả câu; `clean_spoken` và guard chạy ở `ShowDirector`/`ScriptRunner` như cũ, nên không model nào đi tắt guard (US1 #4). `qa_eval --entry` (R10) ghim từng model để chấm, vẫn kiểm nền tảng. Kiểm `X-Routed-Via` trước chữ đầu (R6) nên không câu nào của nền tảng chưa chấm tới người xem. |
| IV | Đạt | contracts/adapters.md: Protocol không đổi. Khác ARCHITECTURE §3: thêm `REPLY_ENGINE` vào danh sách biến chọn adapter và `ChainReplyEngine` vào docstring; sửa ở pha Foundational. `preflight()` là method của lớp cụ thể, lifespan gọi khi `REPLY_ENGINE=chain`. `brain/` nhận hook giả lập lỗi dạng hàm, không import `director/`. |
| V | Đạt | Mỗi kịch bản chấp nhận có test không mạng (liệt kê ở `/sdd.tasks`), trừ phần đo thời gian thật và lỗi cấu hình thật (quickstart). |
| VI | Đạt, có rủi ro | Xem bảng độ trễ. Mục đang nghỉ cộng 0 s; lỗi ngay hoặc sai nền tảng cộng ≈ 0,3 s; hết giờ chờ mục 1 cộng 3,5 s (Q18; đo ở T055: câu chào 4,25–4,61 s, 1/5 lần 7,08 s; sau ADR-040 mục 1 chờ 2,5 s, câu chào 2,91–3,31 s, 0/10 lần > 5 s). Tổng giới hạn chờ ≤ 8 s được kiểm lúc khởi động (FR-009). Lần kiểm `GET /models` (≤ 5 s mỗi dịch vụ) chạy trước khi nhận request. |
| VII | Đạt | `ChainState` là lớp thuần với hai trạng thái; không có lớp bọc nhiều engine; không có tác vụ nền. |
| VIII | Đạt | Các mốc `llm_first_sentence`, `segment_requested` giữ nguyên (FR-006). Log mới `llm_preflight`, `llm_attempt` (có `routed_via`), `llm_switch`, `llm_entry_rest`, `llm_chain_exhausted`, `llm_turn` (contracts/events.md). |
| IX | Đạt | Chỗ chưa chắc ghi `TODO:` (danh sách cuối file). |

Không có vi phạm mới. Rủi ro Điều VI (Q18) được biện minh ở "Theo dõi độ phức tạp" và có cổng quyết định ở T055.

## Ảnh hưởng ngân sách độ trễ

Cột "Đo ở T055" là số đo thật ngày 2026-11-04 (quickstart, "Kết quả kiểm chứng"), `FakeTTS` + static; cột "Ước tính" là số lúc plan
lấy từ benchmark ADR-035 (p95 câu đầu), giữ để so.

**(a) Câu đầu của show (SC-001 của 004, SC-003 của 008, ≤ 5 s).** TTS và phát tính theo 004: `FakeTTS` ≈ 0 s; giọng 003 ≈ 1,0 s; static
< 0,1 s. Lần kiểm lúc khởi động xong trước khi trang điều khiển bấm được "Bắt đầu show", nên không nằm trong bảng.

| Khâu | Ngân sách (ARCHITECTURE §4) | Ước tính (lúc plan) | Đo ở T055 | Cách đo |
|------|-----------------------------|---------------------|-----------|---------|
| Chọn mục | — | đọc `ChainState`, < 1 ms; mục nghỉ cộng 0 s | lượt hết chuỗi khi mọi mục nghỉ ≈ 0 ms | `llm_attempt outcome=skipped` |
| LLM câu đầu, mục 1 trả lời | 1,5 s | SEA-LION p95 2,81 s: **vượt dòng 1,5 s** | SEA-LION p50 0,86 s, p95 1,30 s, lớn nhất 2,11 s (64 phân đoạn): trong dòng 1,5 s | `llm_first_sentence − segment_requested` |
| LLM câu đầu, mục 1 lỗi ngay hoặc sai nền tảng | 1,5 s | ≈ 0,3 s lỗi + gpt-oss p95 1,04 s ≈ 1,4 s | lỗi giả lập 0,0 s + gpt-oss p95 1,72 s (49 lượt); lỗi thật chưa đo | như trên + `llm_switch` |
| LLM câu đầu, mục 1 hết giờ chờ | 1,5 s | 3,5 s + ≈ 1,4 s ≈ 4,9 s | 3,5 s + gpt-oss 0,73–1,11 s; 1/5 lần gpt-oss cũng hết giờ (2,016 s) rồi Qwen 1,55 s | như trên |
| **Tổng, mục 1 trả lời** | **≤ 5 s** | ≈ 2,9 s (fake TTS, static) / ≈ 3,9 s (giọng 003) | 0,98 s và 0,66 s (show US1, US2); 10/10 câu chào ≤ 1,64 s. Giọng 003 chưa đo | `show_first_sentence_s` |
| **Tổng, mục 1 lỗi ngay** | **≤ 5 s** | ≈ 1,5 s / ≈ 2,5 s | 10/10 câu chào ≤ 5 s: 0,69–1,86 s, 1 lần 3,05 s (gpt-oss hết giờ thật → Qwen) | quickstart US2 bước 2 |
| **Tổng, mục 1 hết giờ chờ** | **≤ 5 s** | ≈ 5,0 s / ≈ 6,0 s: **có thể vượt** (Q18) | 4,25 / 4,39 / 4,44 / 4,61 / **7,08** s: **1/5 vượt** (Q18); giọng 003 cộng ≈ 1 s. Sau ADR-040 (`sealion` 2,5 s → Qwen): 10/10 câu chào 2,91–3,31 s, 0 vượt | quickstart US2 bước 5 |

**(b) Khoảng lặng giữa hai câu (p95 ≤ 1,5 s).** Không đổi về cơ chế: `ScriptRunner` sinh trước một phân đoạn, phân đoạn dài 15–40 s. Cả
phân đoạn của SEA-LION p95 5,62 s; trường hợp xấu nhất (hết giờ mục 1 + hết giờ mục 2 + mục 3 cả phân đoạn) ≈ 3,5 + 2,0 + ≈ 3 s ≈ 8,5 s, vẫn
ngắn hơn một phân đoạn đang phát. Khoảng lặng chỉ tăng khi cả chuỗi lỗi (đã có ở 004: nhãn gap `error` / `fault`). Đo ở T055 (show 12,7
phút có giả lập lỗi): `script` p95 0,016 s; `segment_boundary` p95 0,728 s, lớn nhất 3,578 s. Một phân đoạn chạy cả ba mục (hết giờ
SEA-LION 3,5 s + hết giờ thật gpt-oss 2,016 s + Qwen 0,578 s ≈ 6,1 s) không gây khoảng lặng > 5 s vì đã sinh trước.

**(c) Comment → miệng bắt đầu nói (< 5 s p95).**
- `total ≈ max(phần còn lại của câu kịch bản, LLM câu đầu + TTS) + round trip`.
- SEA-LION reply p95 2,40 s, cao hơn Gemini dự kiến (1,5 s). Câu kịch bản dài 4–7 s vẫn là phần lớn nhất (rủi ro đã ghi ở plan 004 (c)).
- Đường comment đang tạm dừng (ADR-026), nên chỉ đo ở quickstart nếu bật lại.
- Đo ở T055 (3 comment mock, show US1, chỉ SEA-LION): câu đầu LLM 1,23 / 1,36 s; comment → khung hình đầu 1,23 / 2,30 / 1,36 s.

**Giới hạn chờ câu đầu theo mục (FR-009):** 3,5 + 2,0 + 2,0 = 7,5 s ≤ min(`LLM_TIMEOUT_S` 8, `SCRIPT_LLM_TIMEOUT_S` 10). Ở chế độ dự phòng
(`SCRIPT_RETRY_TIMEOUT_S` 4 s), mục 2 chỉ còn 0,5 s nếu mục 1 hết giờ; chấp nhận (research R4).

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/008-llm-provider-chain/
├── spec.md
├── plan.md            # file này
├── research.md        # Phase 0 (R1–R13)
├── data-model.md      # Phase 1
├── contracts/
│   ├── adapters.md    # ChainReplyEngine (preflight), OpenAICompatClient, ChainState, FaultInjector; đối chiếu ARCHITECTURE §3
│   ├── config.md      # LLM_CHAIN (platform), REPLY_ENGINE=chain, key, lỗi cấu hình và lỗi kiểm lúc khởi động
│   ├── api.md         # /api/state, /health, /api/debug/fault, WebSocket, trang điều khiển
│   └── events.md      # log, sự kiện llm_chain, bản tổng hợp, báo cáo bộ kiểm
├── quickstart.md      # Phase 1
└── tasks.md           # /sdd.tasks
```

### Mã nguồn (đường dẫn thật)
```
src/ai_live/
├── core/config.py              # SỬA: ChainEntryConfig (có platform); reply_engine thêm "chain" (mặc định); llm_chain,
│                               #       llm_chain_cooldown_s, freellmapi_key, groq_api_key
├── core/events.py              # SỬA: EventType.LLM_CHAIN
├── brain/openai_compat.py      # MỚI: OpenAICompatClient (httpx stream SSE, kiểm X-Routed-Via, list_models), ProviderFailure,
│                               #       StreamMeta, phân loại lỗi R3
├── brain/chain_state.py        # MỚI: ChainState, EntryState, AttemptReason (thuần)
├── brain/chain_engine.py       # MỚI: ChainReplyEngine, preflight, Attempt, TurnRecord, Usage, PreflightResult; observer; aclose
├── brain/factory.py            # SỬA: REPLY_ENGINE=chain
├── brain/__main__.py           # SỬA: CLI thử nhanh gọi preflight() khi chain (thêm sau phân tích 2026-11-04)
├── director/faults.py          # SỬA: lỗi theo mục (ENTRY_FAULT_MODES, take_entry)
├── director/show_director.py   # SỬA: turn observer → log llm_turn có utterance_id; llm_model nhãn "chain"
├── director/show_stats.py      # SỬA: phần llm_chain của bản tổng hợp
├── security/redact.py          # SỬA: mẫu gsk_, freellmapi-, sk-
├── app/main.py                 # SỬA: lifespan gọi preflight; hook giả lập lỗi (chỉ dev), observer → EventBus, aclose lúc tắt
├── app/context.py              # SỬA: build_state thêm llm_chain
├── app/routes.py               # SỬA: FaultIn.entry, /health có reply_engine, llm_ready
├── app/static/control.{html,js}# SỬA: khu "Model LLM", giả lập lỗi theo mục
├── qa_eval/__main__.py         # SỬA: --entry; preflight trước khi chạy; nhãn engine chain / chain:<label>
├── qa_eval/runner.py           # SỬA: ghi model_label, model, provider mỗi câu hỏi; so sánh in engine
└── qa_eval/script_eval.py      # SỬA: như runner cho phân đoạn
.env.example                    # SỬA: REPLY_ENGINE=chain, LLM_CHAIN, LLM_CHAIN_COOLDOWN_S, FREELLMAPI_KEY, GROQ_API_KEY
pyproject.toml                  # SỬA: httpx sang dependencies (đã duyệt 2026-11-03); mô tả marker live_llm
tests/
├── fixtures/fake_openai.py                       # MỚI: nhà cung cấp OpenAI-compatible giả (MockTransport), cả /models
├── unit/test_chain_state.py, test_openai_compat.py, test_chain_engine.py   # MỚI
├── unit/test_config.py, test_redact.py, test_events.py, test_cli.py         # SỬA
├── unit/test_show_stats.py, test_qa_eval_script_cli.py                     # SỬA
├── contract/test_reply_engine_contract.py, contract/conftest.py            # SỬA: thêm ChainReplyEngine
├── integration/test_show_director.py, test_show_api.py                     # SỬA: chuyển mục trong show, /api/debug/fault có entry,
│                                                                           #       app không khởi động khi preflight lỗi
└── live/test_chain_engine.py                     # MỚI, marker live_llm
```

Cập nhật `src/README.md` (dòng `brain/`), `docs/ARCHITECTURE.md` §1 và §3 ở pha Foundational.

### Biến môi trường mới (cập nhật `.env.example`; `tests/unit/test_config.py` kiểm khớp mặc định)

| Biến | Mặc định | Ghi chú |
|------|----------|---------|
| `REPLY_ENGINE` | `chain` (đổi từ `gemini`) | `chain \| gemini \| fake` |
| `LLM_CHAIN` | 3 mục ADR-035, hai mục đầu có `platform` (contracts/config.md §2) | JSON một dòng |
| `LLM_CHAIN_COOLDOWN_S` | `60` | thời gian nghỉ cố định cho mọi lỗi |
| `FREELLMAPI_KEY` | trống | secret |
| `GROQ_API_KEY` | trống | secret |

## Phase 0: Nghiên cứu → [`research.md`](./research.md)

13 quyết định:
- R1 cấu trúc engine, R2 cấu hình chuỗi (có `platform`), R3 phân loại lỗi, R4 giới hạn chờ câu đầu, R5 trạng thái nghỉ;
- R6 định danh model, kiểm nền tảng và log, R7 hết chuỗi, R8 giả lập lỗi theo mục, R9 kiểm lúc khởi động, trang điều khiển và bản tổng hợp;
- R10 bộ kiểm từng model, R11 test thật, R12 che key, R13 dependency.

## Phase 1: Thiết kế

- [`data-model.md`](./data-model.md): ChainEntryConfig, EntryState (hai trạng thái), AttemptReason, Attempt, TurnRecord, ChainSnapshot,
  phần `llm_chain` của bản tổng hợp, kết quả bộ kiểm, PreflightResult.
- [`contracts/`](./contracts/): adapter và module, cấu hình, HTTP/WebSocket, log và sự kiện.
- [`quickstart.md`](./quickstart.md): kiểm US1–US4 trên laptop, không GPU; bước gọi `GET /models` thật đánh dấu **[mạng]**, bước gọi chat
  thật đánh dấu **[mạng + hạn mức]**.

## ADR cần ghi

- **ADR-037 (Đã chốt 2026-11-03):** Cấu hình chuỗi model:
  - `REPLY_ENGINE=chain` thành mặc định;
  - `LLM_CHAIN` là JSON một dòng; `key_env` trỏ tới trường secret của `Settings` (`FREELLMAPI_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`);
  - mục loopback bắt buộc khai `platform`; cấm model `auto`, `auto:*`, `fusion`; gửi `X-FreeLLM-Cache: off`;
  - giới hạn chờ câu đầu theo mục, tổng ≤ min(`LLM_TIMEOUT_S`, `SCRIPT_LLM_TIMEOUT_S`);
  - kiểm `GET /models` một lần lúc khởi động, lỗi thì không khởi động;
  - `LLM_CHAIN_COOLDOWN_S=60`; chuỗi mặc định 3 mục; Gemini chỉ thêm sau khi qua benchmark.
- **ADR-038 (Đã chốt 2026-11-03):** Phân loại lỗi nhà cung cấp và nghỉ mục (R3, R5, R6):
  - chuyển chỉ trước câu đầu;
  - mọi lỗi (trừ `blocked`) nghỉ cố định `LLM_CHAIN_COOLDOWN_S`, không đọc `Retry-After`, không có trạng thái tắt;
  - `X-Routed-Via` không khớp `platform` → `wrong_platform`, từ chối trước chữ đầu;
  - hủy không phạt mục;
  - hết chuỗi dùng `kind` có sẵn (`rate_limited` / `api_error`).
- **ADR-039 (Đã chốt 2026-11-03):** Bề mặt quan sát của chuỗi:
  - sự kiện `llm_chain` và khóa `llm_chain` trong `/api/state`;
  - log `llm_preflight`, `llm_attempt` (có `routed_via`), `llm_switch`, `llm_entry_rest`, `llm_chain_exhausted`, `llm_turn`;
  - `FaultIn.entry` với các mode lỗi theo mục (`rate_limited`, `overloaded`, `timeout`, `empty`, `wrong_platform`, `interrupted`);
  - phần `llm_chain` trong bản tổng hợp show (không có request/token);
  - observer chỉ trên `ChainReplyEngine` (Protocol không đổi);
  - mẫu che key Groq / freellmapi / OpenAI.
- **Dependency (theo ADR-035):** `httpx` sang `dependencies` runtime, người dùng duyệt 2026-11-03 (task T001).

## Rủi ro mới

- **Q16:** freellmapi gom nhóm theo tên model hoặc tự chuyển nội bộ, cho lượt tới một nền tảng chưa benchmark (ví dụ `gpt-oss-120b` qua
  Cloudflare thay vì Groq). Giảm thiểu: kiểm nền tảng chặt theo `X-Routed-Via` trước chữ đầu (FR-024), gửi `X-FreeLLM-Cache: off`, log
  nền tảng thật; tắt nền tảng chưa benchmark trên dashboard freellmapi.
- **Q17:** (bỏ ở làm rõ 2026-11-03) Không còn nghỉ theo `Retry-After`; chuỗi chỉ dùng một ngày demo, mục hết hạn mức ngày chỉ nghỉ 60 s rồi
  thử lại.
- **Q18:** Mục 1 hết giờ chờ ngay câu chào mở màn thì câu đầu ≈ 5–6 s, vượt 5 s. Giảm thiểu: đo ở quickstart; nếu > 1/10 lần thì hỏi người
  dùng có hạ giới hạn chờ của mục 1 không (research R4).
- **Q19:** Giọng văn đổi giữa hai phân đoạn khi chuyển model (đã chấp nhận ở làm rõ 2026-11-03). Giảm thiểu: cùng prompt và luật xưng hô;
  đếm số lần chuyển mỗi show trong bản tổng hợp.
- **S8:** Body lỗi của nhà cung cấp có thể chứa lại key; lọt vào log, `errors.jsonl`, trang điều khiển hoặc thông báo lỗi khởi động. Giảm
  thiểu: mẫu che mới và che theo giá trị key (R12); kiểm SC-008 bằng tìm chuỗi.

## TODO còn mở

- Tên model chính xác trên freellmapi và Groq (`GET /v1/models`) (R2); lần kiểm lúc khởi động báo sai ngay. Đã trả lời ở T055: `llm_preflight ok=true` cho cả ba tên.
- python-dotenv đọc JSON không nháy trong `.env` (R2).
- Endpoint OpenAI-compatible của Gemini nếu sau này gọi thẳng (R2).
- Hạ giới hạn chờ của SEA-LION nếu câu chào > 5 s quá 1/10 lần (R4); cổng quyết định ở T055. Đã trả lời: ADR-040 hạ xuống 2,5 s.
- Groq và freellmapi có trả `usage` khi stream không (R6).
- Thời gian bắt tay TLS tới Groq từ laptop (contracts/adapters.md §3).
- Tên model và giới hạn chờ của mục 4 Gemini (contracts/config.md §2).

## Theo dõi độ phức tạp

| Vi phạm | Vì sao cần | Phương án đơn giản hơn bị loại vì |
|---------|-----------|-----------------------------------|
| Điều VI (rủi ro, Q18): mục 1 hết giờ chờ ngay câu chào mở màn thì câu đầu ≈ 4,9–5,9 s, có thể vượt 5 s | Giới hạn chờ 3,5 s của SEA-LION đặt quanh p95 × 1,25 (p95 câu đầu 2,81 s, ADR-035) để không cắt nhầm lượt chậm bình thường của model tiếng Việt tốt nhất (R4). Chỉ xảy ra khi mục 1 treo đúng lúc mở màn; lỗi ngay hay sai nền tảng chỉ cộng ≈ 0,3 s | Hạ xuống 2,5 s: cắt nhầm khoảng 5–10% lượt bình thường của SEA-LION. Chưa có số đo thật nên giữ 3,5 s, đo ở T055; nếu câu chào > 5 s quá 1/10 lần thì hỏi người dùng có hạ giới hạn (chỉ đổi cấu hình `LLM_CHAIN`). T055: 1/5 lần 7,08 s; người dùng chọn hạ, ADR-040 đặt 2,5 s (p95 đo được 1,30 s, lớn nhất 2,11 s) |

Ngoài rủi ro trên, không có vi phạm mới. Chỗ lệch Điều I (nhãn AI chưa ghép vào frame ở chế độ static) kế thừa từ 001 và được giải ở 005. Phiên bản này bớt
độ phức tạp so với plan đầu: bỏ trạng thái tắt, nghỉ theo `Retry-After` và tác vụ nền kiểm gateway.
