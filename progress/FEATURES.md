# Sổ đăng ký feature

> Nguồn gốc của trạng thái là dòng "Trạng thái" trong từng `spec.md`; file này tóm tắt và nối các file liên quan.
> `/sdd.specify` thêm dòng + thẻ mới; các lệnh sau cập nhật theo [README.md](README.md) §3.
> Trạng thái: `Draft → Clarified → Planned → Tasked → In progress → Done` (thêm "tạm dừng" kèm ADR nếu có).

## Bảng tổng

| ID | Tên | Mốc | Trạng thái | Tasks | Bước kế tiếp |
|----|-----|-----|-----------|-------|--------------|
| [001-local-reply-pipeline](#001-local-reply-pipeline) | Pipeline trả lời comment chạy local | M1a | Tasked (tạm dừng, ADR-026) | 101/116 | Chờ người dùng mở lại phần trả lời comment |
| [003-vietnamese-tts](#003-vietnamese-tts) | Giọng tiếng Việt thật cho AI host | M1a | In progress | 53/54 | Xong mọi task chạy được trên laptop (chốt `vieneu` + Thùy Dung + đoạn mẫu, `gemini` dự phòng chỉ vài câu vì free tier 3 RPM / 10 RPD; phiên 30 phút 60/60 lượt); còn T050 [GPU], làm được từ 2026-11-11 vì lip-sync của 005 đã chạy (US1 xong) |
| [004-show-director](#004-show-director) | AI host tự nói kịch bản giới thiệu sản phẩm, sinh realtime | M1a | In progress | 74/81 | Phase 9: T072–T074 xong; còn T075–T079 (gọi LLM thật bằng chuỗi 008, chờ người dùng đồng ý), T080, T081 |
| [005-lipsync-livetalking](#005-lipsync-livetalking) | AI host chuyển động tự nhiên, nhép miệng realtime trên laptop | M1b | In progress (2026-11-07) | 61/83 | US1 xong (T045 đạt 2026-11-10 sau khi làm mượt clip nền rung; T046 SC-001 10/10 trên giọng VieNeu Thùy Dung, T047 SC-002 12/12 ảnh có nhãn "AI" trong khung hình, 2026-11-11); US2 xong phần code T048–T061 (2026-11-11), chờ người dùng chạy T062–T063 [GPU] |
| [008-llm-provider-chain](#008-llm-provider-chain) | Chuỗi model LLM miễn phí, tự chuyển model khi lỗi | M1a | Done | 59/59 | Xong 2026-11-05; mở khóa T075–T079 của 004 |

## Thẻ feature

Mỗi thẻ có cùng các key: `folder`, `status`, `artifacts`, `tasks`, `analyze`, `adrs`, `depends_on`, `agents`, `roadmap`, `open`.

### 001-local-reply-pipeline
- `folder`: [specs/001-local-reply-pipeline/](../specs/001-local-reply-pipeline/)
- `status`: Tasked, tạm dừng từ 2026-10-31 (ADR-026). Code đã có giữ nguyên, mock comment dùng làm công cụ thử cho 003 và 005
- `artifacts`: [spec](../specs/001-local-reply-pipeline/spec.md) · [plan](../specs/001-local-reply-pipeline/plan.md) ·
  [research](../specs/001-local-reply-pipeline/research.md) · [data-model](../specs/001-local-reply-pipeline/data-model.md) ·
  [contracts](../specs/001-local-reply-pipeline/contracts/) · [quickstart](../specs/001-local-reply-pipeline/quickstart.md) ·
  [tasks](../specs/001-local-reply-pipeline/tasks.md)
- `tasks`: 101/116 xong, 0 chờ GPU. Còn lại: T038, T083 (test `live_llm`), T098–T110 (docs, đo SC, chạy quickstart, `/update-context`)
- `analyze`: TODO: chưa ghi kết quả `/sdd.analyze` lần cuối vào đây (chạy trước khi có `progress/`)
- `adrs`: ADR-002, 003, 005, 012, 014, 015, 016, 017, 018, 019, 020, 026
- `depends_on`: —
- `agents`: ai-comments, ai-brain, ai-media, ai-orchestrator, ai-qa
- `roadmap`: M1a (MockSource, CommentQueue, ReplyEngine, bộ câu hỏi, StaticRenderer, log độ trễ)
- `open`: —

### 003-vietnamese-tts
- `folder`: [specs/003-vietnamese-tts/](../specs/003-vietnamese-tts/)
- `status`: In progress (2026-11-07). Phase 1 Setup (T001–T005) xong: T002 đóng bằng thư mục cache riêng `VIENEU_MODEL_CACHE` (mặc định `~/.cache/ai-live/hf`, adapter đặt `HF_HUB_CACHE` + `HF_HUB_DISABLE_SYMLINKS=1` trước khi import vieneu; người dùng duyệt, đã xóa bản tải lần đầu; research R1, ghi chú ADR-024). Phase 2 Foundational (T006–T019) xong: cấu hình TTS mới (bỏ ElevenLabs/OSS), `TTSEngineError` + `warm_up()` trong Protocol, lớp bọc `SpeechTTS` (chuẩn hóa, đếm ký tự, nghỉ sau lỗi hết hạn mức), `create_tts()` luôn trả `SpeechTTS`, app làm nóng TTS lúc khởi động và ghi `tts_usage.json` lúc đóng. US1 T020–T025 xong: `tts/vieneu_tts.py` (luồng phụ + `asyncio.Queue`, cờ dừng khi `aclose()`, khóa tuần tự, lọc FIR hạ 48 → 16 kHz), nhánh `vieneu` trong `create_tts()`; test live: làm nóng 10,8 s, chunk đầu 0,26 s, 2,88 s tiếng tạo trong 1,75 s (4 luồng CPU). T026 phần máy tự kiểm xong 2026-11-09 (nhật ký cuối tasks.md): với `TTS_TIMEOUT_S=5` câu 9,6 s tiếng bị cắt và lượt lỗi `timeout` vì thời gian chờ áp cho cả câu (VieNeu ~0,63 s/giây tiếng); với 15 s thì 3/3 lượt đạt, câu đầu 0,30 s, lặng giữa câu 0,06 s, "Bỏ qua" làm CPU về 0 trong 1 s; `fake` như 001. Người dùng nghe WAV, xác nhận → T026 tick. Sửa timeout theo ADR-049 (`TTS_TIMEOUT_S` cho mỗi lần chờ chunk, không cho cả câu; spec 001 sửa trước): chạy lại với 5 s thì câu 9,5 s tiếng đọc trọn. US1 xong (26/54). US2 xong 2026-11-09 (T034: người dùng nghe 5 WAV, đúng cả 5). US3 T035–T043 xong 2026-11-09: `tts/gemini_tts.py` (Interactions API, PCM16 16 kHz, 429 → `quota_exhausted`, che khóa), nhánh `gemini` trong `create_tts()`, `say` làm nóng + in nguồn/chữ gửi/số ký tự + báo lỗi theo `kind`; `turn_finished` thêm `error_kind`/`error_message`, thông báo `TTSEngineError` dùng nguyên văn, `SpeechTTS` gắn "Thử lại sau N giây." (lệch spec ghi ở nhật ký cuối tasks.md). T044 xong 2026-11-09 (Gemini thật: đoạn đầu 4,0 s, 2,88 s tiếng trong 6,47 s; API không nhận yêu cầu 16 kHz nên adapter hạ 24 → 16 kHz bằng `tts/resample.py` dùng chung với VieNeu, `input` theo dạng có cấu trúc của docs; sửa lỗi `genai.Client` bị thu hồi; contract §2, R2, R5 sửa trước). T045 xong 2026-11-09: `say` VieNeu (2 giọng) và Gemini (Leda, Aoede) đổi bằng cấu hình, người dùng nghe rõ; lỗi giả lập `error`/`timeout` ở bước tts với VieNeu thật, comment sau vẫn trả lời bằng tiếng thật (SC-004). US3 xong (45/54). Phase 6 (2026-11-09): T046–T047 xong. T049 phần VieNeu: giữ 4 luồng; giọng mặc định `Thùy Dung`; thêm biến tùy chọn `VIENEU_REF_AUDIO` (đoạn mẫu do chính giọng có sẵn đọc, mã hóa một lần lúc warm-up bằng hàm nội bộ của vieneu, không tải gì; spec FR-002 sửa trước, ADR-024 ghi chú, RISKS G15); đo 20 lượt p95 0,516 s, người dùng nghe ổn. Người dùng chốt `vieneu` mặc định, `gemini` dự phòng; Gemini không đo đủ 20 lượt (giữ hạn mức, số đơn lẻ 3,5–4,1 s đã không đạt SC-003); code và `.env.example` giữ `fake`, `.env` máy này đặt `vieneu`. T049 xong (48/54). T051 xong 2026-11-09 (SC-005: phiên 29 phút 36 giây, 60/60 lượt `completed`, 0 lỗi, p95 câu đầu → chunk đầu 0,484 s, 84 request / 6348 ký tự). T052 xong 2026-11-10: quickstart khớp thực tế; sửa lỗi `say --out` vào thư mục chưa có (tự tạo thư mục trước warm-up, báo "Không ghi được file ...", 2 test mới); quickstart thêm 2 dòng. T053 xong: 1859 passed, ruff sạch (51/54). T048 xong 2026-11-10: AI Studio cho `Gemini 3.8 Flash TTS` free 3 RPM, 10K TPM, 10 RPD (research R2, ADR-024, RISKS Q12), Gemini dự phòng chỉ cầm cự vài câu (52/54). Còn T050 [GPU] chờ 005, T054 `/update-context`.
- `artifacts`: [spec](../specs/003-vietnamese-tts/spec.md) · [plan](../specs/003-vietnamese-tts/plan.md) ·
  [research](../specs/003-vietnamese-tts/research.md) · [data-model](../specs/003-vietnamese-tts/data-model.md) ·
  [contracts](../specs/003-vietnamese-tts/contracts/) · [quickstart](../specs/003-vietnamese-tts/quickstart.md) ·
  [tasks](../specs/003-vietnamese-tts/tasks.md)
- `tasks`: 53/54, 0 `[~]` (T001–T049, T051–T054 xong, US1–US3 và Polish xong; còn T050 [GPU] chờ 005; MVP = Setup + Foundational + US1: T001–T026, đã xong)
- `analyze`: 2026-11-07, Sẵn sàng implement (0 CRITICAL, 3 HIGH, 5 MEDIUM, 8 LOW); nên sửa 3 HIGH trước: thiếu đo độ trễ show kịch bản, spec chưa theo ADR-026, chưa định nghĩa hành vi show khi Gemini hết hạn mức
- `adrs`: ADR-018, 019, 022, 023, 024, 025 (đã chốt 2026-11-07), ADR-049 (2026-11-09, `TTS_TIMEOUT_S` cho mỗi lần chờ chunk)
- `depends_on`: 001 (pipeline và mock comment để thử giọng)
- `agents`: ai-media (chính, `tts/`), ai-orchestrator (`core/`, `app/main.py`, `director/`), ai-qa (`tests/contract/`, test tích hợp TTS)
- `roadmap`: M1a mục `TTSEngine`
- `open`: T050 làm được từ 2026-11-11 (005 US1 xong; đo VieNeu cùng nhép miệng trên GPU laptop); Gemini dự phòng chỉ cầm cự vài câu (3 RPM / 10 RPD), dự phòng thật cần gói trả phí (hỏi người dùng); `VIENEU_REF_AUDIO` dùng hàm nội bộ của `vieneu` (RISKS G15), rà khi nâng phiên bản; VieNeu in cảnh báo HF Hub lúc nạp dù đã có cache (có thể gọi mạng, chưa xem)

### 004-show-director
- `folder`: [specs/004-show-director/](../specs/004-show-director/)
- `status`: In progress (2026-11-01). Setup, Foundational, Phase 3–8 (US1–US6) xong (checkpoint US6, 2026-11-02); 81 task, 0 `[GPU]`; không thêm dependency mới
- `artifacts`: [spec](../specs/004-show-director/spec.md) · [plan](../specs/004-show-director/plan.md) ·
  [research](../specs/004-show-director/research.md) · [data-model](../specs/004-show-director/data-model.md) ·
  [contracts](../specs/004-show-director/contracts/) · [quickstart](../specs/004-show-director/quickstart.md) ·
  [tasks](../specs/004-show-director/tasks.md)
- `tasks`: 74/81 (Setup T001–T004, Foundational T005–T015, US1 T016–T039, US2 T040–T046, US3 T047–T053, US4 T054–T060, US5 T061–T068, US6 T069–T071, Phase 9 T072–T074 xong 2026-11-03; G1 đã chạy 2026-11-02: T038 2 passed; T046 SC-007 đạt 10/10 mỗi lệnh với fake)
- `analyze`: 2026-11-01 Sẵn sàng implement (0 CRITICAL, 1 HIGH, 6 MEDIUM, 3 LOW). HIGH: contract test Gemini `narrate()` ở T013
  (Foundational) nhưng Gemini làm ở T028 (US1), checkpoint Foundational không xanh được; đã xử lý bằng `xfail(strict=True)` cho case Gemini (đã gỡ ở US1). A4 đã sửa (guard: tham số không bắt buộc, code chạy thật phải truyền cụm từ; T017, T024, T026, T034, T035); A2 thêm vào T069, A3 thêm vào T047
- `adrs`: ADR-017, 018, 026, 029, 030, 031, 032, 033 (030–033 đã chốt 2026-11-01)
- `depends_on`: 001 (guard chặn giá bịa, ReplyEngine, trang điều khiển); 003 (giọng thật, không bắt buộc cho P1)
- `agents`: ai-orchestrator (`director/`, `app/`, `core/`), ai-brain (`brain/` narrate, prompt, sanitize, guard; `qa_eval/` script),
  ai-comments (`data/rules/platform_phrases.txt`), ai-qa (contract test, fixture). ai-media: không cần (host.js không đổi)
- `roadmap`: M1a mục `ShowDirector`
- `open`: TODO trong research: R4 (mẫu sản phẩm không có giá; chữ quy tắc kịch bản đã duyệt, ADR-033),
  R14 (RPM/RPD thật trong AI Studio; ADR-035 đổi sang chuỗi model free; G1–G5 (T075–T079) chạy bằng engine của feature 008, 008 xong 2026-11-05); quickstart: cách chấm SC-009 (SC-003 dùng `qa_eval script --session`). Rủi ro mới Q14, Q15. G1 xong 2026-11-02 (giá và khuyến mãi đúng file; 2/3 lần câu đầu > 50 s, đo lại ở G3); T108 (eval lại guard 001, G2) chưa chạy; phần nhìn bước 2 quickstart US1 (phụ đề, nhãn AI) và US2 (nhân vật, nhãn AI khi tạm dừng; nút Kết thúc, nhãn trạng thái) chưa kiểm bằng trình duyệt. US2: ai-qa còn thiếu test (latency_ms của skip ≤ 1000 và của pause/resume chưa assert; phân đoạn đã chuẩn bị còn sau khi tạm dừng; skip lúc chào kết qua API; "không chạy lại sau ended" chưa có thời gian chờ; segment_id của câu nói lại sau resume); control.js giữ bản nhãn trạng thái riêng thay vì `ShowState.label`. Cách hiểu của ai-orchestrator chờ người dùng xem: câu của phân đoạn bị bỏ qua dùng lý do `interrupted`; `paused_discard` chỉ ghi log, không ghi jsonl; FR-030 (chào kết chờ comment) để US6. US3: ai-qa còn thiếu test (SC-006 gộp ≥ 3 lỗi llm + ≥ 3 lỗi tts trong một show với gap `fault` ≤ 8 s; bộ đếm lỗi liên tiếp về 0 khi có lần thành công; đọc lại văn bản dự phòng lần 2 không bị lọc trùng; guard chặn câu xấu trong dự phòng; dải cảnh báo dự phòng trên trang điều khiển). Cách hiểu của ai-orchestrator chờ người dùng xem: bộ lọc trùng tính cả câu đã nhận nhưng chưa nói; câu chào kết và câu dự phòng không qua bộ lọc trùng (vẫn qua guard); lần thử lại ra toàn câu bị chặn vẫn tính là dịch vụ chạy; phân đoạn dự phòng có `topic: intro`, `origin: fallback`, ô mở màn dùng sản phẩm chính. US4: lần chạy `qa_eval script` thật
  với Gemini đầu tiên (khoảng 30 lần gọi) chưa chạy, để G3; danh sách sai xưng hô (tôi, bạn, các bạn, quý khách, quí khách; nguyên từ,
  không phân biệt hoa thường; "bạn" ở ngôi thứ ba không tính) người dùng duyệt 2026-11-03; mã thoát 3 = chưa chấm hết vì lỗi dịch vụ, không tính SC-008 (ai-brain tự chọn).
  Cách hiểu của ai-brain chờ xem: "định dạng" = `clean_spoken` khác `normalize_text`; mỗi câu tối đa 1 vi phạm guard; số câu ngoài
  min–max chỉ cảnh báo; 429/hết giờ ghi lỗi, không thử lại; so sánh với lần gần nhất cùng nguồn nội dung và chế độ. Hai file
  `test_script_grader.py`, `test_script_eval.py` chưa thuộc Owns của ai-brain. US5: ai-qa còn thiếu test (vocab `segment_next`
  planned/ready/discarded; chọn khi N+1 đang sinh; thay catalog xóa mục đã chọn; chọn lúc tạm dừng rồi tiếp tục; bộ chọn trên trang
  cần trình duyệt). Cách hiểu của ai-orchestrator chờ xem: chọn được khi tạm dừng; closing/ended/idle → 409; ở chế độ dự phòng lựa chọn
  thành lần thử lại; ô bị bỏ của vòng xoay được nói ngay sau ô đã chọn; bỏ một narrate chậm có hiệu lực ở câu kế hoặc lúc hết giờ.
  US6: `POST /api/comments` lúc chào kết trả `202 waiting` rồi mới bỏ với `show_ended` qua sự kiện và `comments.jsonl`, api.md §3 viết
  chưa rõ (chờ người dùng chọn); chưa có test HTTP cho đường này; FR-030 hiểu là chào kết chỉ chờ câu trả lời đang nói; câu trả lời ghi
  vào lịch sử với sản phẩm của phân đoạn đang nói (spec chưa nói); `comments.answered` chỉ đếm câu trả lời đã có frame đầu

### 005-lipsync-livetalking
- `folder`: [specs/005-lipsync-livetalking/](../specs/005-lipsync-livetalking/)
- `status`: In progress (2026-11-07): Phase 1 Setup xong (fork dựng ở `vendor/livetalking`, torch 2.9.1+cu128, model đã tải); Phase 2 Foundational xong; Phase 3 US1 xong phần app (T022–T028, T030–T038) và phần fork (T029, T039–T042: `ailive_ext/` ingest, label, clips, prepare + móc `# ailive:` trong `app.py`, `config.py`, `base_avatar.py`, `wav2lip_avatar.py`; 42 test fork), T043 (người dùng) và checkpoint GPU T044–T047 xong 2026-11-11: US1 xong. 83 task (US1 26, US2 16, US3 5, US4 8; 13 `[GPU]`). Plan: Wav2Lip `wav2lip256` trong fork LiveTalking chạy process riêng, tiếng vào qua `/ailive/ws`, hình ra `/host` bằng WebRTC, nhãn AI vẽ trong khung của fork, `SwitchingRenderer` tự về ảnh tĩnh. Phạm vi: nhân vật nửa người từ ảnh gương mặt AI + bộ clip nền tạo offline (ADR-036), xoay vòng clip chờ / nói, cử chỉ theo nội dung để feature sau, lỗi tạo hình 2 lượt liền thì tự về ảnh tĩnh
- `artifacts`: [spec](../specs/005-lipsync-livetalking/spec.md) · [plan](../specs/005-lipsync-livetalking/plan.md) (2 lần cổng Đạt) · [tasks](../specs/005-lipsync-livetalking/tasks.md) · [research](../specs/005-lipsync-livetalking/research.md) R1–R15 · [data-model](../specs/005-lipsync-livetalking/data-model.md) · [contracts](../specs/005-lipsync-livetalking/contracts/) (fork-protocol, adapters, api, events) · [quickstart](../specs/005-lipsync-livetalking/quickstart.md) · notebook tạo gương mặt và clip nền
  [scripts/avatar_clips/make_avatar_clips.ipynb](../scripts/avatar_clips/make_avatar_clips.ipynb) (chạy trên Kaggle/Colab). Đã chạy 2
  lượt trên Kaggle T4 (2026-11-06): lượt 1 tạo 4 gương mặt, người dùng chọn `face_3_seed44`; lượt 2 tạo 4 clip (`idle_01`, `idle_02`
  kèm bản ping-pong, `talk_01`, `talk_02`), khoảng 9,5 phút một clip. Kết quả ở `assets/avatars/demo_host_01/` (gitignore). Kiểm thô bằng
  OpenCV (2026-11-06): cả 4 clip đúng một mặt mọi khung, idle miệng khép suốt, bản ping-pong lặp mượt; `talk_01` hé miệng thấy răng ở
  khung ~84–106; cuối clip nói lệch tư thế so với khung đầu clip chờ (plan cần xử lý chỗ về clip chờ). Người dùng chưa duyệt bằng mắt. Bản chạy lượt 2 trên Kaggle có thêm ghim commit ComfyUI và kiểm sha256 ảnh đã duyệt, bản trong repo chưa có
- `tasks`: 61/83, 0 `[~]` (T001–T061 xong; US2 2026-11-11: T048–T061 phần code + test (renderer lỗi/nối lại, `SwitchingRenderer` tự về ảnh tĩnh sau 2 lượt lỗi, `record_render_outcome` + `render_stats` từ director và script runner, `GET /api/avatar`, `POST /api/avatar/lipsync`, `/health` có `avatar`, tin `mode` ở trang host, dải cảnh báo + nút bật lại ở trang điều khiển, fork bắt OOM/lỗi suy luận → `error` + về clip chờ); còn T062–T063 [GPU] (máy tự chạy bằng bộ tự kiểm quickstart §11, thêm 2026-11-12: bộ ghi luồng của fork + `scripts/selfcheck/lipsync_check.py`); US1 xong; T047 đạt 2026-11-11: 12/12 ảnh Chrome headless (6 chờ, 6 nói) có nhãn "AI" trong khung hình, nhãn CSS ẩn khi video chạy; T046 đạt 2026-11-11: 10 đoạn VieNeu `Thùy Dung` 5,0–7,0 s chấm 10/10 khớp, `first_frame_s` 0,92–1,16 s, `render_fps` 24,8–25,3, đoạn 34,9 s và đoạn im lặng đạt, VRAM 2 656 MB không đổi; T045 đạt 2026-11-10: clip Wan 2.2 rung nhẹ liên tục, làm mượt bằng `scripts/avatar_clips/smooth_clips.py` (quickstart bước 4b), clip chờ mượt 5 khung, `talk_02` mượt 3 khung đặt lên đầu, `talk_01` giữ gốc; trước đó: T043 người dùng viết `character.json` / bổ sung `provenance.json`; T044–T047 `[GPU]` laptop, cần T043)
- `analyze`: 2026-11-06 Sẵn sàng implement (0 CRITICAL, 1 HIGH, 7 MEDIUM, 7 LOW). HIGH: giữa hai câu cùng lượt fork về clip chờ (im lặng ≥ 1 lô suy luận, giao thức không có tin hết lượt), trái US2 #1; nên sửa fork-protocol + T014/T042/T066 trước khi implement. MEDIUM: T072 thiếu test, nút giảm kích thước khung (R8) không có task, Owns của agent, trường hợp biên (câu > 30 s, tiếng im lặng, đóng host), FR-019 hiển thị ↔ ack, test chặn `/api/debug/speak-audio` khi tắt router debug, đo lặng giữa câu / câu đầu show ở US4. Sửa 2026-11-06 theo đồng ý của người dùng: HIGH theo cách (b), fork giữ clip nói tối đa `LIVETALKING_HOLD_S` (1,5 s, miệng khép) sau mỗi câu bằng `ClipScheduler` trong `rotation.py` (research R7, fork-protocol §4, T014, T042, T064–T067, T062); MEDIUM: thêm T083 (test `lipskip`), nút (2) R8 vào T075, trường hợp biên vào T046/T050, ghi chú FR-019 ↔ ack, 404 khi tắt router debug vào T028, đo lặng giữa câu / câu đầu show + chọn `LIVETALKING_LEAD_S` vào T073; LOW: T003 đã có sẵn, plan thêm `test_script_runner.py` và sửa FR-004/005, nhãn US1 #1/#4 sang T045, số đo ghi vào ADR-041 + quickstart. Còn để người dùng quyết: Owns của agent cho file mới (chỉ chặn `/sdd.dispatch`), 3 TODO (nơi đẩy fork R2, logo LiveTalking R5, quy ước `CUSTOMER_ID`)
- `adrs`: ADR-004, 008, 016, 019, 023, 025, 029, 036, 041–048 (041–047 chốt 2026-11-06, 048 chốt đủ 2026-11-07)
- `depends_on`: 001 (pipeline, mock comment); 003 (giọng thật)
- `agents`: ai-media (chính: fork, renderer, CLI avatar, trang host); ai-orchestrator (core/protocols, ShowDirector, route, trang điều khiển); ai-qa (fork giả, contract test)
- `roadmap`: M1b (fork LiveTalking, nhãn AI ghép vào frame)
- `open`: US2 còn T062–T063 [GPU] (người dùng chạy); cột fps của bảng độ trễ để T071 (US4); OOM giữa câu: `flush_talk()` bỏ cả câu khác đã xếp trong fork, các câu đó hết hạn ack ở app và tính lỗi (chấp nhận, ghi chú T061); clip 24 fps so với fork 25 fps cần xem bằng mắt. TODO chính: nơi đẩy nhánh `ailive` (R2), fps/VRAM khi chạy 30 phút trên 1650 Ti (SC-006; số đo ngắn đã ghi ADR-041), cu128 với driver 565.90, chạy native Windows, license checkpoint, lệch ack ↔ hiển thị (plan §Rủi ro mới)

### 008-llm-provider-chain
- `folder`: [specs/008-llm-provider-chain/](../specs/008-llm-provider-chain/)
- `status`: Done (2026-11-05). Setup + Foundational (T001–T015) US1 (T016–T025, T058, T059), US2 (T026–T036), US3 (T037–T046) và US4 (T047–T052) xong qua `/sdd.dispatch`; Polish T053, T054, T056 xong; T055 chạy 2026-11-04 (quickstart "Kết quả kiểm chứng": US1, SC-002, SC-003, SC-005, SC-006, SC-008 đạt; SC-009 đạt a–f; SC-007 7/8; SC-001 sealion đạt, gptoss không đạt, qwen kịch bản chưa chấm đủ; cổng Q18 chạm ngưỡng). 2026-11-05: ADR-040 bỏ gptoss, sealion chờ 2,5 s; đo lại Q18 đạt (lớn nhất 3,31 s), qwen kịch bản 21/21 0 vi phạm nên SC-001 đạt cho chuỗi mới; US2 bước 9 (tắt / bật Cloudflare giữa show) và US3 xem bằng trình duyệt đạt, bước 10 bỏ qua; còn chốt SC-007, chưa tick (checkpoint US3/US4; khu "Model LLM" chưa mở trình duyệt; quickstart US3 bước 4 và US4 cần mạng; bảng a–f và show 5 phút quickstart US1 cần mạng, làm ở T055)
- `artifacts`: [spec](../specs/008-llm-provider-chain/spec.md): 4 user story (P1 model đầu chuỗi; P1 tự chuyển model khi lỗi; P2 theo dõi model đang nói; P3 kiểm từng model), 24 FR, 9 SC · [plan](../specs/008-llm-provider-chain/plan.md) (2 lần cổng Đạt; câu chào có thể > 5 s khi mục 1 hết giờ chờ, Q18) · [research](../specs/008-llm-provider-chain/research.md) R1–R13 · [data-model](../specs/008-llm-provider-chain/data-model.md) · [contracts](../specs/008-llm-provider-chain/contracts/) (adapters, config, api, events) · [quickstart](../specs/008-llm-provider-chain/quickstart.md) · [tasks](../specs/008-llm-provider-chain/tasks.md): 59 task (Setup 2, Foundational 13, US1 12, US2 11, US3 10, US4 6, Polish 5; T058–T059 thêm sau phân tích), không có `[GPU]`
- `tasks`: 59/59
- `analyze`: 2026-11-03 Sẵn sàng implement (0 CRITICAL, 1 HIGH, 6 MEDIUM, 5 LOW). Sửa 2026-11-04 theo đồng ý của người dùng: HIGH (rủi ro Điều VI/Q18 vào "Theo dõi độ phức tạp", cổng quyết định ở T055), 6 MEDIUM (thêm T058–T059 preflight cho CLI `brain`; test mục ghim lỗi ở T047/T048; bỏ `[P]` sai ở T033, T041; bỏ TODO cũ; chốt log ra `logs/` cho SC-008; `SecretStr | None`), 4 LOW; L5 là báo nhầm (comment trong contracts đã là tiếng Anh). Không còn vấn đề mở
- `adrs`: ADR-040 (chuỗi mặc định `sealion` 2,5 s → `qwen`, đã chốt 2026-11-05), ADR-037 (cấu hình chuỗi, đã chốt 2026-11-03), ADR-038 (phân loại lỗi, nghỉ mục, kiểm nền tảng, đã chốt), ADR-039 (quan sát, giả lập lỗi, che key, đã chốt); ADR-034 (dịch vụ gom key local), ADR-035 (chuỗi model, thứ tự, httpx), ADR-018 (Gemini, xuống cuối chuỗi), ADR-019 (không trả phí), ADR-032 (chế độ dự phòng của 004)
- `depends_on`: 004 (`narrate()`, giới hạn thời gian phân đoạn, chế độ dự phòng, giả lập lỗi); 001 (`reply()`, bộ câu hỏi mẫu); freellmapi đã cài (ADR-034)
- `agents`: ai-brain (chính: bộ sinh lời thoại, bộ kiểm); ai-orchestrator (cấu hình, trang điều khiển, tổng hợp show, giả lập lỗi theo mục); ai-qa (contract test, nhà cung cấp giả)
- `roadmap`: M1a (chặn G1–G5 của 004, T075–T079)
- `open`: không còn `[NEEDS CLARIFICATION]`; làm rõ 2026-11-03: mỗi lượt bắt đầu từ mục cao nhất đang sẵn sàng (quay lại ngay), không có nút ghim/tắt mục giữa show. Làm rõ sau plan (freellmapi chỉ dùng 1 ngày demo, ưu tiên chính xác): nghỉ cố định 60 s, không Retry-After, không tắt mục, không kiểm 15 s, không thống kê token; kiểm key + model bằng `GET /models` lúc khởi động (lỗi thì không khởi động); mục freellmapi khai `platform`, `X-Routed-Via` sai thì từ chối và chuyển mục. Chờ câu đầu 3,5 / 2,0 / 2,0 s. httpx sang runtime đã duyệt (T001). `fake_openai` không có chế độ server; bước bằng tay US2 dùng chuỗi thật. dotenv đọc được `LLM_CHAIN` JSON không nháy (test T004 đọc `.env.example`). TODO: tên model chính xác (`/v1/models`), Groq/freellmapi có trả `usage` khi stream không

## Đề xuất chưa tạo

Mỗi dòng là một lần `/sdd.specify`. Thứ tự theo ROADMAP; người dùng có thể gộp, tách hoặc đổi.

| Đề xuất ID | Nội dung | Mốc | Cần GPU |
|-----------|----------|-----|---------|
| ~~002-product-qa-eval~~ | Đã gộp vào `001` (User Story 5), chốt khi clarify 2026-10-30 | M1a | Không |
| 006-youtube-live | Đẩy RTMP lên YouTube Unlisted (phần đọc comment tạm hoãn, ADR-026) | M1c | Có (phần RTMP + avatar) |
| 007-demo-readiness | Chạy liên tục 30 phút, watchdog cơ bản, runbook, video dự phòng | M1d | Có |
| 009-live-scene-layout | Bố cục cảnh live quanh host AI (người dùng yêu cầu 2026-11-07, làm sau 003). Chi tiết ở dưới bảng | M1b/M1d | Không (hướng B); Có (hướng C) |

**Ghi chú 009-live-scene-layout** (ghi lại từ trao đổi 2026-11-07, chưa phải spec; `/sdd.specify` dùng làm đầu vào):

- **Yêu cầu của người dùng:** live bán hàng bằng AI thường có bố cục người ngồi sau bàn, sản phẩm đặt hai bên hoặc phía sau. Hiện host
  005 đứng trên phông trơn đúng như clip nền làm trên Kaggle (FR-002 của 005 giữ nguyên bối cảnh ảnh gốc); chưa feature nào làm cảnh.
- **Ba hướng đã bàn:**
  - A. Vẽ sẵn bàn/kệ vào ảnh gốc rồi tạo lại clip nền: không thêm code, nhưng đổi sản phẩm phải làm lại clip + `prepare`, và sản phẩm do AI
    vẽ dễ sai hình thật (trái ràng buộc 7).
  - B. **Đề xuất**: ghép lớp realtime mỗi khung: phông sau, ảnh thật sản phẩm do khách gửi, thẻ tên/giá lấy từ file dữ liệu sản phẩm, phụ
    đề; làm nổi sản phẩm host đang nói (ShowDirector biết phân đoạn). Demo Meet có thể bắt đầu bằng bố cục web quanh `<video>`; khi
    ra OBS/YouTube/Shopee phải ghép trong khung hình như nhãn AI (ADR-044).
  - C. Tách nền người (matting) đặt vào cảnh bàn: đẹp nhất nhưng cần model mới + ADR, GPU 4 GB đã dùng ~2,7 GB; để sau.
- **Ràng buộc giữ nguyên:** nhãn "AI" luôn trong khung, watermark "LiveTalking" không bị che (RISKS L1); ảnh nền và ảnh sản phẩm tĩnh
  không phải video dựng sẵn; giá/tên chỉ lấy từ dữ liệu sản phẩm.
- TODO: khung dọc 9:16 (kiểu Shopee) hay ngang 16:9?
- TODO: khách có ảnh thật sản phẩm (tốt nhất nền trong suốt) không?
- TODO: có cần làm nổi sản phẩm đang được nói tới không?
