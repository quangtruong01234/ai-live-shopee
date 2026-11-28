# Kế hoạch triển khai: Pipeline trả lời comment chạy local

- **Feature ID:** `001-local-reply-pipeline` · **Ngày:** 2026-10-30 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/001-local-reply-pipeline/spec.md` (trạng thái Clarified, 5 user story, 25 FR, 9 SC)

## Tóm tắt

Người vận hành gõ comment giả lập trên trang điều khiển. Comment đi qua bộ lọc (rỗng, link, tục tĩu, trùng, quá dài) và bộ phân
loại ưu tiên bằng luật từ khóa, rồi vào hàng đợi ưu tiên in-process. `ShowDirector` lấy từng comment, gọi `ReplyEngine` (Gemini
streaming, toàn bộ nội dung sản phẩm nằm trong prompt), tách từng câu, cho qua **guard đầu ra** (khẳng định bị cấm, số tiền không có
trong dữ liệu), rồi đưa sang `FakeTTS` và `StaticRenderer`. Màn hình host là một trang web: ảnh tĩnh, nhãn "AI" cố định, phụ đề theo câu,
phát audio PCM nhận qua WebSocket. Nội dung sản phẩm được nạp từ **file Word theo mẫu** (python-docx), kiểm tra chặt và thay được giữa phiên.
Mỗi lượt nói ghi 4 mốc độ trễ ra file JSONL. Bộ 10 câu hỏi mẫu được chạy và chấm bằng một lệnh riêng, dùng đúng `ReplyEngine` của live.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv). Đổi từ 3.10 theo ADR-020 (đã chốt 2026-10-30) vì `google-genai` bản mới nhất cần Python ≥ 3.11.
- **Phụ thuộc chính:** chưa có gì được cài (repo chưa có `pyproject.toml`). Stack đã chốt ở ADR-003/005/018: FastAPI, asyncio, Gemini API (free tier).
- **Phụ thuộc MỚI, đã duyệt 2026-10-30 qua ADR-014/015/018** (chưa chạy `uv add`; phiên bản lấy bản ổn định mới nhất lúc cài, khóa trong `uv.lock`):

  | Gói | Nhóm | Dùng cho | ADR |
  |-----|------|----------|-----|
  | `fastapi` | runtime | API, WebSocket, phục vụ trang tĩnh | ADR-003 (đã chốt stack) |
  | `uvicorn[standard]` | runtime | server ASGI, có WebSocket và `--reload` | ADR-003 |
  | `google-genai` | runtime | gọi Gemini streaming (SDK chính thức, Apache-2.0) | **ADR-018** |
  | `python-docx` | runtime | đọc file nội dung Word theo mẫu (kéo theo `lxml`) | **ADR-014** |
  | `pydantic-settings` | runtime | đọc cấu hình từ `.env` (giải TODO trong CLAUDE.md) | **ADR-015** |
  | `pytest` | dev | chạy test | ADR-015 |
  | `httpx` | dev | `TestClient` của FastAPI | ADR-015 |
  | `ruff` | dev | lint + format | ADR-015 |

  Không dùng: `pytest-asyncio` (dùng plugin `anyio` có sẵn theo FastAPI), `python-multipart` (upload file bằng body nhị phân),
  `structlog` (dùng `logging` chuẩn + formatter JSON), framework frontend (HTML + JS thuần), `pyyaml` (dùng JSON).
- **Lưu trữ:** không có DB. Nội dung sản phẩm giữ trong bộ nhớ (model pydantic bất biến). Comment, lượt nói, lỗi ghi JSONL theo phiên
  ở `data/sessions/<session_id>/`. Kết quả chấm ở `data/eval/runs/`. Cả hai thư mục được gitignore.
- **Kiểm thử:** pytest + `anyio`. Mặc định không cần mạng, GPU hay API key: `FakeReplyEngine` (kịch bản câu trả lời, độ trễ, lỗi cấu hình
  được), `FakeTTS`, `StaticRenderer` với kênh host giả, đồng hồ giả cho test hết hạn. File Word cho test được dựng bằng code trong fixture.
  Test gọi Gemini thật mang marker `live_llm`, bị loại khỏi lần chạy mặc định (`-m "not live_llm"`).
- **Nơi chạy:** chỉ laptop, `AVATAR_MODE=static`. **Không có bước nào cần GPU/RunPod.**
- **Adapter liên quan:** CommentSource (`MockSource`), CommentQueue (`InMemoryCommentQueue`), ProductStore (`DocxProductStore`),
  ReplyEngine (`GeminiReplyEngine`, `FakeReplyEngine`), TTSEngine (`FakeTTS`), AvatarRenderer (`StaticRenderer`).
  OutputSink: không dùng ở chế độ static (trang host chính là đầu ra).
- **Mục tiêu hiệu năng:** p95 từ `comment_received` đến `avatar_first_frame` ≤ 3,5 s khi host rảnh (SC-001); câu đầu LLM ≤ 1,5 s;
  lệnh bỏ qua / tạm dừng ≤ 1 s (SC-007).
- **Ràng buộc khác:** app chỉ bind `127.0.0.1` (trang điều khiển không có đăng nhập, spec Giả định); không có cấu hình tắt nhãn AI;
  file nội dung thật không vào git.

## Kiểm tra Constitution (cổng)

### Lần 1 (trước Phase 0)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt (lệch có theo dõi) | Câu trả lời và audio sinh tại thời điểm trả lời; không có đường phát file dựng sẵn. Nhãn AI cố định trên trang host, không có biến tắt. **Lệch:** nhãn chưa ghép vào *frame* (chế độ static không có frame video); ghép frame thuộc 005, xem "Theo dõi độ phức tạp". 1 host 1 tài khoản: N/A ở 001 vì chưa có tài khoản nền tảng; sổ đăng ký host ↔ tài khoản làm ở M4 / feature nền tảng (RISKS P4). |
| II. Đồng ý và bảo mật | Đạt | Ảnh avatar là hình minh họa không phải người thật. Secret chỉ từ `.env`, có bộ lọc che secret trong log (FR-021). File nội dung thật nằm ngoài git. |
| III. Trả lời có căn cứ | Đạt | Prompt chỉ chứa dữ liệu từ file; guard đầu ra chặn khẳng định bị cấm và số tiền lạ; bộ câu hỏi mẫu là regression. |
| IV. Adapter trước | Đạt | Mọi khâu sau Protocol; chạy độc lập từng khâu: `python -m ai_live.comments`, `ai_live.products`, `ai_live.brain`, `ai_live.tts`; renderer qua `POST /api/debug/speak` (chỉ `APP_ENV=dev`). Có khác biệt với ARCHITECTURE §2–3, xem ADR-014, ADR-016. |
| V. Test trước | Đạt | Mọi kịch bản chấp nhận có test tự động dùng fake; test Gemini thật tách bằng marker. |
| VI. Ngân sách độ trễ | Đạt | Xem bảng bên dưới; đo bằng 4 mốc + mốc phụ `turn_started`. |
| VII. Đơn giản trước | Đạt | Không DB, không Redis, không framework frontend. 5 dependency runtime mới, mỗi cái có ADR (đã chốt 2026-10-30). |
| VIII. Quan sát được | Đạt | Log JSON có `utterance_id`; timeout ở LLM, TTS, renderer; lỗi một lượt không dừng phiên. |
| IX. Ngôn ngữ và tài liệu | Đạt | Định danh tiếng Anh; docs tiếng Việt; chỗ chưa chắc ghi `TODO:`. |

### Lần 2 (sau Phase 1)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I | Đạt (lệch có theo dõi) | Nhãn trên trang host, chưa trong frame (như lần 1). `contracts/api.md`: không endpoint nào ẩn nhãn; `AI_LABEL_TEXT` rỗng thì app không khởi động. FakeTTS sinh PCM tại thời điểm gọi, không đọc file. |
| II | Đạt | `events.md`: log không chứa key; tên tác giả và nội dung comment được giữ trong file phiên (gitignore). Upload giới hạn 5 MB, chỉ `.docx`. |
| III | Đạt | `research.md` R6–R8: prompt, chống injection, guard theo câu. Bộ câu hỏi mẫu chạy qua đúng `ReplyEngine` + guard của live. |
| IV | Đạt | `contracts/adapters.md`: khác biệt với ARCHITECTURE §3 đã nêu rõ (thêm `text` vào `speak`, `snapshot()` của queue, `MockSource.push`, bỏ `search`/`narrate` khỏi 001), chốt ở ADR-016; ARCHITECTURE §3 được sửa ở pha Foundational. Lệnh chạy độc lập có test ở `tests/unit/test_cli.py`. |
| V | Đạt | `quickstart.md` chỉ dùng cho kiểm chứng tay; mọi FR có test tự động tương ứng (liệt kê ở `/sdd.tasks`). |
| VI | Đạt | Guard + tách câu thêm < 10 ms mỗi câu. Ngân sách local 3,5 s giữ nguyên. |
| VII | Đạt | `EventBus` là lớp cụ thể duy nhất, không Protocol. Không thêm abstraction ngoài các Protocol của Điều IV. |
| VIII | Đạt | Mốc `turn_started` thêm vào để tách thời gian chờ hàng đợi; 4 mốc bắt buộc giữ nguyên tên. |
| IX | Đạt | |

Có 1 chỗ lệch Điều I (nhãn chưa ghép vào frame), đã ghi trong "Theo dõi độ phức tạp" và được người dùng đồng ý.

## Ảnh hưởng ngân sách độ trễ

Định nghĩa đo cho SC-001: `total = avatar_first_frame − comment_received`, chỉ tính lượt mà comment đến khi host đang rảnh
(gửi comment kế tiếp sau khi lượt trước nói xong). Lượt phải chờ host nói xong lượt trước được báo riêng ở cột `queue_wait`. Lý do ở `research.md` R12.

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| Ingest + lọc | 0,2 s | Chuẩn hóa, regex, tra bảng trùng trong bộ nhớ, ước tính < 5 ms | `comment_received` ghi ngay khi API nhận |
| Queue → director | 0,3 s | Heap in-process + `asyncio.Condition`, ước tính < 10 ms khi host rảnh | mốc phụ `turn_started` |
| LLM câu đầu | 1,5 s | Gemini streaming, `thinking_level=low`, tách câu ngay khi gặp dấu kết câu; guard < 10 ms/câu | `llm_first_sentence` (sau guard) |
| TTS chunk đầu | 1,0 s | `FakeTTS` ≈ 0 s (có `FAKE_TTS_DELAY_MS` để giả lập). Đo lại khi xong 003 | `tts_first_chunk` |
| Avatar frame đầu | 0,8 s (lip-sync, chưa áp dụng) | Static: WebSocket localhost + Web Audio bắt đầu phát, ước tính < 0,1 s | `avatar_first_frame` = lúc server nhận ack `playback_started` |
| **Tổng local** | **≤ 3,5 s** | | median / p95 trên ≥ 20 lượt |

Các con số "ước tính" chưa đo; sẽ thay bằng số đo thật sau `/sdd.implement`.

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/001-local-reply-pipeline/
├── spec.md
├── plan.md            # file này
├── research.md        # Phase 0
├── data-model.md      # Phase 1
├── contracts/
│   ├── adapters.md        # Protocol của adapter, đối chiếu ARCHITECTURE §3
│   ├── api.md             # HTTP + WebSocket cho trang điều khiển và màn hình host
│   ├── events.md          # schema log, JSONL phiên, sự kiện EventBus
│   └── content-template.md# mẫu file Word nội dung + định dạng bộ câu hỏi mẫu
├── quickstart.md      # Phase 1
└── tasks.md           # /sdd.tasks
```

