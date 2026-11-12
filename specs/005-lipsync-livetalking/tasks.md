# Tasks: AI host chuyển động tự nhiên, nhép miệng realtime trên laptop

- **Feature ID:** `005-lipsync-livetalking` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[GPU]**: cần GPU; chạy trên GPU laptop GTX 1650 Ti trước (ADR-023), RunPod chỉ dự phòng và cần người dùng duyệt chi phí; gom vào đợt GPU
  (xem cuối file).
- **[US#]**: thuộc user story nào (US1...US4). Phase Setup, Foundational và Hoàn thiện không gắn nhãn này.
- Mỗi task ghi **đường dẫn file cụ thể**. Một task chỉ đủ nhỏ để xong và kiểm chứng trong một lần làm.
- Thứ tự phase theo ưu tiên trong spec: US1 (P1) → US2 (P2) → US3 (P3) → US4 (P4).
- **(ADR-048)**: task chỉ làm được sau khi người dùng duyệt ADR-048 (khai báo dependency, dựng venv fork, tải model). Mọi task sửa
  `vendor/livetalking/` cần bản clone của T008. Phần app (renderer, route, trang, test với fork giả) không cần fork thật, chỉ cần T005.
- Đường dẫn `vendor/livetalking/...` nằm ngoài git của repo này (nhánh `ailive` của fork, plan §Mã nguồn fork). Các sửa trong `app.py` và
  `avatars/base_avatar.py` của fork đánh dấu `# ailive:`.

## Phase 1: Setup

- [x] T001 Hỏi người dùng duyệt ADR-041 đến ADR-047; khi được duyệt, chuyển sang `Đã chốt` trong `docs/DECISIONS.md` và bỏ dòng
  ADR-041–047 khỏi `progress/OPEN.md` §2. Người dùng duyệt cả 7 ngày 2026-11-06
- [x] T002 Hỏi người dùng duyệt **riêng** ADR-048 (khai báo `websockets`; venv fork torch 2.9.1 cu128/cu126 + requirements LiveTalking; tải tay
  `wav2lip256.pth`, `s3fd.pth`). Có thể duyệt từng phần: phần `websockets` (đã có sẵn trong `.venv`, bản 17.3, kéo theo `uvicorn[standard]`)
  mở khóa toàn bộ phần app; phần venv fork + model mở khóa T008, T009 và các task `vendor/`. Ghi kết quả vào `docs/DECISIONS.md`,
  `progress/OPEN.md` §2. 2026-11-06: người dùng chỉ duyệt phần `websockets`; venv fork + model còn chờ
- [x] T003 [P] Thêm `vendor/` vào `.gitignore` (plan §Cấu trúc mã nguồn). Đã có sẵn ở `.gitignore` (analyze A9)
- [x] T004 [P] Sửa khối Avatar / LiveTalking trong `.env.example` theo contracts/events.md §5: thêm `CUSTOMER_ID`, `AVATAR_DIR`,
  `LIVETALKING_PYTHON`, `LIVETALKING_FIRST_FRAME_TIMEOUT_S`, `LIVETALKING_RECONNECT_MAX_S`, `LIVETALKING_LEAD_S`, `AVATAR_FALLBACK_AFTER` và
  bốn biến chỉ fork đọc `LIVETALKING_BATCH_SIZE`, `LIVETALKING_LIP_EVERY_N`, `LIVETALKING_TRANSITION_S`, `LIVETALKING_HOLD_S`; sửa comment `AVATAR_MODE` (livetalking
  chạy trên GPU laptop, RunPod dự phòng); bỏ TODO cổng cũ của `LIVETALKING_URL` (data-model §1)
- [x] T005 Khai báo `websockets` trong `pyproject.toml` bằng `uv add websockets` (cập nhật `uv.lock`) **(ADR-048, phần websockets)**
- [x] T006 [P] Viết `scripts/livetalking/setup.ps1`: clone `https://github.com/lipku/LiveTalking` vào `vendor/livetalking`, checkout
  `LIVETALKING_UPSTREAM_COMMIT`, tạo nhánh `ailive`, `uv venv --python 3.12` trong `vendor/livetalking/.venv`, cài torch cu128 + requirements,
  không tải model, cuối cùng in hướng dẫn tải tay (fork-protocol §5, research R11, R14). Giữ nguyên các `TODO:` của plan (SHA ghim, nguồn
  nhánh `ailive`) cho tới khi có câu trả lời
- [x] T007 [P] Viết `scripts/livetalking/run.ps1`: đọc `.env` của repo, chạy
  `python app.py --model wav2lip --transport webrtc --max_session 1 --listenport 8010 --ailive_character <AVATAR_DIR>` với `AI_LABEL_TEXT`,
  `AI_LABEL_POSITION`, `LIVETALKING_BATCH_SIZE`, `LIVETALKING_LIP_EVERY_N`, `LIVETALKING_TRANSITION_S`, `LIVETALKING_HOLD_S` (fork-protocol §5; tên cờ kiểm lại theo
  `config.yaml` của commit ghim)
- [x] T008 [GPU] Chạy `scripts/livetalking/setup.ps1` và lệnh kiểm CUDA ở quickstart bước 1 (`True`, `GeForce GTX 1650 Ti`, có `sm_75`); sai
  thì làm theo research R11 (cu126 rồi mới hỏi về driver). Ghi dung lượng đã tải và bản torch dùng được vào `docs/DECISIONS.md` ADR-048
  **(ADR-048)**
- [x] T009 Tải tay `wav2lip256.pth` → `vendor/livetalking/models/wav2lip.pth` và `s3fd.pth` →
  `vendor/livetalking/avatars/wav2lip/face_detection/detection/sfd/s3fd.pth` (quickstart bước 3); ghi sha256 hai file vào `docs/DECISIONS.md`
  ADR-048; không commit **(ADR-048)**

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

### Test nền tảng (viết trước, phải FAIL)

- [x] T010 [P] Test cấu hình trong `tests/unit/test_config.py`: mặc định các biến mới khớp `.env.example`; ở `AVATAR_MODE=livetalking` thiếu
  `CUSTOMER_ID` hoặc `AVATAR_ID` → lỗi; `CUSTOMER_ID` sai mẫu `[a-z0-9_-]{1,64}` → lỗi; `LIVETALKING_URL` có host khác `127.0.0.1`/`localhost`
  → lỗi; `AI_LABEL_TEXT` rỗng hoặc ngoài ASCII in được → lỗi ở `livetalking`, vẫn nhận chữ tiếng Việt ở `static`;
  `LIVETALKING_FIRST_FRAME_TIMEOUT_S`, `LIVETALKING_RECONNECT_MAX_S` ≤ 0, `LIVETALKING_LEAD_S` < 0, `AVATAR_FALLBACK_AFTER` < 1 → lỗi; bốn biến
  chỉ fork đọc được miễn khỏi phép so `.env.example` ↔ config (data-model §1)
- [x] T011 [P] Test sự kiện trong `tests/unit/test_events.py`: có `EventType.AVATAR_MODE`, `EventType.LIPSYNC_HEALTH` với payload theo
  contracts/events.md §1; `message` lỗi đi qua `redact`
- [x] T012 [P] Test số đo trong `tests/unit/test_latency.py`: `TurnLatency` có `render_fps`, `infer_fps`, `clips_used` mặc định `None`; `step_stats`
  có `render_fps` p50/p95 chỉ tính lượt có số, lượt `static` không làm sai thống kê (data-model §5, FR-020)
- [x] T013 [P] Test `HostLink` trong `tests/integration/test_ws_host.py`: `ready` có `lipsync_session` → `StaticRenderer.lipsync_session` đổi và
  gọi `on_session_change`; tin `lipsync_session` riêng cũng đổi được; `send_to_host` chuyển tin tới trang host; `ready` không có
  `lipsync_session` chạy như cũ (contracts/adapters.md §5, contracts/api.md §4)
- [x] T014 [P] Viết fork giả `tests/fixtures/fake_fork.py` (cạnh `fake_host.py`) theo contracts/fork-protocol.md §1–§3: `GET /ailive/health`,
  `/ailive/ws?sessionid=` gửi `hello` (có `boot_id`), nhận `sentence_start` + PCM + `sentence_end` rồi gửi `playback_started`, `stats`,
  `sentence_played` theo độ dài tiếng; `health` định kỳ; `pong`; đóng mã 4404 khi sai session; điều khiển được từ test: trễ ack, không ack,
  gửi `error {kind}`, ngắt kết nối, đổi `boot_id` khi nối lại, `clip_id` trong `stats` (giữ nguyên qua các câu `seq > 0` của cùng lượt,
  đổi ở `seq = 0`) (phụ thuộc T005)

### Implement nền tảng

- [x] T015 Thêm biến và kiểm tra mới vào `src/ai_live/core/config.py` (data-model §1; phụ thuộc T010)
- [x] T016 [P] Thêm `AVATAR_MODE`, `LIPSYNC_HEALTH` vào `src/ai_live/core/events.py` (phụ thuộc T011)
- [x] T017 [P] Thêm `AvatarModeState`, `RenderTurnStats`, `LipsyncHealth` và ba trường tùy chọn của `TurnLatency` vào
  `src/ai_live/core/models.py` (data-model §4–§6)
- [x] T018 [P] Thêm `RendererError(kind, message)`, Protocol tùy chọn `RenderOutcomeSink.record_render_outcome(uid, ok)` và
  `RenderStatsSource.render_stats(uid)` vào `src/ai_live/core/protocols.py` (contracts/adapters.md §2)
- [x] T019 Thêm `render_fps` p50/p95 vào `step_stats` trong `src/ai_live/director/latency.py` (phụ thuộc T012, T017)
- [x] T020 Sửa `src/ai_live/director/session_log.py`: ghi `avatar.jsonl` (đổi chế độ, sức khỏe, VRAM đỉnh), thêm `render_fps`, `infer_fps`,
  `clips_used` vào `latency.jsonl`, nhận các `kind` mới của `errors.jsonl` (`lipsync_unavailable`, `vram_oom`, `inference_failed`, `bad_audio`,
  `renderer_restarted`) (contracts/events.md §3–§4; phụ thuộc T017)
- [x] T021 Cho `src/ai_live/avatar/static_renderer.py` thỏa `HostLink`: `lipsync_session`, `send_to_host`, `on_session_change`; nhận
  `lipsync_session` trong `ready` và tin riêng (phụ thuộc T013)

**Checkpoint:** `uv run pytest` xanh với T010–T013; chế độ `static` chạy như cũ.

## Phase 3: User Story 1: Nhân vật chờ và nhép miệng theo tiếng có sẵn (P1) 🎯 MVP

**Mục tiêu:** chuẩn bị một nhân vật từ `character.json` + `provenance.json`, bật fork, thấy nhân vật chờ với miệng khép và nhãn "AI" trong
khung, đưa một file WAV vào thì miệng nhép theo rồi về chờ.

**Kiểm chứng độc lập:** quickstart bước 2, 4, 5, 6 (SC-001, SC-002).

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [x] T022 [P] [US1] Test hồ sơ nhân vật trong `tests/unit/test_character.py`: `load_character` đọc đúng `character.json` hợp lệ;
  `validate_for_session` từ chối: `customer_id` khác `CUSTOMER_ID` (FR-004), thiếu `customer_id` (`missing_customer`), thiếu `provenance.json`
  (`missing_provenance`, US1 #6), thiếu trường hoặc thiếu mục cho một clip (`provenance_incomplete`), `adult_fictional_confirmed` khác `true`
  (FR-005), không có clip `idle` hoặc không có clip `talk` (`kind_missing`, FR-002, FR-012), file clip không có (`missing_file`),
  `prepare.status` khác `ready`; nhận nhiều clip mỗi loại (data-model §2–§3)
- [x] T023 [US1] Test `prepare_character` trong `tests/unit/test_character.py` với `run` giả (không gọi fork thật): JSON `ready` → ghi mục
  `prepare` (trạng thái, `fork_commit`, `frame_size`, từng clip) vào `character.json`; `failed` với `face_count` → lỗi nêu tên clip và số khung
  (US1 #5, FR-003); `size_mismatch`, `bad_video`; mã thoát 2 → `fork_failed`; trạng thái `preparing` trong lúc chạy; nhân vật đã chuẩn bị với
  `fork_commit` khác → log `avatar_prepared_with_other_fork` (FR-001; phụ thuộc T022 vì cùng file)
- [x] T024 [P] [US1] Test CLI trong `tests/unit/test_avatar_cli.py`: `python -m ai_live.avatar check <dir>` in "Hồ sơ hợp lệ" hoặc từng lỗi kèm
  mã, mã thoát khác 0 khi lỗi; `prepare <dir>` gọi `prepare_character` và in bảng clip (contracts/events.md §6)
- [x] T025 [P] [US1] Test đường nói của `LiveTalkingRenderer` với fork giả trong `tests/unit/test_livetalking_renderer.py`: nhận `hello` →
  `ready`; `speak` chưa `ready` → `RendererError("lipsync_unavailable")`; gửi `sentence_start {utterance_id, seq, text, sample_rate:16000}` +
  PCM16 + `sentence_end`; chờ `playback_started` rồi mới gửi `subtitle` cho trang host, `sentence_played` → `subtitle_clear` và `speak` trả về;
  mốc `avatar_first_frame` = lúc nhận `playback_started` câu đầu (FR-019); không có `playback_started` trong `first_frame_timeout_s` →
  `RendererError("timeout")`; `LIVETALKING_LEAD_S` > 0 trả về sớm đúng phần còn lại; `render_stats(uid)` cộng dồn `frames`, `render_fps`,
  `infer_fps`, `clips_used` qua các câu (FR-006, FR-020, US1 #2, #3; contracts/adapters.md §3)
- [x] T026 [P] [US1] Test phần chuyển tiếp của `SwitchingRenderer` trong `tests/unit/test_switching_renderer.py`: `attach`, `detach`,
  `handle_message`, `host_ready`, `ack_timeout_s` đi thẳng tới `StaticRenderer`; ở `livetalking` câu `seq=0` chọn renderer nhép miệng và cả
  lượt giữ renderer đó; ở `static` mọi câu đi tới `StaticRenderer` (contracts/adapters.md §4)
- [x] T027 [P] [US1] Mở rộng `tests/contract/test_renderer_contract.py` cho `LiveTalkingRenderer` (fork giả) và `SwitchingRenderer` ở cả hai
  chế độ: cùng hợp đồng `AvatarRenderer` với `StaticRenderer` (contracts/adapters.md §1)
- [x] T028 [P] [US1] Test route trong `tests/integration/test_avatar_api.py`: `POST /api/debug/speak-audio` với WAV PCM16 mono 16 kHz → 200 có
  `first_frame_s`, `render_fps`; sai định dạng hoặc > 5 MB → 422 `bad_audio`; đang nói → 409 `busy`; renderer lỗi → 503 kèm `kind` (FR-011);
  `POST /api/debug/speak-audio` → 404 khi `APP_ENV` khác `dev` (router debug tắt, analyze A7); `GET /api/host-config` đúng chế độ và nhãn; `/avatar-image` trả `AVATAR_DIR/face.png` ở `livetalking`; app ở `livetalking` với nhân vật của
  khách khác không khởi động và báo khách (FR-004); app ở `static` vẫn dùng `StaticRenderer` như 001/004 (FR-014) (contracts/api.md §1–§3)
- [x] T029 [P] [US1] Test fork trong `vendor/livetalking/ailive_ext/tests/test_ingest.py` (cắt PCM16 thành khung float32 320 mẫu, gắn `datainfo`
  đầu/cuối, độn im lặng khung cuối, `stop` xóa đệm) và `vendor/livetalking/ailive_ext/tests/test_label.py` (nhãn có ở đúng góc trên khung giả;
  chữ rỗng / ngoài ASCII bị từ chối) (fork-protocol §6; phụ thuộc T008) **(ADR-048)**

### Implement US1

- [x] T030 [US1] Viết `src/ai_live/avatar/character.py`: `load_character`, `validate_for_session`, `prepare_character(avatar_dir, fork_python,
  run=...)`, `PrepareError` với 9 mã (data-model §2–§3, contracts/adapters.md §7; phụ thuộc T022, T023)
- [x] T031 [US1] Viết CLI `src/ai_live/avatar/__main__.py`: `prepare`, `check` (phụ thuộc T024, T030)
- [x] T032 [P] [US1] Viết `src/ai_live/avatar/livetalking_renderer.py` phần đường nói: nối `/ailive/ws` theo `HostLink.lipsync_session`, nhận
  `hello`, `speak` theo T025, chờ ack, `subtitle`/`subtitle_clear`, mốc `avatar_first_frame`, cộng dồn `RenderTurnStats`, lưu `LipsyncHealth`
  (phụ thuộc T005, T014, T018, T025)
- [x] T033 [P] [US1] Viết `src/ai_live/avatar/switching_renderer.py` phần chuyển tiếp và chọn renderer ở `seq=0` (phụ thuộc T026)
- [x] T034 [US1] Viết `src/ai_live/avatar/factory.py` `create_renderer(settings, bus)`: `static` → `StaticRenderer`; `livetalking` → kiểm nhân
  vật bằng `validate_for_session` rồi dựng `SwitchingRenderer(LiveTalkingRenderer, StaticRenderer)` với ảnh dự phòng `face.png`
  (contracts/adapters.md §6; phụ thuộc T030, T032, T033)
- [x] T035 [US1] Đổi `AppContext.renderer` sang kiểu `HostRenderer` trong `src/ai_live/app/context.py` và dùng `create_renderer` thay chỗ ném
  `AvatarModeError` trong `src/ai_live/app/main.py` (phụ thuộc T034)
- [x] T036 [US1] Thêm vào `src/ai_live/app/routes.py`: `POST /api/debug/speak-audio`, `GET /api/host-config`, `/avatar-image` trả `face.png` ở
  `livetalking` (contracts/api.md §1–§3; phụ thuộc T028, T035)
- [x] T037 [P] [US1] Sửa `src/ai_live/app/static/host.html`, `src/ai_live/app/static/host.js`: đọc `/api/host-config`; ở `livetalking` mở
  `<video>` + WebRTC `/offer` tới fork, gửi `sessionid` trong `ready` hoặc tin `lipsync_session`, hiện phụ đề theo `subtitle`/`subtitle_clear`,
  không vẽ nhãn CSS (nhãn đã nằm trong khung); `static` giữ nguyên (contracts/api.md §3–§4, FR-018)
- [x] T038 [P] [US1] Thêm khu "Thử bằng tiếng có sẵn" (chọn WAV, gửi `/api/debug/speak-audio`, hiện `first_frame_s`, `render_fps` hoặc lỗi) vào
  `src/ai_live/app/static/control.html`, `src/ai_live/app/static/control.js`, `src/ai_live/app/static/style.css` (contracts/api.md §5, FR-011)
- [x] T039 [US1] Viết `vendor/livetalking/ailive_ext/ingest.py` và gắn route `/ailive/ws`, `GET /ailive/health` vào `vendor/livetalking/app.py`:
  nhận câu, đẩy khung vào `put_audio_frame`, gửi `hello`, `playback_started` (khi WebRTC gửi khung nhép miệng đầu của câu), `sentence_played`,
  `stats`, `health` mỗi 5 s, `pong`, xử lý `stop`, mã 4404 (fork-protocol §1–§3; phụ thuộc T029) **(ADR-048)**
- [x] T040 [US1] Viết `vendor/livetalking/ailive_ext/label.py` và gọi trong `process_frames` của `vendor/livetalking/avatars/base_avatar.py` ngay
  trước `push_video_frame`, sau watermark gốc; fork thoát khi chữ nhãn rỗng hoặc ngoài ASCII; không có cách tắt nhãn; giữ watermark
  "LiveTalking" (fork-protocol §4, FR-010; phụ thuộc T029) **(ADR-048)**
- [x] T041 [P] [US1] Viết `vendor/livetalking/ailive_ext/prepare.py`: đọc `character.json`, chạy `genavatar` cho từng clip vào thư mục
  `<character_id>__<clip_id>`, đếm mặt S3FD ở mọi khung, in một dòng JSON, mã thoát 0/1/2 (fork-protocol §5, FR-001, FR-003; phụ thuộc T008)
  **(ADR-048)**
- [x] T042 [US1] Sửa `vendor/livetalking/avatars/base_avatar.py`: nạp mọi thư mục avatar của nhân vật lúc khởi động, khi im lặng chạy clip chờ
  đi tới đi lùi với khung nền gốc (miệng khép, không suy luận miệng); khoảng giữ clip nói giữa hai câu thêm ở T066 (fork-protocol §4, FR-008; phụ thuộc T040 vì cùng file) **(ADR-048)**
- [x] T043 [US1] Người dùng viết `assets/avatars/demo_host_01/character.json` (data-model §2: `customer_id: "demo_customer_01"`, 2 clip `idle`,
  2 clip `talk`, bản gốc không `_pingpong`) và bổ sung `assets/avatars/demo_host_01/provenance.json` (mục cho từng clip,
  `adult_fictional_confirmed: true` sau khi **người dùng tự xác nhận** gương mặt trông là người trưởng thành, không cố ý giống người có thật,
  FR-005); không commit. Chạy quickstart bước 2: `check` báo "Hồ sơ hợp lệ" và hai lần thử lỗi (US1 #6, FR-002) (phụ thuộc T031)
- [x] T044 [GPU] [US1] Quickstart bước 4: `uv run python -m ai_live.avatar prepare assets/avatars/demo_host_01` → 4 clip `ready`; ghi thời gian
  chạy và RAM; thử một clip 2 mặt hoặc không mặt → `failed` nêu tên clip và khung (US1 #5, FR-003) (phụ thuộc T009, T041, T043)
- [x] T045 [GPU] [US1] Quickstart bước 5: bật `scripts/livetalking/run.ps1` và app với `AVATAR_MODE=livetalking`; mở `/host` trên Chrome thấy clip
  chờ, miệng khép, nhãn "AI" trong khung, watermark (US1 #1); để chờ lâu hơn một vòng clip chờ, chỗ lặp không nhảy hình (US1 #4); thử `CUSTOMER_ID=khach_khac` → app không mở (FR-004) (phụ thuộc T007, T036–T042, T044)
- [x] T046 [GPU] [US1] Quickstart bước 6: 10 đoạn WAV tiếng Việt 5–15 s do người vận hành tự đọc (sửa 2026-11-10: VieNeu `Thùy Dung`, giả định spec), chấm bằng mắt ≥ 8/10 khớp, không thấy miệng mở
  khi im; ghi `first_frame_s`, `render_fps`; thêm một WAV > 30 s (nhép hết câu, không tràn bộ nhớ) và một WAV toàn im lặng (miệng gần như khép,
  không lỗi) (SC-001, US1 #2, #3, FR-006, FR-008, trường hợp biên của spec; phụ thuộc T045)
- [x] T047 [GPU] [US1] Chụp ≥ 10 ảnh màn hình `/host` ở thời điểm ngẫu nhiên (lúc chờ và lúc nói): 100% có nhãn "AI" trong khung hình nhân vật;
  ghi kết quả vào quickstart (SC-002, FR-010; phụ thuộc T045)

**Checkpoint:** `uv run pytest` xanh (T022–T028); quickstart bước 2, 4, 5, 6 đạt; SC-001, SC-002 có kết quả. Dừng, kiểm chứng, demo.

## Phase 4: User Story 2: Nhân vật nhép miệng chạy trong show kịch bản và đường comment (P2)

**Mục tiêu:** show 004 và đường comment 001 chạy như cũ ở chế độ nhép miệng; bỏ qua dừng ngay; lỗi render chỉ làm hỏng lượt đó; 2 lượt lỗi
liền nhau thì tự về ảnh tĩnh, người vận hành bật lại được.

**Kiểm chứng độc lập:** quickstart bước 7 (SC-003, SC-004, SC-005).

### Test cho US2 (viết trước, phải FAIL trước khi implement)

- [x] T048 [US2] Test lỗi và phục hồi của `LiveTalkingRenderer` trong `tests/unit/test_livetalking_renderer.py`: fork gửi `error {kind}` →
  `RendererError(kind)`; `vram_oom` → log `lipsync_vram_oom` (FR-021); fork ngắt → `speak` kế tiếp `lipsync_unavailable`, log
  `lipsync_disconnected`, tự nối lại với backoff ≤ `reconnect_max_s`, log `lipsync_connected`; `boot_id` đổi khi nối lại → log
  `renderer_restarted` (FR-021); `interrupt` gửi `stop` cho fork và trang host, `speak` đang chờ kết thúc ngay (FR-016); `health` phát
  `LIPSYNC_HEALTH` (FR-017; phụ thuộc T025 vì cùng file)
- [x] T049 [P] [US2] Test chuyển chế độ trong `tests/unit/test_switching_renderer.py`: 1 lượt lỗi chưa chuyển; 2 lượt lỗi liền nhau (khác
  `utterance_id`) → `active=static`, `reason=render_errors` từ lượt **kế tiếp**, phát `AVATAR_MODE`, gửi tin `mode` cho trang host, log
  `avatar_fallback`, ghi `avatar.jsonl`; nhiều câu cùng lượt chỉ đếm một lần; `ok=True` đặt bộ đếm về 0; lỗi của `StaticRenderer` sau khi
  chuyển không đếm thêm; `enable_lipsync()` đưa về `livetalking`, bộ đếm 0, log `avatar_lipsync_enabled`; `enable_lipsync()` khi cấu hình
  `static` → `ValueError`; ở cấu hình `static` không đếm (data-model §4, FR-022)
- [x] T050 [P] [US2] Test tích hợp với fork giả trong `tests/integration/test_show_director.py`: phân đoạn show nói đủ câu, phụ đề đúng câu đang
  nói, tạm dừng / tiếp tục chạy như cũ (US2 #1, FR-015); comment mock hỏi giá được trả lời bằng nhân vật nhép miệng (US2 #2); bỏ qua → fork nhận
  `stop`, lượt dừng ≤ 1 s, nhân vật về chờ (US2 #3, FR-016, SC-004); lượt lỗi render ghi `errors.jsonl` bước `render` với đúng `kind`, show chạy
  tiếp lượt sau (US2 #4, FR-017, SC-005); 2 lượt lỗi → lượt thứ 3 qua `StaticRenderer` (US2 #5, FR-022); bật lại → lượt kế tiếp qua fork
  (US2 #6); cấu hình `static` giữ hành vi 004 (US2 #7, FR-014); đóng trang host giữa lượt ở `livetalking` → lỗi "chưa mở màn hình host" như
  001, mở lại thì lượt sau chạy (trường hợp biên của spec, analyze A5)
- [x] T051 [P] [US2] Test trong `tests/integration/test_script_runner.py`: `ScriptRunner` gọi `record_render_outcome` một lần mỗi lượt (đúng
  `ok`), không gọi khi lượt dừng trước bước render; log `render_stats` (`render_fps`, `infer_fps`, `clips_used`) cho mỗi câu đã nói (câu
  kịch bản không có `TurnLatency` theo 004 R2, sửa 2026-11-11, contracts/adapters.md §2)
- [x] T052 [P] [US2] Test route trong `tests/integration/test_avatar_api.py`: `GET /api/avatar` trả `AvatarModeState` + `LipsyncHealth`;
  `POST /api/avatar/lipsync` → 200 và chế độ về `livetalking`; ở cấu hình `static` → 409 `not_lipsync_mode`; `GET /health` có trường `avatar`
  (contracts/api.md §1–§2; phụ thuộc T028 vì cùng file)
- [x] T053 [P] [US2] Test trong `tests/integration/test_ws_host.py`: trang host nhận tin `mode` khi tự chuyển và khi bật lại; `subtitle`,
  `subtitle_clear` đến đúng thứ tự (contracts/api.md §4; phụ thuộc T013 vì cùng file)
  _Ghi chú 2026-11-11: T048 và T053 xanh ngay khi viết vì code của US1 (T032) và T055 đã có; test LT/switching viết bổ sung sau implement._

### Implement US2

- [x] T054 [US2] Sửa `src/ai_live/avatar/livetalking_renderer.py`: ánh xạ `error {kind}` → `RendererError`, nối lại có backoff, theo dõi
  `boot_id`, `interrupt` gửi `stop` cho fork và trang host, phát `LIPSYNC_HEALTH`, log `lipsync_connected`, `lipsync_disconnected`,
  `renderer_restarted`, `lipsync_vram_oom` (contracts/adapters.md §3, contracts/events.md §2; phụ thuộc T048)
- [x] T055 [P] [US2] Sửa `src/ai_live/avatar/switching_renderer.py`: `record_render_outcome`, `AvatarModeState`, `mode`, `enable_lipsync()`, tin
  `mode` qua `send_to_host`, phát `AVATAR_MODE`, ghi `avatar.jsonl`, log `avatar_fallback`, `avatar_lipsync_enabled`; `render_stats` chuyển tới
  renderer đã dùng cho lượt (phụ thuộc T049)
- [x] T056 [P] [US2] Sửa `src/ai_live/director/show_director.py`: gọi `record_render_outcome` khi renderer có Protocol này, chép `render_stats`
  vào `TurnLatency`, `_render_error_kind` đọc `exc.kind` của `RendererError` (phụ thuộc T050)
- [x] T057 [P] [US2] Sửa `src/ai_live/director/script_runner.py`: gọi `record_render_outcome`, chép `render_stats` như T056 (phụ thuộc T051)
- [x] T058 [US2] Thêm vào `src/ai_live/app/routes.py`: `GET /api/avatar`, `POST /api/avatar/lipsync` (409 `not_lipsync_mode` khi `ValueError`),
  trường `avatar` của `GET /health` (phụ thuộc T036, T052, T055)
- [x] T059 [P] [US2] Sửa `src/ai_live/app/static/host.js`: tin `mode` = `static` → ẩn `<video>`, hiện `face.png` + phát Web Audio + nhãn CSS;
  `mode` = `livetalking` → quay lại video (contracts/api.md §4, FR-022; phụ thuộc T037)
- [x] T060 [P] [US2] Sửa `src/ai_live/app/static/control.html`, `src/ai_live/app/static/control.js`, `src/ai_live/app/static/style.css`: dải cảnh
  báo khi về ảnh tĩnh, nút "Bật lại nhân vật nhép miệng" gọi `/api/avatar/lipsync`, ô trạng thái "Nhép miệng: đã nối / mất nối" theo
  `AVATAR_MODE`, `LIPSYNC_HEALTH` (contracts/api.md §5; phụ thuộc T038)
- [x] T061 [US2] Sửa `vendor/livetalking/ailive_ext/ingest.py` và `vendor/livetalking/avatars/base_avatar.py`: bắt
  `torch.cuda.OutOfMemoryError` / lỗi suy luận → gửi `error {kind: vram_oom | inference_failed}` và về clip chờ; `health` có VRAM đang dùng
  và đỉnh; `stop` dừng tiếng và miệng, về clip chờ (fork-protocol §3–§4, FR-016, FR-021; phụ thuộc T039, T042) **(ADR-048)**
  _Ghi chú 2026-11-11: lô hỏng thành khung im lặng không gắn tag (không có ack), `flush_talk()` như `stop`, `error` mang `utterance_id` của câu
  đang suy luận và `vram_peak_mb` khi OOM (thêm vào fork-protocol §3); app bỏ phần tiếng còn lại của câu đó. Test fork:
  `ailive_ext/tests/test_ingest.py`, `test_inference_error.py` (chạy vòng `inference` thật, không GPU). Câu khác đã xếp trong fork bị
  `flush_talk()` bỏ sẽ hết hạn ack ở app và tính lỗi; chấp nhận vì OOM hiếm, 2 lượt lỗi thì về ảnh tĩnh._
- [x] T062 [GPU] [US2] Quickstart bước 7.1–7.3: show có phụ đề, tạm dừng / tiếp tục (FR-015); quay màn hình: giữa hai câu cùng phân đoạn
  nhân vật giữ clip nói với miệng khép, không về clip chờ (US2 #1); gửi một comment mock hỏi giá qua `/api/comments`
  (US2 #2); bỏ qua 5 lần, đo bằng quay màn hình ≤ 1 s (SC-004); ≥ 20 lượt không lượt nào tiếng xong trước khi miệng bắt đầu, xem
  `GET /api/latency` (SC-003) (phụ thuộc T045, T054–T061)
  _Ghi chú 2026-11-12: tự kiểm bằng bộ ghi luồng (quickstart §11) + Chrome DevTools đo tiếng ở trang host; kết quả ở quickstart §7.
  Sửa hai lỗi tìm ra: (1) bỏ qua còn tiếng 1,0–1,5 s vì `stop` chỉ xóa đệm, không xóa phần đã suy luận và hàng đợi WebRTC → fork bỏ mọi
  tiếng nói vào trước `stop` (fork-protocol §2, test `ailive_ext/tests/test_stop_drop.py`), sau sửa 0,00–0,56 s; (2) tạm dừng lúc một
  câu đã gửi fork mà chưa phát thì câu đó vẫn phát sau khi dừng (+1,41 s) → `ScriptRunner.pause()` dừng và giữ lại câu đó như câu đang
  xếp hàng, `LiveTalkingRenderer.interrupt()` cho câu nói lại bắt đầu lượt mới `seq 0`. US2 #1 (giữ clip nói giữa hai câu) **chưa đạt**:
  cả 49 khoảng nghỉ cùng phân đoạn về `idle_01`; phần này thuộc T064–T066 (US3), không sửa trong T062._
- [x] T063 [GPU] [US2] Quickstart bước 7.4–7.5: `POST /api/debug/fault` bước `render` `count: 1` rồi `count: 2` → về ảnh tĩnh + dải cảnh báo, bấm
  bật lại → video (SC-005, FR-022); tắt fork giữa show → 2 lượt lỗi rồi ảnh tĩnh, show không dừng; bật lại fork + bấm bật lại → log
  `renderer_restarted` (FR-017, FR-021) (phụ thuộc T062)
  - Kết quả 2026-11-12 (quickstart §7): cả 5 mục đạt. Lỗi tìm ra và đã sửa: fork bật lại trong lúc đang ảnh tĩnh thì luồng WebRTC mới
    không tự phát (video ẩn + tắt tiếng), bật lại thì video đứng; `host.js` `showVideo` nay gọi `play()`.

**Checkpoint:** `uv run pytest` xanh (T048–T053); quickstart bước 7 đạt; SC-003, SC-004, SC-005 có kết quả.

## Phase 5: User Story 3: Clip chờ và clip nói xoay vòng, chuyển clip không giật (P3)

**Mục tiêu:** mỗi lần cần clip mới thì chọn clip đúng loại khác clip vừa dùng; chuyển clip mượt.

**Kiểm chứng độc lập:** quickstart bước 8 (SC-007, SC-008).

### Test cho US3 (viết trước, phải FAIL trước khi implement)

- [ ] T064 [P] [US3] Test `pick_next` trong `vendor/livetalking/ailive_ext/tests/test_rotation.py`: chỉ chọn clip đúng loại; khác `last_id` khi có
  ≥ 2 clip (US3 #1, #2); chỉ một clip thì trả clip đó (US3 #3); `rng` cố định cho kết quả lặp lại được. `ClipScheduler(hold_s)` với đồng hồ giả: sau
  `sentence_end` giữ clip nói tới `hold_s`, câu `seq > 0` trong khoảng giữ giữ nguyên clip, `seq = 0` chọn clip nói mới, quá `hold_s`
  hoặc `stop` → clip chờ (US2 #1, research R7; fork-protocol §4; phụ thuộc T008)
  **(ADR-048)**

### Implement US3

- [ ] T065 [US3] Viết `vendor/livetalking/ailive_ext/rotation.py`: `pick_next(clips, kind, last_id, rng)` và `ClipScheduler`
  (FR-012, FR-013, US2 #1; phụ thuộc T064)
  **(ADR-048)**
- [ ] T066 [US3] Sửa `vendor/livetalking/avatars/base_avatar.py`: chọn clip theo `ClipScheduler`: clip nói mới bằng `pick_next` khi nhận `sentence_start seq=0`,
  câu dài hơn clip thì lặp đi tới đi lùi; sau mỗi câu giữ clip nói (khung nền gốc, không dán miệng) tối đa `LIVETALKING_HOLD_S`; chọn clip
  chờ khi hết khoảng giữ hoặc `stop` và sau mỗi vòng đi tới đi lùi đầy đủ; clip mới bắt đầu ở khung 0, trộn dần
  `LIVETALKING_TRANSITION_S` bằng `enable_transition`; quay lại chờ thì chỉ số clip chờ về 0; `stats` gửi `clip_id` (fork-protocol §4,
  FR-009, FR-013, US2 #1; phụ thuộc T042, T061, T065) **(ADR-048)**
- [ ] T067 [GPU] [US3] Quickstart bước 8: chờ 3 phút + 10 lượt nói, quay màn hình, đếm giật ≤ 1 (SC-007); nếu giật thì chỉnh
  `LIVETALKING_TRANSITION_S`, nếu về clip chờ giữa hai câu thì nâng `LIVETALKING_HOLD_S`, ghi giá trị chọn vào `.env.example`; `clips_used` trong `GET /api/latency` không trùng clip nói ở hai lượt liền
  nhau (US3 #1, #2, FR-009) (phụ thuộc T066, T070)
- [ ] T068 [GPU] [US3] SC-008: cho ≥ 3 người ngoài dự án xem 1 phút chờ, hỏi "trông như đang sống không"; ghi kết quả (đạt khi ≥ 2/3) vào
  quickstart bước 8 (phụ thuộc T067)

**Checkpoint:** test xoay clip xanh trong venv fork; quickstart bước 8 đạt; SC-007, SC-008 có kết quả.

## Phase 6: User Story 4: Đo tốc độ và độ ổn định trên laptop (P4)

**Mục tiêu:** bảng độ trễ có số khung hình mỗi giây và thời gian bước tạo hình; có số thật của 20 lượt và 30 phút trên laptop.

**Kiểm chứng độc lập:** quickstart bước 9 (SC-006).

### Test cho US4 (viết trước, phải FAIL trước khi implement)

- [ ] T069 [P] [US4] Test trong `tests/integration/test_avatar_api.py`: `GET /api/latency` có cột `render_fps`, `infer_fps`, `clips_used` theo từng
  lượt (`null` ở `static`) và `render_fps` p50/p95 trong phần tóm tắt (US4 #1, FR-020; phụ thuộc T052 vì cùng file)

- [ ] T083 [P] [US4] Test `vendor/livetalking/ailive_ext/tests/test_lipskip.py` (numpy, không GPU): với `n` = 1, 2, 3 và lô 16 khung chỉ
  các khung `i % n == 0` được suy luận; khung còn lại dán miệng của khung suy luận gần nhất trước nó lên khung nền của chính nó, đúng
  tọa độ mặt; `n` < 1 bị từ chối (fork-protocol §4, §6, research R8; phụ thuộc T008) **(ADR-048)**

### Implement US4

- [ ] T070 [US4] Thêm cột `render_fps`, `infer_fps`, `clips_used` và `render_fps` p50/p95 vào `GET /api/latency` trong
  `src/ai_live/app/routes.py` (contracts/api.md §2; phụ thuộc T019, T058, T069)
- [ ] T071 [P] [US4] Thêm cột fps và clip vào bảng độ trễ trong `src/ai_live/app/static/control.js` (contracts/api.md §5; phụ thuộc T060)
- [ ] T072 [US4] Viết `vendor/livetalking/ailive_ext/lipskip.py` và gọi trong `vendor/livetalking/avatars/base_avatar.py`:
  `LIVETALKING_LIP_EVERY_N = n` chỉ suy luận miệng 1/n khung trong lô, khung khác
  dán lại miệng vừa tạo lên khung nền hiện tại; `LIVETALKING_BATCH_SIZE` truyền vào `batch_size` (fork-protocol §4, research R6, R8, FR-007;
  phụ thuộc T066, T083) **(ADR-048)**
- [ ] T073 [GPU] [US4] Quickstart bước 9: 20 lượt rồi chạy show 30 phút; ghi `render_fps`, `infer_fps` p50/p95, bước
  `tts_first_chunk → avatar_first_frame` p50/p95, cả lượt p50/p95, VRAM đỉnh (`avatar.jsonl`), số lần `vram_oom` / `renderer_restarted`,
  khoảng lặng giữa câu p95 và câu đầu show (`segment_requested → avatar_first_frame`, Điều VI) vào `docs/DECISIONS.md` ADR-041 và bảng
  ở `specs/005-lipsync-livetalking/quickstart.md` bước 9 (spec SC-006 chỉ trỏ tới). Nếu lặng p95 > 1,5 s: đề xuất `LIVETALKING_LEAD_S`
  (gợi ý bằng độ trễ khung đầu p50) cho người dùng duyệt, chạy lại 20 lượt và ghi so sánh; nếu lặng p95 > `LIVETALKING_HOLD_S` thì
  nâng `LIVETALKING_HOLD_S` (research R15) (US4 #1, #2; phụ thuộc T063, T070)
- [ ] T074 [GPU] [US4] Đo lệch ack ↔ hiển thị: quay màn hình 60 fps cùng log, ≥ 10 câu; ghi vào `specs/005-lipsync-livetalking/research.md` R6;
  nếu lệch làm tiếng xong trước miệng thì đề xuất giá trị `LIVETALKING_LEAD_S` cho người dùng duyệt (FR-019, SC-003) (phụ thuộc T073)
- [ ] T075 [GPU] [US4] Chỉnh `LIVETALKING_BATCH_SIZE` (16, 8, 4) và, nếu fps < 25, thử `LIVETALKING_LIP_EVERY_N=2`; nếu vẫn < 25, nút (2)
  của R8 (bộ clip nhỏ hơn, ví dụ 360×624, rồi chạy lại `prepare`): dừng hỏi người dùng cách tạo bộ clip đó trước khi làm; ghi bảng so
  sánh vào `docs/DECISIONS.md` ADR-041. Nếu mọi cách đều dưới 25 khung/giây và người dùng thấy không đạt: dừng, báo người dùng, **hỏi chi phí trước khi
  tính RunPod** (`docs/RUNPOD.md`) (FR-007, SC-006; phụ thuộc T072, T073)

**Checkpoint:** `uv run pytest` xanh; test `lipskip` xanh trong venv fork; SC-006 có số thật ghi vào ADR-041 và quickstart bước 9.

## Phase 7: Hoàn thiện và việc chung

- [ ] T076 [P] Cập nhật `docs/ARCHITECTURE.md` §3 theo contracts/adapters.md §8 (Protocol tùy chọn, `LiveTalkingRenderer`, `SwitchingRenderer`,
  `HostLink`, fork process riêng) (phụ thuộc T001)
- [ ] T077 [P] Cập nhật `docs/VENDORS.md` (LiveTalking + Wav2Lip đã dùng, ADR-041/048) và `docs/RUNPOD.md` (chạy fork bằng
  `scripts/livetalking/` khi phải dùng RunPod) (phụ thuộc T001, T002)
- [ ] T078 [P] Cập nhật `src/README.md`: các module mới trong `src/ai_live/avatar/`, `scripts/livetalking/`, `vendor/livetalking/` ngoài git
- [ ] T079 [P] Cập nhật `docs/RISKS.md` các mục license và GPU của plan (§Rủi ro mới) bằng số đo và kết quả thật từ T008, T073, T075; điều chưa rõ
  (license checkpoint `wav2lip256.pth`) giữ `TODO:` kèm câu hỏi cụ thể
- [ ] T080 [GPU] Quickstart bước 10: chia sẻ tab `/host` có tiếng vào Google Meet; bên kia thấy nhân vật, nhãn "AI", nghe tiếng khớp miệng
  (FR-018) (phụ thuộc T063)
- [ ] T081 Chạy quickstart bước 0: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` xanh, không test nào cần
  `vendor/livetalking` hay GPU; và `vendor/livetalking/.venv/Scripts/python -m pytest vendor/livetalking/ailive_ext/tests` xanh
- [ ] T082 Chạy `/update-context`

## Phụ thuộc và thứ tự

- Setup → Foundational → US1 → US2 → US3 → US4 → Hoàn thiện. US4 phần app (T069–T071) chỉ cần Foundational + T058, có thể làm cùng US3.
- **ADR-048 chặn:** T005 (và qua đó T014, T032 cùng mọi test dùng fork giả), T008, T009 và mọi task `vendor/livetalking/` (T029, T039–T042, T061,
  T064–T066, T072, T083). Nếu người dùng duyệt phần `websockets` trước, toàn bộ phần app của US1–US4 làm được với fork giả; phần fork chờ phần còn
  lại của ADR-048.
- `src/ai_live/avatar/livetalking_renderer.py` sửa ở T032, T054; `switching_renderer.py` ở T033, T055; `routes.py` ở T036, T058, T070;
  `host.js` ở T037, T059; `control.*` ở T038, T060, T071; `vendor/livetalking/avatars/base_avatar.py` ở T040, T042, T061, T066, T072. Các task
  cùng file chạy tuần tự theo thứ tự trên.
- Test thêm vào cùng file viết tuần tự: `test_character.py` T022 → T023; `test_livetalking_renderer.py` T025 → T048; `test_switching_renderer.py`
  T026 → T049; `test_avatar_api.py` T028 → T052 → T069; `test_ws_host.py` T013 → T053.
- T043 cần người dùng làm tay (xác nhận gương mặt, FR-005); T044 trở đi cần T043.

## Chạy song song

- Setup: T004, T006, T007 (T003 đã có sẵn).
- Foundational: T010–T014 (test + fork giả) cùng lúc → T015, T016, T017, T018 → T019, T020, T021.
- US1, test: T022, T024, T025, T026, T027, T028 cùng lúc; T023 sau T022. Implement: T030, T032, T033, T037, T038, T041 cùng lúc; rồi T031, T034 →
  T035 → T036. Nhánh fork T039 → T040 → T042 chạy song song nhánh app.
- US2, test: T048–T053 cùng lúc (T048 sau T025 đã xong). Implement: T055, T056, T057, T059, T060 cùng lúc; T054; T058 sau T055; T061 nhánh fork.
- Theo agent khi `/sdd.dispatch`: `ai-media` (avatar/, host.*, fork, `scripts/livetalking/`), `ai-orchestrator` (core/, director/, routes,
  main, context, control.*), `ai-qa` (fork giả, contract test). Danh sách Owns hiện tại chưa có `scripts/livetalking/**`,
  `vendor/livetalking/ailive_ext/**`, `tests/fixtures/fake_fork.py`, `tests/unit/test_livetalking_renderer.py`,
  `tests/unit/test_switching_renderer.py`, `tests/unit/test_character.py`, `tests/integration/test_avatar_api.py`; cần người dùng chọn thêm vào
  `.claude/agents/*.md` trước khi dispatch.

## Đợt GPU

Tất cả chạy trên GPU laptop GTX 1650 Ti (ADR-023), sinh hình realtime, không dựng sẵn. RunPod chỉ khi laptop không đủ, **hỏi chi phí và chờ
người dùng đồng ý trước khi bật pod** (`docs/RUNPOD.md`).

- Đợt 1 (dựng): T008 (venv fork + CUDA, quickstart 1).
- Đợt 2 (US1): T044 (prepare) → T045 (bật fork + app) → T046 (SC-001) → T047 (SC-002).
- Đợt 3 (US2): T062 (show, skip, SC-003, SC-004) → T063 (lỗi giả lập, tắt fork, SC-005).
- Đợt 4 (US3): T067 (SC-007) → T068 (SC-008, cần người xem ngoài dự án).
- Đợt 5 (US4 + Meet): T073 (30 phút, SC-006) → T074 (lệch ack) → T075 (chỉnh batch / LIP_EVERY_N) → T080 (Google Meet, FR-018).

## Chiến lược MVP

1. Setup + Foundational → 2. US1 → **dừng, kiểm chứng, demo** (WAV có sẵn trên laptop) → 3. US2 (show + comment, tự về ảnh tĩnh) → US3 → US4
   từng bước → 4. Hoàn thiện. Nếu ADR-048 chỉ được duyệt phần `websockets`, làm trước toàn bộ phần app với fork giả, đợt GPU để sau.

## Kiểm tra độ phủ

| Yêu cầu | Task |
|---------|------|
| FR-001 | T023, T030, T031, T041, T044 |
| FR-002 | T022, T043 |
| FR-003 | T023, T041, T044 |
| FR-004 | T022, T028, T030, T034, T043, T045 |
| FR-005 | T022, T043 |
| FR-006 | T025, T032, T039, T046 |
| FR-007 | T062 (SC-003), T072, T074, T075, T083 |
| FR-008 | T042, T046 |
| FR-009 | T064, T066, T067 |
| FR-010 | T029, T040, T047 |
| FR-011 | T028, T036, T038, T046 |
| FR-012 | T022, T030, T065 |
| FR-013 | T064, T065, T066, T067 |
| FR-014 | T026, T028, T034, T050 |
| FR-015 | T050, T051, T056, T057, T062 |
| FR-016 | T048, T050, T054, T061, T062 |
| FR-017 | T048, T050, T056, T063 |
| FR-018 | T037, T080 |
| FR-019 | T025, T032, T074 |
| FR-020 | T012, T019, T025, T069, T070, T071 |
| FR-021 | T048, T054, T061, T063 |
| FR-022 | T049, T052, T055, T058, T059, T060, T063 |
| SC-001 | T046 |
| SC-002 | T047 |
| SC-003 | T025, T062, T074 |
| SC-004 | T050, T062 |
| SC-005 | T050, T063 |
| SC-006 | T073, T075 (lặng giữa câu và câu đầu show ở T073) |
| SC-007 | T067 |
| SC-008 | T068 |

## Nhật ký lỗi gặp khi implement

<!-- /sdd.implement và /sdd.dispatch ghi lỗi đáng nhớ vào đây. -->

- 2026-11-10, T045: clip nền Wan 2.2 rung nhẹ liên tục (vận tốc đảo chiều gần như mỗi khung, ~0,3–0,5 px), người dùng thấy trên Chrome.
  Số đo frame diff ở lần tự kiểm 2026-11-07 không bắt được. Thêm `scripts/avatar_clips/smooth_clips.py` (làm mượt theo thời gian, PyAV +
  numpy của venv fork, không dependency mới) và quickstart bước 4b; clip chờ mượt 5 khung, `talk_02` mượt 3 khung đặt lên đầu, `talk_01`
  giữ gốc. Lệch so với plan: plan không có bước xử lý clip giữa notebook Kaggle và `prepare`. Đề xuất: notebook
  `make_avatar_clips.ipynb` chạy luôn bước làm mượt ở lần tạo clip sau (chưa làm).
- 2026-11-11, T046: người dùng chọn chấm SC-001 trên 10 đoạn VieNeu `Thùy Dung` thay cho giọng người vận hành tự đọc (giọng chạy live
  thật; giả định spec sửa trước, 2026-11-10). Lệch so với task gốc chỉ ở nguồn tiếng; 10/10 khớp, số đo ở quickstart bước 6.
- 2026-11-11, T047: người dùng không muốn dùng màn hình của mình, nên ảnh chụp bằng Chrome headless + DevTools Protocol (cùng
  trang `/host`, cùng luồng WebRTC từ fork) thay cho Chrome người dùng đang mở. 12/12 ảnh (6 chờ, 6 nói) có nhãn "AI" trong khung
  hình; nhãn CSS ẩn khi video chạy. Kết quả ở quickstart bước 6.
