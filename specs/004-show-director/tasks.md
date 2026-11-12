# Tasks: AI host tự nói kịch bản giới thiệu sản phẩm, sinh realtime

- **Feature ID:** `004-show-director` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[GPU]**: cần GPU; chạy trên GPU laptop trước (ADR-023), RunPod chỉ dự phòng và cần duyệt chi phí; gom vào đợt GPU (xem cuối file).
  Feature 004 **không có** task GPU (`AVATAR_MODE=static`, `TTS_PROVIDER=fake`; đo lại với 003/005 ghi ở quickstart **[Đo lại]**).
- **[US#]**: thuộc user story nào (US1, US2...). Phase Setup, Foundational và Hoàn thiện không gắn nhãn này.
- Mỗi task ghi **đường dẫn file cụ thể**. Một task chỉ đủ nhỏ để xong và kiểm chứng trong một lần làm.
- Thứ tự phase theo ưu tiên trong spec: US1 (P1) → US2, US3, US4 (P2) → US5, US6 (P3).
- Task cần gọi LLM thật ghi **(LLM thật, G#)** (trước 2026-11-03 ghi **(gemini, G#)**; từ ADR-035 dùng engine của 008) theo lịch giai đoạn ở research R14; chỉ chạy khi người dùng đồng ý, mặc định
  `REPLY_ENGINE=fake`.

## Phase 1: Setup

- [x] T001 Chuyển ADR-030, ADR-031, ADR-032 sang `Đã chốt` trong `docs/DECISIONS.md` (người dùng duyệt ngầm khi yêu cầu chạy tiếp
  `/sdd.tasks` ngày 2026-11-01) và bỏ ba dòng đó khỏi `progress/OPEN.md` §2
- [x] T002 [P] Thêm 9 biến `SCRIPT_SEGMENT_MIN_SENTENCES`, `SCRIPT_SEGMENT_MAX_SENTENCES`, `SCRIPT_PRIMARY_SHARE`, `SCRIPT_FALLBACK_AFTER`,
  `SCRIPT_LLM_TIMEOUT_S`, `SCRIPT_RETRY_TIMEOUT_S`, `SCRIPT_HISTORY_SENTENCES`, `SCRIPT_MAX_TOKENS`, `PLATFORM_PHRASES_PATH` với mặc định và
  chú thích vào `.env.example` (plan "Biến môi trường mới")
- [x] T003 [P] Thêm `data/eval/script_runs/` vào `.gitignore` (data-model §10; hiện chỉ có `data/eval/runs/`)
- [x] T004 [P] Tạo `data/rules/platform_phrases.txt`: mỗi dòng một cụm cơ chế nền tảng (giỏ hàng, thêm vào giỏ, mã giảm giá, voucher,
  ghim sản phẩm, bấm link, link bên dưới...), dòng đầu `# TODO:` nhắc người dùng xem lại danh sách (research R9, contracts/adapters.md §4)

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

### Test nền tảng (viết trước, phải FAIL)

- [x] T005 [P] Test model mới trong `tests/unit/test_show_models.py`: `Utterance` phải có đúng một trong `comment_id`/`segment_id`;
  `SegmentRequest` từ chối `min > max` hoặc `min < 1`; `Topic.label` tiếng Việt cho 9 chủ đề; `REQUIRED_SCRIPT_MILESTONES` đủ 4 mốc;
  `SpokenHistory.recent_for()` chỉ trả câu của đúng sản phẩm, tối đa `n`; câu `fallback` không vào `seen_word_forms` (data-model §1–§8)
- [x] T006 [P] Test cấu hình trong `tests/unit/test_config.py`: mặc định 9 biến mới khớp `.env.example`; `SCRIPT_SEGMENT_MAX_SENTENCES`
  < `SCRIPT_SEGMENT_MIN_SENTENCES` → lỗi; `SCRIPT_PRIMARY_SHARE` ngoài `0.5`–`0.9` → lỗi (phụ thuộc T002)
- [x] T007 [P] Test sự kiện trong `tests/unit/test_events.py`: có 6 loại `show_state`, `segment_started`, `segment_finished`,
  `segment_next`, `show_stats`, `show_error`; payload `show_error.message` đi qua `redact` (contracts/events.md §3)

### Implement nền tảng

- [x] T008 Sửa `src/ai_live/core/models.py`: thêm enum `ShowState`, `ShowMode`, `Topic` (có `label`), `SegmentOrigin`, `SegmentStatus`,
  `SentenceStatus`, `GapKind`; thêm `Milestone.SEGMENT_REQUESTED`, `REQUIRED_SCRIPT_MILESTONES`, `GuardReason.LINK/UNKNOWN_PERCENT/
  PLATFORM_PHRASE`, `DropReason.SHOW_ENDED` (nhãn "phiên đã kết thúc"); `Utterance.comment_id` thành optional, thêm `segment_id`, `show_id`
  và kiểm tra ở data-model §2; thêm `ShowSession`, `Segment`, `SegmentRequest`, `ScriptSentence`, `SpokenLine`, `SpokenHistory`,
  `SentenceGap`, `ShowSummary` (data-model §3–§9). Mọi chỗ tạo `Utterance` của 001 vẫn chạy (phụ thuộc T005)
- [x] T009 [P] Sửa `src/ai_live/core/config.py`: 9 biến `SCRIPT_*`/`PLATFORM_PHRASES_PATH` và validator min ≤ max, `0.5 ≤ primary_share
  ≤ 0.9` (phụ thuộc T006)
- [x] T010 [P] Sửa `src/ai_live/core/events.py`: thêm 6 loại sự kiện EventBus của contracts/events.md §3 (phụ thuộc T007)
- [x] T011 Sửa `src/ai_live/core/protocols.py`: thêm `ReplyEngine.narrate(request: SegmentRequest, catalog: ProductCatalog) ->
  AsyncIterator[str]` kèm docstring về `ReplyEngineError` và việc engine không tự cắt số câu (contracts/adapters.md §1, ADR-030)
  (phụ thuộc T008)
- [x] T012 [P] Sửa `docs/ARCHITECTURE.md` §3: thay dòng ghi chú `narrate(segment_hint, catalog)` bằng chữ ký `narrate(request:
  SegmentRequest, catalog)`; ghi guard có thêm `unknown_percent`, `link`, `platform_phrase` và `clean_spoken` chạy trước guard ở cả hai
  đường (ADR-030, ADR-031)
- [x] T013 Contract test `narrate()` trong `tests/contract/test_reply_engine_contract.py` cho `FakeReplyEngine` và `GeminiReplyEngine`
  (dùng `tests/fixtures/fake_genai.py`): mỗi giá trị yield là câu không rỗng; lỗi ném ra là `ReplyEngineError`; `catalog` không đổi sau
  khi gọi (contracts/adapters.md §1) (phụ thuộc T011)
- [x] T014 Sửa `src/ai_live/brain/fake_engine.py`: `narrate()` có kịch bản theo `(product_id, topic)`, mặc định
  `"Câu {n} về {topic} của {product_name}."` với `n` tăng mỗi lần gọi; tham số `delay_s`, `first_sentence_delay_s`, `fail_next(kind, count)`
  (contracts/adapters.md §1) (phụ thuộc T011, T013)
- [x] T015 Tách `_take_fault`/`_faulty_stream` của `ShowDirector` ra lớp `FaultInjector` trong `src/ai_live/director/faults.py`;
  `src/ai_live/director/show_director.py` dùng lớp này, hành vi 001 không đổi (`tests/integration/test_show_director.py` của 001 vẫn xanh)
  (contracts/adapters.md §6)

**Checkpoint:** nền tảng sẵn sàng; `uv run pytest` xanh (test 001 không đổi), các story bắt đầu được.

---

## Phase 3: User Story 1: Bấm "Bắt đầu show", host tự nói liên tục về sản phẩm (P1) 🎯 MVP

**Mục tiêu:** một phiên kịch bản tự chạy: chào mở màn rồi xoay vòng phân đoạn sản phẩm × chủ đề, mỗi câu sinh realtime, qua làm sạch và
guard, phát thành tiếng kèm phụ đề.
**Kiểm thử độc lập:** nạp file mẫu, bấm "Bắt đầu show", để chạy 5 phút không chạm vào gì (quickstart US1).

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [x] T016 [P] [US1] Test `tests/unit/test_sanitize.py`: bỏ đầu dòng `-`, `*`, `•`, `–`, `1.`, `1)`; `#` tiêu đề; `**…**`, `__…__`,
  `` `…` ``; emoji nhóm `So`, `U+FE0F`, `U+200D`; giữ dấu tiếng Việt, `1.250.000`, `%`, dấu câu; `clean_spoken` idempotent
  (contracts/adapters.md §3, FR-009)
- [x] T017 [P] [US1] Test guard mở rộng trong `tests/unit/test_guard.py`: thứ tự `forbidden_claim` → `unknown_amount` → `unknown_percent` →
  `link` → `platform_phrase`; "giảm 30%" và "30 phần trăm" bị chặn khi file không có 30 (FR-011); câu có link bị chặn (FR-012); "bấm vào
  giỏ hàng" bị chặn khi catalog không có cụm đó, được phép khi promotions có (FR-013); khẳng định bị cấm bị chặn (US1 #5); nạp
  `platform_phrases.txt` bỏ dòng trống và dòng `#`; file thiếu → lỗi cấu hình; `OutputGuard()` không tham số vẫn chặn 4 loại kia nhưng
  không kiểm `platform_phrase` (contracts/adapters.md §4, analyze A4)
- [x] T018 [P] [US1] Test `tests/unit/test_script_prompt.py`: system prompt dùng `render_catalog()` và có giá từng phân loại (US1 #3);
  luật xưng "em", gọi "anh chị", từ ngữ miền Nam, câu ≤ 25 từ, không ký hiệu (FR-009); chỉ dùng dữ liệu trong file (FR-010); `faq` chỉ dùng
  cặp hỏi–đáp có trong file (FR-014); `call_to_action` không nhắc cơ chế nền tảng (FR-013); segment message có `topic_brief`, min/max câu,
  `previous_sentence`, `recent_lines` (bọc chống injection như 001); không chứa `GEMINI_API_KEY`, đường dẫn file, `session_id` (FR-027)
- [x] T019 [P] [US1] Test `tests/unit/test_segment_planner.py` (phần xoay vòng): `available_topics()` theo điều kiện dữ liệu R5 (không có
  giá → không có `price`, US1 #4; không có khuyến mãi → không có `promotion`, FR-004); 1000 lần `next_slot()` không có hai slot liền nhau trùng
  cả `(product_id, topic)` (US1 #2); tỷ lệ sản phẩm chính ≥ `primary_share`; mỗi sản phẩm phụ có mặt trong mỗi chu kỳ (FR-005); file chỉ có
  sản phẩm chính → chỉ xoay chủ đề của nó; catalog đúng một tổ hợp → cho trùng; `peek_slot()` không tiêu ô; `replace_catalog()` giữ con trỏ
  sản phẩm còn lại và bỏ sản phẩm bị xóa (contracts/adapters.md §5)
- [x] T020 [P] [US1] Test `tests/unit/test_show_stats.py`: gap theo từng `GapKind`; `counted` = `script` + `segment_boundary` + `error`;
  p95 `null` khi < 20 mẫu và dùng hàm của `director/latency.py`; `show_first_sentence_s`; `primary_share`; `secondary_coverage` theo cửa sổ
  10 phút; `duplicates.before_filter_rate`, `spoken_rate`, `identical_segments`; câu `fallback` không tính vào `spoken_rate`
  (data-model §9, contracts/adapters.md §8)
- [x] T021 [P] [US1] Test `narrate()` của Gemini trong `tests/unit/test_gemini_engine.py` (dùng `fake_genai`): `system_instruction =
  build_script_system_prompt(catalog)`, `contents = build_segment_message(...)`, `max_output_tokens = SCRIPT_MAX_TOKENS`; log `llm_usage`
  có `segment_id`; 429 → `ReplyEngineError(kind="rate_limited")` (contracts/adapters.md §1)
- [x] T022 [P] [US1] Test lệnh `python -m ai_live.brain narrate --product ID --topic T` với `REPLY_ENGINE=fake` trong `tests/unit/test_cli.py`:
  in từng câu, mã thoát 0; tổ hợp không có dữ liệu → mã thoát khác 0 kèm thông báo tiếng Việt (Điều IV)
- [x] T023 [US1] Test `tests/integration/test_script_runner.py` (phần chạy thường), dùng `FakeReplyEngine` + `FakeTTS` + host giả: phân đoạn
  đầu là `opening` (FR-002); mỗi câu là một `Utterance` có `segment_id`, `show_id` và một `sentence_start` `seq = 0` (FR-008); đủ 4 mốc
  `REQUIRED_SCRIPT_MILESTONES` (FR-022); `sentence_gap` có `kind` `script`/`segment_boundary`; phân đoạn N+1 `ready` trước khi N nói xong
  (FR-007); câu bị guard chặn thì bỏ, phân đoạn bị chặn hết → `blocked` và sang phân đoạn kế; ký hiệu bị làm sạch, câu còn < 4 ký tự chữ →
  `dropped` `empty_after_clean`; câu vượt `max_sentences` → `sentence_count_exceeded`; đổi catalog giữa chừng → phân đoạn đã chuẩn bị bị
  `discarded`, sản phẩm bị xóa không còn được nói (trường hợp biên); ghi `segments.jsonl`, `script_sentences.jsonl` (contracts/events.md §2)
- [x] T024 [US1] Test `tests/integration/test_show_api.py` (phần bắt đầu): `POST /api/show/start` → 200 có `show_id`; gọi lần hai →
  `already_running: true`, vẫn một luồng nói; host chưa `ready` → `409 host_unavailable`; chưa nạp nội dung → `409 no_content` (thông báo
  tiếng Việt của contracts/api.md §2); `GET /api/show` trả `ShowSnapshot`; `GET /api/state` có `show`; `POST /api/debug/speak` khi show chạy
  → `409 busy`; file phiên và log không chứa giá trị `GEMINI_API_KEY` giả đặt trong env (FR-027); guard của app đã nạp cụm từ: câu kịch bản
  "bấm vào giỏ hàng" từ engine giả bị chặn `platform_phrase` (analyze A4)

### Implement US1

- [x] T025 [P] [US1] Tạo `src/ai_live/brain/sanitize.py` với `clean_spoken()` (contracts/adapters.md §3) (phụ thuộc T016)
- [x] T026 [P] [US1] Sửa `src/ai_live/brain/guard.py`: `OutputGuard(platform_phrases=())` (tham số không bắt buộc), hàm nạp file `platform_phrases.txt`, ba kiểm tra
  `unknown_percent`, `link`, `platform_phrase` theo thứ tự ở contracts/adapters.md §4; chỗ tạo guard trong `brain/__main__.py` và
  `qa_eval/runner.py` phải truyền cụm từ nạp từ `PLATFORM_PHRASES_PATH` (analyze A4) (phụ thuộc T004, T017)
- [x] T027 [P] [US1] Tạo `src/ai_live/brain/script_prompt.py`: `SCRIPT_RULES` (tiếng Việt, research R4), `build_script_system_prompt()`,
  `build_segment_message()`, `topic_brief()` (contracts/adapters.md §2) (phụ thuộc T018)
- [x] T028 [US1] Sửa `src/ai_live/brain/gemini_engine.py`: `narrate()` theo contracts/adapters.md §1 (phụ thuộc T021, T027)
- [x] T029 [US1] Sửa `src/ai_live/brain/__main__.py`: lệnh con `narrate --product ID --topic T` (phụ thuộc T022, T028)
- [x] T030 [P] [US1] Tạo `src/ai_live/director/segment_planner.py`: `SegmentPlanner` với `available_topics`, `availability`, `next_slot`,
  `peek_slot`, `replace_catalog`, `PlannedSlot` (research R5, R6; `choose`/`take_override` làm ở US5) (phụ thuộc T019)
- [x] T031 [P] [US1] Tạo `src/ai_live/director/show_stats.py`: `ShowStats` thuần, không I/O (contracts/adapters.md §8) (phụ thuộc T020)
- [x] T032 [US1] Sửa `src/ai_live/director/session_log.py`: ghi `segments.jsonl`, `script_sentences.jsonl` (`marks` tương đối so với
  `segment_requested`), `show_summary_<show_id>.json`; thêm `show_id` vào `utterances.jsonl`/`comments.jsonl` và `segment_id` vào
  `errors.jsonl`; mọi dòng qua `redact`, ghi ở worker thread (contracts/events.md §2, FR-023, FR-027)
- [x] T033 [US1] Tạo `src/ai_live/director/script_runner.py`: `ScriptRunner` ba tầng `_write`/`_voice`/`_play` (research R7): mở màn, xoay
  vòng theo planner, làm sạch → guard → hàng chữ, tầng tiếng ≤ `SENTENCE_QUEUE_MAX`, giữ `_floor` từng câu, kiểm `catalog_version` trước câu
  đầu của phân đoạn, `on_catalog_replaced()`, ghi mốc, `sentence_gap`, sự kiện `segment_started`/`segment_finished`/`segment_next`/
  `show_stats`, `snapshot()`, hủy sạch task con và ghi bảng tổng hợp trong `finally` (phụ thuộc T014, T025, T026, T028, T030, T031, T032, T023)
- [x] T034 [US1] Sửa `src/ai_live/director/show_director.py`: `start_show()` (ném `HostUnavailable`, `NoContent`; trả `already_running`),
  `show_snapshot()`, khóa `_floor`, dựng `ScriptRunner` với `FaultInjector`, gọi `clean_spoken()` trước guard ở đường comment (ADR-031),
  `debug/speak` báo bận khi có show; không phát `turn_started`/`turn_finished` cho câu kịch bản; thay `self._guard = OutputGuard()` bằng
  tham số `guard: OutputGuard | None = None` dùng chung cho đường comment và `ScriptRunner` (analyze A4) (phụ thuộc T033)
- [x] T035 [US1] Sửa `src/ai_live/app/context.py` và `src/ai_live/app/errors.py`: nạp `platform_phrases.txt` khi khởi động (thiếu file →
  app không khởi động) và truyền `OutputGuard(phrases)` vào `ShowDirector` ở `app/main.py` (analyze A4), lỗi `host_unavailable`, `no_content` với thông báo tiếng Việt (phụ thuộc T026, T034)
- [x] T036 [US1] Sửa `src/ai_live/app/routes.py`: `POST /api/show/start`, `GET /api/show`, `GET /api/state` có `show`, `POST /api/debug/speak`
  → `409 busy` khi show chạy; log `control_command` `show_start` (contracts/api.md §2–§3) (phụ thuộc T024, T035)
- [x] T037 [US1] Sửa `src/ai_live/app/static/control.html` và `control.js`: khu "Show" có nút **Bắt đầu show**, trạng thái, chế độ, phân đoạn
  đang nói (sản phẩm, chủ đề, câu đang nói), phân đoạn kế, 10 câu bị chặn gần nhất kèm lý do, 10 lỗi gần nhất, gap p95/max theo `show_stats`
  (FR-019, contracts/api.md §1) (phụ thuộc T036)
- [x] T038 [P] [US1] Tạo `tests/live/test_gemini_narrate.py` (marker `live_llm`, không chạy mặc định): gọi `narrate()` thật cho `opening` và
  một phân đoạn `price`, mọi câu qua `clean_spoken` + guard đạt (phụ thuộc T028)
- [x] T039 [US1] Chạy quickstart US1 bước 1–6 với `REPLY_ENGINE=fake`, ghi kết quả vào "Kết quả kiểm chứng" của
  `specs/004-show-director/quickstart.md` (phụ thuộc T037)

**Checkpoint:** US1 chạy và test độc lập được. Dừng lại, báo người dùng, demo. Bước gemini của US1 (bước 4, T038) chạy ở G1 khi người
dùng đồng ý.

---

## Phase 4: User Story 2: Tạm dừng, tiếp tục, bỏ qua, kết thúc (P2)

**Mục tiêu:** người vận hành điều khiển được phiên: dừng ở cuối câu, tiếp tục đúng chỗ, bỏ phân đoạn trong ≤ 1 s, kết thúc có lời chào.
**Kiểm thử độc lập:** bấm mỗi nút ≥ 10 lần khi phiên đang chạy, đo thời gian tới lúc thấy hiệu lực (quickstart US2).

### Test cho US2 (viết trước, phải FAIL trước khi implement)

- [x] T040 [US2] Test điều khiển trong `tests/integration/test_script_runner.py`: `pause()` → nói hết câu đang nói, không có `sentence_start`
  mới, `renderer.interrupt()` không được gọi (US2 #1, FR-015); tiếng đã tạo bị bỏ (`paused_discard`), chữ giữ lại; `resume()` → câu kế của
  phân đoạn đang dở phát trong ≤ 3 s với `FakeTTS` (US2 #2); phân đoạn đang sinh dở lúc pause không mất (trường hợp biên); `skip()` →
  `interrupt()` được gọi, phần còn lại bị bỏ, phân đoạn `skipped`, phân đoạn kế nói luôn (US2 #3, FR-016); `close()` → phân đoạn `closing`
  ≤ 2 câu rồi dừng (US2 #4, FR-017); LLM lỗi lúc chào kết → nói `CLOSING_FALLBACK_SENTENCE` qua guard; `skip()` lúc `closing` → dừng ngay
- [x] T041 [US2] Test `tests/integration/test_show_api.py` (phần điều khiển): `POST /api/pause`, `/api/resume`, `/api/skip` khi có show trả
  `show_state` và `skipped_segment_id`; `POST /api/show/end` idempotent ở `idle`/`ended`; `end` lúc `paused` vẫn nói chào kết; sau `ended` không
  tự chạy lại, `start` tạo `show_id` mới; có `show_summary_<show_id>.json`; log `control_command` `show_end`; `control_applied` (skip) có
  `latency_ms` (SC-007)

### Implement US2

- [x] T042 [US2] Sửa `src/ai_live/director/script_runner.py`: `pause()`, `resume()`, `skip()`, `close()` và `CLOSING_FALLBACK_SENTENCE`
  (research R7, R13) (phụ thuộc T040)
- [x] T043 [US2] Sửa `src/ai_live/director/show_director.py`: `end_show()`, chuyển trạng thái `running`/`paused`/`closing`/`ended` theo
  data-model §3; `pause()`/`resume()`/`skip()` của 001 áp dụng cho show, `skip()` ưu tiên lượt comment đang nói (phụ thuộc T042)
- [x] T044 [US2] Sửa `src/ai_live/app/routes.py`: `POST /api/show/end`; body trả về của pause/resume/skip có `show_state`,
  `skipped_segment_id` (contracts/api.md §2–§3) (phụ thuộc T041, T043)
- [x] T045 [US2] Sửa `src/ai_live/app/static/control.html` và `control.js`: nút **Kết thúc**, nhãn trạng thái tiếng Việt (chưa chạy / đang chạy /
  tạm dừng / đang chào kết / đã kết thúc) (FR-019) (phụ thuộc T044)
- [x] T046 [US2] Chạy quickstart US2 bước 1–5 (≥ 10 lần mỗi nút, `REPLY_ENGINE=fake`), ghi SC-007 vào "Kết quả kiểm chứng" của
  `specs/004-show-director/quickstart.md` (phụ thuộc T045)

**Checkpoint:** US1 + US2 chạy độc lập được. Dừng lại, báo người dùng.

---

## Phase 5: User Story 3: Chạy 30 phút không lặp nguyên văn, không đứng khi có lỗi (P2)

**Mục tiêu:** phiên dài vẫn xoay vòng đều, không lặp nguyên văn, chịu được lỗi LLM/TTS và có chế độ dự phòng.
**Kiểm thử độc lập:** chạy 30 phút, giả lập ≥ 3 lỗi mỗi bước, đọc file lịch sử và nhật ký lỗi (quickstart US3).

### Test cho US3 (viết trước, phải FAIL trước khi implement)

- [x] T047 [US3] Test độ bền trong `tests/integration/test_script_runner.py`: `narrate()` lỗi hoặc quá `SCRIPT_LLM_TIMEOUT_S` → phân đoạn
  `failed`, lỗi vào `errors.jsonl` kèm bước và có `show_error`, show vẫn chạy (US3 #3, FR-020); TTS lỗi một câu → câu `tts_error`, câu kế vẫn
  nói (US3 #4); TTS quá `TTS_TIMEOUT_S` ở một câu → câu `tts_error`, câu kế vẫn nói (US3 #4, R7); host không gửi ack `playback_started`
  trong `RENDERER_ACK_TIMEOUT_S` → câu `render_error`, câu kế vẫn nói, show vẫn `running` (analyze A3); `SCRIPT_FALLBACK_AFTER` phân đoạn lỗi liên tiếp → `mode = fallback`, đọc nguyên văn câu của `intro`/`description` qua guard,
  log `mode_changed` (FR-021); thử lại trước mỗi phân đoạn dự phòng với `SCRIPT_RETRY_TIMEOUT_S`, thành công → về `normal`; phân đoạn
  `blocked` không tính là lỗi dịch vụ; gap có `kind` `fault`/`error` đúng loại (R12); host ngắt kết nối → câu `render_error`, show vẫn
  `running`; `run()` bị hủy → ghi bảng tổng hợp với `ended_by: "shutdown"`
- [x] T048 [US3] Test chống lặp và phiên dài trong `tests/integration/test_script_runner.py`: câu trùng `word_form` với câu đã nói →
  `dropped` `duplicate` (R11, FR-006); chạy ≥ 200 phân đoạn với `FakeReplyEngine` không độ trễ → `primary_share` ≥ 0,5, mọi cửa sổ
  `secondary_coverage` rỗng (SC-004), `spoken_rate` ≤ 0,05 và `identical_segments` = 0 (SC-005, US3 #1–#2)
- [x] T049 [US3] Test `tests/integration/test_show_api.py` (phần lỗi và nội dung): `POST /api/debug/fault` `step: "llm"` làm lỗi lần gọi
  `narrate()` kế tiếp (FR-024); `PUT /api/content` lúc show chạy → phân đoạn đang nói được nói hết, phân đoạn kế dùng nội dung mới; file mới
  lỗi → giữ nội dung cũ và báo lỗi như 001; snapshot có `mode`

### Implement US3

- [x] T050 [US3] Sửa `src/ai_live/director/script_runner.py`: timeout cả phân đoạn, bỏ phân đoạn khi LLM lỗi, bỏ câu khi TTS lỗi, đếm
  `consecutive_llm_failures`, chế độ dự phòng và thử lại (research R10), lớp chống lặp 2 bằng `SpokenHistory` (R11), nhãn gap `fault`/`error`
  (phụ thuộc T047, T048)
- [x] T051 [US3] Sửa `src/ai_live/director/show_director.py` và `src/ai_live/director/faults.py`: lỗi bước `llm` áp dụng cho cả `reply()` và
  `narrate()`; `PUT /api/content` gọi `on_catalog_replaced()` của runner (phụ thuộc T050)
- [x] T052 [US3] Sửa `src/ai_live/app/routes.py` để `PUT /api/content` chuyển nội dung mới cho show đang chạy (contracts/api.md §3)
  (phụ thuộc T049, T051)
- [x] T053 [US3] Sửa `src/ai_live/app/static/control.html` và `control.js`: dải cảnh báo "Đang ở chế độ dự phòng" khi `mode = fallback`,
  danh sách lỗi gần đây cập nhật theo `show_error` (FR-019, FR-021) (phụ thuộc T052)

**Checkpoint:** US1–US3 chạy được với `REPLY_ENGINE=fake`. Phiên 30 phút với LLM thật (quickstart US3, engine 008) để tới G5 ở Phase 9. Dừng lại, báo
người dùng.

---

## Phase 6: User Story 4: Tự kiểm tra kịch bản không bịa trước khi lên phiên (P2)

**Mục tiêu:** một lệnh sinh phân đoạn mẫu cho mọi tổ hợp có dữ liệu, chấm tự động, lưu và so với lần trước; thêm lệnh chấm lại lịch sử phiên
cho SC-003.
**Kiểm thử độc lập:** chạy lệnh với file mẫu hai lần, xem báo cáo và phần so sánh (quickstart US4).

### Test cho US4 (viết trước, phải FAIL trước khi implement)

- [x] T054 [P] [US4] Test `tests/unit/test_script_grader.py`: chấm trên chữ thô từng loại `unknown_amount`, `unknown_percent`,
  `forbidden_claim`, `link`, `platform_phrase` (qua `OutputGuard`), `bad_pronoun` ("tôi", "bạn", "quý khách", "các bạn"; "bên mình" không
  vi phạm), `formatting` (`clean_spoken(x) != normalize_text(x)`); số câu ngoài min–max chỉ là cảnh báo (US4 #2, FR-025, research R15)
- [x] T055 [P] [US4] Test `tests/unit/test_script_eval.py` với `FakeReplyEngine`: mọi tổ hợp sản phẩm × chủ đề có dữ liệu cùng `opening`,
  `closing` đều có phân đoạn (US4 #1); file kết quả theo data-model §10; lần hai có `previous` và `delta` (US4 #3, FR-026); lỗi 429/timeout
  ghi `error`, không tính vi phạm; `--session DIR` chấm lại mọi câu `spoken` trong `script_sentences.jsonl` (SC-003)
- [x] T056 [US4] Test CLI trong `tests/unit/test_cli.py`: `python -m ai_live.qa_eval script --content PATH` với `REPLY_ENGINE=fake` → mã thoát
  0, có file trong `data/eval/script_runs/` (dùng thư mục tạm); có vi phạm → mã thoát khác 0; `script --session DIR` chạy được

### Implement US4

- [x] T057 [P] [US4] Tạo `src/ai_live/qa_eval/script_grader.py` (phụ thuộc T054)
- [x] T058 [US4] Tạo `src/ai_live/qa_eval/script_eval.py`: chạy mọi tổ hợp qua `create_reply_engine(settings).narrate()`, nghỉ `GEMINI_PACE_S`
  giữa hai lần gọi Gemini, `--per-combo N` (mặc định 1), lưu `ScriptEvalRun`, so với lần trước cùng `content_source`; chế độ `--session DIR`
  (phụ thuộc T055, T057)
- [x] T059 [US4] Sửa `src/ai_live/qa_eval/__main__.py`: lệnh con `script [--content PATH] [--per-combo N] [--session DIR]`, mã thoát khác 0
  khi có vi phạm (phụ thuộc T056, T058)
- [x] T060 [US4] Đối chiếu lệnh SC-003 ở quickstart US3 bước 3 (`specs/004-show-director/quickstart.md`) với CLI đã làm ở T059, sửa
  quickstart nếu tên tham số khác (phụ thuộc T059)

**Checkpoint:** lệnh tự kiểm tra chạy được với `REPLY_ENGINE=fake`. Các lần chạy LLM thật (G2, G3, engine 008) ở Phase 9. Dừng lại, báo người dùng.

---

## Phase 7: User Story 5: Người vận hành chọn sản phẩm hoặc chủ đề cho phân đoạn kế tiếp (P3)

**Mục tiêu:** chọn sản phẩm và/hoặc chủ đề có dữ liệu cho phân đoạn kế, không cắt phân đoạn đang nói, rồi xoay vòng tiếp như cũ.
**Kiểm thử độc lập:** đang chạy, chọn sản phẩm phụ + "khuyến mãi", xem phân đoạn kế (quickstart US5).

### Test cho US5 (viết trước, phải FAIL trước khi implement)

- [x] T061 [P] [US5] Test `tests/unit/test_segment_planner.py` (phần chọn tay): chỉ chọn sản phẩm → chủ đề kế theo con trỏ của sản phẩm đó;
  chỉ chọn chủ đề → sản phẩm đầu tiên có chủ đề đó, sản phẩm chính trước; tổ hợp không có dữ liệu → `TopicUnavailable` (US5 #2);
  `take_override()` trả slot một lần; phân đoạn chọn tay không tiêu ô xoay vòng (FR-018, research R6)
- [x] T062 [US5] Test chọn tay trong `tests/integration/test_script_runner.py`: chọn khi N+1 đã sinh sẵn → N+1 `discarded`, phân đoạn ngay sau
  N là slot đã chọn với `origin = operator`; phân đoạn N không bị cắt (US5 #1)
- [x] T063 [US5] Test `tests/integration/test_show_api.py` (phần chọn tay): `POST /api/show/next` → 200 `origin: operator`; show chưa chạy →
  `409 show_not_running`; tổ hợp không có dữ liệu → `422 topic_unavailable`; body rỗng → `422 validation_error`; `GET /api/show` có
  `available_topics` chỉ gồm chủ đề có dữ liệu; log `control_command` `show_next`

### Implement US5

- [x] T064 [P] [US5] Sửa `src/ai_live/director/segment_planner.py`: `choose()`, `take_override()`, `TopicUnavailable` (phụ thuộc T061)
- [x] T065 [US5] Sửa `src/ai_live/director/script_runner.py`: nhận override, bỏ phân đoạn kế đã sinh, sinh lại theo slot đã chọn, phát
  `segment_next` (phụ thuộc T062, T064)
- [x] T066 [US5] Sửa `src/ai_live/director/show_director.py`: `choose_next()` ném `ShowNotRunning`, `TopicUnavailable` (phụ thuộc T065)
- [x] T067 [US5] Sửa `src/ai_live/app/routes.py` và `src/ai_live/app/errors.py`: `POST /api/show/next` và hai lỗi mới với thông báo tiếng
  Việt (contracts/api.md §2) (phụ thuộc T063, T066)
- [x] T068 [US5] Sửa `src/ai_live/app/static/control.html` và `control.js`: bộ chọn "phân đoạn kế tiếp", danh sách chủ đề lọc theo
  `available_topics` của sản phẩm đã chọn (FR-018, US5 #2) (phụ thuộc T067)

**Checkpoint:** US5 chạy được. Dừng lại, báo người dùng.

---

## Phase 8: User Story 6: Comment mock chen vào kịch bản đang chạy (P3)

**Mục tiêu:** comment mock hợp lệ làm kịch bản dừng ở cuối câu, host trả lời theo đường 001 rồi quay lại kịch bản.
**Kiểm thử độc lập:** gửi 10 comment mock ở các thời điểm khác nhau khi phiên đang chạy (quickstart US6).

### Test cho US6 (viết trước, phải FAIL trước khi implement)

- [x] T069 [US6] Test `tests/integration/test_show_director.py` (phần chen comment): comment hợp lệ → câu kịch bản đang nói được nói hết,
  không câu kịch bản nào `interrupted`, LLM của lượt trả lời bắt đầu ngay còn tầng phát chờ `_floor` (US6 #1, FR-028); trả lời xong và hàng đợi
  trống → câu kế của phân đoạn bị ngắt (US6 #2, FR-029); nhiều comment liền → trả lời hết theo thứ tự ưu tiên của 001 rồi mới quay lại; comment
  bị lọc → kịch bản không bị ngắt, có lý do loại (US6 #3); comment lúc `paused` được trả lời sau `resume` nếu chưa quá hạn; comment lúc
  `closing`/`ended` → `dropped` `show_ended` (FR-030); `skip()` khi đang trả lời → comment kế hoặc về kịch bản; tiếng kịch bản đã tạo được giữ
  qua lượt trả lời; gap `kind = comment`; lời trả lời vào `SpokenHistory` với `source = "reply"` và `comment_text` (FR-030), không tính vào xoay
  vòng; lượt trả lời có đủ mốc `comment_received` → `avatar_first_frame` (US6 #4) và `show_id` trong `utterances.jsonl`/`comments.jsonl`;
  câu trả lời comment có markdown/emoji (engine giả) được `clean_spoken()` làm sạch trước guard và chữ đọc/ghi log là chữ đã làm sạch (ADR-031,
  analyze A2)

### Implement US6

- [x] T070 [US6] Sửa `src/ai_live/director/show_director.py`: `InterleaveGate` (`pending()`, `wait_clear()`), tầng phát của lượt comment giữ
  `_floor` cả lượt, `run()` ghi `dropped` `show_ended` khi `closing`/`ended`, thêm lời trả lời vào `SpokenHistory` (research R8,
  contracts/adapters.md §7) (phụ thuộc T069)
- [x] T071 [US6] Sửa `src/ai_live/director/script_runner.py`: sau mỗi câu kiểm `InterleaveGate.pending()`, nhả `_floor` và chờ
  `wait_clear()`, giữ tiếng đã tạo; ghi gap `comment` (phụ thuộc T070)

**Checkpoint:** US6 chạy được với `REPLY_ENGINE=fake`. Đo SC-011 với LLM thật (engine 008) ở G5. Dừng lại, báo người dùng.

---

## Phase 9: Hoàn thiện và việc chung

- [x] T072 [P] Cập nhật `src/README.md`: module mới `director/segment_planner.py`, `script_runner.py`, `show_stats.py`, `faults.py`,
  `brain/script_prompt.py`, `brain/sanitize.py`, `qa_eval/script_grader.py`, `script_eval.py`
- [x] T073 [P] Cập nhật `docs/ARCHITECTURE.md` §2/§4: luồng kịch bản `ShowDirector` → `ScriptRunner` và cách đo khoảng lặng (R12)
- [x] T074 `uv run pytest` và `uv run ruff check . && uv run ruff format --check .` đều sạch (ai-qa wave-check)
> Cập nhật 2026-11-03 (ADR-035): T075–T079 chạy bằng engine chuỗi model free qua freellmapi của feature `008-llm-provider-chain`, không
> chạy bằng Gemini trực tiếp (benchmark 2026-11-02: Gemini lỗi 30/31 lượt). Chờ 008 xong mới làm. Giá trị `REPLY_ENGINE` và tên test
> `live_llm` của adapter chốt ở spec 008. Lần G1 bằng Gemini ngày 2026-11-02 (quickstart "Kết quả kiểm chứng") giữ làm lịch sử.
> Cập nhật 2026-11-04: adapter chuỗi của 008 đã code (`REPLY_ENGINE=chain`, 54/59 task, US1–US4 xong). G1 dùng
> `tests/live/test_chain_engine.py` (marker `live_llm`, từng mục ghim bằng `only=`); muốn kiểm riêng một model thì dùng
> `qa_eval run --entry <nhãn>` / `qa_eval script --entry <nhãn>`. Vẫn chờ T055 của 008 (quickstart cùng người dùng) và người dùng đồng ý.

- [x] T075 **(LLM thật, G1)** Chạy test `live_llm` của `narrate()` với engine 008 và quickstart US1 bước 4; ghi số request thật theo từng
  model trong chuỗi vào "Kết quả kiểm chứng" của `specs/004-show-director/quickstart.md` (cần người dùng đồng ý)
- [x] T076 **(LLM thật, G2)** Hồi quy Điều III sau khi đổi guard và bộ làm sạch: `uv run python -m ai_live.qa_eval run` với bộ 10 câu của 001,
  điểm không thấp hơn lần chạy trước trong `data/eval/runs/`; cùng ngày chạy `qa_eval script` lần 1. Người dùng xem danh sách "sai xưng hô"
  và `data/rules/platform_phrases.txt` trong báo cáo (research R9, R15 `TODO:`)
- [x] T077 **(LLM thật, G3)** SC-008: `qa_eval script` 3 lần liên tiếp đều 0 vi phạm, mỗi lần một ngày nếu RPD thấp; ghi vào "Kết quả kiểm chứng"
- [x] T078 **(LLM thật, G4)** SC-001: quickstart US1 bước 7 (10 lần **Bắt đầu show** → **Kết thúc**), ghi vào "Kết quả kiểm chứng"
  > Kết quả 2026-11-12 (T075–T078, cùng một ngày, 121 request, 0 lỗi 429): `narrate()` 2/2 model đạt; giá đúng file; `qa_eval run` 9/10 rồi 10/10; `qa_eval script` 3/3 lần 0 vi phạm (SC-008 đạt); SC-001 10/10 ≤ 5 s (2,0–2,67 s). Chi tiết: quickstart "G1–G4, engine 008".
- [ ] T079 **(LLM thật, G5)** Tổng duyệt ngày riêng: quickstart US3 (SC-002 đến SC-006, SC-010, có SC-003 chấm bằng `qa_eval script --session`),
  US6 bước 5 (SC-011), SC-009 theo cách người dùng chọn ở `TODO:` quickstart US3 bước 4; ghi vào "Kết quả kiểm chứng"
  > Chạy một phần 2026-11-12 (cùng ngày G1–G4, laptop chạy pin; chưa đóng): SC-005, SC-006, SC-010 đạt; SC-002 p95 2,845 s và SC-011 p95 7,41 s
  > chưa đạt; SC-004 0,4902 sát ngưỡng; SC-003 chấm lại có 24 câu `unsupported_claim` nên thêm ADR-050 (prompt + guard). Còn: SC-009
  > (người chấm), tổng duyệt lại ngày riêng sau khi sửa. Chi tiết: quickstart "G5".
- [x] T080 Cập nhật `docs/RISKS.md` Q14 và `specs/004-show-director/research.md` R14 bằng số request thật từ T075–T079
- [x] T081 Chạy `/update-context` — Đã chạy 2026-11-12 (cùng 005 T082)

## Phụ thuộc và thứ tự

- Setup → Foundational → US1 → US2 → US3 → US4 → US5 → US6 → Hoàn thiện. US4 chỉ cần Foundational + T025, T026, T027, T028 của US1,
  nên làm song song được với US2/US3 nếu cần.
- `src/ai_live/director/script_runner.py` bị sửa ở T033, T042, T050, T065, T071; `show_director.py` ở T015, T034, T043, T051, T066, T070;
  `routes.py` ở T036, T044, T052, T067; `control.*` ở T037, T045, T053, T068. Các task cùng file chạy tuần tự theo thứ tự trên.
- `tests/integration/test_script_runner.py` thêm ở T023, T040, T047, T048, T062; `test_show_api.py` ở T024, T041, T049, T063: viết tuần tự.
- T013 (contract) phải FAIL trước T014; T021 trước T028.
- T075–T079 cần LLM thật (engine của feature 008, ADR-035), 008 đã xong và sự đồng ý của người dùng; chạy theo lịch G1–G5 ở
  research R14, không gộp G5 với việc khác.

## Chạy song song

- Setup: T002, T003, T004.
- Foundational: T005, T006, T007 (test) → T009, T010, T012 song song; T008 → T011 → T013 → T014; T015 độc lập với nhánh brain.
- US1, test: T016–T022 cùng lúc (khác file). Implement: T025, T026, T027, T030, T031 cùng lúc; rồi T028 → T029; T032 song song nhánh brain;
  T033 chờ tất cả.
- Theo agent khi `/sdd.dispatch`: `ai-brain` (sanitize, guard, prompt, gemini, CLI brain, qa_eval), `ai-orchestrator` (core, director, app),
  `ai-qa` (contract test, `test_cli.py`), `ai-comments` (`data/rules/platform_phrases.txt`) chạy cùng đợt.

## Đợt GPU

- Không có task `[GPU]`. Các bước **[Đo lại]** của quickstart (SC-001, SC-002, SC-011) đo lại khi có giọng 003 hoặc nhân vật 005 trên GPU laptop
  (ADR-023); RunPod chỉ dự phòng và cần người dùng duyệt chi phí (`docs/RUNPOD.md`).

## Chiến lược MVP

1. Setup + Foundational → 2. US1 → **dừng, kiểm chứng, demo** (fake, rồi G1 nếu người dùng đồng ý) → 3. US2 → US3 → US4 → US5 → US6 từng
   bước → 4. Hoàn thiện với lịch LLM thật G1–G5 (engine 008, ADR-035).

## Nhật ký lỗi gặp khi implement

<!-- /sdd.implement và /sdd.dispatch ghi lỗi đáng nhớ vào đây. -->

- 2026-11-01 (Foundational) Contract test `narrate()` ở T013 chạy cho cả `GeminiReplyEngine`, nhưng Gemini chỉ có `narrate()` ở T028, nên checkpoint Foundational sẽ không xanh. Cách xử lý: đánh `xfail(strict=True)` cho các case Gemini qua `NARRATE_PENDING` trong `tests/contract/conftest.py`. **T028 phải xóa mục `"gemini"` khỏi `NARRATE_PENDING`**, nếu không bộ test sẽ đỏ (XPASS strict). Đã xử lý 2026-11-01: ai-qa bỏ hẳn cơ chế `NARRATE_PENDING`; 12 case Gemini `narrate()` chạy thật và đạt.
- 2026-11-01 (Foundational) `extract_amounts` của guard coi số nguyên trần ≥ 1000 là tiền. `FakeReplyEngine` đánh số câu `n` tăng mãi, nên một engine giả sinh quá 999 câu sẽ bị guard chặn `unknown_amount`. Test soak dài với cùng một engine giả cần lưu ý.
- 2026-11-01 (US1) Đợt 2 bị lỗi 429 "session limit" ở cả 3 agent giữa chừng. Kiểm git status và grep: chưa có sửa dở nào, chạy lại nguyên đợt.
- 2026-11-01 (US1) T038 đã viết file `tests/live/test_gemini_narrate.py` nhưng **chưa chạy** (marker `live_llm`). Chạy ở G1 khi người dùng đồng ý.
- 2026-11-02 (G1) T038 chạy với Gemini thật: 2 passed. 2/3 lần `narrate` thử tay có câu đầu sau 53 s và 58 s (1 lần 6,8 s), không có
  429; show sẽ hết hạn ở `SCRIPT_LLM_TIMEOUT_S` = 10 s và dùng câu dự phòng. Chi tiết ở quickstart "G1"; đo lại ở G3.
- 2026-11-01 (US1) T039 chạy bằng script giả lập màn hình host qua `/ws/host` (gửi `ready`, ack `playback_started`/`sentence_played` theo độ dài audio), không có trình duyệt. Phần nhìn của bước 2 (phụ đề, nhãn AI) chưa kiểm, cần mở `/host` bằng trình duyệt. Bước 6: khi show **đang chạy** mà host ngắt, `POST /api/show/start` trả `200 already_running: true`, không trả `409 host_unavailable`. Chỉ trả `409` khi chưa có show. contracts/api.md §2 chưa nói kiểm nào trước, cần người dùng chọn.
- 2026-11-02 (US2) Trên Windows `time.monotonic` chỉ chính xác khoảng 15,6 ms, nên `control_applied.latency_ms` thường ra 0,0 và nhiều sự
  kiện liền nhau có cùng `t_mono`. Khi ghép log theo thời gian, dùng `>=` (không dùng `>` hay `bisect_right`), nếu không sẽ bỏ sót sự kiện.
- 2026-11-02 (US2) T046: phía client phải lấy mốc thời gian **trước** khi gửi lệnh. Sau `POST /api/skip`, phân đoạn kế đã gửi
  `sentence_start` trước khi HTTP trả về; lấy mốc sau response sẽ bỏ sót câu đó và đo nhầm sang câu thứ hai (~3 s). Kết quả đúng tính
  từ log server. Phần nhìn (nhân vật và nhãn AI khi tạm dừng, nút **Kết thúc**, nhãn trạng thái) chưa kiểm, cần trình duyệt.
- 2026-11-02 (US3) Test soak ≥ 200 phân đoạn (T048) né lỗi guard "số ≥ 1000 là tiền" bằng engine giả `_SoakEngine`: câu không có chữ số,
  mỗi câu có một mã chỉ gồm phụ âm (không ghép thành cụm từ cấm), cố ý lặp mỗi lần gọi thứ 5 để bộ lọc trùng thật sự phải làm việc. Guard
  không đổi. `ScriptRunner` có thêm tham số `wall_clock` (mặc định đồng hồ thật) để test điều khiển cửa sổ 10 phút.
- 2026-11-02 (US3) Test dự phòng/thử lại từng bị chập chờn: dừng show trong lúc phân đoạn thử lại thành công còn đang nói, phân đoạn đó bị
  ghi `discarded`. Đã sửa: chờ `segment_finished` của phân đoạn đó rồi mới dừng, vẫn bắt buộc `done`.
- 2026-11-02 (US4–US6) Đợt 1 bị lỗi 429 "session limit" ở ai-brain và ai-orchestrator giữa chừng. Sau khi hạn mức hồi lại, gọi tiếp
  đúng agent đó (SendMessage), dặn kiểm file đang sửa dở trước; phần đã làm được giữ, không phải chạy lại cả đợt.
- 2026-11-02 (US4) T054/T055 đặt tên test `tests/unit/test_script_grader.py` và `test_script_eval.py`, không khớp danh sách Owns của
  ai-brain (`test_qa_eval_*`, `test_brain_*`). Cần thêm hai file vào `.claude/agents/ai-brain.md` hoặc đổi tên; chờ người dùng chọn.
- 2026-11-02 (US6) ai-orchestrator sửa hai lỗi tranh chấp khi tạm dừng: (1) `run()` có thể đã lấy comment đến ngay sau Tạm dừng rồi trả
  lời khi Tiếp tục; nay Tạm dừng hủy `queue.get()` đang chờ để comment nằm lại hàng đợi và hết hạn như 001. (2) Comment đã lấy khỏi hàng
  đợi nhưng chưa tới lượt không được cổng chen comment thấy, nên một câu kịch bản lọt lên trước; nay cổng đếm cả trạng thái `_taking`.