### Mã nguồn
```
pyproject.toml                         # uv, ruff, pytest (marker live_llm)
src/ai_live/
├── core/protocols.py                  # Protocol của adapter (theo contracts/adapters.md)
├── core/config.py                     # Settings (pydantic-settings)
├── core/models.py                     # Comment, Priority, DropReason, Utterance, TurnOutcome
├── core/events.py                     # EventBus in-process (pub/sub cho WebSocket)
├── core/text.py                       # chuẩn hóa: bỏ dấu, gộp khoảng trắng, chuẩn hóa số tiền
├── core/logging.py                    # formatter JSON
├── security/redact.py                 # che secret trong log (FR-021)
├── comments/mock_source.py            # MockSource
├── comments/filters.py                # CommentFilter: rỗng, link, tục tĩu, trùng, cắt 300 ký tự
├── comments/classifier.py             # PriorityClassifier theo luật từ khóa
├── comments/__main__.py               # `python -m ai_live.comments` (lọc + phân loại + xếp hàng, in kết quả)
├── comment_queue/memory_queue.py      # InMemoryCommentQueue
├── products/models.py                 # Product, Variant, ProductCatalog
├── products/docx_loader.py            # đọc + kiểm tra file Word theo mẫu
├── products/store.py                  # DocxProductStore (thay nội dung nguyên tử)
├── products/__main__.py               # `python -m ai_live.products validate <file>`
├── brain/prompt.py                    # system prompt + render nội dung sản phẩm
├── brain/sentence_splitter.py         # tách câu, không cắt trong số "1.250.000"
├── brain/guard.py                     # OutputGuard: khẳng định bị cấm, số tiền lạ
├── brain/gemini_engine.py             # GeminiReplyEngine
├── brain/fake_engine.py               # FakeReplyEngine
├── brain/__main__.py                  # `python -m ai_live.brain ask "<comment>"` (engine + guard, in từng câu)
├── tts/fake_tts.py                    # FakeTTS (PCM16 mono)
├── tts/factory.py                     # chọn TTS theo TTS_PROVIDER
├── tts/__main__.py                    # `python -m ai_live.tts say "<câu>" --out x.wav`
├── avatar/static_renderer.py          # StaticRenderer (đẩy audio + phụ đề tới trang host)
├── director/show_director.py          # vòng lượt nói, tạm dừng, bỏ qua, timeout
├── director/latency.py                # LatencyTracker, tổng hợp median/p95
├── director/session_log.py            # ghi JSONL phiên
├── qa_eval/grader.py                  # chấm ý bắt buộc / ý bị cấm
├── qa_eval/__main__.py                # `python -m ai_live.qa_eval run ...`
└── app/
    ├── main.py                        # FastAPI app factory, lifespan, ghép adapter
    ├── routes.py                      # HTTP API
    ├── ws.py                          # WebSocket /ws/control, /ws/host
    └── static/                        # control.html, host.html, *.js, style.css, avatar-placeholder.svg
tests/
├── conftest.py, fixtures/content_builder.py   # dựng file .docx trong test
├── unit/test_{filters,classifier,memory_queue,docx_loader,sentence_splitter,guard,prompt,latency,grader,redact,fake_tts}.py
├── unit/test_{events,config,text,cli}.py   # EventBus, Settings, chuẩn hóa văn bản, lệnh chạy độc lập (Điều IV)
├── integration/test_{show_director,api,ws_host,pipeline_fake}.py
└── live/test_gemini_engine.py         # marker live_llm
data/products/demo.docx                # nội dung mẫu HƯ CẤU (commit)
data/products/template.docx            # mẫu trống cho người soạn (commit)
data/rules/profanity.txt, data/rules/priority_keywords.json
data/eval/demo_questions.json          # 10 câu hỏi mẫu cho file demo (commit)
data/eval/adversarial_questions.json   # câu hỏi gài (giá lạ, khuyến mãi, cam kết y tế) để thử guard (commit)
scripts/make_demo_content.py           # sinh demo.docx và template.docx từ code (để review được bằng diff)
```

