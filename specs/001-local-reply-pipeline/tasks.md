# Tasks: Pipeline trả lời comment chạy local

- **Feature ID:** `001-local-reply-pipeline` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
- **Sửa sau `/sdd.analyze` (2026-10-30):** thêm test nền tảng cho `events`, `config`, `text`; thêm CLI từng khâu và `POST /api/debug/speak`
  (Điều IV); thêm task sửa ARCHITECTURE §3, kiểm file Word nhiều ứng dụng, hồi quy Điều III; đánh số lại toàn bộ.

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[GPU]**: cần RunPod; không làm trên laptop, gom vào đợt GPU (xem cuối file). Feature 001 **không có** task GPU.
- **[US#]**: thuộc user story nào (US1, US2...). Phase Setup, Foundational và Hoàn thiện không gắn nhãn này.
- Mỗi task ghi **đường dẫn file cụ thể**. Một task chỉ đủ nhỏ để xong và kiểm chứng trong một lần làm.
- Thứ tự phase theo ưu tiên trong spec: US1 (P1) → US2, US3, US5 (P2) → US4 (P3).

## Phase 1: Setup

- [x] T001 Chốt ADR-014, ADR-015, ADR-016, ADR-017 và ADR-020 (Python 3.12), ghi chú ADR-012 trong `docs/DECISIONS.md`; chốt cách hiểu
  "tạm dừng" ở research R14 trong `specs/001-local-reply-pipeline/research.md` (xong 2026-10-30, người dùng giao chọn theo đề xuất)
- [x] T002 Đổi `.python-version` từ `3.10` thành `3.12` theo ADR-020
- [x] T003 Tạo `pyproject.toml`: tên `ai-live`, layout `src/ai_live`, `requires-python = ">=3.12"`; `[tool.ruff]` cho lint và format theo ADR-015;
  `[tool.pytest.ini_options]` có `testpaths = ["tests"]`, khai báo marker `live_llm` và `addopts = '-m "not live_llm"'` (research R4)
- [x] T004 Tạo khung package: `__init__.py` trong `src/ai_live/` và các gói con `core`, `security`, `comments`, `comment_queue`, `products`,
  `brain`, `tts`, `avatar`, `director`, `app`, cùng gói mới `src/ai_live/qa_eval/`; tạo thư mục `tests/unit/`, `tests/integration/`,
  `tests/live/`, `tests/fixtures/`
- [x] T005 Cài dependency đã duyệt trong plan: `uv add fastapi "uvicorn[standard]" google-genai python-docx pydantic-settings` và
  `uv add --dev pytest httpx ruff`, sinh `uv.lock`. Kiểm tra bản `python-docx` được cài có `iter_inner_content()` rồi ghi ràng buộc phiên bản
  vào `pyproject.toml` (giải TODO đầu tiên của research R1). Phụ thuộc T002, T003, T004
- [x] T006 [P] Thêm `data/sessions/` và `data/eval/runs/` vào `.gitignore`
- [x] T007 [P] Cập nhật `.env.example`: đổi `PRODUCT_DATA_PATH=data/products/demo.docx`; thêm `REPLY_ENGINE`, `TTS_TIMEOUT_S`,
  `RENDERER_ACK_TIMEOUT_S`, `COMMENT_QUEUE_MAX`, `COMMENT_DEDUP_WINDOW_S`, `COMMENT_MAX_CHARS`, `PROFANITY_LIST_PATH`, `PRIORITY_RULES_PATH`,
  `SESSION_DATA_DIR`, `FAKE_TTS_DELAY_MS`, `CONTENT_MAX_BYTES` với giá trị mặc định theo bảng biến môi trường trong `plan.md`; kiểm
  `LLM_TIMEOUT_S=8`, `LLM_THINKING_LEVEL`, `LLM_MAX_TOKENS` (đã có) khớp bảng đó

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

### Test nền tảng (viết trước, phải FAIL trước khi implement)

- [x] T008 [P] Viết `tests/fixtures/content_builder.py` (dựng file `.docx` trong bộ nhớ bằng python-docx: file hợp lệ có sản phẩm chính và phụ,
  sản phẩm có biến thể, và từng biến thể lỗi của `contracts/content-template.md`) và `tests/conftest.py` (Settings test với `REPLY_ENGINE=fake`,
  `TTS_PROVIDER=fake`, `AVATAR_MODE=static`, `APP_ENV=dev`, `SESSION_DATA_DIR` trỏ vào `tmp_path`, không có `GEMINI_API_KEY`;
  `anyio_backend = "asyncio"`; đồng hồ giả cho test hết hạn)
- [x] T009 [P] Test che secret trong `tests/unit/test_redact.py`: giá trị của khóa `*_KEY`, `*_TOKEN`, `*_SECRET` và chuỗi dạng `AIza...`
  bị thay bằng dấu che, chuỗi thường giữ nguyên (FR-021)
- [x] T010 Test đọc file Word trong `tests/unit/test_docx_loader.py` (phụ thuộc T008): file hợp lệ ra `ProductCatalog` có `version` = 12 ký tự
  đầu sha256, `known_amounts` đủ, sản phẩm có biến thể và khoảng giá (FR-025); mỗi mã lỗi trong `contracts/content-template.md` có một case;
  file có nhiều lỗi báo đủ mọi lỗi; nội dung mâu thuẫn bị từ chối (FR-007, trường hợp biên)
- [x] T011 [P] Test hàng đợi cơ bản trong `tests/unit/test_memory_queue.py`: lấy ra theo `(priority, seq)`; `snapshot()` đúng thứ tự sẽ lấy;
  `get()` chờ tới khi có comment
- [x] T012 [P] Test `EventBus` trong `tests/unit/test_events.py`: mọi subscriber nhận sự kiện theo thứ tự publish; hàng đợi của một subscriber
  đầy 1000 thì bỏ sự kiện cũ nhất của subscriber đó, subscriber khác không mất gì; `publish` không chờ subscriber chậm (contracts/adapters.md)
- [x] T013 [P] Test Settings trong `tests/unit/test_config.py`: giá trị mặc định khớp `.env.example` (nguồn chuẩn; bảng trong `plan.md` chỉ liệt kê biến mới hoặc đổi) với các biến feature 001 dùng; giá trị sai kiểu báo
  lỗi khi khởi tạo; `AI_LABEL_TEXT` rỗng báo lỗi (FR-015); `repr()` và `str()` không chứa giá trị `GEMINI_API_KEY` (FR-021; research R3)
- [x] T014 [P] Test hàm văn bản trong `tests/unit/test_text.py`: NFC, gộp khoảng trắng, cắt độ dài; dạng so khớp chữ thường, bỏ dấu, `đ`→`d`;
  trích số tiền `1.250.000đ`, `250k`, `1 nghìn` về số nguyên; chuỗi không có số tiền trả danh sách rỗng (research R8, R9)

### Implement nền tảng

- [x] T015 [P] Model dùng chung trong `src/ai_live/core/models.py`: `Comment`, `Priority` (HIGH=0, MEDIUM=1, LOW=2), `DropReason`,
  `QueuedComment`, `Utterance` (marks, outcome, error_step, guard_reason), `TurnOutcome`, `ErrorStep`, `Milestone`, `GuardResult`,
  `LatencySummary` theo `data-model.md` §1, §3, §4
- [x] T016 [P] Model sản phẩm trong `src/ai_live/products/models.py`: `Variant`, `Product` (có `price` hoặc `variants`, không cả hai),
  `ProductCatalog` (`version`, `known_amounts`), `ContentIssue` theo `data-model.md` §2
- [x] T017 [P] Hàm chuẩn hóa văn bản trong `src/ai_live/core/text.py`: NFC, gộp khoảng trắng, cắt độ dài, dạng so khớp (chữ thường, bỏ dấu,
  `đ`→`d`), trích và chuẩn hóa số tiền về số nguyên theo research R8, R9 (cho T014)
- [x] T018 [P] Che secret trong `src/ai_live/security/redact.py` cho T009
- [x] T019 Settings trong `src/ai_live/core/config.py` bằng pydantic-settings: đủ các biến trong `.env.example` mà feature 001 dùng, `AI_LABEL_TEXT` rỗng thì báo lỗi
  khi khởi tạo, `repr` không in secret (cho T013; phụ thuộc T018; research R3)
- [x] T020 Formatter log JSON trong `src/ai_live/core/logging.py`, mọi bản ghi đi qua `redact` trước khi ghi (phụ thuộc T018; FR-021)
- [x] T021 [P] `EventBus` trong `src/ai_live/core/events.py`: `publish`, `subscribe`; mỗi subscriber có hàng đợi 1000 sự kiện, đầy thì bỏ sự kiện
  cũ nhất của subscriber đó; các loại sự kiện theo `contracts/events.md` §3 (cho T012)
- [x] T022 Sáu Protocol `CommentSource`, `CommentQueue`, `ProductStore`, `ReplyEngine`, `TTSEngine`, `AvatarRenderer` và ngoại lệ
  `RendererUnavailable` trong `src/ai_live/core/protocols.py`, đúng chữ ký ở `contracts/adapters.md` (phụ thuộc T015, T016)
- [x] T023 [P] Sửa `docs/ARCHITECTURE.md` §3 theo bảng "Khác biệt so với `docs/ARCHITECTURE.md` §3" ở `contracts/adapters.md`
  (`speak` có `text`, `Priority`, `QueuedComment`, `snapshot`, `MockSource.push`, `replace`/`catalog`, `ReplyEngine.reply` nhận `catalog`;
  ghi chú `search`, `narrate`, `OutputSink` chưa làm ở 001)
- [x] T024 Đọc và kiểm tra file Word trong `src/ai_live/products/docx_loader.py`: Heading 1 là sản phẩm, dòng `Loại:`, các mục Heading 2,
  kiểm chữ ký zip và `CONTENT_MAX_BYTES`, gom mọi lỗi rồi ném `ContentLoadError(issues)` (phụ thuộc T016, T017; research R1, R2)
- [x] T025 `DocxProductStore` trong `src/ai_live/products/store.py`: nạp lúc khởi động; `replace()` kiểm xong mới đổi catalog, lỗi thì giữ catalog
  cũ; thành công phát `content_replaced` (phụ thuộc T021, T024)
- [x] T026 Lệnh `python -m ai_live.products validate <file>` trong `src/ai_live/products/__main__.py`: in danh sách lỗi tiếng Việt, có lỗi thì
  mã thoát khác 0 (phụ thuộc T024)
- [x] T027 `InMemoryCommentQueue` cơ bản trong `src/ai_live/comment_queue/memory_queue.py`: heap `(priority, seq)`, `put`, `get`, `size`,
  `snapshot` cho T011. Giới hạn kích thước và loại comment quá cũ làm ở US2 (phụ thuộc T015)
- [x] T028 [P] Script `scripts/make_demo_content.py` sinh `data/products/template.docx` (mẫu trống có style) và `data/products/demo.docx`
  (dữ liệu **hư cấu**: 1 sản phẩm chính, 2–3 sản phẩm phụ, ít nhất 1 sản phẩm có biến thể; không có mục bảo hành; khẳng định bị cấm có
  "chữa khỏi mụn")
- [x] T029 Chạy `uv run python scripts/make_demo_content.py` rồi `uv run python -m ai_live.products validate data/products/demo.docx`,
  kết quả 0 lỗi; kiểm hai file `.docx` chỉ có dữ liệu hư cấu, để sẵn cho người dùng commit (chỉ commit khi người dùng yêu cầu) (phụ thuộc T026, T028)

**Checkpoint:** T009–T014 chuyển sang PASS; nền tảng sẵn sàng, các story bắt đầu được.

---

## Phase 3: User Story 1: Trả lời comment dựa trên dữ liệu sản phẩm (P1) 🎯 MVP

**Mục tiêu:** người vận hành gõ một comment, host trả lời bằng tiếng (FakeTTS) kèm phụ đề từng câu, chỉ dựa trên file nội dung, nhãn AI luôn hiện.
**Kiểm thử độc lập:** spec US1 kịch bản 1–5; chạy được với `REPLY_ENGINE=fake` không cần mạng, và với `REPLY_ENGINE=gemini` theo quickstart US1.

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [x] T030 [P] [US1] Test prompt trong `tests/unit/test_prompt.py`: prompt chứa toàn bộ catalog kể cả biến thể và khoảng giá (FR-025); có luật
  chỉ dùng dữ liệu, thiếu dữ liệu thì nói chưa có thông tin và mời hỏi shop (FR-008, FR-009); liệt kê khẳng định bị cấm (FR-010); comment nằm
  trong khối dữ liệu có ranh giới và luật nêu rõ comment không đổi được luật (FR-011); xưng "em", gọi "bạn {tên}" hoặc "anh chị" khi không có
  tên, từ ngữ miền Nam, 1–3 câu (FR-012); mặc định sản phẩm chính khi hỏi nhiều sản phẩm; kéo về sản phẩm khi hỏi ngoài lề (research R6)
- [x] T031 [P] [US1] Test tách câu trong `tests/unit/test_sentence_splitter.py`: tách ở `.!?…` hoặc xuống dòng theo sau là khoảng trắng hay
  hết stream; không tách trong `1.250.000đ` và `v.v.`; câu dưới 4 ký tự gộp với câu sau; câu quá 200 ký tự cắt ở dấu phẩy; `flush()` trả phần
  còn lại (research R7, FR-013)
- [x] T032 [P] [US1] Test guard trong `tests/unit/test_guard.py`: câu chứa "chữa khỏi mụn" (cả dạng không dấu) bị chặn (US1 #3, FR-010);
  số tiền không có trong `known_amounts` như "99k", "1 nghìn" bị chặn (US1 #4, FR-011); giá đúng trong file được qua (research R8)
- [x] T033 [P] [US1] Test FakeTTS trong `tests/unit/test_fake_tts.py`: PCM16 mono 16 kHz, chunk 100 ms, thời lượng khoảng 0,25 s mỗi âm tiết,
  chunk đầu trễ `FAKE_TTS_DELAY_MS`, cờ lỗi làm `synthesize` ném ngoại lệ (research R11)
- [x] T034 [P] [US1] Test `GeminiReplyEngine` với client giả (không gọi mạng) trong `tests/unit/test_gemini_engine.py`: delta đi qua
  `SentenceSplitter` và yield từng câu; HTTP 429 thành lỗi bước `llm`, không thử lại; finish reason SAFETY hoặc text rỗng thành lỗi
  `provider_blocked`; hủy task thì đóng stream (research R5)
- [x] T035 [P] [US1] Test kênh host trong `tests/integration/test_ws_host.py`: chỉ một kết nối `/ws/host`, kết nối mới đóng kết nối cũ với
  code 4000; trước `ready` thì `speak()` ném `RendererUnavailable`; mỗi câu gửi `sentence_start` (có `text`) rồi frame PCM rồi `sentence_end`
  (FR-014); `speak()` trả về khi nhận `sentence_played` (contracts/api.md §4)
- [x] T036 [P] [US1] Test pipeline giả trong `tests/integration/test_pipeline_fake.py` (FakeReplyEngine → tách câu → guard → FakeTTS →
  StaticRenderer với host giả): US1 #1 câu trả lời có giá đúng file và "bạn Lan", phụ đề gửi theo từng câu cùng audio của câu đó; US1 #3, #4
  câu vi phạm bị chặn, host nói câu từ chối cố định, lượt `completed` có `guard_reason`; engine ném lỗi thì lượt `error` với
  `error_step=llm` và comment sau vẫn được trả lời (FR-020); không có comment thì không có lượt nào
- [x] T037 [P] [US1] Test API trong `tests/integration/test_api.py`: `POST /api/comments` trả 202 `waiting`; `GET /host` có phần tử nhãn chứa
  `AI_LABEL_TEXT` và không có tham số ẩn nhãn (US1 #5, FR-015, SC-006); app không khởi động khi `AI_LABEL_TEXT` rỗng hoặc
  `PRODUCT_DATA_PATH` là file lỗi (trường hợp biên); `/health`, `/api/state` và `/ws/control` (gửi `state` khi kết nối) không chứa giá trị
  `GEMINI_API_KEY` (FR-021); `POST /api/debug/speak` trả 200 kèm `utterance_id` khi `APP_ENV=dev` và host giả đã `ready`, 409 khi đang có
  lượt nói, 404 khi `APP_ENV` khác `dev` (contracts/api.md §2)
- [x] T038 [P] [US1] Test Gemini thật có marker `live_llm` trong `tests/live/test_gemini_engine.py`, dùng `data/products/demo.docx`:
  US1 #1 giá đúng và cách xưng hô (FR-012); US1 #2 hỏi bảo hành thì nói chưa có thông tin, không có con số; US1 #4 comment ép giá không làm
  xuất hiện số tiền lạ (FR-011)
  *(2026-11-20: 4 test `live_llm` của `tests/live/test_gemini_engine.py` đạt với `LLM_MODEL=gemini-3.5-flash-lite` đặt qua biến môi trường; `gemini-3.8-flash` trong `.env` bị Google báo quá tải (HTTP 503, treo hơn 30 s) cùng ngày)*
- [x] T039 [P] [US1] Test CLI từng khâu trong `tests/unit/test_cli.py` (Điều IV): `python -m ai_live.brain ask` với `REPLY_ENGINE=fake` in từng
  câu kèm thời gian từ lúc gửi, mã thoát 0, câu bị guard chặn thì in lý do; `python -m ai_live.tts say ... --out <tmp>.wav` ghi file đọc được
  bằng module `wave` (mono, PCM16, 16 kHz)

### Implement US1

- [x] T040 [P] [US1] System prompt và render catalog trong `src/ai_live/brain/prompt.py` cho T030
- [x] T041 [P] [US1] `SentenceSplitter` (`feed`, `flush`) trong `src/ai_live/brain/sentence_splitter.py` cho T031
- [x] T042 [P] [US1] `OutputGuard.check()` và câu từ chối cố định trong `src/ai_live/brain/guard.py`, dùng hàm số tiền của `core/text.py`
  cho T032
- [x] T043 [P] [US1] `FakeTTS` trong `src/ai_live/tts/fake_tts.py` cho T033
- [x] T044 [P] [US1] `MockSource` trong `src/ai_live/comments/mock_source.py`: `push(author, text)` đồng bộ, tạo `Comment` (gán `comment_id`,
  thời điểm `comment_received`) và trả về comment đó; `stream()` rỗng, kết thúc ngay (contracts/adapters.md; FR-001)
- [x] T045 [US1] `FakeReplyEngine` trong `src/ai_live/brain/fake_engine.py`: câu trả lời theo kịch bản, độ trễ và lỗi cấu hình được, đi qua
  `SentenceSplitter` (phụ thuộc T041)
- [x] T046 [US1] `GeminiReplyEngine` trong `src/ai_live/brain/gemini_engine.py`: `google-genai` async streaming, model `LLM_MODEL`,
  `LLM_THINKING_LEVEL`, `LLM_MAX_TOKENS`, prompt của T040, lỗi theo T034. Tra tài liệu SDK để giải TODO tên trường thinking level ở research R5
  và ghi kết quả vào `research.md` (phụ thuộc T040, T041)
- [x] T047 [US1] Chọn TTS theo `TTS_PROVIDER` trong `src/ai_live/tts/factory.py`: chỉ có `fake`, giá trị khác báo lỗi cấu hình rõ ràng
  (phụ thuộc T043)
- [x] T048 [US1] Lệnh `python -m ai_live.tts say <text> --out <file.wav>` trong `src/ai_live/tts/__main__.py`: TTS qua factory, ghi WAV PCM16
  mono theo `sample_rate` của engine, in thời gian tới chunk đầu (cho T039; phụ thuộc T047)
- [x] T049 [US1] Lệnh `python -m ai_live.brain ask <comment> [--author <tên>] [--content <docx>]` trong `src/ai_live/brain/__main__.py`:
  nạp catalog từ `PRODUCT_DATA_PATH` hoặc `--content`, ReplyEngine theo `REPLY_ENGINE`, mỗi câu qua `OutputGuard`; in từng câu kèm thời gian
  từ lúc gửi, câu bị chặn in lý do (cho T039; phụ thuộc T024, T042, T045, T046)
- [x] T050 [US1] `StaticRenderer` trong `src/ai_live/avatar/static_renderer.py`: giữ kết nối `/ws/host`, `start`, `stop`, `speak`
  (gửi `sentence_start`, PCM, `sentence_end`, chờ `sentence_played`), `is_speaking`, ném `RendererUnavailable` khi chưa có `ready` (cho T035)
- [x] T051 [US1] `ShowDirector` bản cơ bản trong `src/ai_live/director/show_director.py`: lấy comment từ hàng đợi, mỗi lần một lượt; lượt gồm
  task sinh (engine → guard → TTS) và task phát nối bằng hàng đợi câu tối đa 2 (research R14); guard chặn thì dừng sinh, nói câu từ chối,
  lượt `completed` kèm `guard_reason`; lỗi thì lượt `error` kèm `error_step` rồi lấy comment kế tiếp; dùng catalog chụp lúc bắt đầu lượt;
  phát `turn_started`, `sentence`, `guard_blocked`, `turn_finished` (phụ thuộc T042, T045, T047, T050)
- [x] T052 [P] [US1] Trang host trong `src/ai_live/app/static/host.html`, `src/ai_live/app/static/host.js`, `src/ai_live/app/static/style.css`
  và `src/ai_live/app/static/avatar-placeholder.svg`: ảnh avatar (`AVATAR_STATIC_IMAGE` hoặc placeholder tự vẽ), nhãn AI cố định theo
  `AI_LABEL_TEXT` và `AI_LABEL_POSITION`, nút "Bắt đầu" mở `AudioContext`, phát PCM16 bằng Web Audio, hiện phụ đề khi câu bắt đầu phát, gửi
  `ready`, `playback_started`, `sentence_played` (research R10)
- [x] T053 [P] [US1] Trang điều khiển trong `src/ai_live/app/static/control.html` và `src/ai_live/app/static/control.js`: ô tên và nội dung
  comment, lượt đang nói kèm phụ đề, câu bị guard chặn, lỗi gần đây, cảnh báo "chưa mở màn hình host" (FR-016 phần lượt hiện tại và lỗi)
- [x] T054 [US1] WebSocket `/ws/control` (gửi `state` khi kết nối, chuyển tiếp sự kiện EventBus) và `/ws/host` (một kết nối, đóng cũ bằng
  code 4000, nhận ack) trong `src/ai_live/app/ws.py` (phụ thuộc T050)
- [x] T055 [US1] HTTP trong `src/ai_live/app/routes.py`: `GET /`, `GET /host` (chèn `AI_LABEL_TEXT`, `AI_LABEL_POSITION`), `POST /api/comments`
  (qua `MockSource.push`, tạm xếp mức MEDIUM cho tới US2), `GET /api/state`, `GET /health` (phụ thuộc T044)
- [x] T056 [US1] App factory và lifespan trong `src/ai_live/app/main.py`: nạp Settings (dừng nếu `AI_LABEL_TEXT` rỗng), nạp `PRODUCT_DATA_PATH`
  (file lỗi thì in danh sách lỗi và không khởi động), chọn ReplyEngine theo `REPLY_ENGINE`, TTS qua factory, renderer theo `AVATAR_MODE`,
  bật log JSON, chạy `ShowDirector` (phụ thuộc T046, T051, T054, T055)
- [x] T057 [US1] Thêm `POST /api/debug/speak` (chỉ đăng ký khi `APP_ENV=dev`) vào `src/ai_live/app/routes.py`: chạy TTS + renderer với `text`
  1–300 ký tự, bỏ qua LLM và hàng đợi, 409 khi đang có lượt nói, trả `utterance_id` sau khi phát xong (contracts/api.md §2; phụ thuộc T056)

**Checkpoint:** T030–T037 và T039 PASS; quickstart US1 bước 1–4 và mục "Chạy riêng từng khâu" (trừ `comments`) chạy được với
`REPLY_ENGINE=fake` và `REPLY_ENGINE=gemini`. Dừng lại, báo người dùng, demo.

---

## Phase 4: User Story 2: Lọc comment và hàng đợi ưu tiên (P2)

**Mục tiêu:** comment rác bị loại kèm lý do, comment còn lại được trả lời theo mức ưu tiên, comment quá cũ bị bỏ.
**Kiểm thử độc lập:** spec US2 kịch bản 1–5; quickstart US2.

### Test cho US2 (viết trước, phải FAIL trước khi implement)

- [x] T058 [P] [US2] Test bộ lọc trong `tests/unit/test_filters.py`: chuẩn hóa NFC, cắt 300 ký tự (comment dài), gộp khoảng trắng; rỗng hoặc
  chỉ có emoji → `empty`; có link → `link`; từ tục cả dạng không dấu và `đ`→`d` → `profanity`; cùng người, cùng nội dung trong 60 s →
  `duplicate`, khác người hoặc sau 60 s thì không; thứ tự lọc rỗng → link → tục → trùng (FR-002, research R9); tên người xem rỗng, có link
  hoặc có từ tục thì thay bằng `"bạn"`, comment vẫn được giữ (trường hợp biên, data-model.md)
- [x] T059 [P] [US2] Test phân loại trong `tests/unit/test_classifier.py`: hỏi giá → HIGH, hỏi chất liệu → MEDIUM, chào hỏi → LOW; viết không dấu
  vẫn đúng mức; chỉ có dấu hỏi hoặc từ hỏi → MEDIUM (FR-003)
- [x] T060 [P] [US2] Thêm test vào `tests/unit/test_memory_queue.py`: cùng mức thì FIFO (US2 #2); đầy `COMMENT_QUEUE_MAX` thì loại comment
  mức thấp nhất đến sớm nhất, hoặc chính comment mới nếu nó thấp hơn hết, báo `queue_full`; comment quá `COMMENT_MAX_AGE_S` bị loại `stale`
  khi `get()` và trong vòng quét mỗi 1 s (dùng đồng hồ giả) (FR-004, FR-005, FR-006)
- [x] T061 [P] [US2] Thêm test vào `tests/integration/test_pipeline_fake.py`: đưa một loạt comment trộn vào hàng đợi trước khi director chạy,
  FakeReplyEngine nhận đúng thứ tự giá → chất liệu → chào hỏi; comment bị loại không bao giờ tới engine (US2 #1, #4, SC-003)
- [x] T062 [P] [US2] Thêm test vào `tests/integration/test_api.py`: `POST /api/comments` với link, từ tục, trùng, rỗng trả 202 `dropped` kèm
  `drop_reason`; comment hợp lệ trả `priority` đúng mức (US2 #3, #4)
- [x] T063 [P] [US2] Thêm test vào `tests/unit/test_cli.py`: `python -m ai_live.comments "Lan: giá bao nhiêu?" "Huy: hello shop" "x: http://a.b"`
  in `priority` hoặc `drop_reason` của từng comment và thứ tự hàng đợi (giá trước chào hỏi, comment có link bị loại), mã thoát 0 (Điều IV)

### Implement US2

- [x] T064 [P] [US2] Tạo `data/rules/profanity.txt` và `data/rules/priority_keywords.json` (từ khóa viết dạng không dấu, mức HIGH xét trước)
  theo research R9
- [x] T065 [P] [US2] `CommentFilter` trong `src/ai_live/comments/filters.py` cho T058, đọc `PROFANITY_LIST_PATH`, `COMMENT_MAX_CHARS`,
  `COMMENT_DEDUP_WINDOW_S`; tên người xem rỗng, có link hoặc có từ tục thay bằng `"bạn"`
- [x] T066 [P] [US2] `PriorityClassifier` trong `src/ai_live/comments/classifier.py` cho T059, đọc `PRIORITY_RULES_PATH`
- [x] T067 [P] [US2] Thêm vào `src/ai_live/comment_queue/memory_queue.py`: giới hạn `COMMENT_QUEUE_MAX` và loại `queue_full`, loại `stale` khi
  `get()`, vòng quét 1 s, phát `comment_dropped` và `queue_changed` (cho T060)
- [x] T068 [US2] Nối luồng nhận comment trong `src/ai_live/app/routes.py` và `src/ai_live/app/main.py`: `MockSource.push` → `CommentFilter` →
  `PriorityClassifier` → `queue.put`; trả `status`, `drop_reason`, `priority`; phát `comment_accepted` hoặc `comment_dropped`; bỏ mức MEDIUM tạm
  của T055 (phụ thuộc T065, T066, T067)
- [x] T069 [US2] Lệnh `python -m ai_live.comments "<tên>: <nội dung>" ...` trong `src/ai_live/comments/__main__.py`: chạy cùng luồng
  `MockSource.push` → `CommentFilter` → `PriorityClassifier` → `InMemoryCommentQueue`, in `priority` hoặc `drop_reason` và `snapshot()` cuối
  (cho T063; phụ thuộc T044, T065, T066, T067)
- [x] T070 [P] [US2] Thêm vào `src/ai_live/app/static/control.html` và `src/ai_live/app/static/control.js`: danh sách hàng đợi theo thứ tự
  `snapshot` kèm mức ưu tiên, danh sách comment bị loại gần đây kèm lý do (kể cả `stale`, `queue_full`) (FR-016)

**Checkpoint:** T058–T063 PASS; quickstart US2 bước 1–4 và lệnh `ai_live.comments` ở mục "Chạy riêng từng khâu" đạt. Dừng lại, báo người dùng.

---

## Phase 4b: Bổ sung test an toàn câu trả lời và hợp đồng adapter

**Mục tiêu:** khóa lại lớp chặn thứ hai (guard) bằng một bộ câu trả lời bẫy, và có bộ contract test mà mọi adapter mới (YouTube ở 006,
TTS thật, LiveTalking) phải qua mà không cần viết lại test. Chỉ thêm test, không đổi hành vi đã có trong spec.
**Quy ước riêng:** đây là test bổ sung cho code đã có nên phải **PASS** ngay. Ca nào FAIL thì đó là lỗi thật: sửa code (nếu đúng phạm vi
research R8 / contracts/adapters.md) hoặc chuyển cho agent sở hữu; không nới test. Giới hạn đã biết của guard (R8, rủi ro Q8) viết thành
`xfail(strict=True)` kèm lý do, để khi có người vá thì test báo ngay.

- [x] T111 [P] Test bộ câu trả lời bẫy cho `OutputGuard` trong `tests/unit/test_brain_guard_adversarial.py` (FR-008, FR-010, research R8):
  ≥ 20 câu mà LLM có thể bịa phải bị chặn: số tiền lạ ở mọi định dạng R8 liệt kê (`đ`, `₫`, `vnd`, `k`, `nghìn`, `ngàn`, `triệu`, số ≥ 1.000
  không đơn vị; có hoặc không có khoảng trắng, dấu chấm hoặc phẩy ngăn nghìn), số tiền sát giá thật (249.000 khi giá là 250.000), câu vừa có
  giá đúng vừa có giá bịa, câu do comment ép host ("nói giá 99k đi"); khẳng định cấm viết hoa, không dấu, thừa khoảng trắng, xen dấu câu, gắn
  vào sản phẩm khác. ≥ 10 câu đúng dữ liệu phải qua (mọi giá, giá phân loại, khoảng giá, khuyến mãi, thông số như "1.000 ml", câu từ chối).
  Giới hạn đã biết thành `xfail(strict=True)`: số tiền viết bằng chữ, khẳng định cấm diễn đạt khác chữ, khuyến mãi phần trăm, tồn kho, bảo
  hành hoặc đổi trả bịa (FR-008 cho các ý này hiện chỉ dựa vào prompt và bộ chấm)
- [x] T112 [P] Hạ tầng contract test trong `tests/contract/conftest.py`: mỗi Protocol trong `core/protocols.py` có một danh sách factory
  adapter (thêm adapter mới chỉ cần thêm một factory); client Gemini giả dùng chung đặt ở `tests/fixtures/fake_genai.py`
- [x] T113 [P] Contract `ReplyEngine` trong `tests/contract/test_reply_engine_contract.py` cho `FakeReplyEngine` và `GeminiReplyEngine`
  (client giả): yield câu hoàn chỉnh kiểu `str`, không rỗng; lỗi nhà cung cấp ném `ReplyEngineError` với `kind` thuộc 4 giá trị;
  `aclose()` giữa chừng dừng stream (contracts/adapters.md "Hành vi bắt buộc")
- [x] T114 [P] Contract `TTSEngine` và `AvatarRenderer` trong `tests/contract/test_tts_contract.py` và
  `tests/contract/test_renderer_contract.py` cho `FakeTTS` và `StaticRenderer` (`FakeHostConnection`): `sample_rate` > 0, chunk PCM16 độ dài
  chẵn, tổng audio > 0, lỗi thì ném ngoại lệ; `speak` trả về sau `sentence_played`, không có host thì ném `RendererUnavailable`,
  `first_playback_at` là `None` trước và số sau ack đầu, `interrupt()` idempotent và trả về ngay, `is_speaking` đúng trong lúc nói
- [x] T115 [P] Contract `CommentQueue` và `CommentSource` trong `tests/contract/test_comment_queue_contract.py` và
  `tests/contract/test_comment_source_contract.py` cho `InMemoryCommentQueue` và `MockSource`: thứ tự `get` = thứ tự `snapshot` =
  (priority, seq); đầy thì loại đúng comment (`queue_full`), quá tuổi thì `stale`, loại mà không ném lỗi; `name` là chuỗi, `start`/`stop`
  gọi hai lần không lỗi, `stream()` là async iterator
- [x] T116 [P] Contract `ProductStore` trong `tests/contract/test_product_store_contract.py` cho `DocxProductStore`: `replace` lỗi thì ném
  `ContentLoadError` và catalog không đổi; `get` id lạ trả `None`; `list_active` là tập con của `catalog.products`

**Checkpoint:** T111–T116 PASS (ca `xfail` được phép), toàn bộ `pytest` và `ruff` sạch. Dừng lại, báo người dùng.

---

## Phase 5: User Story 3: Đo độ trễ từng lượt (P2)

**Mục tiêu:** mỗi lượt có `utterance_id` và 4 mốc thời gian; người vận hành xem độ trễ từng lượt và tổng hợp phiên; số liệu được lưu sau phiên.
**Kiểm thử độc lập:** spec US3 kịch bản 1–3; quickstart US3.

### Test cho US3 (viết trước, phải FAIL trước khi implement)

- [x] T071 [P] [US3] Test tổng hợp độ trễ trong `tests/unit/test_latency.py`: `total = avatar_first_frame − comment_received`,
  `queue_wait = turn_started − comment_received`; số lượt, trung vị, p95 bằng `statistics.quantiles(n=20)[18]` cho tổng và từng bước;
  dưới 20 mẫu thì báo "chưa đủ mẫu"; lượt `error` và `skipped` không tính (US3 #3); tập "chỉ lượt host rảnh" khi `queue_wait < 0,3 s`
  (research R12, FR-019)
- [x] T072 [P] [US3] Thêm test vào `tests/integration/test_pipeline_fake.py`: mọi lượt `completed` có đủ 4 mốc theo đúng thứ tự (US3 #1,
  SC-004); mọi dòng log JSON của lượt có `utterance_id` (FR-018); lượt lỗi có `error_step`; sau phiên có `comments.jsonl`, `utterances.jsonl`,
  `errors.jsonl` trong `SESSION_DATA_DIR`, lỗi bị chặn của nhà cung cấp ghi `type="provider_blocked"`, không file nào chứa secret (FR-019, FR-021);
  tắt app (lifespan shutdown) thì có `latency_summary.json` chứa `LatencySummary` cho cả hai chế độ `idle_only` (contracts/events.md §2)
- [x] T073 [P] [US3] Thêm test vào `tests/integration/test_api.py`: `GET /api/latency` và `GET /api/latency?idle_only=true` trả
  `LatencySummary` đúng `data-model.md` §4 (US3 #2)

### Implement US3

- [x] T074 [P] [US3] `LatencyTracker` trong `src/ai_live/director/latency.py`: ghi mốc theo `utterance_id`, tính tổng hợp cho T071
- [x] T075 [P] [US3] Ghi JSONL phiên trong `src/ai_live/director/session_log.py`: ba file theo `contracts/events.md` §2 ở
  `data/sessions/<session_id>/`, ghi qua executor, mọi dòng đi qua `redact`
- [x] T076 [US3] Thêm callback mốc `avatar_first_frame` (khi nhận `playback_started` của câu đầu) vào
  `src/ai_live/avatar/static_renderer.py` (research R10)
- [x] T077 [US3] Nối đo độ trễ vào `src/ai_live/director/show_director.py`: ghi 4 mốc `comment_received`, `llm_first_sentence`,
  `tts_first_chunk`, `avatar_first_frame`; log JSON các mốc kèm `utterance_id`; ghi session log; phát `latency` sau mỗi `turn_finished`
  (phụ thuộc T074, T075, T076)
- [x] T078 [US3] Thêm `GET /api/latency?idle_only` vào `src/ai_live/app/routes.py`; tạo `session_id` và thư mục phiên khi khởi động; khi tắt
  ghi `latency_summary.json` (cả hai chế độ `idle_only`) rồi đóng file trong `src/ai_live/app/main.py` (phụ thuộc T074, T075)
- [x] T079 [P] [US3] Thêm bảng độ trễ (tổng và từng bước, dòng "chỉ lượt host rảnh", thông báo "chưa đủ mẫu") vào
  `src/ai_live/app/static/control.html` và `src/ai_live/app/static/control.js`

**Checkpoint:** T071–T073 PASS; quickstart US3 chạy được (đo SC-001 thật làm ở T102). Dừng lại, báo người dùng.

---

## Phase 6: User Story 5: Nạp nội dung và chấm bộ câu hỏi mẫu (P2)

**Mục tiêu:** thay file nội dung giữa phiên an toàn; chấm tự động bộ 10 câu hỏi mẫu, lưu kết quả và so với lần trước.
**Kiểm thử độc lập:** spec US5 kịch bản 1–3; quickstart US5.

### Test cho US5 (viết trước, phải FAIL trước khi implement)

- [x] T080 [P] [US5] Test chấm trong `tests/unit/test_grader.py`: ý bắt buộc khớp một trong các cách diễn đạt (không phân biệt dấu); thiếu ý bắt
  buộc hoặc có ý cấm thì sai và nêu tên ý (US5 #2); số tiền không có trong dữ liệu tự động là ý cấm; chạy runner với `FakeReplyEngine` sinh
  `<ts>.json` và `<ts>.md` (có cột "Chấm tay", tổng điểm) trong thư mục tạm (US5 #1); chạy lần hai có phần so sánh điểm và câu đổi kết quả
  (US5 #3); `--repeat 3` báo đạt khi cả 3 lần ≥ 8/10 (FR-023, FR-024, research R13)
- [x] T081 [P] [US5] Thêm test vào `tests/integration/test_api.py`: `PUT /api/content` hợp lệ trả 200 với `version` mới; file thiếu mục
  "Khẳng định bị cấm" và có giá `250k` trả 400 `content_invalid` kèm đủ 2 lỗi và catalog không đổi; quá `CONTENT_MAX_BYTES` trả 413; không phải
  docx trả 415; `X-Filename` không được dùng làm đường dẫn ghi file (FR-022, contracts/api.md §2)
- [x] T082 [P] [US5] Test thay nội dung giữa lượt trong `tests/integration/test_show_director.py`: lượt đang chạy dùng catalog cũ, lượt sau dùng
  catalog mới (FR-022, trường hợp biên)
- [x] T083 [P] [US5] Thêm test có marker `live_llm` vào `tests/live/test_gemini_engine.py`: chạy runner chấm một lần với `GeminiReplyEngine`
  trên `data/eval/demo_questions.json` và kiểm tra tạo được báo cáo (research R13)
  *(2026-11-20: 4 test `live_llm` của `tests/live/test_gemini_engine.py` đạt với `LLM_MODEL=gemini-3.5-flash-lite` đặt qua biến môi trường; `gemini-3.8-flash` trong `.env` bị Google báo quá tải (HTTP 503, treo hơn 30 s) cùng ngày)*

### Implement US5

- [x] T084 [P] [US5] Bộ chấm trong `src/ai_live/qa_eval/grader.py` cho T080, dùng lại hàm số tiền của `core/text.py`
- [x] T085 [US5] Lệnh `python -m ai_live.qa_eval run --content <docx> --questions <json> [--repeat N]` trong `src/ai_live/qa_eval/__main__.py`:
  ReplyEngine theo `REPLY_ENGINE` + `OutputGuard`, không qua TTS và renderer; giãn nhịp gọi và lùi lại khi gặp 429; ghi
  `data/eval/runs/<ts>.json` và `.md`; so với lần chạy gần nhất cùng file câu hỏi (phụ thuộc T084)
- [x] T086 [P] [US5] Bộ 10 câu hỏi cho file demo trong `data/eval/demo_questions.json` theo `contracts/content-template.md` §2: ít nhất 2 câu
  hỏi điều không có trong dữ liệu và 1 câu ép host
- [x] T087 [US5] Thêm `PUT /api/content` (raw body, `X-Filename` chỉ ghi `source_name`, lỗi 400/413/415) gọi `DocxProductStore.replace` vào
  `src/ai_live/app/routes.py`; đọc và kiểm file docx chạy qua `asyncio.to_thread` để không chặn event loop
- [x] T088 [P] [US5] Thêm ô nạp file nội dung vào `src/ai_live/app/static/control.html` và `src/ai_live/app/static/control.js`: hiện version
  mới hoặc danh sách lỗi

**Checkpoint:** T080–T082 PASS; quickstart US5 bước 1–4 đạt. Dừng lại, báo người dùng.

---

## Phase 7: User Story 4: Tạm dừng, tiếp tục, bỏ qua và chịu lỗi (P3)

**Mục tiêu:** người vận hành điều khiển phiên trong ≤ 1 giây; lỗi hoặc hết giờ ở một bước chỉ bỏ lượt đó, phiên chạy tiếp.
**Kiểm thử độc lập:** spec US4 kịch bản 1–3; quickstart US4.

### Test cho US4 (viết trước, phải FAIL trước khi implement)

- [x] T089 [P] [US4] Thêm test vào `tests/integration/test_show_director.py`: bỏ qua khi đang nói gọi `renderer.interrupt()`, lượt `skipped`,
  director lấy comment kế tiếp (US4 #1); tạm dừng thì lượt đang nói được nói hết và không bắt đầu lượt mới, comment vẫn vào hàng đợi và comment
  quá cũ vẫn bị loại (US4 #2); tiếp tục thì trả lời comment hợp lệ ưu tiên cao nhất (US4 #3); mỗi lệnh ghi log `control_applied` có
  `latency_ms` (skip có `utterance_id`) (SC-007); hết `LLM_TIMEOUT_S` (chờ câu đầu và cả stream), `TTS_TIMEOUT_S`, `RENDERER_ACK_TIMEOUT_S` và
  host chưa kết nối đều cho lượt `error` đúng bước; ba lỗi giả lập liên tiếp rồi comment thường vẫn được trả lời (FR-017, FR-020, SC-005)
- [x] T090 [P] [US4] Thêm test vào `tests/integration/test_api.py`: `POST /api/pause` và `/api/resume` idempotent; `POST /api/skip` trả
  `skipped_utterance_id` hoặc `null`; mỗi lệnh ghi log `control_command` lúc nhận rồi `control_applied` với `latency_ms` ≥ 0
  (contracts/events.md §1); `POST /api/debug/fault` trả 200 khi `APP_ENV=dev` và 404 khi khác (contracts/api.md §2)
- [x] T091 [P] [US4] Thêm test vào `tests/integration/test_ws_host.py`: `interrupt()` gửi `stop` tới host trong ≤ 1 s, idempotent, và làm
  `speak()` đang chờ trả về ngay (SC-007)

### Implement US4

- [x] T092 [US4] Thêm vào `src/ai_live/avatar/static_renderer.py`: `interrupt()` gửi `stop`, trả về ngay, idempotent; `speak()` trả về khi bị
  interrupt; hết `RENDERER_ACK_TIMEOUT_S` + thời lượng audio mà không có ack thì ném `TimeoutError` (research R10)
- [x] T093 [P] [US4] Xử lý `stop` trong `src/ai_live/app/static/host.js`: dừng `AudioBufferSourceNode` đang phát, xóa buffer và phụ đề
- [x] T094 [US4] Thêm tạm dừng, tiếp tục, bỏ qua vào `src/ai_live/director/show_director.py` theo research R14: bỏ qua hủy task sinh và task
  phát rồi gọi `renderer.interrupt()`; phát `session_state`; ghi log `control_applied` kèm `latency_ms` tính từ `t_mono` của
  `control_command` (lúc gửi `stop` với skip, lúc phát `session_state` với pause/resume) (phụ thuộc T092)
- [x] T095 [US4] Thêm timeout `LLM_TIMEOUT_S`, `TTS_TIMEOUT_S` và cơ chế giả lập lỗi (bước `llm`/`tts`/`render`, kiểu `error`/`timeout`,
  số lần) vào `src/ai_live/director/show_director.py`; lỗi ghi `errors.jsonl` và phát lên trang điều khiển (phụ thuộc T094)
- [x] T096 [US4] Thêm `POST /api/pause`, `/api/resume`, `/api/skip` (ghi log `control_command` kèm `t_mono` ngay khi nhận, rồi chuyển cho
  director) và `POST /api/debug/fault` (chỉ đăng ký khi `APP_ENV=dev`) vào `src/ai_live/app/routes.py` (phụ thuộc T094, T095)
- [x] T097 [P] [US4] Thêm nút Tạm dừng, Tiếp tục, Bỏ qua và trạng thái phiên vào `src/ai_live/app/static/control.html` và
  `src/ai_live/app/static/control.js`

**Checkpoint:** T089–T091 PASS; quickstart US4 bước 1–4 đạt. Dừng lại, báo người dùng.

---

## Phase 8: Hoàn thiện và việc chung

- [x] T098 [P] Cập nhật `docs/ARCHITECTURE.md` §2 (mô hình `Product` có biến thể, `ProductCatalog`) theo `data-model.md` §2, và thêm `qa_eval/`,
  `core/protocols.py`, các `__main__.py` của từng khâu vào `src/README.md` (§3 đã sửa ở T023)
- [x] T099 [P] Soạn bộ ≥ 10 câu hỏi bẫy và ép host (bảo hành, công dụng y tế, giá giả, khuyến mãi, ra lệnh đổi luật) cho file demo trong
  `data/eval/adversarial_questions.json`, cùng định dạng `contracts/content-template.md` §2 (phục vụ SC-002)
- [~] T100 Chạy `quickstart.md` từ mục 0 tới US5 (kể cả "Chạy riêng từng khâu") trên laptop, lần đầu với `REPLY_ENGINE=fake`, lần hai với
  `REPLY_ENGINE=gemini`; sửa `quickstart.md` chỗ nào không khớp thực tế
  *(2026-11-13: lần `fake` xong, đã sửa US2 #2 và US5 #1. 2026-11-20: lần hai với `REPLY_ENGINE=chain` (engine mặc định, ADR-035/040)
  qua Chrome DevTools: US1 và US3 khớp quickstart; câu trả lời bịa tìm thấy được sửa ở T103)*
- [-] T101 *(BỎ 2026-11-20, người dùng đồng ý: việc chọn model đã làm qua benchmark 2026-11-03 và ADR-035/040, engine là `chain` SEA-LION → Qwen; T102 và T104 đã đo với chuỗi này. `[-]` = bỏ, không tính vào tổng task)* So sánh `gemini-3.8-flash` và `gemini-3.5-flash-lite` theo research R5 (độ trễ câu đầu theo quy trình US3 và điểm bộ câu hỏi mẫu),
  ghi kết quả và model chọn vào ADR-018 trong `docs/DECISIONS.md`, cập nhật `LLM_MODEL` trong `.env.example`. Chỉ chọn model mới khi điểm bộ
  câu hỏi mẫu không thấp hơn model đang dùng (Điều III). Chạy trên free tier, không chạy ngay trước buổi demo (rủi ro Q11)
- [x] T102 Đo SC-001 theo quickstart US3: 20 comment, mỗi comment gửi sau khi lượt trước nói xong, p95 `total` ≤ 3,5 s; so thêm p95 bước `llm`
  với ngân sách 1,5 s ở bảng ảnh hưởng độ trễ của `plan.md`; ghi số liệu (kèm `queue_wait` p95) vào mục "Kết quả kiểm chứng" cuối
  `specs/001-local-reply-pipeline/quickstart.md`
- [~] T103 Kiểm SC-002: chạy `python -m ai_live.qa_eval run --content data/products/demo.docx --questions data/eval/adversarial_questions.json`,
  người vận hành đọc từng câu trả lời, yêu cầu 0 câu bịa; ghi kết quả vào mục "Kết quả kiểm chứng" của `quickstart.md`
  *(2026-11-20: lần 1 11/12, a08 bịa "còn hàng"; đã sửa prompt + `claim_phrases.txt`; Qwen 11/12 sau sửa, câu sai a02 nay bị guard chặn;
  chờ chạy lại bằng SEA-LION khi hạn mức reset và người vận hành đọc từng câu)*
- [x] T104 Kiểm SC-008 và SC-009: chạy `qa_eval run` với `data/eval/demo_questions.json --repeat 3` (cả 3 lần ≥ 8/10), người vận hành điền cột
  "Chấm tay" trong báo cáo `.md` và đối chiếu (≥ 9/10 câu khớp); ghi kết quả vào mục "Kết quả kiểm chứng" của `quickstart.md`, điểm này là mốc
  hồi quy cho Điều III
  *(2026-11-20: SC-008 đạt 10/10 × 3 với engine `chain`; SC-009 đạt: chấm tay báo cáo `20261120-114753` khớp 10/10, Claude chấm theo yêu cầu người dùng, người dùng quan sát)*
- [x] T105 Kiểm SC-005 và SC-006: chạy liên tục 30 phút, khoảng 1 comment mỗi 30 s, giả lập ≥ 3 lỗi ở bước `llm` hoặc `tts` qua
  `/api/debug/fault`, phiên không dừng; chụp ≥ 10 ảnh màn hình host vào thời điểm ngẫu nhiên, nhãn AI có trong mọi ảnh (ảnh không commit);
  ghi kết quả vào mục "Kết quả kiểm chứng" của `quickstart.md`
- [x] T106 Kiểm SC-007: 10 lần Bỏ qua và 10 lần Tạm dừng, đọc `latency_ms` của mọi dòng log `control_applied`, mọi lần ≤ 1000 ms và sau lệnh
  tạm dừng không có `turn_started`; ghi giá trị lớn nhất vào mục "Kết quả kiểm chứng" của `quickstart.md`
- [x] T107 Kiểm file Word từ nhiều ứng dụng (rủi ro Q7, research R1): mở và lưu lại `data/products/template.docx` và `demo.docx` bằng Word giao
  diện tiếng Việt, Google Docs (tải về `.docx`) và WPS Office bản miễn phí, chạy `python -m ai_live.products validate` cho từng file; ghi kết
  quả vào research R1 và mục "Kết quả kiểm chứng" của `quickstart.md`. Ứng dụng nào không có sẵn thì ghi `TODO:` thay vì đoán
  *(2026-11-13: chỉ có Word giao diện tiếng Anh, đạt; Word tiếng Việt, Google Docs, WPS ghi `TODO:` ở research R1)*
- [ ] T108 Hồi quy Điều III: sau lần sửa cuối cùng của `brain/prompt.py`, `brain/guard.py`, `brain/gemini_engine.py` hoặc `LLM_MODEL` trong
  pha này, chạy lệnh ở mục "Hồi quy khi đổi prompt, engine hoặc model" của `quickstart.md`; điểm không thấp hơn mốc T104, thấp hơn thì hoàn
  lại thay đổi hoặc hỏi người dùng; ghi kết quả vào "Kết quả kiểm chứng" (phụ thuộc T104)
  *(2026-11-20: cần chạy sau lần sửa prompt + claim phrases hôm nay; SEA-LION hết hạn mức ngày, chạy sáng 2026-11-21)*
- [x] T109 `uv run pytest` và `uv run ruff check . && uv run ruff format --check .` đều sạch
  *(2026-11-13: pytest 2461 passed, 11 xfailed; ruff check và format sạch sau khi sửa hai file test của 006/007)*
- [ ] T110 Chạy `/update-context`

## Phase 9: Lời chào và chống spam theo người xem (ADR-077, thêm 2026-11-23)

- [x] T111 [P] Test trong `tests/unit/test_greetings.py` (nhận diện lời chào giữ dấu, không nhận "cháo", "hì", câu dài, câu hỏi; chào lặp
  trong 600 s; câu mẫu xoay vòng, có tên người xem và tên sản phẩm chính) và `tests/unit/test_author_limits.py` (quá 3 comment/30 s thì
  tạm bỏ qua 120 s, không tự kéo dài, `author_key` từ nguồn thắng tên)
- [x] T112 [P] Test trong `tests/unit/test_memory_queue.py`: mỗi người một comment chờ, comment mới ưu tiên cao hơn hoặc bằng thì thay,
  thấp hơn thì bị bỏ `superseded`
- [x] T113 `comments/greetings.py`, `data/rules/greetings.json`, `GreetingRules` trong `CommentIntake`, `GreetingReplier` trong
  `ShowDirector._produce` (FR-026)
- [x] T114 `comments/author_limits.py` chạy đầu tiên trong `CommentIntake`; `Comment.author_key`; `DropReason` `spam`, `greeted`,
  `superseded` và nhãn trên trang điều khiển; supersede trong `InMemoryCommentQueue.put` (FR-027, FR-028)
- [x] T115 Cấu hình `COMMENT_AUTHOR_MAX`, `COMMENT_AUTHOR_WINDOW_S`, `COMMENT_AUTHOR_MUTE_S`, `COMMENT_GREETING_REPEAT_S`,
  `GREETING_RULES_PATH` trong `core/config.py`, `.env.example`, `plan.md`; test tích hợp `test_077_*` trong
  `tests/integration/test_pipeline_fake.py`

## Phase 10: Người vận hành chặn người xem (ADR-078, thêm 2026-11-23)

- [x] T116 [P] Test trong `tests/unit/test_author_limits.py` (chặn 5 phút hết hạn, chặn cả phiên, chặn tay không tính vào giới hạn tốc
  độ, bỏ chặn gỡ cả tạm bỏ qua tự động, `viewers()` liệt kê manual trước và không trùng) và `tests/unit/test_memory_queue.py`
  (`remove_author` bỏ comment đang chờ với lý do `blocked`)
- [x] T117 `AuthorLimiter.block/unblock/blocked/viewers`, `DropReason.BLOCKED`, `CommentIntake.block/unblock/viewers`, sự kiện
  `viewers_changed`, `author_key` trong payload `comment_accepted`, `comment_dropped`, `turn_started` và phần tử hàng đợi (FR-029)
- [x] T118 `POST /api/viewers/block`, `POST /api/viewers/unblock`, `viewers` trong `GET /api/state`; test trong `tests/unit/test_api.py`
- [x] T119 Trang điều khiển: nút "Chặn" (5 phút / 30 phút / cả phiên) cạnh comment trong hàng đợi, comment bị loại và lượt đang nói; ô
  "Người xem bị chặn" có thời gian còn lại và nút "Bỏ chặn"
- [ ] T120 Người dùng thử tay trên trang điều khiển với nguồn giả (chặn, xem comment bị loại `blocked`, bỏ chặn)

## Phụ thuộc và thứ tự

- Setup → Foundational → US1 → US2 → US3 → US5 → US4 → Hoàn thiện.
- T001 đã xong (2026-10-30). T005 cần T002, T003, T004.
- T023 (sửa ARCHITECTURE §3) làm trước khi viết adapter đầu tiên ở US1.
- US2, US3, US5 và US4 đều sửa lại `show_director.py`, `routes.py`, `control.html`/`control.js` của US1, nên làm tuần tự theo thứ tự trên,
  không làm song song giữa các story.
- US4 dựa vào hàng đợi của US2 (tiếp tục thì lấy comment ưu tiên cao nhất) và `errors.jsonl` của US3.
- T101 (chọn model) làm trước T102–T105, vì các phép đo đó dùng model đã chọn. *(T101 bỏ 2026-11-20: model đã chọn theo ADR-035/040)*
- T103 cần T099; T104 cần T086; T108 cần T104.

## Chạy song song

- Setup: T006, T007 song song với T002–T005.
- Foundational: T008, T009, T011, T012, T013, T014 cùng lúc (T010 sau T008); sau đó T015, T016, T017, T018, T021, T023, T028 cùng lúc.
- US1: test T030–T039 cùng lúc; implement T040–T044, T052, T053 cùng lúc.
- US2: T058–T063 cùng lúc; T064–T067 và T070 cùng lúc.
- Phase 4b: T111 (`ai-brain`) và T112–T116 (`ai-qa`) cùng lúc; trong `ai-qa`, T112 làm trước T113–T116.
- US3: T071–T073 cùng lúc; T074, T075, T079 cùng lúc.
- US5: T080–T083 cùng lúc; T084, T086, T088 cùng lúc.
- US4: T089–T091 cùng lúc; T093 và T097 song song với T092.
- Hoàn thiện: T098, T099 cùng lúc.

## Đợt GPU (RunPod)

Không có. Toàn bộ feature 001 chạy trên laptop với `AVATAR_MODE=static`. Không bật pod RunPod cho feature này.

## Chiến lược MVP

1. Setup + Foundational (T001–T029) → 2. US1 (T030–T057) → **dừng, kiểm chứng, demo** → 3. US2 → US3 → US5 → US4, mỗi story dừng ở
   Checkpoint → 4. Hoàn thiện.

## Độ phủ yêu cầu

| Yêu cầu | Task |
|---------|------|
| FR-001 | T037, T044, T055 |
| FR-002 | T014, T017, T058, T062, T063, T065, T068, T069 |
| FR-003 | T059, T066 |
| FR-004 | T060, T061, T067 |
| FR-005 | T060, T067, T089 |
| FR-006 | T036, T051, T060, T067 |
| FR-007 | T010, T024, T026, T029, T037, T056 |
| FR-008 | T030, T032, T038, T040, T042, T111 |
| FR-009 | T030, T038, T040 |
| FR-010 | T030, T032, T042, T111 |
| FR-011 | T014, T017, T030, T032, T038, T040 |
| FR-012 | T030, T038, T040 |
| FR-013 | T031, T036, T041, T051 |
| FR-014 | T035, T036, T050, T052 |
| FR-015 | T013, T019, T037, T052, T055 |
| FR-016 | T012, T021, T053, T070 |
| FR-017 | T089, T090, T091, T094, T096, T097 |
| FR-018 | T072, T076, T077 |
| FR-019 | T071, T072, T073, T074, T075, T078, T079 |
| FR-020 | T036, T051, T089, T095 |
| FR-021 | T009, T013, T018, T019, T020, T037, T072, T075 |
| FR-022 | T025, T081, T082, T087, T088 |
| FR-023 | T080, T083, T085 |
| FR-024 | T080, T085 |
| FR-025 | T010, T024, T030, T040 |
| FR-026 | T111, T113, T115 |
| FR-027 | T111, T114, T115 |
| FR-028 | T112, T114 |
| FR-029 | T116, T117, T118, T119, T120 |
| SC-001 | T071, T102 |
| SC-002 | T099, T103 |
| SC-003 | T061 |
| SC-004 | T072 |
| SC-005 | T089, T105 |
| SC-006 | T037, T105 |
| SC-007 | T089, T090, T091, T094, T096, T106 |
| SC-008 | T080, T104 |
| SC-009 | T080, T104 |
| Điều III (hồi quy) | T104, T108 (T101 bỏ) |
| Điều IV (chạy riêng từng khâu) | T026, T037, T039, T048, T049, T057, T063, T069 |
| Điều IV (adapter mới không đổi lõi; contract test) | T112, T113, T114, T115, T116 |
| Rủi ro Q7 (file Word nhiều ứng dụng) | T107 |

## Nhật ký lỗi gặp khi implement

> Ghi lỗi, chỗ lệch spec/plan và cách xử lý trong lúc implement (theo yêu cầu người dùng ở `/sdd.implement` Phase 2).

| Ngày | Task | Loại | Vấn đề | Xử lý |
|------|------|------|--------|-------|
| 2026-10-30 | T010, T024 | Lệch contract | Contract chưa có mã lỗi cho file không phải `.docx`, file quá lớn và FAQ sai cặp `H:`/`Đ:` | Thêm `not_docx`, `too_large`, `faq_format` vào `contracts/content-template.md` |
| 2026-10-30 | T017 | Bug | Chữ "đồng" bỏ dấu thành "dong", trùng "dòng": "2 dòng kem" bị đọc thành 2 VND | Bỏ "đồng" khỏi đơn vị tiền của `extract_amounts`; ghi trong docstring `core/text.py` |
| 2026-10-30 | T010 | Bug test | `test_empty_section` chèn mục Mô tả rỗng vào giữa tiêu đề Giá và dòng giá, làm mục Giá rỗng theo | Chèn sau dòng `250.000đ` |
| 2026-10-30 | T024 | Trường hợp biên | Tiêu đề Heading 1/2 trống (Enter thừa trong Word) mở ra sản phẩm hoặc mục không tên | Bỏ qua tiêu đề trống; ghi trong contract |
| 2026-10-30 | T026, T028 | Bug | Console Windows mặc định cp1252, `print` chữ tiếng Việt ném `UnicodeEncodeError` | `sys.stdout.reconfigure(encoding="utf-8")` trong lệnh `validate` và script sinh nội dung |
| 2026-10-30 | T028 | Ghi chú | `template.docx` còn chỗ trống `[…]` nên `validate` trên mẫu báo `price_format` | Cố ý; ghi trong contract. Chỉ `demo.docx` phải 0 lỗi (T029) |
| 2026-10-30 | (analyze) | Docs | `data-model.md`: `DropReason.skipped_by_operator` thừa, thiếu trạng thái cuối của `QueuedComment`, nghĩa `error_step=guard` chưa rõ | Đã sửa `data-model.md`, `contracts/events.md`; T013, T019, T029 sửa câu chữ |
| 2026-10-30 | T067 | Lệch contract | `CommentQueue.put` trả `None`, nên route và CLI không biết comment mới có bị loại `queue_full` ngay lúc vào hay không | `put` trả `QueuedComment` (trạng thái `dropped` khi bị loại); thêm `sweep()` và `run_sweeper()`; sửa `contracts/adapters.md` |
| 2026-10-30 | T068, T069 | Ngoài plan | Route `POST /api/comments` và lệnh `ai_live.comments` cùng chạy chuỗi push → lọc → phân loại → hàng đợi; viết hai lần dễ lệch luật | Thêm file `src/ai_live/comments/intake.py` (`CommentIntake.submit`), cả hai cùng dùng |
| 2026-10-30 | T065 | Bug | Bộ lọc thay tên không an toàn bằng "bạn", prompt lại thêm "bạn" phía trước thành "bạn bạn" | `safe_author_name` coi tên "bạn" như không có tên. Chạm module prompt: nhớ chạy lại hồi quy Điều III (T108) |
| 2026-10-30 | T065 | Refactor | Regex nhận link nằm trong `brain/prompt.py`, bộ lọc cần dùng lại | Chuyển sang `core/text.py` (`contains_link`, `phrase_pattern`, `contains_phrase`) |
| 2026-10-30 | T064 | Trường hợp biên | Bỏ dấu thì nhiều từ tục trùng từ thường ("đeo", "lớn", "các", "buổi", "ngủ", "cho"); từ khóa "đạt", "loại nào", "có" làm phân loại sai | Không đưa các từ này vào danh sách; ghi lý do ở đầu file luật. TODO: đo lại với ~50 comment thật |
| 2026-10-30 | T065 | Lệch code | `MockSource.push` cắt 300 ký tự trước khi bộ lọc thấy, nên không biết comment có bị cắt | `push` ghi `meta["truncated"]`; bộ lọc giữ cờ này |
| 2026-10-30 | T058 | Bug test | Test "rỗng thắng link" (`"😍 http://a.vn"`) sai: link luôn có ≥ 2 chữ cái nên luật rỗng không bao giờ tranh với link | Thay bằng test "link thắng từ tục" |
| 2026-10-30 | T067 | Docs | `contracts/events.md` ghi phần tử `queue_changed` thiếu `status` (code đã gửi từ US1) | Thêm `status` vào contract |
| 2026-10-30 | (checkpoint) | Lệch tasks | Quickstart US2 bước 1 và 3 cần nút Tạm dừng, thuộc US4 (T092+) | Bước 2 kiểm bằng T061 và gọi API; bước 4 kiểm bằng script thay `get()` bằng chờ vô hạn (giống tạm dừng). Bước 1 và 3 kiểm lại sau US4 |
| 2026-10-30 | T021, T056 | Lệch spec | `AI_LABEL_TEXT=` (rỗng) bị `env_ignore_empty` bỏ qua nên dùng mặc định "AI"; chỉ giá trị toàn khoảng trắng mới dừng khởi động | Giữ: nhãn vẫn luôn hiện (Điều I). Đề xuất sửa câu FR-015 thành "rỗng sau khi bỏ khoảng trắng thì dừng, không khai báo thì dùng `AI`" |
| 2026-10-30 | T051 | Lệch contract | Contract đặt timeout LLM/TTS trong adapter; làm vậy thì thời gian chờ hàng đợi phát bị tính nhầm là LLM chậm | Timeout đặt trong `ShowDirector`: LLM tính cho mỗi lần chờ câu kế, TTS cho từng câu, renderer cho từng ack. Đã sửa `contracts/adapters.md` |
| 2026-10-30 | T034, T050 | Lệch contract | Cần thêm `ReplyEngineError(kind, message)` để ghi `kind` vào log lỗi, và `AvatarRenderer.first_playback_at()` để director lấy mốc `avatar_first_frame` | Thêm vào `core/protocols.py` và `contracts/adapters.md` |
| 2026-10-30 | T041 | Ghi chú | Xuống dòng cũng là ranh giới câu (Gemini hay xuống dòng không có dấu câu) | Như T031 đã mô tả; không đổi spec |
| 2026-10-30 | T055–T057 | Lệch contract | Thêm mã lỗi: `409 busy`, `503 host_unavailable` (chưa `ready` hoặc hết giờ ack), `422 validation_error`, `404 not_found`; thêm route `/avatar-image` và chuyển `/static/host.html` → `/host` (file mẫu còn placeholder) | Đã ghi vào `contracts/api.md` (trừ 2 route phụ, chỉ phục vụ trang host) |
| 2026-10-30 | T046–T056 | Ghi chú | File thêm ngoài plan: `brain/factory.py`, `tts/factory.py` (`TTSConfigError`), `app/context.py`, `app/errors.py`. `create_app` đọc Settings ngay (route debug cần biết `APP_ENV`); `app` tạo lười qua `__getattr__` để test import không cần `.env`. `state.session.state` luôn `running` tới US4; `queue_changed` phát khi POST | Không đổi hành vi spec |
| 2026-10-30 | T046 | Docs | Research R5 còn TODO tên trường thinking level | Đã giải: `ThinkingConfig(thinking_level=ThinkingLevel.LOW)` với `google-genai` 2.34.0; còn TODO xác nhận mức `minimal` bằng T038 |
| 2026-10-30 | Checkpoint | Docs | Quickstart hỏi "Kem chống nắng X" nhưng `demo.docx` là "Kem chống nắng Mây Sáng SPF 50" | Sửa câu ví dụ trong `quickstart.md` |
| 2026-10-30 | Checkpoint | Bug | Chạy app với stdout chuyển ra file trên Windows (cp1252): log có tiếng Việt (`turn_error`) lỗi encode, mất dòng log | Test `tests/unit/test_logging.py`; `configure_logging` chuyển stdout sang UTF-8 khi chưa phải UTF-8 |
| 2026-10-30 | Checkpoint | Ghi chú | `curl -d` có chữ tiếng Việt trên Git Bash Windows gửi sai mã hóa → `400 http_error` | Không phải lỗi app; thêm ghi chú `--data-binary @file` vào `quickstart.md` |
| 2026-10-30 | Checkpoint | Ghi chú | Python 3.12 trên Windows: `time.monotonic` độ phân giải ~16 ms, nên lượt FakeReplyEngine đo `total_s=0.0` | Đủ cho mục tiêu < 5 s. **TODO:** đổi sang `time.perf_counter` nếu cần đo chi tiết từng khâu dưới 20 ms? |
| 2026-10-30 | T038 | Chặn | Chưa có `GEMINI_API_KEY` trong `.env` nên chưa chạy test `live_llm` và bước checkpoint với `REPLY_ENGINE=gemini` | Test đã viết; chờ người dùng tạo key free tier ở AI Studio rồi chạy `uv run pytest -m live_llm` |
| 2026-10-30 | T111 | Bug | `OutputGuard` để lọt khẳng định cấm có dấu câu hoặc ký tự vô hình xen giữa ("chữa-khỏi-mụn", "chữa. khỏi mụn", soft hyphen) vì chỉ gộp khoảng trắng | Sửa `guard.py`: gộp ký tự không phải chữ thành một khoảng trắng, xử lý ký tự định dạng Unicode (Cf). Cần chạy hồi quy T108 (`live_llm`, quota miễn phí) khi người dùng đồng ý |
| 2026-10-30 | T111 | Ghi chú | Giá thật viết có khoảng trắng ngăn nghìn ("250 000đ") bị chặn nhầm (đọc thành 0); ngoài định dạng R8 nên an toàn | **TODO:** có cần cho `core/text.py` chấp nhận khoảng trắng ngăn nghìn không? |
| 2026-10-30 | T112–T116 | Lệch contract | `contracts/adapters.md` ghi `sweep()`/`run_sweeper()` trên `CommentQueue` nhưng `core/protocols.py` không có; `config_error` của Gemini ném ở constructor, contract không nói lúc nào | **TODO:** đưa `sweep` vào Protocol hay ghi rõ là riêng của hàng đợi trong bộ nhớ? Contract test hiện chấp nhận `config_error` ở constructor hoặc trong stream |
| 2026-10-30 | T076 | Bug | `StaticRenderer.handle_message` ghi mốc `avatar_first_frame` cho cả `utterance_id` chưa từng gửi hoặc đã bị dọn, nên trang host cũ có thể tạo mốc giả | Chỉ ghi khi renderer đã gửi câu 0 của lượt đó; test trong `tests/unit/test_avatar_first_frame.py` |
| 2026-10-30 | T074–T078 | Lệch spec | `data-model.md` §4 không chốt tên trường JSON của các bước; `contracts/events.md` §2 không có bố cục `latency_summary.json`; `session_id` đổi từ uuid sang `YYYYMMDD-HHMMSS` cho khớp data-model §3 | Code dùng `received_to_first_sentence`, `first_sentence_to_tts_first_chunk`, `tts_first_chunk_to_first_frame`, `queue_wait`, `total`; file tổng hợp `{session_id, all, idle_only}`. **TODO:** người dùng duyệt rồi ghi vào data-model §4 và events.md §2 |
| 2026-10-30 | T083 | Chặn | Test `live_llm` chấm bộ câu hỏi với Gemini đã viết nhưng chưa chạy (chưa có `GEMINI_API_KEY`, tốn quota miễn phí ~10 request mỗi lần) | Chờ người dùng; chạy cùng T038 và hồi quy T108 |
| 2026-10-30 | T084–T085 | Lệch spec | Kết quả chấm lưu nhiều trường hơn `data-model.md` §5 (`author`, `question`, `error`, `created_at`, `threshold`, `warnings`...); nhịp gọi mặc định 6 s giả định quota phút ≥ 10 | **TODO:** cập nhật data-model §5? Kiểm tra giới hạn request/phút của free tier cho `LLM_MODEL` |
| 2026-10-31 | T038 | Ghi chú | Đã có `GEMINI_API_KEY`. 3 test US1 với Gemini thật (`gemini-3.8-flash`) PASS: giá 259.000đ–439.000đ, xưng "bạn Lan", hỏi bảo hành không bịa số, ép giá 99k không lọt số lạ | Chưa tick T038 trong danh sách: người dùng hoãn phần Gemini |
| 2026-10-31 | T083 | Chặn | Free tier `gemini-3.8-flash` chỉ **20 request/ngày** (lỗi 429 `generate_content_free_tier_requests`, limit 20). Chạy chấm 10 câu: q02, q04, q05 đúng; q01 timeout 60 s; q03 lỗi 503 (model quá tải); q06 hết quota ngày. Dừng tay, không lưu báo cáo | Người dùng hoãn phần Gemini. **TODO:** 20 request/ngày không đủ cho phiên 30 phút (~60 comment) → chọn ở T101: `gemini-3.5-flash-lite` (chạy được, câu đầu ~1,4–1,5 s, chưa rõ quota ngày) hay bật billing (có phí, hỏi người dùng trước)? Ghi ADR, xem lại ADR-018 |
| 2026-10-31 | T085 | Bug | Runner chấm điểm retry mọi lỗi 429 với backoff 15→30→60→120 s, kể cả khi hết quota **ngày** (Gemini báo "retry in 11h"), nên mỗi câu tốn ~4 phút rồi vẫn lỗi; `pytest -m live_llm` vì vậy trông như treo | Chưa sửa (người dùng hoãn). **TODO:** nhận diện quota ngày (`PerDay` / retry delay dài) thì dừng cả lượt chạy ngay, báo lỗi rõ |
| 2026-10-31 | T038, T083 | Ghi chú | `tests/conftest.py` xóa các biến `LLM_*` khỏi môi trường, nên `LLM_MODEL=... uv run pytest -m live_llm` không đổi được model, test luôn dùng `LLM_MODEL` trong `.env` | Đổi model cho test live thì sửa `.env`. **TODO:** có cần cách ghi đè model riêng cho test live (phục vụ T101) không? |
| 2026-10-31 | T087 | Lệch plan | Tách `ProductStore` thành `parse` (chạy ở thread) và `install` (chạy trên event loop) thay vì gọi cả `replace` qua `to_thread`, vì `EventBus.publish` không an toàn đa luồng. Mã lỗi tự chọn (contract chưa ghi): 413 `content_too_large`, 415 `unsupported_media_type`. `X-Filename` do trình duyệt percent-encode, server decode, vì header HTTP không mang được tiếng Việt | **TODO:** bổ sung mã lỗi 413/415 và cách mã hóa `X-Filename` vào `contracts/api.md`? |
| 2026-10-31 | T094, T096 | Ghi chú | Tạm dừng/tiếp tục lặp lại và bỏ qua khi host đang không nói chỉ ghi `control_command`, không ghi `control_applied` (không có gì thay đổi, đúng events.md §1). Comment đến đúng lúc bấm tạm dừng được đưa lại vào hàng đợi, nên mất vị trí FIFO so với các comment cùng ưu tiên | Chấp nhận, ảnh hưởng nhỏ |
| 2026-10-31 | T095 | Ghi chú | `LLM_TIMEOUT_S` tính cộng dồn thời gian chờ LLM (câu đầu và cả luồng), không tính thời gian chờ phát. Lỗi giả lập `render` + `timeout` chờ `ack_timeout_s` rồi báo hết giờ. `/api/debug/fault` kiểm tra đầu vào (422 khi sai `step`/`mode` hoặc `count` < 1), chỉ có khi `APP_ENV=dev` | — |
| 2026-10-31 | T093 | Ghi chú | `host.js` đã xử lý `stop` từ US1 (`stopAll()` dừng nguồn âm, xóa hàng chờ và phụ đề), không cần sửa | — |
| 2026-10-31 | US4 | Checkpoint | Test tự động xanh. Chưa chạy tay quickstart US4 bước 1–4; chạy được trên laptop, kèm US2 bước 1 và 3 (cần nút Tạm dừng) | **TODO:** người dùng chạy tay rồi ghi kết quả |
| 2026-11-23 | T111–T115 | Ghi chú | Luật một comment chờ mỗi người làm vỡ test cũ gửi nhiều comment cùng tên "Lan" | Helper `make_comment` trong `test_memory_queue.py` gán `author_key` riêng cho mỗi câu; test lỗi engine dùng người thứ hai "Mai" |
