# Sổ đăng ký feature

> Nguồn gốc của trạng thái là dòng "Trạng thái" trong từng `spec.md`; file này tóm tắt và nối các file liên quan.
> `/sdd.specify` thêm dòng + thẻ mới; các lệnh sau cập nhật theo [README.md](README.md) §3.
> Trạng thái: `Draft → Clarified → Planned → Tasked → In progress → Done` (thêm "tạm dừng" kèm ADR nếu có).

## Bảng tổng

| ID | Tên | Mốc | Trạng thái | Tasks | Bước kế tiếp |
|----|-----|-----|-----------|-------|--------------|
| [001-local-reply-pipeline](#001-local-reply-pipeline) | Pipeline trả lời comment chạy local | M1a | Tasked (tạm dừng, ADR-026) | 107/116 | Việc không cần LLM xong 2026-11-13 (docs, quickstart nửa fake, ruff/pytest); còn 8 task cần LLM thật + `/update-context` |
| [003-vietnamese-tts](#003-vietnamese-tts) | Giọng tiếng Việt thật cho AI host | M1a | Done | 54/54 | Xong 2026-11-12 (chốt `vieneu` + Thùy Dung + đoạn mẫu, `gemini` dự phòng chỉ vài câu vì free tier 3 RPM / 10 RPD; phiên 30 phút 60/60 lượt); T050: cùng nhép miệng 005, p95 câu đầu → chunk đầu 0,921 s (chạy pin) |
| [004-show-director](#004-show-director) | AI host tự nói kịch bản giới thiệu sản phẩm, sinh realtime | M1a | In progress | 80/81 | Xong trừ T079 (SC-009 người chấm, tổng duyệt lại ngày riêng); ADR-050 guard `unsupported_claim` |
| [005-lipsync-livetalking](#005-lipsync-livetalking) | AI host chuyển động tự nhiên, nhép miệng realtime trên laptop | M1b | In progress (2026-11-07) | 81/83 | US4 đo xong 2026-11-12 (T069–T075, T083: show 30 phút 0 lỗi, `render_fps` 25,1; `LIVETALKING_LEAD_S` 2,5 đưa lặng nghe được p95 xuống 0,76–1,0 s, chờ duyệt; giữ batch 16); còn T068, T075 phần chờ người dùng, T080 Meet; US1 xong (T045 đạt 2026-11-10 sau khi làm mượt clip nền rung; T046 SC-001 10/10 trên giọng VieNeu Thùy Dung, T047 SC-002 12/12 ảnh có nhãn "AI" trong khung hình, 2026-11-11); US2 xong phần code T048–T061 (2026-11-11); T062 đạt 2026-11-12 bằng bộ tự kiểm (SC-003, SC-004 sau sửa; giữ clip nói chờ US3); T063 đạt 2026-11-12 (SC-005, tắt/bật fork giữa show); US2 xong; US3 T064–T067 xong 2026-11-12 (SC-007 0 chỗ giật; clip nói giữ qua các câu kịch bản, `HOLD_S` 2,5), T068 cần người xem; tiếp US4 |
| [008-llm-provider-chain](#008-llm-provider-chain) | Chuỗi model LLM miễn phí, tự chuyển model khi lỗi | M1a | Done | 59/59 | Xong 2026-11-05; mở khóa T075–T079 của 004 |
| [009-live-scene-layout](#009-live-scene-layout) | Bố cục cảnh live quanh AI host (khung dọc): bàn bày sản phẩm thật + thẻ tên/giá trước host, làm nổi sản phẩm đang nói | M1b | Done (2026-11-13) | 38/38 | Code + đo xong (SC-001–005 đạt, SC-004 trên GPU laptop: fps giảm 0%); chờ người dùng: ảnh thật của khách + SC-007, SC-006 (3 người xem), xác nhận ADR-051/052 |
| [010-natural-mouth-shapes](#010-natural-mouth-shapes) | Khẩu hình miệng host AI giống người thật khi nói tiếng Việt | M1b | In progress (2026-11-13) | 30/32 | Phần máy xong: bộ đo khẩu hình, núm `LIVETALKING_MOUTH_METHOD` (mặc định `w2l`, ADR-055), loại đoạn đầu nghiêng (ADR-056). Chờ người dùng: chấm A/B r4 `w2l` vs `shift=-1` (T018 → T019), ngưỡng góc đầu (T026) |
| [007-demo-readiness](#007-demo-readiness) | Sẵn sàng cho buổi demo: kiểm tra trước demo, canh show, báo cáo tổng duyệt 30 phút, video dự phòng | M1d | In progress (2026-11-13) | 58/59 | Phần máy xong 2026-11-13; chờ người dùng T058 (xem video dự phòng, thử Meet, xác nhận ADR-057). GPU laptop: T054 show 30 phút 327 câu 0 lỗi, lặng p95 3,0 s (SC-004 đạt so 005), 2 cảnh báo sai đã sửa bằng `WATCHDOG_AUDIO_ACK_LIPSYNC_S` 6 s; T055 video dự phòng 157 s `Đạt`; T056 tắt fork giữa show báo sau 0,6 s; T057 không gọi LLM. Setup + Foundational + US1 xong (kiểm tra trước demo: `GET /api/readiness`, lệnh `python -m ai_live.ops readiness`, nút trên trang điều khiển, kiểm bằng trình duyệt); US2 canh show xong (`ops/watchdog.py`, tự bỏ câu kẹt 15 s, banner trên trang điều khiển, nhịp `host_status` từ tab host, kiểm bằng trình duyệt); US3 báo cáo tổng duyệt xong (`python -m ai_live.ops report`, `gaps.jsonl`); US4 video dự phòng xong phần code (show `verbatim`, lệnh `backup-video`, không có đường phát video); RUNBOOK + tài liệu (T051–T052); làm không gọi LLM free; ADR-057 Đề xuất |
| [011-ultralight-live-lipsync](#011-ultralight-live-lipsync) | Host AI nhép miệng bằng model riêng của nhân vật (Ultralight) trong show live | M1b | In progress (2026-11-19) | 46/63 (1 `[~]`) | US1 phần code xong (T010–T035); T003 xong 2026-11-19 (Kaggle v3 đủ 200 epoch); T036–T038 xong 2026-11-19 (cài model, miệng khép, `desk_top` 0,78); T039 xong 2026-11-19 (fork + app chạy Ultralight, readiness "Model nhép miệng" Đạt, trang điều khiển đúng dòng model); T040 chạy 2026-11-19 (show 10 phút: render_fps p50 25,13, infer_fps p50 109, VRAM 2120 MB, lặng p95 0,047 s, câu đầu 2,36 s, nhãn 14/14 ảnh), còn người dùng xem chỗ nối vòng khung; T046 xong 2026-11-19 (bộ đo khẩu hình: ultralight **chưa đạt** SC-001, 1/4 chỉ số tốt hơn, LSE-C 2,90 so với 5,91 của w2l; hai lần đo trùng, SC-004 đạt; gói xem mù `out/mouth/runs/011_t046_r1/ab/PHIEU.md`); T042–T045 xong 2026-11-19 (lệnh `python -m ai_live.ops lipsync-compare`, mã thoát 0/1/2/3); T047 xong 2026-11-19 (show A Wav2Lip `demo_host_01` 11 phút, 0 lỗi); T048 xong: **Chưa đạt** (khẩu hình 1/4, LSE-C 2,90 so với 5,91; hiệu năng đều Đạt), báo cáo `out/011_compare/2026-11-19_23-22-39/` → theo ADR-066 giữ Wav2Lip cho demo; bước kế T049 (người dùng chấm gói xem mù), T050 (ghi số vào ADR-066); đánh giá Ultralight ngay khi model Kaggle xong (ADR-066 sửa 2026-11-19) |
| [012-product-image-upload](#012-product-image-upload) | Đổi ảnh sản phẩm ngay trên trang điều khiển giữa phiên live (chọn món, tải ảnh, xác nhận quyền dùng, xem trước, áp dụng ≤ 2 s; chuẩn bị bộ sản phẩm mới rồi áp một lần; hoàn tác/gỡ) | M1d | In progress (2026-11-20) | 66/70 (+3 `[~]`) | Phần máy không GPU xong; chờ người dùng xem `out/012_review/README.md` (bấm giờ tay SC-002/SC-005), T067/T068 trên GPU laptop |
| [006-obs-output](#006-obs-output) | Đưa AI host vào OBS thành một nguồn hình có tiếng (bỏ YouTube) | M2 | In progress (2026-11-13) | 30/35 | Phần máy không GPU xong (trang `/obs`, vai obs > host, kiểm tra trước demo + canh show theo chế độ, runbook §8); còn 4 `[GPU]`, T029 chạy OBS portable (bị chặn quyền) và gói duyệt |

## Thẻ feature

Mỗi thẻ có cùng các key: `folder`, `status`, `artifacts`, `tasks`, `analyze`, `adrs`, `depends_on`, `agents`, `roadmap`, `open`.

### 001-local-reply-pipeline
- `folder`: [specs/001-local-reply-pipeline/](../specs/001-local-reply-pipeline/)
- `status`: Tasked, tạm dừng từ 2026-10-31 (ADR-026). Code đã có giữ nguyên, mock comment dùng làm công cụ thử cho 003 và 005
- `artifacts`: [spec](../specs/001-local-reply-pipeline/spec.md) · [plan](../specs/001-local-reply-pipeline/plan.md) ·
  [research](../specs/001-local-reply-pipeline/research.md) · [data-model](../specs/001-local-reply-pipeline/data-model.md) ·
  [contracts](../specs/001-local-reply-pipeline/contracts/) · [quickstart](../specs/001-local-reply-pipeline/quickstart.md) ·
  [tasks](../specs/001-local-reply-pipeline/tasks.md)
- `tasks`: 107/116 xong, 0 chờ GPU. 2026-11-13 xong T098, T099, T105–T107, T109 và nửa `fake` của T100 (kết quả thô `out/001_checks/`).
  Còn lại cần LLM thật: T038, T083 (test `live_llm`), T100 lần hai, T101–T104, T108; T110 `/update-context`
- `analyze`: TODO: chưa ghi kết quả `/sdd.analyze` lần cuối vào đây (chạy trước khi có `progress/`)
- `adrs`: ADR-002, 003, 005, 012, 014, 015, 016, 017, 018, 019, 020, 026
- `depends_on`: —
- `agents`: ai-comments, ai-brain, ai-media, ai-orchestrator, ai-qa
- `roadmap`: M1a (MockSource, CommentQueue, ReplyEngine, bộ câu hỏi, StaticRenderer, log độ trễ)
- `open`: —

### 003-vietnamese-tts
- `folder`: [specs/003-vietnamese-tts/](../specs/003-vietnamese-tts/)
- `status`: Done (2026-11-12, T050 xong: đo VieNeu cùng nhép miệng 005 trên laptop, 20/20 lượt, p95 câu đầu → chunk đầu 0,921 s, chunk đầu → khung đầu p95 1,600 s, laptop chạy pin). Phase 1 Setup (T001–T005) xong: T002 đóng bằng thư mục cache riêng `VIENEU_MODEL_CACHE` (mặc định `~/.cache/ai-live/hf`, adapter đặt `HF_HUB_CACHE` + `HF_HUB_DISABLE_SYMLINKS=1` trước khi import vieneu; người dùng duyệt, đã xóa bản tải lần đầu; research R1, ghi chú ADR-024). Phase 2 Foundational (T006–T019) xong: cấu hình TTS mới (bỏ ElevenLabs/OSS), `TTSEngineError` + `warm_up()` trong Protocol, lớp bọc `SpeechTTS` (chuẩn hóa, đếm ký tự, nghỉ sau lỗi hết hạn mức), `create_tts()` luôn trả `SpeechTTS`, app làm nóng TTS lúc khởi động và ghi `tts_usage.json` lúc đóng. US1 T020–T025 xong: `tts/vieneu_tts.py` (luồng phụ + `asyncio.Queue`, cờ dừng khi `aclose()`, khóa tuần tự, lọc FIR hạ 48 → 16 kHz), nhánh `vieneu` trong `create_tts()`; test live: làm nóng 10,8 s, chunk đầu 0,26 s, 2,88 s tiếng tạo trong 1,75 s (4 luồng CPU). T026 phần máy tự kiểm xong 2026-11-09 (nhật ký cuối tasks.md): với `TTS_TIMEOUT_S=5` câu 9,6 s tiếng bị cắt và lượt lỗi `timeout` vì thời gian chờ áp cho cả câu (VieNeu ~0,63 s/giây tiếng); với 15 s thì 3/3 lượt đạt, câu đầu 0,30 s, lặng giữa câu 0,06 s, "Bỏ qua" làm CPU về 0 trong 1 s; `fake` như 001. Người dùng nghe WAV, xác nhận → T026 tick. Sửa timeout theo ADR-049 (`TTS_TIMEOUT_S` cho mỗi lần chờ chunk, không cho cả câu; spec 001 sửa trước): chạy lại với 5 s thì câu 9,5 s tiếng đọc trọn. US1 xong (26/54). US2 xong 2026-11-09 (T034: người dùng nghe 5 WAV, đúng cả 5). US3 T035–T043 xong 2026-11-09: `tts/gemini_tts.py` (Interactions API, PCM16 16 kHz, 429 → `quota_exhausted`, che khóa), nhánh `gemini` trong `create_tts()`, `say` làm nóng + in nguồn/chữ gửi/số ký tự + báo lỗi theo `kind`; `turn_finished` thêm `error_kind`/`error_message`, thông báo `TTSEngineError` dùng nguyên văn, `SpeechTTS` gắn "Thử lại sau N giây." (lệch spec ghi ở nhật ký cuối tasks.md). T044 xong 2026-11-09 (Gemini thật: đoạn đầu 4,0 s, 2,88 s tiếng trong 6,47 s; API không nhận yêu cầu 16 kHz nên adapter hạ 24 → 16 kHz bằng `tts/resample.py` dùng chung với VieNeu, `input` theo dạng có cấu trúc của docs; sửa lỗi `genai.Client` bị thu hồi; contract §2, R2, R5 sửa trước). T045 xong 2026-11-09: `say` VieNeu (2 giọng) và Gemini (Leda, Aoede) đổi bằng cấu hình, người dùng nghe rõ; lỗi giả lập `error`/`timeout` ở bước tts với VieNeu thật, comment sau vẫn trả lời bằng tiếng thật (SC-004). US3 xong (45/54). Phase 6 (2026-11-09): T046–T047 xong. T049 phần VieNeu: giữ 4 luồng; giọng mặc định `Thùy Dung`; thêm biến tùy chọn `VIENEU_REF_AUDIO` (đoạn mẫu do chính giọng có sẵn đọc, mã hóa một lần lúc warm-up bằng hàm nội bộ của vieneu, không tải gì; spec FR-002 sửa trước, ADR-024 ghi chú, RISKS G15); đo 20 lượt p95 0,516 s, người dùng nghe ổn. Người dùng chốt `vieneu` mặc định, `gemini` dự phòng; Gemini không đo đủ 20 lượt (giữ hạn mức, số đơn lẻ 3,5–4,1 s đã không đạt SC-003); code và `.env.example` giữ `fake`, `.env` máy này đặt `vieneu`. T049 xong (48/54). T051 xong 2026-11-09 (SC-005: phiên 29 phút 36 giây, 60/60 lượt `completed`, 0 lỗi, p95 câu đầu → chunk đầu 0,484 s, 84 request / 6348 ký tự). T052 xong 2026-11-10: quickstart khớp thực tế; sửa lỗi `say --out` vào thư mục chưa có (tự tạo thư mục trước warm-up, báo "Không ghi được file ...", 2 test mới); quickstart thêm 2 dòng. T053 xong: 1859 passed, ruff sạch (51/54). T048 xong 2026-11-10: AI Studio cho `Gemini 3.8 Flash TTS` free 3 RPM, 10K TPM, 10 RPD (research R2, ADR-024, RISKS Q12), Gemini dự phòng chỉ cầm cự vài câu (52/54). Còn T050 [GPU] chờ 005, T054 `/update-context`.
- `artifacts`: [spec](../specs/003-vietnamese-tts/spec.md) · [plan](../specs/003-vietnamese-tts/plan.md) ·
  [research](../specs/003-vietnamese-tts/research.md) · [data-model](../specs/003-vietnamese-tts/data-model.md) ·
  [contracts](../specs/003-vietnamese-tts/contracts/) · [quickstart](../specs/003-vietnamese-tts/quickstart.md) ·
  [tasks](../specs/003-vietnamese-tts/tasks.md)
- `tasks`: 54/54, 0 `[~]` (xong hết; T050 2026-11-12; MVP = Setup + Foundational + US1: T001–T026, đã xong)
- `analyze`: 2026-11-07, Sẵn sàng implement (0 CRITICAL, 3 HIGH, 5 MEDIUM, 8 LOW); nên sửa 3 HIGH trước: thiếu đo độ trễ show kịch bản, spec chưa theo ADR-026, chưa định nghĩa hành vi show khi Gemini hết hạn mức
- `adrs`: ADR-018, 019, 022, 023, 024, 025 (đã chốt 2026-11-07), ADR-049 (2026-11-09, `TTS_TIMEOUT_S` cho mỗi lần chờ chunk)
- `depends_on`: 001 (pipeline và mock comment để thử giọng)
- `agents`: ai-media (chính, `tts/`), ai-orchestrator (`core/`, `app/main.py`, `director/`), ai-qa (`tests/contract/`, test tích hợp TTS)
- `roadmap`: M1a mục `TTSEngine`
- `open`: đo lại T050 khi cắm sạc (p95 0,921 s sát ngưỡng 1,0 s; cân nhắc 6 luồng nếu vượt khi show dài); Gemini dự phòng chỉ cầm cự vài câu (3 RPM / 10 RPD), dự phòng thật cần gói trả phí (hỏi người dùng); `VIENEU_REF_AUDIO` dùng hàm nội bộ của `vieneu` (RISKS G15), rà khi nâng phiên bản; VieNeu in cảnh báo HF Hub lúc nạp dù đã có cache (có thể gọi mạng, chưa xem)

### 004-show-director
- `folder`: [specs/004-show-director/](../specs/004-show-director/)
- `status`: In progress (2026-11-01). Setup, Foundational, Phase 3–8 (US1–US6) xong (checkpoint US6, 2026-11-02); 81 task, 0 `[GPU]`; không thêm dependency mới
- `artifacts`: [spec](../specs/004-show-director/spec.md) · [plan](../specs/004-show-director/plan.md) ·
  [research](../specs/004-show-director/research.md) · [data-model](../specs/004-show-director/data-model.md) ·
  [contracts](../specs/004-show-director/contracts/) · [quickstart](../specs/004-show-director/quickstart.md) ·
  [tasks](../specs/004-show-director/tasks.md)
- `tasks`: 80/81 (2026-11-12: T075–T078, T080, T081 xong; T079 chạy một phần, chờ SC-009 và tổng duyệt ngày riêng; ADR-050 thêm guard `unsupported_claim`) (Setup T001–T004, Foundational T005–T015, US1 T016–T039, US2 T040–T046, US3 T047–T053, US4 T054–T060, US5 T061–T068, US6 T069–T071, Phase 9 T072–T074 xong 2026-11-03; G1 đã chạy 2026-11-02: T038 2 passed; T046 SC-007 đạt 10/10 mỗi lệnh với fake)
- `analyze`: 2026-11-01 Sẵn sàng implement (0 CRITICAL, 1 HIGH, 6 MEDIUM, 3 LOW). HIGH: contract test Gemini `narrate()` ở T013
  (Foundational) nhưng Gemini làm ở T028 (US1), checkpoint Foundational không xanh được; đã xử lý bằng `xfail(strict=True)` cho case Gemini (đã gỡ ở US1). A4 đã sửa (guard: tham số không bắt buộc, code chạy thật phải truyền cụm từ; T017, T024, T026, T034, T035); A2 thêm vào T069, A3 thêm vào T047
- `adrs`: ADR-017, 018, 026, 029, 030, 031, 032, 033 (030–033 đã chốt 2026-11-01), 050 (2026-11-12)
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
- `tasks`: 81/83, 0 `[~]` (còn T068 người xem, T080 Meet; T075 người dùng chốt 2026-11-16: `LEAD_S` 2,5 thành mặc định, batch 16, không làm bộ clip nhỏ hơn, không RunPod; US4 2026-11-12: T069–T072, T083 cột fps + clip trong `/api/latency`, test `lipskip`; T073 show 30 phút 322 câu 0 lỗi, `render_fps` p50 25,1, VRAM 2 656 MB không đổi, lặng giữa câu p95 2,98 s; thử `LIVETALKING_LEAD_S` 0 / 1,3 / 2,5 → lặng nghe được p95 3,19 / 1,96 / 0,76–1,00 s, đề xuất 2,5 chờ duyệt; sửa 2 lỗi đo khi `LEAD_S` > 0 (`sentence_gap` tính từ `sentence_played`, `RenderSettleSource`) và nối `SessionLog.record_avatar` (2c7bbf3); T074 lệch ack ↔ Chrome trung vị 0,28 s; T075 batch 16/8/4 + `LIP_EVERY_N` 2: chỉ batch 16 gần 25 khung/giây, n = 2 không tăng `render_fps`; T076–T079 docs; T081 1929 passed, fork 114 passed; T064–T067 2026-11-12: T064–T067 2026-11-12: `ClipScheduler` + `Crossfade` trong fork, bộ ghi luồng chấm 4 bản ghi: 0 chỗ giật; lần đầu tìm ra câu kịch bản nào cũng `seq 0` nên clip nói đổi và chạy lại từ khung 0 ở mọi câu, sửa spec rồi code: giữ clip qua các câu trong khoảng giữ, đổi sau một vòng ở ranh giới câu, `LIVETALKING_HOLD_S=2.5`; 0/49 khoảng nghỉ về clip chờ; miệng r 0,08 do đoạn đầu ngửa trong clip nói, chờ người dùng xem; T063 2026-11-12: lỗi giả lập 1 rồi 2 lượt → ảnh tĩnh + dải cảnh báo, bật lại → video; tắt fork giữa show → 2 lượt lỗi, ảnh tĩnh, show chạy tiếp; bật lại fork → `renderer_restarted`; sửa `host.js` để video tự phát sau khi fork bật lại lúc đang ảnh tĩnh; T062 2026-11-12: tự kiểm bằng bộ ghi luồng + Chrome DevTools, SC-003 đạt (80 câu), SC-004 đạt sau khi fork bỏ mọi tiếng nói vào trước `stop` (1,0–1,5 s → 0,00–0,56 s), tạm dừng không còn phát câu đã gửi fork mà chưa nghe (12 lần chạy lại, 0 lỗi), comment hỏi giá đúng; US2 #1 giữ clip nói chưa đạt → T064–T066; US2 2026-11-11: T048–T061 phần code + test (renderer lỗi/nối lại, `SwitchingRenderer` tự về ảnh tĩnh sau 2 lượt lỗi, `record_render_outcome` + `render_stats` từ director và script runner, `GET /api/avatar`, `POST /api/avatar/lipsync`, `/health` có `avatar`, tin `mode` ở trang host, dải cảnh báo + nút bật lại ở trang điều khiển, fork bắt OOM/lỗi suy luận → `error` + về clip chờ); còn T062–T063 [GPU] (máy tự chạy bằng bộ tự kiểm quickstart §11, thêm 2026-11-12: bộ ghi luồng của fork + `scripts/selfcheck/lipsync_check.py`); US1 xong; T047 đạt 2026-11-11: 12/12 ảnh Chrome headless (6 chờ, 6 nói) có nhãn "AI" trong khung hình, nhãn CSS ẩn khi video chạy; T046 đạt 2026-11-11: 10 đoạn VieNeu `Thùy Dung` 5,0–7,0 s chấm 10/10 khớp, `first_frame_s` 0,92–1,16 s, `render_fps` 24,8–25,3, đoạn 34,9 s và đoạn im lặng đạt, VRAM 2 656 MB không đổi; T045 đạt 2026-11-10: clip Wan 2.2 rung nhẹ liên tục, làm mượt bằng `scripts/avatar_clips/smooth_clips.py` (quickstart bước 4b), clip chờ mượt 5 khung, `talk_02` mượt 3 khung đặt lên đầu, `talk_01` giữ gốc; trước đó: T043 người dùng viết `character.json` / bổ sung `provenance.json`; T044–T047 `[GPU]` laptop, cần T043)
- `analyze`: 2026-11-06 Sẵn sàng implement (0 CRITICAL, 1 HIGH, 7 MEDIUM, 7 LOW). HIGH: giữa hai câu cùng lượt fork về clip chờ (im lặng ≥ 1 lô suy luận, giao thức không có tin hết lượt), trái US2 #1; nên sửa fork-protocol + T014/T042/T066 trước khi implement. MEDIUM: T072 thiếu test, nút giảm kích thước khung (R8) không có task, Owns của agent, trường hợp biên (câu > 30 s, tiếng im lặng, đóng host), FR-019 hiển thị ↔ ack, test chặn `/api/debug/speak-audio` khi tắt router debug, đo lặng giữa câu / câu đầu show ở US4. Sửa 2026-11-06 theo đồng ý của người dùng: HIGH theo cách (b), fork giữ clip nói tối đa `LIVETALKING_HOLD_S` (1,5 s, miệng khép) sau mỗi câu bằng `ClipScheduler` trong `rotation.py` (research R7, fork-protocol §4, T014, T042, T064–T067, T062); MEDIUM: thêm T083 (test `lipskip`), nút (2) R8 vào T075, trường hợp biên vào T046/T050, ghi chú FR-019 ↔ ack, 404 khi tắt router debug vào T028, đo lặng giữa câu / câu đầu show + chọn `LIVETALKING_LEAD_S` vào T073; LOW: T003 đã có sẵn, plan thêm `test_script_runner.py` và sửa FR-004/005, nhãn US1 #1/#4 sang T045, số đo ghi vào ADR-041 + quickstart. Còn để người dùng quyết: Owns của agent cho file mới (chỉ chặn `/sdd.dispatch`), 3 TODO (nơi đẩy fork R2, logo LiveTalking R5, quy ước `CUSTOMER_ID`)
- `adrs`: ADR-004, 008, 016, 019, 023, 025, 029, 036, 041–048 (041–047 chốt 2026-11-06, 048 chốt đủ 2026-11-07)
- `depends_on`: 001 (pipeline, mock comment); 003 (giọng thật)
- `agents`: ai-media (chính: fork, renderer, CLI avatar, trang host); ai-orchestrator (core/protocols, ShowDirector, route, trang điều khiển); ai-qa (fork giả, contract test)
- `roadmap`: M1b (fork LiveTalking, nhãn AI ghép vào frame)
- `open`: chờ người dùng (gói duyệt 2026-11-12): đổi mặc định `LIVETALKING_LEAD_S` 0 → 2,5; chọn batch 16 (mượt) hay 8 (nhanh); bộ clip nhỏ hơn (R8) hoặc RunPod (hỏi chi phí); xem bản ghi lượt bình luận (`render_fps` ~18 khi VieNeu vừa tổng hợp vừa phát); clip nói có đoạn đầu ngửa/nghiêng (`talk_02` khung ~64–120, `talk_01` ~32–60, quickstart bước 8); duyệt sửa spec phiên 2026-11-12; T068 (3 người xem), T080 (Meet). Đã biết: OOM giữa câu bỏ cả câu khác đã xếp trong fork (ghi chú T061); clip 24 fps so với fork 25 fps cần xem bằng mắt; lệch ack ↔ Chrome của lượt bình luận trung vị 0,63 s, p95 0,81 s (30 lượt, 2026-11-13, quickstart bước 9), bình luận → nghe tiếng p95 ≈ 2,9 s. TODO chính: nơi đẩy nhánh `ailive` (R2), license checkpoint `wav2lip256.pth` (RISKS L11), 3 TODO chạy fork trên RunPod (`docs/RUNPOD.md`)

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

### 009-live-scene-layout
- `folder`: [specs/009-live-scene-layout/](../specs/009-live-scene-layout/)
- `status`: Done (2026-11-13; plan → implement tự làm theo ủy quyền "chạy liên tục"; phần cần người ở `open`). Hướng B của ghi chú 2026-11-07: ghép lớp ảnh tĩnh + chữ vào chính khung hình gửi đi, không tạo lại
  clip, không tách nền người, không thêm phông (host giữ đầy khung dọc)
- `artifacts`: [spec](../specs/009-live-scene-layout/spec.md): 3 user story (P1 bàn trước host bày mọi sản phẩm + thẻ tên/giá trong
  khung dọc 9:16; P2 làm nổi + to sản phẩm đang nói; P3 phụ đề trong khung), 22 FR, 7 SC · [plan](../specs/009-live-scene-layout/plan.md)
  (cổng Hiến pháp đạt) · [research](../specs/009-live-scene-layout/research.md) R1–R12 ·
  [data-model](../specs/009-live-scene-layout/data-model.md) · [contracts](../specs/009-live-scene-layout/contracts/) (scene-set,
  fork-protocol, api, adapters) · [quickstart](../specs/009-live-scene-layout/quickstart.md) ·
  [tasks](../specs/009-live-scene-layout/tasks.md): 38 task (Setup 3, Foundational 6, US1 17, US2 4, US3 2, Hoàn thiện 6), `[GPU]` T026, T034
- `tasks`: 38/38
- `results` (2026-11-13): SC-001 30/30 ảnh không đổi trong vùng mặt/nhãn/watermark; SC-002 12/12 thẻ khớp nguyên văn giá và khuyến mãi (kể cả sau thay file; một tên dài bị cắt bằng "…"); SC-003 146 lần đổi món nổi, lệch so với ack phát câu đầu 1–17 ms (p95 0,016 s); SC-005 show 30 phút, thay file ở phút 15, 356 mẫu, 0 lỗi sản phẩm; SC-004 (GPU laptop, 2 show 10 phút) `render_fps` 25,10 → 25,10, `scene_ms` trung vị 4,66 ms, lặng p95 3,05 → 2,14 s; T026: cảnh trong WebRTC dưới watermark + nhãn, tắt fork → ảnh tĩnh giữ cảnh
- `analyze`: 2026-11-13 Sẵn sàng implement (0 CRITICAL, 0 HIGH, 1 MEDIUM, 1 LOW). Mọi FR có task; MEDIUM: SC-002/003/005 chưa có
  task đo → thêm T038; LOW: FR-020 chưa có test riêng → thêm vào T012. Đã sửa ngay
- `adrs`: ADR-051 (Pillow trực tiếp, font của máy), ADR-052 (ghép cảnh, `scene_layer`, bộ cảnh ngoài git, làm nổi theo ack phát),
  cả hai tự chốt theo ủy quyền, chờ xác nhận; ADR-044 (nhãn "AI" trong khung, giữ watermark), ADR-046 (tự về ảnh tĩnh), ADR-016 (ảnh tĩnh + nhãn CSS), ADR-036 (ảnh tạo bằng
  AI, chỉ áp dụng cho ảnh bàn). Có thể cần ADR mới ở plan nếu vẽ chữ tiếng Việt có dấu trong khung cần thêm phụ thuộc (ADR-044 đã loại
  Pillow vì "chưa cần")
- `depends_on`: 005 (khung hình nhân vật, nhãn, watermark, tự về ảnh tĩnh); 004 (sản phẩm của câu đang phát, cho US2); 001 (dữ liệu
  sản phẩm, thay file giữa phiên)
- `agents`: ai-media (chính: ghép cảnh vào khung trong fork và ở chế độ ảnh tĩnh, trang host); ai-orchestrator (cấu hình, gửi sản phẩm
  nổi, bảng độ trễ, trang điều khiển); ai-brain (định dạng giá/khuyến mãi từ dữ liệu sản phẩm); ai-qa (test vùng cấm, khớp thẻ ↔ file)
- `roadmap`: M1b mục "Bố cục cảnh live quanh host"; dùng cho M1d
- `open`: không còn `[NEEDS CLARIFICATION]`. Làm rõ 2026-11-13: khung dọc 9:16; khách chỉ có ảnh chụp sản phẩm, mình chỉnh trước phiên
  (cắt nền, cỡ, sáng, bóng; không vẽ thêm chi tiết, giữ ảnh gốc + hồ sơ chỉnh, SC-007); host giữ đầy khung, phông của clip làm phông sau;
  mọi sản phẩm bày trên bàn cùng lúc, món đang nói to hơn. Để plan: cách cắt nền (tay hay công cụ; model mới cần ADR), cách vẽ chữ
  tiếng Việt trong khung, định dạng giá, cỡ/hiệu ứng làm nổi. Giả định: phụ đề trong khung mặc định tắt cho demo Meet. Chờ người dùng (2026-11-13): ảnh thật của khách thay ảnh mẫu "ẢNH MẪU" + `provenance.json` (SC-007), SC-006 (3 người xem, gộp 005 T068), xác nhận ADR-051/052, license font (RISKS L12)

### 007-demo-readiness
- `folder`: [specs/007-demo-readiness/](../specs/007-demo-readiness/)
- `status`: In progress (2026-11-13; người dùng: "Tiếp tục feature mới mà không đụng đến LLM API Free", làm liên tục theo ủy quyền).
  Phần máy xong 2026-11-13, chỉ còn T058 chờ người dùng
- `artifacts`: [spec](../specs/007-demo-readiness/spec.md): 4 user story (P1 kiểm tra trước demo; P2 canh show khi đang chạy; P3 báo cáo
  tổng duyệt 30 phút theo PRD tiêu chí 3, 4; P4 làm video dự phòng 2–3 phút), 21 FR, 7 SC; [plan](../specs/007-demo-readiness/plan.md),
  [research](../specs/007-demo-readiness/research.md) R1–R9, [data-model](../specs/007-demo-readiness/data-model.md),
  [contracts](../specs/007-demo-readiness/contracts/) (api, files, cli), [quickstart](../specs/007-demo-readiness/quickstart.md), [tasks](../specs/007-demo-readiness/tasks.md)
- `tasks`: 58/59 (2026-11-13: T053 kiểm sạch; T054–T057 trên GPU laptop, quickstart "Kết quả kiểm chứng" §5, §6, §T056, §T057: show 30
  phút 327 câu 0 lỗi, lặng p95 3,0 s so 005 2,98 s; 2 cảnh báo mất tiếng sai → thêm `WATCHDOG_AUDIO_ACK_LIPSYNC_S` 6 s; video dự phòng
  157 s `Đạt`; tắt fork giữa show: `fork_lost` sau 0,6 s, bấm bật lại sớm thì bấm lại (chữ banner + RUNBOOK đã sửa); T059 xong.
  Trước đó: T001–T026 xong: Setup, Foundational, US1 kiểm tra trước demo; T027–T035 xong: US2 canh show; cả hai kiểm bằng trình duyệt ở quickstart "Kết quả kiểm chứng" §1, §2; T036–T042 xong: US3 báo cáo tổng duyệt, §3; T043–T050 xong: US4 video dự phòng phần code; T051–T052 xong: RUNBOOK, ARCHITECTURE, RISKS Q25–Q27, src/README) (Setup T001–T004, Foundational T005–T017, US1 T018–T026, US2 T027–T035, US3 T036–T042, US4 T043–T050, Polish
  T051–T059; GPU T054–T056; T058 chờ người dùng)
- `analyze`: 2026-11-13: Sẵn sàng implement (0 CRITICAL, 0 HIGH, 4 MEDIUM, 4 LOW): nhãn Điều V/VII/IX trong bảng constitution của plan
  lệch tên; `HOST_STATUS` mỗi giây sẽ bị `/ws/control` chuyển hết lên trang điều khiển; `[P]` sai ở T028/T029, T043/T044 (cùng file);
  FR-012 so với "tắt canh" còn SC-004 so với 005 T073; đã sửa theo ủy quyền làm liên tục
- `adrs`: ADR-057 (Đề xuất, đã ghi trong DECISIONS: tự bỏ câu kẹt, tín hiệu tab host, video dự phòng `verbatim` + recorder, nguồn điện qua ctypes; thêm hai ngưỡng mất tiếng sau T054); liên quan ADR-023 (nhép miệng trên laptop), ADR-026, ADR-040
- `depends_on`: 004 (show, chế độ dự phòng), 005 (fork, bộ ghi luồng, `lipsync_health`), 009 (cảnh, ảnh mẫu), `docs/RUNBOOK.md`
- `agents`: ai-orchestrator (kiểm tra, canh show, báo cáo, trang điều khiển); ai-media (tab host báo khung/tiếng, video dự phòng); ai-qa
- `roadmap`: M1d (phiên 30 phút, video dự phòng, runbook)
- `open`: không còn `[NEEDS CLARIFICATION]`; clarify 2026-11-13 tự chọn khuyến nghị (tự bỏ câu kẹt ở 15 giây; video dự phòng mặc định
  đọc nguyên văn file sản phẩm), người dùng xem lại ở gói duyệt. Chờ người dùng ([OPEN.md](OPEN.md) §2, §4): xem video dự phòng + thử
  Meet (T058), xác nhận ADR-057, xóa `AILIVE_RECORD_DIR` khỏi `.env` trước demo, tổng duyệt 30 phút với LLM thật ở T-1 ngày

### 010-natural-mouth-shapes
- `folder`: [specs/010-natural-mouth-shapes/](../specs/010-natural-mouth-shapes/)
- `status`: In progress (2026-11-13; specify → implement tự làm liên tục theo ủy quyền, cho phép cài tool mỗi thứ một ADR). Phần máy xong,
  còn 2 task chờ người dùng (T018 chấm A/B, T019 show nếu đổi mặc định); T026 xong 2026-11-16 (giữ ngưỡng 35/20/30); tra cứu repo khác ở research R13
- `artifacts`: [spec](../specs/010-natural-mouth-shapes/spec.md): 3 user story (P1 khẩu hình giống người hơn trong show; P2 bộ đo khách
  quan + gói xem mù; P3 clip nói chỉ dùng đoạn mặt thẳng), 14 FR, 7 SC · [plan](../specs/010-natural-mouth-shapes/plan.md) (cổng Hiến pháp
  đạt) · [research](../specs/010-natural-mouth-shapes/research.md) R1–R12 · [data-model](../specs/010-natural-mouth-shapes/data-model.md)
  · [contracts](../specs/010-natural-mouth-shapes/contracts/) (mouth-method, mouth-eval) ·
  [quickstart](../specs/010-natural-mouth-shapes/quickstart.md) (§7 gói duyệt) · [tasks](../specs/010-natural-mouth-shapes/tasks.md):
  32 task (Setup 4, Foundational 3, US2 7, US1 5, US3 7, Hoàn thiện 6), `[GPU]` T010–T014, T019, T025, T026
- `tasks`: 30/32
- `results` (2026-11-13, 24 câu bộ v1, `demo_host_01__talk_01`, GTX 1650 Ti): `w2l` LSE-C 6,394, closure 0,677, open_ratio 1,230,
  spread_ratio 0,985, corr 0,220, `render_fps` 28,8. Không núm hậu kỳ nào (paste/color/sharpen/gain/ref offset/ref môi khép) đạt SC-001.
  `shift=-1`: lệch hình–tiếng SyncNet −1 → 0 khung, corr +16%, closure −6%, LSE-C −0,7%. SC-002/003 chưa đạt với mọi cách (giới hạn của
  wav2lip256 + clip nói hiện có); SC-005 đạt với mặc định `w2l` (số show 30 phút của 005); SC-006 đạt hiển nhiên (ngưỡng mặc định không
  loại khung nào, R11); SC-007 đạt (r4 trùng r2/r3 từng chữ số); SC-004 chờ người xem. MuseTalk 1.5 ~0,7 khung/giây trên laptop → loại
  r5 (bộ câu v2, thêm nhóm số): baseline mới cho lần đo sau, `s1` LSE-C 6,465 ≥ `w2l` 6,399 nhưng vẫn 1/4 chỉ số hình miệng → SC-001 chưa đạt
- `analyze`: 2026-11-13 tự chạy sau tasks (tasks viết sau khi đã làm, xem ghi chú tasks.md): mọi FR có task; FR-014 không dùng (không
  tinh chỉnh model); SC-001/002/003 ghi rõ "chưa đạt" thay vì sửa ngưỡng
- `adrs`: ADR-053 (MediaPipe Face Landmarker, sửa bởi ADR-056), ADR-054 (SyncNet + python_speech_features, chỉ đo), ADR-055 (núm
  `LIVETALKING_MOUTH_METHOD`, mặc định `w2l`, loại MuseTalk trên laptop), ADR-056 (loại đoạn clip nói đầu nghiêng lúc `prepare`); ADR-023,
  ADR-041, ADR-044
- `depends_on`: 005 (fork, wav2lip256, clip nhân vật, bảng độ trễ); 003 (VieNeu đọc bộ câu)
- `agents`: ai-media (fork, bộ đo, prepare); ai-orchestrator (cột "Miệng" bảng độ trễ); ai-qa (test)
- `roadmap`: M1b mục "Khẩu hình giống người"
- `open`: không còn `[NEEDS CLARIFICATION]`. Chờ người dùng (gói duyệt quickstart §7): chấm A/B `out/mouth/runs/r4/ab/PHIEU.md` (≥ 3
  người); giữ hay siết ngưỡng góc đầu 35/20/30; nếu khẩu hình vẫn chưa đủ: quay clip nói mới hay thử model mạnh hơn trên GPU thuê (tốn tiền)

### 006-obs-output
- `folder`: [specs/006-obs-output/](../specs/006-obs-output/)
- `status`: In progress (2026-11-13; specify → implement tự làm liên tục theo ủy quyền, người dùng xem lại ở gói duyệt). Phần không GPU
  xong: `/obs`, `/ws/host?role=` (4000/4001), `OUTPUT_MODE=meet|obs` (`webrtc` cũ chạy như meet), kiểm tra trước demo và canh show
  theo chế độ (`WATCHDOG_HOST_STALE_S`), trang điều khiển "Đầu ra", RUNBOOK §8, ARCHITECTURE. Kiểm: pytest 2461 passed, ruff sạch,
  Chrome MCP (quickstart §5). T029: OBS 33.0.1 portable đã tải và dựng cấu hình ngoài repo, chạy `obs64.exe` bị bộ phân quyền chặn
- `artifacts`: [spec](../specs/006-obs-output/spec.md): 3 user story (P1 thêm AI host vào OBS thành một nguồn có tiếng, không bấm gì;
  P2 chạy lâu, tự nối lại, trang host không cướp tiếng; P3 kiểm tra trước demo + cảnh báo khi đầu ra OBS đứt), 14 FR, 7 SC;
  [plan](../specs/006-obs-output/plan.md) (Browser Source trang `/obs`, vai `obs` > `host` với mã đóng 4001, nhả phiên WebRTC của fork,
  `OUTPUT_MODE=meet|obs`, không thư viện mới); [research](../specs/006-obs-output/research.md) R1–R12;
  [data-model](../specs/006-obs-output/data-model.md); [contracts/api.md](../specs/006-obs-output/contracts/api.md);
  [quickstart](../specs/006-obs-output/quickstart.md); [tasks](../specs/006-obs-output/tasks.md)
- `tasks`: 30/35. Còn: T018, T019, T030, T031 `[GPU]`; T029 `[~]` (chờ cho phép chạy OBS)
- `analyze`: 2026-11-13 Sẵn sàng implement (0 CRITICAL, 1 HIGH, 1 MEDIUM, 2 LOW, đã sửa hết: luật nhịp ngừng `WATCHDOG_HOST_STALE_S` cho FR-010 vào contracts §8 + T021/T024; T031 ghi rõ show 30 phút; T012 kiểm ảnh chờ trước show; T027 thêm tắt chế độ ngủ)
- `adrs`: ADR-058 (Chấp nhận 2026-11-19: bỏ M1c YouTube; OBS Browser Source `/obs`; vai obs > host; `OUTPUT_MODE=meet|obs`), ADR-059 (Chấp nhận, người dùng xác nhận 2026-11-19: OBS portable làm công cụ kiểm ngoài repo); rủi ro Q28–Q32
- `depends_on`: 005 (fork, khung nhép miệng, ảnh tĩnh dự phòng), 007 (kiểm tra trước demo, canh show), 009 (cảnh trong khung)
- `agents`: ai-orchestrator (vai kết nối, kiểm tra, canh show); ai-media (trang đầu ra OBS); ai-qa
- `roadmap`: M2 "Output cho OBS" (làm sớm); thay đề xuất `006-youtube-live` (M1c) vì người dùng không live trên YouTube
- `open`: không còn `[NEEDS CLARIFICATION]`; clarify 2026-11-13 tự chọn khuyến nghị (xem thử trong cửa sổ OBS, đầu ra OBS ưu tiên hơn
  trang host, chế độ phát chọn lúc khởi động mặc định Meet, không phụ đề trong khung OBS); TODO plan: đo thời gian fork nhả phiên WebRTC
  (R5), `framesDecoded` và tiếng vào mixer trong CEF của OBS (R3), bộ tự kiểm đọc được Fragmented MP4 của OBS không (R10)

### 011-ultralight-live-lipsync
- `folder`: [specs/011-ultralight-live-lipsync/](../specs/011-ultralight-live-lipsync/)
- `status`: In progress (2026-11-19, Setup + Foundational xong trừ T003, US1 phần code T010–T035 xong; tasks 2026-11-19; plan 2026-11-19, ADR-067–069 Chấp nhận; clarify 2026-11-19, ADR-066). Mở theo ADR-064 mục 4 và ADR-060 mục 5 trong lúc chờ Kaggle huấn luyện model dev
- `artifacts`: [spec](../specs/011-ultralight-live-lipsync/spec.md): 3 user story (P1 chạy show kịch bản bằng model riêng của
  `demo_host_02`, mặc định vẫn Wav2Lip; P2 so sánh với Wav2Lip theo ngưỡng ADR-060 mục 5 + gói xem mù; P3 đổi thầy dev/prod bằng thiết
  lập và kiểm tra trước demo chặn model sai), 16 FR, 8 SC; [plan](../specs/011-ultralight-live-lipsync/plan.md),
  [research](../specs/011-ultralight-live-lipsync/research.md) (R1–R11, 3 TODO đo khi có model: khung im lặng, fps/VRAM, mép bàn),
  [data-model](../specs/011-ultralight-live-lipsync/data-model.md), contracts
  ([lipsync-selection](../specs/011-ultralight-live-lipsync/contracts/lipsync-selection.md),
  [lipsync-compare](../specs/011-ultralight-live-lipsync/contracts/lipsync-compare.md)),
  [quickstart](../specs/011-ultralight-live-lipsync/quickstart.md); không phụ thuộc mới;
  [tasks](../specs/011-ultralight-live-lipsync/tasks.md) (63 task: Setup 3, Foundational 6, US1 32, US2 9, US3 7, Hoàn thiện 6;
  25 `[P]`, 8 `[GPU]` laptop)
- `tasks`: 34/63, 0 `[~]` (T001, T002, T004–T035; T003 chờ Kaggle v3 chạy xong; T036–T041 cần model và GPU laptop)
- `analyze`: 2026-11-19 Sẵn sàng implement (0 CRITICAL, 0 HIGH, 5 MEDIUM, 8 LOW); đã sửa M1–M5, L1–L6 cùng ngày ("ok sửa đi"),
  L7 (TODO đóng ở T037/T038/T040) và L8 (dựa vào test 005/007) giữ nguyên
- `adrs`: ADR-060 (Ultralight, ngưỡng mục 5), ADR-062 (demo giữ Wav2Lip tới khi đạt), ADR-064 (hai thầy MuseTalk dev / InfiniteTalk
  prod), ADR-065 (chữ nhãn AI), ADR-066 (`demo_host_02` cho khách demo; đánh giá ngay khi model Kaggle xong (sửa 2026-11-19), đạt thì demo dùng thầy
  MuseTalk), ADR-067 (Chấp nhận: chọn model bằng `LIVETALKING_MODEL` + `LIVETALKING_ULTRALIGHT_TEACHER`, fork kiểm bản ghi cài đặt,
  `lipsync_models`, khối `lipsync`), ADR-068 (Chấp nhận: nhân vật có sẵn bàn), ADR-069 (Chấp nhận: lệnh `lipsync-compare`);
  ADR-023, ADR-044, ADR-055
- `depends_on`: 005 (fork, bảng độ trễ, nối lại), 007 (kiểm tra trước demo, canh show), 009 (cảnh live, cần chế độ nhân vật có sẵn bàn),
  010 (bộ đo khẩu hình, bộ câu v2, gói xem mù); model dev từ Kaggle `ai-host-train-ultralight-demo-host-02`
- `agents`: ai-media (fork `app.py`/`ailive_ext`, `run.ps1`, `character.json`, cảnh không bàn); ai-orchestrator (cấu hình,
  `hello`/health `lipsync`, kiểm tra trước demo, trang điều khiển, lệnh `lipsync-compare`); ai-qa (test không GPU, fork giả)
- `roadmap`: M1b mục "Khẩu hình giống người"
- `open`: không còn `[NEEDS CLARIFICATION]` (clarify 2026-11-19: FR-015, FR-016 → ADR-066); ADR-067–069 Chấp nhận 2026-11-19; 3 TODO research
  (R6, R7, R9) chờ model dev từ Kaggle

### 012-product-image-upload
- `folder`: [specs/012-product-image-upload/](../specs/012-product-image-upload/)
- `status`: In progress (2026-11-20; Tasked cùng ngày). Mở theo yêu cầu người dùng lúc chạy demo2: đổi ảnh sản phẩm kịp trên trang điều khiển, không tạo video mới
- `artifacts`: [spec](../specs/012-product-image-upload/spec.md): 4 user story (P1 thay ảnh một sản phẩm giữa phiên, xem trước, lên live
  ≤ 2 s; P2 chuẩn bị bộ sản phẩm mới: file + ảnh, live không đổi cho tới khi bấm "Áp dụng bộ mới"; P3 về ảnh trước, gỡ ảnh; P2 "AI vừa
  nói" và xem dữ liệu sản phẩm đã nạp), 24 FR (kể cả FR-015a), 7 SC. Làm rõ 2026-11-20: không ghi nguồn ảnh/ảnh gốc, chỉ một ô xác nhận
  quyền dùng; đổi bộ sản phẩm chuẩn bị đủ rồi áp một lần. [plan](../specs/012-product-image-upload/plan.md) (cổng hiến pháp 2 lượt Đạt,
  Điều III có ghi chú), [research](../specs/012-product-image-upload/research.md) R1–R12,
  [data-model](../specs/012-product-image-upload/data-model.md), contracts
  [api](../specs/012-product-image-upload/contracts/api.md) (15 endpoint mới) +
  [scene-set](../specs/012-product-image-upload/contracts/scene-set.md) (phần thêm vào hợp đồng 009: `uploads/`),
  [quickstart](../specs/012-product-image-upload/quickstart.md). Không thêm thư viện, không thêm biến môi trường. Rủi ro mới Q37–Q39.
  [tasks](../specs/012-product-image-upload/tasks.md): 70 task (Setup 2, nền 10, US1 15, US2 14, US4 13, US3 7, hoàn thiện 9), 30 `[P]`,
  2 `[GPU]` (SC-001, SC-006 trên GPU laptop); MVP = T001–T027
- `tasks`: 66/70 + 3 `[~]` (2026-11-20): US1–US4 xong, hoàn thiện T055–T066 xong (T065 đo bằng máy, số ở [LOG](LOG.md) và
  `out/012_review/README.md`; T066 2799 passed, ruff sạch). `[~]`: T067 (SC-001), T068 (SC-006) chờ buổi GPU laptop; T069 gói duyệt đã soạn,
  chờ người dùng xem và bấm giờ tay SC-002/SC-005. Còn T070 `/update-context`
- `analyze`: 2026-11-20 Sẵn sàng implement (0 CRITICAL, 0 HIGH, 4 MEDIUM, 4 LOW; đã sửa theo đề xuất, người dùng đồng ý: plan bỏ
  `catalog.products[].image`; T015 thêm ca ảnh tĩnh và hai `apply` sát nhau; T027 hủy xem trước khi món đổi ảnh; T065 đo độ trễ SC-007;
  plan ghi FR-015a, `test_script_runner.py`; spec Điều II bỏ "ảnh gốc"; TODO Q37 giữ tới trước Shopee)
- `adrs`: ADR-071 (Chấp nhận 2026-11-20: `SCENE_DIR/uploads/` + `images.json`, xác nhận quyền dùng thay hồ sơ nguồn 009), ADR-072 (Chấp nhận 2026-11-20: áp bộ mới
  một lần dưới khóa vẽ, bộ chuẩn bị chỉ ở bộ nhớ); ADR-065 (quy định nội dung AI Shopee); ADR của 009 (cảnh ghép lúc phát); mở lại một
  phần "Ngoài phạm vi" của 009 (tải/thay ảnh, không chỉnh ảnh trong app)
- `depends_on`: 009 (bộ cảnh, bộ nạp, `SceneController`, vùng cấm, FR-013 thẻ theo file nội dung), 001 (nạp file nội dung trên trang
  điều khiển), 004 (sự kiện `sentence` thêm `topic`), 007 (kiểm tra trước demo báo `missing_confirmation`, `bad_uploads` là LỖI)
- `agents`: ai-media (scene/: bộ nạp, `ProductImageStore`, `SceneController.preview/reload/hold`); ai-orchestrator (app/: route, bộ chuẩn
  bị, "AI vừa nói", trang điều khiển; ops/readiness; `topic` trong script_runner); ai-brain (`product_detail`); ai-qa (test không GPU,
  bộ file sai SC-004)
- `roadmap`: M1d (đổi sản phẩm khi tổng duyệt và demo); dùng lại ở M2
- `open`: – (TODO trong Q37: trước Shopee có cần ghi người gửi ảnh không)

## Đề xuất chưa tạo

Mỗi dòng là một lần `/sdd.specify`. Thứ tự theo ROADMAP; người dùng có thể gộp, tách hoặc đổi.

| Đề xuất ID | Nội dung | Mốc | Cần GPU |
|-----------|----------|-----|---------|
| ~~002-product-qa-eval~~ | Đã gộp vào `001` (User Story 5), chốt khi clarify 2026-10-30 | M1a | Không |
| ~~006-youtube-live~~ | Bỏ 2026-11-13: người dùng không live trên YouTube; số 006 dùng cho `006-obs-output` | M1c | – |

Ghi chú 009-live-scene-layout (2026-11-07) đã chuyển vào [spec 009](../specs/009-live-scene-layout/spec.md) (Bối cảnh, Giả định, Ngoài phạm vi).