Module mới `qa_eval/` chưa có trong `src/README.md`; cập nhật khi implement. Thư mục `output/` không dùng trong 001.

## Phase 0: Nghiên cứu → [`research.md`](./research.md)

14 quyết định: đọc Word (R1), mẫu file (R2), cấu hình (R3), toolchain test/lint (R4), model LLM (R5), prompt và chống injection (R6),
tách câu (R7), guard đầu ra (R8), phân loại ưu tiên (R9), màn hình host và đo frame đầu (R10), FakeTTS (R11), định nghĩa đo SC-001 (R12),
chấm bộ câu hỏi mẫu (R13) và tạm dừng / bỏ qua (R14).

## Phase 1: Thiết kế

- [`data-model.md`](./data-model.md): Comment, QueuedComment, Product, Variant, ProductCatalog, LiveSession, Utterance, EvalQuestion, EvalRun.
- [`contracts/`](./contracts/): Protocol, API, sự kiện, mẫu nội dung.
- [`quickstart.md`](./quickstart.md): kiểm chứng tay US1–US5, toàn bộ trên laptop.

### Biến môi trường mới hoặc đổi (cập nhật `.env.example` khi implement)

| Biến | Mặc định | Ghi chú |
|------|----------|---------|
| `PRODUCT_DATA_PATH` | `data/products/demo.docx` | đổi từ `demo.json` |
| `REPLY_ENGINE` | `gemini` | `gemini` \| `fake` (fake để chạy không cần API key) |
| `GEMINI_API_KEY` | (trống) | thay `ANTHROPIC_API_KEY` (xóa biến cũ khỏi `.env.example`); key free tier tạo ở Google AI Studio |
| `LLM_MODEL` | `gemini-3.8-flash` | ứng viên ban đầu, chốt bằng benchmark (R5) |
| `LLM_THINKING_LEVEL` | `low` | giảm thời gian "suy nghĩ" để ra câu đầu nhanh (R5) |
| `LLM_TIMEOUT_S` | `8` | timeout mỗi lượt gọi LLM (Điều VIII) |
| `TTS_TIMEOUT_S` | `5` | timeout mỗi lần chờ chunk (chunk đầu và giữa hai chunk), không tính cả câu (ADR-049) |
| `RENDERER_ACK_TIMEOUT_S` | `3` | chờ trang host báo bắt đầu phát |
| `COMMENT_QUEUE_MAX` | `50` | |
| `COMMENT_DEDUP_WINDOW_S` | `60` | |
| `COMMENT_MAX_CHARS` | `300` | |
| `PROFANITY_LIST_PATH` | `data/rules/profanity.txt` | |
| `PRIORITY_RULES_PATH` | `data/rules/priority_keywords.json` | |
| `COMMENT_AUTHOR_MAX` | `3` | FR-027, ADR-077: số comment tối đa của 1 người trong cửa sổ |
| `COMMENT_AUTHOR_WINDOW_S` | `30` | FR-027 |
| `COMMENT_AUTHOR_MUTE_S` | `120` | FR-027: thời gian tạm bỏ qua người gửi quá nhanh |
| `COMMENT_GREETING_REPEAT_S` | `600` | FR-026: chào lại cùng người tối đa 1 lần trong khoảng này |
| `GREETING_RULES_PATH` | `data/rules/greetings.json` | FR-026: từ khóa và câu mẫu chào |
| `SESSION_DATA_DIR` | `data/sessions` | |
| `FAKE_TTS_DELAY_MS` | `0` | giả lập độ trễ TTS |
| `CONTENT_MAX_BYTES` | `5242880` | 5 MB |

