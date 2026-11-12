# Tasks: Giọng đọc tiếng Việt (TTS) cho AI host

- **Feature ID:** 003-vietnamese-tts · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`
- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong).
- **[GPU]**: cần GPU (laptop trước theo ADR-023, RunPod chỉ dự phòng và cần duyệt chi phí); gom vào "Đợt GPU" ở cuối.
- **[US#]**: thuộc user story nào trong spec.
- Mỗi task ghi **đường dẫn file cụ thể**. Đường dẫn mã nguồn tính từ `src/ai_live/`.
- Mọi test unit/contract/integration chạy không mạng, không key, không model: dùng `FakeTTS`, đối tượng Vieneu giả và client Gemini giả
  tiêm qua constructor. Riêng `tests/integration/test_tts_live.py` (marker `live_tts`) dùng model / API thật; phần Gemini tốn hạn mức
  nên **cần người dùng đồng ý trước khi chạy**.
- Ký hiệu bước tay theo quickstart: 📦 cần `vieneu` + model đã tải, 🌐 🔑 cần mạng + `GEMINI_API_KEY` (tốn hạn mức miễn phí).
- File nào bị sửa thì dịch comment/docstring tiếng Việt cũ trong file đó sang tiếng Anh (ADR-022).
- Quyết định lúc tạo tasks (2026-11-07):
  - Thêm cấu hình `tts_abbreviations_path` (`TTS_ABBREVIATIONS_PATH`, mặc định `data/rules/tts_abbreviations.json`) theo cách 001 khai
    đường dẫn file luật; đã ghi vào data-model §1.
  - `warm_up()` của VieNeu lỗi thì app vẫn chạy (research R7); `synthesize()` sau đó ném lại đúng `TTSEngineError` đã gặp, không nạp
    lại model trong lượt (nạp lại chắc chắn vượt `TTS_TIMEOUT_S`), nên lượt đầu báo lỗi bước `tts` với `kind` của lỗi warm-up.
  - Ở US1 factory dùng hàm chuẩn hóa giữ nguyên chữ; US2 mới nối `normalize_for_speech` vào. Nhờ vậy US1 làm và nghe được độc lập.

## Phase 1: Setup

- [x] T001 📦 🌐 `pyproject.toml`, `uv.lock`: `uv add vieneu` (bản CPU/ONNX, ADR-024 đã duyệt 2026-11-07). Kiểm cây phụ thuộc
  (`uv tree --package vieneu`): nếu kéo theo `torch` hoặc gói GPU thì **dừng, báo người dùng**, không tự đổi sang gói khác.
- [x] T002 📦 🌐 Tải model VieNeu-TTS v3 Turbo về cache mặc định của thư viện (ngoài repo, không commit; đã đổi sang thư mục riêng
  `VIENEU_MODEL_CACHE` vì cache symlink không nạp được, người dùng duyệt 2026-11-07, research R1), bằng một script tạm trong
  scratchpad. Ghi kết quả vào `specs/003-vietnamese-tts/research.md` R1 và bỏ các `TODO:` đã trả lời: chữ ký thật của `Vieneu(...)` và
  `infer_stream(...)`, danh sách tên giọng có sẵn (có `Thục Đoan` không), dung lượng model, thư mục cache, sample rate và kiểu dữ liệu
  đầu ra, có tự chuẩn hóa chữ bên trong không, gọi từ nhiều luồng có an toàn không, cách đặt số luồng CPU. Sửa `data-model.md` §1 (dòng
  TODO thư mục cache). Nếu sample rate đầu ra khác 48 kHz thì ghi rõ để T023 dùng đúng hệ số đổi. (phụ thuộc T001)
- [x] T003 `pyproject.toml`: thêm marker `live_tts` ("gọi nguồn giọng thật: VieNeu cần model đã tải, Gemini tốn hạn mức") và đổi
  `addopts` thành `-m "not live_llm and not live_tts"`. (cùng file T001, làm sau T001)
- [x] T004 [P] `tests/conftest.py`: thêm `VIENEU_` vào `_ENV_PREFIXES` để biến môi trường thật của máy không lọt vào test.
- [x] T005 [P] `data/rules/tts_abbreviations.json`: đúng nội dung ở data-model §3 (`SP`, `KM`, `SL`, `VND`).

---

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

### Test (viết trước, phải FAIL trước khi implement)

- [x] T006 [P] `tests/unit/test_config.py`: `TTS_PROVIDER` nhận `fake` / `vieneu` / `gemini`, từ chối `elevenlabs`, `oss` và giá trị lạ;
  mặc định và kiểm tra của các trường mới ở data-model §1 (`tts_quota_cooldown_s` ≥ 0, `vieneu_cpu_threads` ≥ 1, `tts_sample_rate` > 0,
  `vieneu_voice` / `gemini_tts_model` / `gemini_tts_voice` không rỗng, `tts_abbreviations_path`); test sẵn có so `Settings` với
  `.env.example` vẫn chạy và phải thấy thiếu khối TTS mới.
- [x] T007 [P] `tests/contract/test_tts_contract.py`: thêm hợp đồng `warm_up()` cho mọi harness trong `TTS_FACTORIES` (gọi được hai lần,
  không sinh tiếng, `synthesize` chạy được sau đó); `TTSEngineError` có `kind`, `message`, `str(exc) == message`.
- [x] T008 [P] `tests/unit/test_tts_speech.py`: lớp bọc `SpeechTTS` với engine giả và đồng hồ giả, theo contracts/adapters.md §2 và
  data-model §4: engine nhận chữ **đã** qua hàm chuẩn hóa tiêm vào; `usage.requests` và `usage.chars` (độ dài chữ sau chuẩn hóa) tăng
  đúng, kể cả câu lỗi; câu rỗng sau chuẩn hóa → stream kết thúc không có chunk, không gọi engine; lỗi `quota_exhausted` → vào trạng
  thái nghỉ, `quota_errors` += 1, log `tts_quota_exhausted` có `provider`, `cooldown_s`, ném lại lỗi; trong lúc nghỉ → ném ngay
  `quota_exhausted` ("thử lại sau N giây"), không gọi engine, `rejected_in_cooldown` += 1; hết giờ nghỉ → gọi engine thật đúng một lần;
  lỗi `kind` khác đi qua nguyên vẹn, không vào trạng thái nghỉ; `aclose()` của lớp bọc đóng generator của engine (FR-014);
  `warm_up()` và `sample_rate` chuyển tiếp từ engine; chữ đã chuẩn hóa không có trong log mức INFO.
- [x] T009 [P] `tests/unit/test_tts_factory.py`: `TTS_PROVIDER=fake` → `SpeechTTS` bọc `FakeTTS`, `usage.provider == "fake"`,
  `sample_rate == 16000`.
- [x] T010 [P] `tests/integration/test_tts_app.py` (mới): mở app với engine giả qua `create_app` → `warm_up()` được gọi đúng một lần lúc
  khởi động, log `tts_ready` có `provider`, `voice`, `warm_up_s`; engine giả có `warm_up()` ném `TTSEngineError` → app vẫn mở, log
  `tts_warm_up_failed` có `provider`, `kind`, `message`; đóng app → có `data/sessions/<id>/tts_usage.json` đúng 5 trường (contracts/events.md
  §3) và log `tts_usage`. Dùng mẫu fixture của 008: dựng client **trước** fixture gom log.

### Implement

- [x] T011 `core/config.py`: `tts_provider: Literal["fake", "vieneu", "gemini"]`, thêm `tts_quota_cooldown_s`, `vieneu_voice`,
  `vieneu_cpu_threads`, `vieneu_model_cache` (mở `~`), `gemini_tts_model`, `gemini_tts_voice`, `tts_abbreviations_path` với mặc
  định và kiểm tra như data-model §1; bỏ các trường ElevenLabs / OSS. (T006 xanh cùng T012)
- [x] T012 [P] `.env.example`: thay khối TTS bằng đúng contracts/events.md §4 (đã có `VIENEU_MODEL_CACHE`), thêm dòng
  `TTS_ABBREVIATIONS_PATH=`; bỏ `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID`, `OSS_TTS_MODEL_PATH`. (`.env` thật của người dùng không sửa;
  `Settings` có `extra="ignore"` nên các dòng cũ trong `.env` không làm hỏng app, ghi chú cho người dùng xóa khi rảnh.)
- [x] T013 [P] `tests/unit/test_cli.py`: `test_tts_say_unknown_provider_exits_1` đang dùng `"elevenlabs"` làm nhà cung cấp lạ; đổi sang
  một giá trị không có trong cấu hình (ví dụ `"azure"`). Grep `src/` và `tests/` cho `elevenlabs`, `oss_tts`, `OSS_TTS` để không còn chỗ
  sống nào (tài liệu sửa ở T046, T047).
- [x] T014 `core/protocols.py`: thêm `async def warm_up(self) -> None` vào Protocol `TTSEngine`; thêm `TTSEngineError(kind, message)`
  với 5 `kind` ở contracts/adapters.md §1, docstring nêu PCM16 mono 16 kHz (ADR-025).
- [x] T015 `tts/fake_tts.py`: `warm_up()` không làm gì. (phụ thuộc T014; T007 xanh với harness Fake)
- [x] T016 `tts/speech.py` (mới): `TTSUsage` và `SpeechTTS` theo contracts/adapters.md §2, data-model §4. (phụ thuộc T014; T008 xanh)
- [x] T017 `tts/factory.py`: `create_tts()` luôn trả `SpeechTTS`; nhánh `fake` bọc `FakeTTS` với hàm chuẩn hóa giữ nguyên chữ; giá trị lạ
  vẫn ném `TTSConfigError`. (phụ thuộc T011, T016; T009 xanh)
- [x] T018 `director/session_log.py`: hằng tên file `tts_usage.json` và hàm ghi `TTSUsage` vào thư mục phiên (ghi cạnh
  `latency_summary.json`).
- [x] T019 `app/main.py` lifespan: sau khi dựng engine gọi `await tts_engine.warm_up()`, log `tts_ready` hoặc `tts_warm_up_failed` (app
  vẫn chạy); lúc đóng ghi `tts_usage.json` (T018) và log `tts_usage` trước `session_log.close()`. Engine truyền vào `create_app(tts=...)`
  có thể không phải `SpeechTTS`: chỉ ghi usage khi có `usage`. Thêm `warm_up()` cho các TTS giả trong test được truyền vào app
  (`tests/integration/test_show_director.py`, `tests/integration/test_script_runner.py`) nếu test đỏ vì thiếu. (phụ thuộc T014, T018;
  T010 xanh)

**Checkpoint:** `uv run pytest` xanh với `TTS_PROVIDER=fake`; app chạy như 001/004 (US1 kịch bản 3).

---

## Phase 3: User Story 1: Host trả lời bằng giọng tiếng Việt thật (P1) 🎯 MVP

**Mục tiêu:** chọn `TTS_PROVIDER=vieneu` là host đọc bằng giọng tiếng Việt thật chạy trên laptop, từng câu, nối liền.
**Kiểm thử độc lập:** mở phiên với giọng thật, gõ vài comment, nghe câu trả lời và xem bảng độ trễ.

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [x] T020 [P] [US1] `tests/unit/test_vieneu_tts.py`: `VieneuTTS` với đối tượng Vieneu giả tiêm vào (không cần model): chunk ra đúng thứ
  tự; đổi float32 ở sample rate của model (T002) sang int16 16 kHz mono (độ dài đúng hệ số, giá trị bị chặn trong [-32768, 32767],
  `sample_rate == 16000`); chunk đầu tới tay người gọi trước khi model giả sinh xong chunk cuối (FR-004); `aclose()` giữa chừng làm luồng
  phụ dừng (model giả thấy cờ dừng, không sinh thêm) (FR-014); hai lượt gọi liền nhau chạy tuần tự; model ném lỗi → `TTSEngineError`
  `model_error` ("VieNeu lỗi khi đọc câu: …"); `warm_up()` nạp model một lần, đọc thử "Dạ.", truyền `cpu_threads`; tên giọng không có
  trong danh sách → `config_error`; warm-up đặt `HF_HUB_CACHE` = `model_cache` và `HF_HUB_DISABLE_SYMLINKS=1` trước khi import `vieneu`,
  còn `huggingface_hub` đã import từ trước → `config_error` (research R1); warm-up lỗi rồi gọi `synthesize()` → ném lại đúng lỗi đó, không nạp lại; event loop không bị chặn khi
  model giả chạy chậm.
- [x] T021 [P] [US1] `tests/contract/conftest.py`: thêm `VieneuTTSHarness` (model giả, `make()`, `make_failing()`) vào `TTS_FACTORIES` để
  toàn bộ `tests/contract/test_tts_contract.py` chạy cả với `VieneuTTS`.
- [x] T022 [P] [US1] `tests/unit/test_tts_factory.py`: `TTS_PROVIDER=vieneu` → `SpeechTTS` bọc `VieneuTTS` với `vieneu_voice`,
  `vieneu_cpu_threads` từ cấu hình, `usage.provider == "vieneu"`; gói `vieneu` không import được (monkeypatch) → `TTSConfigError` thông
  báo tiếng Việt chỉ cách sửa (`uv sync`).

### Implement US1

- [x] T023 [US1] `tts/vieneu_tts.py` (mới): `VieneuTTS` theo contracts/adapters.md §2 và research R1 (đã cập nhật ở T002): đặt biến
  môi trường cache rồi mới import `vieneu`, `numpy` bên trong; `warm_up()` chạy trong `asyncio.to_thread`; `synthesize()` chạy `infer_stream` trong luồng phụ, đẩy chunk
  qua `asyncio.Queue` bằng `loop.call_soon_threadsafe`, dừng bằng `threading.Event` khi `aclose()`, `asyncio.Lock` để gọi tuần tự; đổi
  định dạng sang PCM16 16 kHz. (phụ thuộc T002, T014; T020, T021 xanh)
- [x] T024 [US1] `tts/factory.py`: nhánh `vieneu` (hàm chuẩn hóa vẫn giữ nguyên chữ ở bước này). (phụ thuộc T023; T022 xanh)
- [x] T025 [US1] 📦 `tests/integration/test_tts_live.py` (mới, marker `live_tts`): `VieneuTTS` thật qua `create_tts` → `warm_up()` xong,
  đọc "Dạ, chị ơi, sản phẩm này đang có sẵn ạ." ra PCM16 16 kHz không rỗng, độ dài chẵn; in thời gian tới chunk đầu (chỉ ghi số).
  Chạy: `uv run pytest -m live_tts tests/integration/test_tts_live.py -k vieneu`.
- [x] T026 [US1] 📦 Chạy tay quickstart "US1" bước 1–5 với `TTS_PROVIDER=vieneu`: kịch bản 1 (nghe được, đúng dấu, phụ đề cùng lúc),
  kịch bản 2 (câu đầu phát trước khi câu cuối tạo xong, không lặng bất thường), "Bỏ qua" giữa câu thì tiếng dừng và CPU hạ (FR-014),
  `fake` vẫn như 001 (kịch bản 3). Người dùng nghe và xác nhận. Ghi số `tts_first_chunk` từ `GET /api/latency` vào mục nhật ký cuối file.

**Checkpoint:** US1 chạy độc lập với giọng VieNeu. Dừng lại, báo người dùng, demo.

---

## Phase 4: User Story 2: Đọc đúng số, giá, đơn vị và viết tắt (P2)

**Mục tiêu:** trước khi đọc, chuyển giá, khoảng giá, phần trăm, đơn vị, size, viết tắt, dãy số thành chữ theo cách nói miền Nam; phụ đề
giữ dạng gốc.
**Kiểm thử độc lập:** cho bộ câu mẫu qua bước chuyển chữ, so với cách đọc kỳ vọng; rồi nghe vài câu.

### Test cho US2 (viết trước, phải FAIL trước khi implement)

- [x] T027 [P] [US2] `tests/unit/test_tts_normalize.py`: bảng ≥ 40 câu (SC-001) lấy từ data-model §3 và nội dung demo, mỗi quy tắc 1–10
  ít nhất 2 câu; đúng nguyên văn kịch bản chấp nhận US2 #1–#4; luật đọc số miền Nam (`ngàn`, `lẻ`, `mốt`, `lăm`, `bốn`, `không trăm`,
  nhóm toàn 0 bị bỏ) (FR-007); dấu chấm ngăn ngàn chỉ khi đủ 3 chữ số, `1.5` → `một chấm năm`, `0,05` → `không phẩy không năm`, số
  > 999 tỷ đọc từng chữ số; số điện thoại, mã giảm giá đọc từng ký tự; emoji, link bị bỏ (FR-008); từ tiếng Anh / thương hiệu giữ nguyên
  ("serum", "Vitamin C"); "Dạ." giữ nguyên; đầu ra chỉ còn chữ, khoảng trắng và `, . ? !`. `load_abbreviations`: file hợp lệ nạp đúng;
  khóa rỗng, khóa trùng khi bỏ hoa thường, giá trị có chữ số → `ValueError`. Chạy không cần nguồn giọng (FR-010).
- [x] T028 [P] [US2] `tests/unit/test_tts_factory.py`: với mọi nhà cung cấp, engine bên trong nhận chữ đã chuẩn hóa ("Giá chỉ 259.000đ"
  → "Giá chỉ hai trăm năm mươi chín ngàn đồng"); `TTS_ABBREVIATIONS_PATH` trỏ tới file thiếu hoặc sai → `TTSConfigError`.
- [x] T029 [P] [US2] `tests/integration/test_tts_subtitles.py` (mới): với `create_tts` thật (`fake`) và TTS giả ghi lại chữ nhận được,
  một câu trả lời comment (ShowDirector) và một phân đoạn kịch bản (ScriptRunner) có "259.000đ" → phụ đề gửi tới trang host vẫn là
  "259.000đ", còn engine nhận dạng chữ (US2 #5, FR-009).
- [x] T030 [P] [US2] `tests/unit/test_cli.py`: `python -m ai_live.tts normalize "<câu>"` in đúng chữ đã chuẩn hóa, không dựng nguồn giọng
  (không gọi `create_tts`), thoát 0.

### Implement US2

- [x] T031 [US2] `tts/normalize.py` (mới): `load_abbreviations(path)` và `normalize_for_speech(text, abbreviations)`, hàm thuần, 10 quy
  tắc theo thứ tự data-model §3. Không thêm thư viện (Điều VII). (T027 xanh)
- [x] T032 [US2] `tts/factory.py`: nạp bảng viết tắt từ `settings.tts_abbreviations_path` một lần, truyền
  `partial(normalize_for_speech, abbreviations=...)` vào `SpeechTTS` cho cả ba nhà cung cấp; lỗi nạp → `TTSConfigError`. (phụ thuộc T031;
  T028, T029 xanh; nếu T029 đỏ vì phụ đề lấy từ chữ đã chuẩn hóa thì sửa chỗ đó ở `director/`, không đổi hợp đồng)
- [x] T033 [US2] `tts/__main__.py`: lệnh con `normalize` (contracts/events.md §5), chỉ nạp `Settings` và bảng viết tắt. (T030 xanh)
- [x] T034 [US2] 📦 Chạy tay quickstart "US2" bước 2 và nghe 5 câu có giá / phần trăm / đơn vị bằng VieNeu (`say --out`). Câu nào nghe sai
  (kể cả `size M` → `sai em` và cách đọc chữ cái trong mã, hai `TODO: nghe thử` ở data-model §3) thì ghi vào nhật ký cuối file, sửa bảng
  test T027 trước rồi mới sửa `normalize.py`; bỏ hai `TODO` đó khi người dùng chốt.

**Checkpoint:** US1 + US2 chạy độc lập; giá đọc đúng; phụ đề giữ dạng gốc. Dừng lại, báo người dùng.

---

## Phase 5: User Story 3: Thử giọng riêng lẻ, đổi giọng bằng cấu hình và chịu lỗi (P3)

**Mục tiêu:** nguồn giọng thứ hai Gemini TTS (dự phòng), thử giọng bằng CLI và lưu file, đổi giọng chỉ bằng cấu hình, lỗi / hết hạn mức
không làm dừng phiên.
**Kiểm thử độc lập:** gõ câu thử và nghe; đổi cấu hình rồi mở lại phiên; giả lập lỗi ở bước tạo tiếng.

### Test cho US3 (viết trước, phải FAIL trước khi implement)

- [x] T035 [P] [US3] `tests/unit/test_gemini_tts.py`: `GeminiTTS` với client giả: request đúng `model`, `input` = chữ đã nhận,
  `response_format` (`audio/l16`, `sample_rate` 16000), `speech_config` có `voice`, `stream=True`; không gửi `session_id`,
  `utterance_id` hay metadata khác; sự kiện `delta.type == "audio"` → `base64` giải mã, ra đúng thứ tự, sự kiện khác bị bỏ qua; lỗi HTTP 429
  → `quota_exhausted` (thông báo ở contracts/events.md §2); lỗi HTTP khác → `api_error` "Gemini TTS lỗi HTTP <mã>: …"; `aclose()` giữa
  chừng đóng stream của client; `warm_up()` không gọi client; khóa API không xuất hiện trong log hay thông báo lỗi (FR-016).
- [x] T036 [P] [US3] `tests/contract/conftest.py`: thêm `GeminiTTSHarness` (client giả) vào `TTS_FACTORIES`.
- [x] T037 [P] [US3] `tests/unit/test_tts_factory.py`: `TTS_PROVIDER=gemini` → `SpeechTTS` bọc `GeminiTTS` với `gemini_tts_model`,
  `gemini_tts_voice`; thiếu `GEMINI_API_KEY` → `TTSConfigError` chỉ cách sửa; đổi `VIENEU_VOICE` / `GEMINI_TTS_VOICE` chỉ qua biến môi
  trường là engine nhận giọng mới (FR-011).
- [x] T038 [P] [US3] `tests/unit/test_cli.py`: `say` gọi `warm_up()` trước câu đầu; in nhà cung cấp, chữ đã chuẩn hóa và số ký tự đã gửi;
  `--out` ghi WAV PCM16 mono 16 kHz đọc lại được (FR-012); lỗi cấu hình → thoát 1 với thông báo tiếng Việt; lỗi `TTSEngineError` → in
  `kind` và thông báo, thoát khác 0.
- [x] T039 [P] [US3] `tests/integration/test_tts_app.py`: chịu lỗi bước tạo tiếng với engine giả bọc trong `SpeechTTS`: (a) ném
  `api_error` / `model_error` giữa câu → `errors.jsonl` có `error_step=tts` và đúng `kind`, trạng thái trang điều khiển có "Lỗi ở bước
  tts" kèm thông báo, comment kế tiếp vẫn được trả lời, lặp 10 lần đạt 10/10 (SC-004); (b) chậm quá `TTS_TIMEOUT_S` → `kind=timeout`;
  (c) `quota_exhausted` → thông báo "Hết hạn mức giọng nói", lượt tiếp theo trong thời gian nghỉ bị từ chối ngay (engine không được gọi),
  phiên không treo, sau giờ nghỉ lượt mới gọi engine lại (US3 #2, #3, FR-013); (d) như (a) nhưng trong một phân đoạn kịch bản của
  ShowDirector (004), show chạy tiếp phân đoạn sau; (e) "Bỏ qua" giữa câu → stream của engine được đóng (FR-014).

### Implement US3

- [x] T040 [US3] `tts/gemini_tts.py` (mới): `GeminiTTS` theo contracts/adapters.md §2, dùng `google-genai` đã có (ADR-018), không thêm
  dependency. (phụ thuộc T014; T035, T036 xanh)
- [x] T041 [US3] `tts/factory.py`: nhánh `gemini` dựng `genai.Client` từ `GEMINI_API_KEY`. (phụ thuộc T040; T037 xanh)
- [x] T042 [US3] `tts/__main__.py`: `say` gọi `warm_up()`, in thông tin như contracts/events.md §5, đọc `usage` của `SpeechTTS`; báo lỗi
  `TTSEngineError` theo `kind`. (phụ thuộc T033; T038 xanh)
- [x] T043 [US3] `director/show_director.py`: chỉ sửa nếu T039 đỏ. Đường lỗi hiện có (`_enqueue` đọc `kind`, thông báo "TTS lỗi: …")
  phải ra đúng `kind` và thông báo tiếng Việt của `TTSEngineError`; ghi nguyên nhân vào nhật ký cuối file. (T039 xanh)
- [x] T044 [US3] 🌐 🔑 `tests/integration/test_tts_live.py`: thêm ca `gemini` (marker `live_tts`): một câu ngắn ra PCM16 16 kHz không
  rỗng, ghi sample rate thật trả về vào research R2 (bỏ `TODO` nếu khớp 16 kHz). **Hỏi người dùng trước khi chạy** (tốn hạn mức):
  `uv run pytest -m live_tts tests/integration/test_tts_live.py -k gemini`.
- [x] T045 [US3] 📦 🌐 🔑 Chạy tay quickstart "US3" bước 1–4: `say --out out_vieneu.wav` và `out_gemini.wav` (file ngoài git, `*.wav` đã
  ignore), nghe; đổi `VIENEU_VOICE` / `GEMINI_TTS_VOICE` trong `.env`, nghe khác giọng, không sửa code (FR-011, FR-012); và quickstart
  "US1" bước 6 (lỗi giả lập ở bước `tts` khi nguồn giọng thật đang chạy).

**Checkpoint:** cả ba nhà cung cấp chạy được, đổi bằng cấu hình; lỗi bước tạo tiếng không làm dừng phiên. Dừng lại, báo người dùng.

---

## Phase 6: Hoàn thiện và việc chung

- [x] T046 [P] `docs/ARCHITECTURE.md`: sơ đồ §1 (`TTSEngine` VieNeu / Gemini thay "OSS / ElevenLabs") và §3 (`warm_up()`,
  `TTSEngineError`, PCM16 mono 16 kHz thay `TODO`, danh sách implementation) theo bảng contracts/adapters.md §5.
- [x] T047 [P] Quét chỗ sống còn ghi ElevenLabs / OSS là adapter TTS: `docs/VENDORS.md` (mục TTS: VieNeu, Gemini TTS đã dùng; ElevenLabs
  giữ làm ứng viên), `src/README.md:15`, `CLAUDE.md` dòng kiến trúc ("open-source model or ElevenLabs"), `docs/RUNPOD.md` (secret và hạn
  mức ElevenLabs → Gemini TTS). ADR và `docs/RISKS.md` L7 là lịch sử / ứng viên, không sửa.
- [x] T048 🌐 Người dùng mở AI Studio xem giới hạn RPM / RPD của `gemini-3.8-flash-tts` gói miễn phí; ghi vào research R2 và ADR-025, bỏ
  `TODO` tương ứng (quickstart §0 bước 3).
- [x] T049 📦 🌐 🔑 SC-002, SC-003, SC-006 khi chạy riêng (không có lip-sync): theo quickstart "SC-003 / SC-006" bước 1–3, mỗi nguồn ≥ 20
  lượt, ghi p95 `tts_first_chunk` từ `GET /api/latency` (≤ 1,0 s), điểm nghe 10 câu (≥ 8/10), `chars` từ `tts_usage.json`; đo
  `VIENEU_CPU_THREADS` (2 / 4 / 6) rồi chốt (research R1). Ghi bảng vào research, nối kết quả vào ADR-024, người dùng chốt nguồn mặc
  định và giọng chính thức; sửa giá trị mặc định ở **mọi** chỗ sống (`core/config.py`, `.env.example`, data-model §1, contracts/events.md
  §4, test cấu hình).
- [x] T050 [GPU] SC-006 khi có lip-sync: lặp đo T049 bước 2 với nhân vật nhép miệng của feature 005 chạy cùng lúc trên GPU laptop
  (ADR-023), chỉ ghi số (p95 `tts_first_chunk`, `tts_first_chunk_to_first_frame`) vào bảng của T049. Cần fork LiveTalking của 005 chạy
  được; chưa có thì để task mở và ghi lý do.
  - Kết quả 2026-11-12 (research "Kết quả SC-003 / SC-006"): 20/20 lượt, p95 câu đầu → chunk đầu 0,921 s, chunk đầu → khung đầu p95
    1,600 s; laptop chạy pin.
- [x] T051 📦 SC-005: phiên 30 phút với nguồn mặc định đã chốt, comment mỗi khoảng 30 giây (quickstart "SC-005"); phiên không dừng vì
  nguồn giọng; ghi `tts_usage.json` và số lỗi bước `tts` vào nhật ký cuối file.
- [x] T052 Chạy `quickstart.md` từ đầu đến cuối (các bước đã làm ở T026, T034, T045, T049, T051 chỉ cần đối chiếu), sửa quickstart nếu
  lệnh hoặc kết quả mong đợi khác thực tế.
- [x] T053 `uv run pytest` và `uv run ruff check . && uv run ruff format --check .` đều sạch.
- [x] T054 Chạy `/update-context`.

## Phụ thuộc và thứ tự

- Setup → Foundational → US1 → US2 → US3 → Hoàn thiện.
- T001 → T002 → T023 (cần API thật của VieNeu và sample rate đầu ra). T003 sau T001 (cùng `pyproject.toml`).
- T014 trước T015, T016, T023, T040. T011 + T016 → T017 → T024 → T032 → T041 (cùng `tts/factory.py`, làm tuần tự).
- T018 → T019. T033 → T042 (cùng `tts/__main__.py`).
- US2 có thể làm trước US1 về mặt mã (T027, T031 không cần VieNeu), nhưng nghe thử T034 cần US1.
- T049 cần US1 và US3 xong; T050 cần feature 005; T051 cần T049 (nguồn mặc định đã chốt).

## Chạy song song

- Setup: T004, T005 cùng lúc với T001.
- Foundational, test: T006, T007, T008, T009, T010. Implement: T012, T013 song song với T011; T015, T016, T018 song song sau T014.
- US1: T020, T021, T022. US2: T027, T028, T029, T030. US3: T035, T036, T037, T038, T039.
- Hoàn thiện: T046, T047.
- Theo agent (`/sdd.dispatch`): ai-media giữ `tts/`; ai-orchestrator giữ `core/`, `app/main.py`, `director/`; ai-qa giữ
  `tests/contract/`, `tests/integration/test_tts_app.py`, `tests/integration/test_tts_subtitles.py`.

## Đợt GPU

- T050: chạy trên GPU laptop (GTX 1650 Ti 4GB) cùng lip-sync của feature 005, theo ADR-023; không cần RunPod. Nếu laptop không chạy nổi
  thì hỏi người dùng về chi phí trước khi bật pod (`docs/RUNPOD.md`).

## Chiến lược MVP

1. Setup + Foundational → 2. US1 (VieNeu đọc câu trả lời) → **dừng, kiểm chứng, demo** → 3. US2 (chuyển chữ) → 4. US3 (Gemini, CLI,
   chịu lỗi) → 5. Hoàn thiện (so sánh nguồn giọng, phiên 30 phút).

## Bảng phủ FR / SC

| Yêu cầu | Task |
|---------|------|
| FR-001 | T020, T023, T025, T026 |
| FR-002 | T049 (chốt giọng có sẵn), T045 |
| FR-003 | T011, T023, T024, T040, T041, T049 |
| FR-004 | T020, T023, T026 |
| FR-005 | T014, T020, T035, T050 |
| FR-006 | T027, T031, T032 |
| FR-007 | T027, T031 |
| FR-008 | T027, T031 |
| FR-009 | T029, T032 |
| FR-010 | T027, T030, T033 |
| FR-011 | T017, T037, T045 |
| FR-012 | T038, T042, T045 |
| FR-013 | T008, T016, T039, T043 |
| FR-014 | T008, T020, T026, T039 |
| FR-015 | T008, T010, T018, T019, T026 |
| FR-016 | T035, T037 |
| SC-001 | T027 |
| SC-002 | T026, T034, T049 |
| SC-003 | T049 |
| SC-004 | T039 |
| SC-005 | T051 |
| SC-006 | T049, T050 |

Không còn FR hay SC nào chưa có task.

## Nhật ký lỗi gặp khi implement

- **2026-11-09, T026 phần máy tự kiểm** (app thật `TTS_PROVIDER=vieneu`, `AVATAR_MODE=static`, `REPLY_ENGINE=fake`, trang `/host`
  giả lập bằng script trong scratchpad: lên lịch phát như `host.js`, gửi ack đúng lúc tiếng bắt đầu / hết; chưa có tai người nghe):
  - Làm nóng 10,3–12,9 s; app mở được trong ~12–15 s.
  - **Lỗi với mặc định `TTS_TIMEOUT_S=5`:** câu "Kem chống nắng Mây Sáng SPF 50 có loại 50 ml giá 259.000đ, loại 100 ml giá
    439.000đ." (9,6 s tiếng) bị cắt ở 6,6 s, lượt báo `turn_error` bước `tts`, `timeout` ("TTS quá 5.0 s"), câu thứ ba không được
    đọc. Nguyên nhân: `ShowDirector._enqueue` áp `TTS_TIMEOUT_S` cho **cả câu** (research R9), VieNeu trên laptop tạo ~0,63 s cho mỗi
    giây tiếng (9,6 s tiếng trong ~6,1 s), nên mọi câu dài hơn ~8 s tiếng đều lỗi. US2 đọc số thành chữ sẽ làm câu dài thêm. Đây là
    trường hợp `TODO` của R9. **Đã sửa (ADR-049):** người dùng chọn tách thời gian chờ; `TTS_TIMEOUT_S` nay áp cho mỗi lần chờ chunk
    (spec 001 sửa trước, `ShowDirector` + `ScriptRunner`, 6 test mới). Chạy lại với `TTS_TIMEOUT_S=5`: câu 9,4–9,5 s tiếng đọc trọn,
    3/3 lượt đủ câu, 0 `turn_error`. `ShowDirector` cũ còn tính cả lúc chờ hàng đợi phát vào thời gian TTS; đã bỏ.
  - Với `TTS_TIMEOUT_S=15` (chỉ đổi biến môi trường): 3 lượt `completed`, 0 lỗi. Câu đầu phát lúc 0,35 s, trước khi câu dài tạo xong
    (6,97 s) (US1 #2). Khoảng lặng giữa các câu 0,05–0,06 s. `GET /api/latency` (3 lượt): `first_sentence_to_tts_first_chunk` trung vị
    0,297 s, `tts_first_chunk_to_first_frame` 0,062 s, `total` 0,36 s (chưa đủ 20 mẫu cho p95).
  - "Bỏ qua" giữa câu dài đang tạo: tiến trình app 2,53 lõi CPU trước khi bỏ qua → 0,73 trong 0,5 s đầu → 0,0 từ giây thứ 1 (FR-014 đạt).
  - `TTS_PROVIDER=fake` (kịch bản 3): 3 lượt `completed`, 1 `skipped`, như 001.
  - Người dùng nghe WAV và xác nhận 2026-11-09 → tick T026.
- **2026-11-09, US2 T027–T033:** test viết trước và đều đỏ đúng lý do (thiếu module `normalize`, engine nhận chữ gốc, không báo
  `TTSConfigError` khi file viết tắt hỏng, argparse không biết lệnh `normalize`, test phụ đề hết giờ chờ). Sau khi code: 138 test
  chuẩn hóa xanh ngay lần đầu; cả bộ 1785 passed, 13 deselected, 11 xfailed; ruff sạch. Lệnh bước 2 của quickstart US2 in đúng chữ mong
  đợi. Lệch so với tasks (đã báo người dùng):
  - T032 ghi "cho cả ba nhà cung cấp", nhưng `gemini` chưa có adapter (T041 làm). Chuẩn hóa đã nối cho `fake` và `vieneu`; `FakeTTS`
    nay cũng nhận chữ đã chuẩn hóa. T041 phải truyền `normalize=load_normalizer(settings)` như hai nhánh kia.
  - T029 dùng giá trong catalog (`250.000đ`) thay cho `259.000đ`, vì bộ lọc đầu ra chặn giá không có trong dữ liệu sản phẩm.
  - In thêm thông tin trong lệnh `say` thuộc T042 (US3), chưa làm.
  - T034: 5 WAV VieNeu đã tạo trong scratchpad của phiên (`t034/cau1.wav`…`cau5.wav`), người dùng nghe, xác nhận cả 5 câu đọc đúng 2026-11-09 → tick T034. Chunk đầu ~11 s vì CLI
    nạp model mà không làm nóng (T042 thêm làm nóng).
- **2026-11-09, US3 T035–T043:** test viết trước, đỏ đúng lý do (thiếu module `gemini_tts`, factory chưa có nhánh `gemini`, `say`
  chưa làm nóng / chưa in số ký tự / chưa báo `kind`, `turn_finished` chưa có `error_kind`, thông báo còn tiền tố "TTS lỗi: "). Lệch so
  với spec/contract (đã báo người dùng):
  - `turn_finished` (WebSocket) thêm `error_kind` và `error_message` (đã che khóa) khi `outcome=error`; trang điều khiển hiện
    "Lỗi ở bước TTS (<kind>): <thông báo>". Contract sự kiện của 001 và 003 §2 đã ghi thêm.
  - Thông báo của `TTSEngineError` dùng nguyên văn ở cả lượt comment lẫn `ScriptRunner` (bỏ tiền tố "TTS lỗi: " cũ của 001/004).
  - `SpeechTTS` gắn "Thử lại sau N giây." vào thông báo hết hạn mức ngay lần lỗi đầu (N = `TTS_QUOTA_COOLDOWN_S`) và dùng cùng đầu câu
    khi từ chối trong lúc nghỉ ("thử lại sau" viết thường cũ đổi thành "Thử lại sau" như contract §2).
  - SDK ném lỗi lớp `google.genai._interactions` (APIStatusError, APIConnectionError…), không phải `genai.errors.APIError` như
    contracts/adapters.md §2 ngầm định; adapter bắt cả hai.
  - Chưa gửi câu chỉ dẫn giọng (style instruction) cho Gemini: research R2 còn `TODO`, chờ T045 nghe thử.
  - `ScriptRunner` (004) giữ `status=spoken` cho câu lỗi **sau** chunk đầu (phần đã phát); lỗi vẫn vào `errors.jsonl` và `show_error`,
    câu sau vẫn đọc. Chỉ ghi nhận, không đổi hành vi 004; test T039 (d) viết theo hành vi này.
  - `SpeechTTS.normalize()` mới để lệnh `say` in đúng chữ gửi đi.
  - Sự cố khi chạy test: test `say` thiếu khóa ban đầu chỉ đặt `GEMINI_API_KEY=""`; `env_ignore_empty=True` làm `Settings` đọc khóa
    thật trong `.env`, gửi **một request thật** (Gemini trả HTTP 400 "Request contains an invalid argument", không có âm thanh). Đã
    sửa test (chạy trong `tmp_path`, xóa biến). Lỗi 400 này cần xem ở T044: có thể dạng request của contract §2 (`response_format`,
    `speech_config`) chưa khớp API thật.
- **2026-11-09, T044 (người dùng cho chạy):** 1 passed: `gemini-3.8-flash-tts`, giọng Leda, câu 39 ký tự, đoạn đầu 4,00 s, xong 6,47 s,
  2,88 s tiếng, 47 chunk, PCM16 16 kHz. Tốn 4 request thật trong lượt này (cộng 1 request lỡ gửi ở trên là 5), chỉ 2 lần có tiếng:
  - Lần 1 không gửi được: `RuntimeError: Cannot send a request, as the client has been closed`. Adapter chỉ giữ
    `client.aio.interactions`, `genai.Client` bị thu hồi thì đóng HTTP client. Sửa: giữ `self._client`; test
    `test_adapter_keeps_the_client_alive` (đỏ trước khi sửa).
  - Lần 2: HTTP 400 "Request contains an invalid argument". Một script thử ngoài repo (2 request) cho thấy API **không nhận**
    `"mime_type": "audio/l16", "sample_rate": 16000` (400 cả khi `input` đúng dạng của docs); bỏ hai trường đó thì API trả l16 24 kHz.
  - Lệch contract §2 / research R2, R5 (đã sửa spec trước code): `input` theo dạng có cấu trúc của docs
    (`[{"type": "user_input", "content": [{"type": "text", "text": ...}]}]`), `response_format={"type": "audio"}`, adapter hạ
    24 → 16 kHz. `delta.mime_type` khác `audio/l16` hoặc tần số không đổi được (vd. 44,1 kHz) → `config_error`.
  - Bộ lọc hạ tần số của VieNeu chuyển ra `tts/resample.py` (`Resampler(nguồn, đích)`, tỉ lệ hữu tỉ, tối đa tăng 4 lần) cho cả hai
    nguồn dùng chung; với 48 → 16 kHz hệ số lọc giữ nguyên như cũ. Test mới `test_resample.py` (14 ca) và 3 ca trong
    `test_gemini_tts.py` (24 kHz → 16 kHz, 44,1 kHz bị từ chối, `audio/mp3` bị từ chối), đỏ trước khi sửa.
  - Chưa làm: thông báo lỗi HTTP vẫn kèm nguyên thân SSE (`event: error data: {...}`) thay vì chỉ `error.message`; chỉ xấu, không lộ
    khóa (đã che).
  - Đoạn đầu 4 s (một lần đo) ghi vào research R2; có thể làm lặng giữa câu vượt 1,5 s, đo thêm ở SC-006.
- **2026-11-09, T045 (người dùng cho chạy, nghe 6 WAV: âm thanh rõ):**
  - US3 bước 1–4: `say --out` ra 4 file trong `out/t045/` (ngoài git): VieNeu giọng mặc định và một giọng khác, Gemini Leda và
    Aoede. Đổi giọng bằng biến môi trường của tiến trình (ghi đè `.env`, cùng đường `Settings`), không sửa `.env` lẫn code
    (FR-011, FR-012). Đoạn đầu: VieNeu ~0,33–0,40 s, Gemini ~3,5–4,1 s. Tốn 2 request Gemini (tổng hôm nay 7).
  - US1 bước 6 (`TTS_PROVIDER=vieneu` để không tốn hạn mức, `AVATAR_MODE=static`, `REPLY_ENGINE=fake`, trang host giả lập):
    `mode=error` → lượt `error`, `error_step=tts`, `error_kind=fault_injected`, "TTS lỗi: Lỗi giả lập ở bước tts"; `mode=timeout`
    → lượt `error` sau 5 s, `error_kind=timeout`, "TTS quá 5.0 s". Comment ngay sau mỗi lỗi đều `completed` với tiếng thật (5,1 s
    PCM 16 kHz, `out/t045/5_sau_loi_error.wav`, `6_sau_loi_timeout.wav`); phiên không dừng (SC-004).
  - Ghi nhận, chưa xem: khi nạp VieNeu, `huggingface_hub` in cảnh báo "unauthenticated requests to the HF Hub" dù model đã có trong
    cache; có thể vẫn gọi mạng lúc khởi động.
  - Câu chỉ dẫn giọng cho Gemini (R2 `TODO`): người dùng nghe thấy rõ, chưa yêu cầu; chưa thêm.
- **2026-11-09, T049:**
  - Đo 2 / 4 / 6 luồng với `Thục Đoan`, đều đạt SC-003; giữ 4 luồng (research R1, bảng kết quả).
  - Người dùng nghe q07: "nắng" thành "nứng". G2P đúng; nghe thử lại câu này với tham số lấy mẫu thấp hơn và 3 giọng khác
    (`out/t049/nang_test/`), người dùng chọn **`Thùy Dung`** làm giọng mặc định. Đã đổi mặc định ở `core/config.py`,
    `.env.example`, `.env` (dòng `VIENEU_VOICE`), data-model §1, contracts/events.md §4 và `tests/unit/test_config.py` (test đỏ
    trước rồi xanh). Test khác truyền `voice="Thục Đoan"` tường minh cho model giả, không phụ thuộc mặc định nên giữ nguyên.
  - Đo lại với `Thùy Dung`, 4 luồng: p95 0,405 s, 20/20 lượt, 0 lỗi; 10 WAV ở `out/t049/thuydung/` chờ chấm điểm nghe.
  - Người dùng chọn lần đọc `D_ThuyDung_lan2` làm đoạn mẫu cố định giọng; nghe `out/t049/ref_lan2/`: ổn. Sửa spec trước (FR-002,
    clarify 2026-11-09, data-model §1–2, contracts/adapters.md §2 và §4, contracts/events.md §4, research R1, quickstart §0), rồi
    test đỏ (`test_vieneu_tts.py` 6 test mới, 7 ca, `test_tts_factory.py`, `test_config.py`), rồi code: biến `VIENEU_REF_AUDIO` ở
    `core/config.py`, `VieneuTTS(ref_audio=...)`, `tts/factory.py`, `.env.example`. File mẫu chép ra
    `~/.cache/ai-live/voices/thuy_dung_lan2.wav`, `.env` trỏ tới. Đo 20 lượt qua app: p95 0,516 s, 0 lỗi (ADR-024).
  - Người dùng chốt nguồn mặc định `vieneu`, `gemini` dự phòng (spec FR-003, research bảng kết quả, ADR-024). **Lệch task:** Gemini
    không đo đủ 20 lượt và không chấm 10 câu; giữ hạn mức free tier vì số đo đơn lẻ (3,5–4,1 s) đã không đạt SC-003. Điểm nghe
    VieNeu: người dùng nghe 10 câu `out/t049/ref_lan2/`, xác nhận ổn (không chấm từng câu). `TTS_PROVIDER` trong code và
    `.env.example` giữ `fake` (test và quickstart §0 cần chạy không model); `.env` của máy này đặt `vieneu`.
  - T050 để mở: fork LiveTalking của 005 chưa chạy được trên laptop.
- **2026-11-09, T051 (SC-005):** phiên 29 phút 36 giây (1776 s), `vieneu` 4 luồng, giọng `Thùy Dung` + đoạn mẫu, không lip-sync
  (`AVATAR_MODE=static`). 60 comment, mỗi comment cách 30 s. Câu trả lời lấy từ 10 câu đã ghi của lần chấm `20261104-171739`
  (`REPLY_ENGINE=fake`, không gọi LLM) vì SC-005 chỉ xét nguồn giọng. Kết quả: 60/60 lượt `completed`, 0 lỗi, 0 bỏ qua; p95 câu đầu →
  chunk đầu 0,484 s (trung vị 0,344 s), p95 nhận comment → phát 0,547 s. `tts_usage`: 84 request, 6348 ký tự, 0 lỗi hạn mức.
  Warm-up 14,3 s. Phiên không dừng vì nguồn giọng → đạt.
- **2026-11-10, T052 (quickstart):** chạy lại các bước làm được trên laptop: §0 `uv run pytest` sạch; US2 `normalize` ra đúng câu
  mong đợi, bảng chuẩn hóa 140 passed; US3 `say` VieNeu (Thùy Dung + đoạn mẫu) chunk đầu 0,42 s, 88 ký tự, 4,40 s tiếng; test
  quota 2 passed; `*.wav` nằm trong `.gitignore`; `/api/debug/fault` và `tts_usage.json` có trong code. US1, Gemini `say`, SC-003/006,
  SC-005 chỉ đối chiếu với T026/T044/T045/T049/T051, không gọi Gemini thêm. Lỗi tìm ra (sửa theo lối tắt sửa lỗi, WORKFLOW §2):
  `say --out` vào thư mục chưa có báo nhầm "TTS lỗi" kèm traceback `Wave_write.__del__` sau khi đã tạo tiếng. Sửa trong
  `tts/__main__.py`: tạo thư mục cha trước warm-up (không tốn hạn mức nếu không ghi được), mở file riêng rồi mới `wave.open`, lỗi
  ghi file báo "Không ghi được file ..."; 2 test mới trong `test_cli.py` đỏ rồi xanh. Quickstart US3 thêm 2 dòng (thư mục tự tạo;
  đổi `VIENEU_VOICE` thì đổi luôn `VIENEU_REF_AUDIO`).
- **2026-11-10, T048:** người dùng gửi ảnh AI Studio (project `AIStreamming`, 28 ngày): `Gemini 3.8 Flash TTS` gói miễn phí 3 RPM,
  10K TPM, 10 RPD; dùng cao nhất 2 RPM, 58 TPM, 7 RPD. Ghi vào research R2, ADR-024 (task ghi ADR-025 là nhầm: giới hạn Gemini TTS
  nằm ở ADR-024), RISKS Q12, quickstart §0 bước 3; bỏ các `TODO` tương ứng. Hệ quả: Gemini chỉ cầm cự vài câu, không chạy hết phiên.
- **2026-11-10, T053:** `uv run pytest` 1859 passed, 14 deselected, 11 xfailed; `ruff check` sạch, `ruff format --check` 156 file đã đúng.