Thêm vào `.gitignore` khi implement: `data/sessions/`, `data/eval/runs/`.

## ADR cần ghi (đã thêm vào `docs/DECISIONS.md`; ADR-014..017 và ADR-020 đã chốt 2026-10-30, người dùng giao chọn theo đề xuất)

- **ADR-014:** File nội dung sản phẩm là Word theo mẫu cố định, đọc bằng `python-docx`; nội dung giữ trong bộ nhớ, không dùng JSON/SQLite
  làm nguồn. Mô hình `Product` thêm `variants`, `intro`, `link` (sửa ARCHITECTURE §2).
- **ADR-015:** Toolchain: `pyproject.toml` + uv, `pydantic-settings`, pytest + plugin anyio + httpx, ruff, log JSON bằng `logging` chuẩn.
- **ADR-016:** Chế độ static: màn hình host là trang web phát PCM qua WebSocket + Web Audio; `avatar_first_frame` = ack `playback_started`.
  `AvatarRenderer.speak` nhận thêm `text` để hiện phụ đề; `CommentQueue` thêm `snapshot()` (sửa ARCHITECTURE §3).
- **ADR-017:** Guard đầu ra tất định theo từng câu trước TTS (khẳng định bị cấm, số tiền không có trong dữ liệu), bổ sung cho prompt.
- **ADR-018:** LLM đổi từ Claude API sang Gemini API (free tier), SDK `google-genai`. Thay phần nhà cung cấp của ADR-005.
  Trạng thái: nhà cung cấp **đã chốt** (người dùng quyết định 2026-10-30); model cụ thể **đề xuất**, chốt bằng benchmark R5.
- **ADR-019:** Chính sách chi phí: trước khi khách đồng ý dùng sản phẩm, bước nào cần trả tiền thì phải báo người dùng và đưa phương án
  miễn phí trước khi làm. Trạng thái: **đã chốt**.
- **ADR-020:** Nâng Python của app từ 3.10 lên 3.12 vì `google-genai` bản mới cần Python ≥ 3.11 (sửa ADR-012). Phương án dự phòng:
  giữ 3.10 và ghim `google-genai<2.34` (bị loại). Trạng thái: **đã chốt 3.12** (2026-10-30).

## Rủi ro mới (đã thêm vào `docs/RISKS.md`)

- Q6: nội dung không qua khách duyệt, mình soạn sai thì host nói sai như sự thật.
- Q7: file Word không theo đúng style mẫu (heading tự gõ in đậm, file từ Google Docs/WPS) nên không nạp được.
- Q8: guard chặn nhầm câu đúng, hoặc bỏ sót số tiền viết bằng chữ.
- Q9: tự chấm bằng khớp cụm từ lệch với chấm tay.
- Q10: Chrome chặn tự phát âm thanh trên trang host.
- S6: trang điều khiển không có đăng nhập; nếu bind ra ngoài (RunPod ở 005) thì ai cũng điều khiển và thay nội dung được.
- S7: free tier Gemini cho Google dùng dữ liệu gửi lên và có người duyệt đọc; không được gửi dữ liệu mật hay dữ liệu cá nhân.
- Q11: free tier có giới hạn tần suất, không cam kết dịch vụ; tên model có thể đổi hoặc ngừng.

## Theo dõi độ phức tạp

| Vi phạm | Vì sao cần | Phương án đơn giản hơn bị loại vì |
|---------|-----------|-----------------------------------|
| Điều I: nhãn "AI" hiển thị trên trang host (HTML) chứ chưa ghép vào frame video | Chế độ static không có frame video; 001 không phát lên nền tảng live nào (chỉ xem trên trình duyệt local) | Ghép nhãn vào ảnh phía server là việc thừa: 005 sẽ làm overlay trên frame thật của renderer lip-sync. Ràng buộc còn lại: không có cấu hình tắt nhãn, `AI_LABEL_TEXT` rỗng thì app không khởi động. |

Người dùng đồng ý 2026-10-30 (giao chọn theo đề xuất sau `/sdd.analyze`). Hết hiệu lực khi bắt đầu 005: từ đó nhãn phải nằm trong frame.
