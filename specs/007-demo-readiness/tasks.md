# Tasks: Sẵn sàng cho buổi demo

- **Feature ID:** `007-demo-readiness` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
- **Ràng buộc chạy:** không gọi LLM free ở bất kỳ task nào (SC-007): mọi lần bật app dùng `REPLY_ENGINE=fake`; biến truyền trên dòng lệnh,
  không sửa `.env`.

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[GPU]**: cần GPU; chạy trên GPU laptop (ADR-023), không RunPod; gom vào đợt GPU (cuối file)
- **[US#]**: thuộc user story nào. Phase Setup, Foundational và Polish không gắn nhãn này.

## Phase 1: Setup

- [x] T001 Ghi ADR-057 vào `docs/DECISIONS.md` (plan "ADR cần ghi": tự bỏ câu kẹt một lần ở 15 s; tín hiệu tab host qua `getStats`
  WebRTC, không phân tích hình; video dự phòng bằng show `verbatim` + recorder fork, không dựng hậu kỳ, app không có đường phát;
  nguồn điện qua `ctypes`, không thêm thư viện)
- [x] T002 Test cấu hình mới trong `tests/unit/test_config.py`: mặc định `watchdog_enabled=True`, `watchdog_silence_s=5`,
  `watchdog_frozen_s=3`, `watchdog_autoskip_s=15`, `watchdog_audio_ack_s=3`, `watchdog_tick_s=0.25`, `readiness_min_free_gb=5`,
  `backup_video_dir=out/backup_video`; từ chối `watchdog_autoskip_s <= watchdog_silence_s` và số âm
- [x] T003 Thêm các biến trên vào `src/ai_live/core/config.py` (validator ràng buộc autoskip > silence) và `.env.example` (gồm cả
  `WATCHDOG_TICK_S`, ghi chú "chỉ để test", vì test cấu hình đòi mọi biến có trong `.env.example`), chú thích tiếng Anh (phụ thuộc T002)
- [x] T004 [P] Tạo gói `src/ai_live/ops/__init__.py` và `src/ai_live/ops/__main__.py` (argparse ba lệnh con `readiness`, `report`,
  `backup-video`, chưa có thân; `contracts/cli.md`)

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

- [x] T005 [P] Test `EventType.HOST_STATUS` và `EventType.ALERT` trong `tests/unit/test_events.py`
- [x] T006 Thêm `HOST_STATUS`, `ALERT` vào `src/ai_live/core/events.py` (phụ thuộc T005)
- [x] T007 [P] Test ghi file phiên mới trong `tests/unit/test_session_log_ops.py`: `write_session_info` → `session.json`,
  `write_gap` → `gaps.jsonl`, `write_alert` → `alerts.jsonl`, `write_readiness` → `readiness.jsonl`; mỗi dòng qua `redact`, flush
  ngay (đọc được trước `close`), thư mục ngoài git (`contracts/files.md` §1–§4)
- [x] T008 Thêm `write_session_info`, `write_gap`, `write_alert`, `write_readiness` vào `src/ai_live/director/session_log.py`
  qua worker sẵn có (phụ thuộc T007)
- [x] T009 [P] Test `src/ai_live/ops/system.py` trong `tests/unit/test_system.py`: `power_status()` trả `"ac"`/`"battery"`/`None`
  theo `ACLineStatus` 1/0/255 (giả lập hàm `ctypes`), `None` ngoài Windows; `free_disk_gb(path)` dùng `shutil.disk_usage`
- [x] T010 Viết `src/ai_live/ops/system.py` (phụ thuộc T009)
- [x] T011 Test trong `tests/integration/test_script_runner.py`: mỗi khoảng lặng runner tính ra được ghi một dòng `gaps.jsonl`
  (`show_id`, `kind`, `counted`, `seconds`, `from_id`, `to_id`, `at`), gồm cả khoảng `paused`/`fault` với `counted=false`
- [x] T012 `src/ai_live/director/script_runner.py`: `_record_gap` gọi `session_log.write_gap` (phụ thuộc T008, T011)
- [x] T013 `src/ai_live/app/main.py`: lúc mở phiên ghi `session.json` (`SessionInfo`, data-model §3, có `power` từ T010) ngay sau
  `SessionLog.open`; test trong `tests/integration/test_api.py` kiểm file có mặt và không có khóa (phụ thuộc T008, T010)
- [x] T014 [P] Test tin `host_status` trong `tests/integration/test_ws_host.py`: tab host hiện tại gửi tin → bus nhận
  `HOST_STATUS` với các trường data-model §2 (thiếu/sai kiểu → `null`, có `received_at`); kết nối cũ đã bị thay thì bỏ qua; app không
  trả lời; `/ws/control` không chuyển `host_status` lên trang điều khiển
- [x] T015 `src/ai_live/avatar/static_renderer.py`: nhận `host_status` và phát `HOST_STATUS` lên bus; `src/ai_live/app/ws.py`: `_forward`
  bỏ qua `HOST_STATUS` (mỗi giây một tin, trang điều khiển không cần) (phụ thuộc T006, T014)
- [x] T016 [P] Test fork trong `vendor/livetalking/ailive_ext/tests/test_ws.py` (nơi có test health sẵn): `/ailive/health` có `record_enabled` đúng theo
  `AILIVE_RECORD_DIR`
- [x] T017 Thêm `record_enabled` vào `/ailive/health` trong `vendor/livetalking/ailive_ext/ingest.py` và fork giả
  `tests/fixtures/fake_fork.py` (phụ thuộc T016)

**Checkpoint:** nền tảng sẵn sàng (sự kiện, file log mới, nhịp tab host, cờ ghi của fork); các story bắt đầu được.

---

## Phase 3: User Story 1: Kiểm tra sẵn sàng trước khi lên sóng (P1) 🎯 MVP

**Mục tiêu:** một nút/lệnh trả về danh sách mục Đạt/Cảnh báo/Lỗi/Không kiểm được và kết luận "Sẵn sàng".
**Kiểm thử độc lập:** cố ý để sai từng điều kiện → đúng mục đó báo Lỗi; sửa xong → "Sẵn sàng" (spec US1).

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [x] T018 [P] [US1] Test hàm kiểm thuần trong `tests/unit/test_readiness.py`: từng dòng bảng data-model §1 (Lỗi/Cảnh báo/Đạt cho
  mỗi `id`), thứ tự `items` cố định, `ready` = không có `fail`, `manual` có đủ ba việc FR-005, mọi `message`/`action` tiếng Việt, mục
  Đạt có `action=None`; SC-001: 6 tình huống (bộ trả lời giả, dev, ghi luồng bật, fork tắt, host chưa mở, cảnh còn ảnh mẫu) → đúng 6 mục
  Lỗi; cấu hình ngày demo → "Sẵn sàng"
- [x] T019 [P] [US1] Test `GET /api/readiness` trong `tests/integration/test_readiness_api.py`: app static + fork giả; JSON đúng
  `contracts/api.md` §1; ghi một dòng `readiness.jsonl`; không đổi trạng thái show, không phát câu nào lên bus `SENTENCE`; engine chain
  giả đếm 0 lượt gọi (FR-004, SC-007); `duration_ms` ≤ 5000 (SC-001); `/health` có `customer_id`, `avatar_id`, `show_active`
- [x] T020 [P] [US1] Test lệnh `python -m ai_live.ops readiness` trong `tests/unit/test_ops_cli.py`: app chạy (API giả qua
  `httpx.MockTransport`) → in đúng kết quả API, mã thoát 0/1; app tắt → `source: offline`, mục `host`/`llm_chain` Lỗi "app chưa bật";
  `--json` in JSON (`contracts/cli.md`)

### Implement US1

- [x] T021 [US1] `src/ai_live/ops/readiness.py`: `CheckStatus`, `ReadinessItem`, `ReadinessResult`, các `check_*` thuần theo
  data-model §1, danh sách `MANUAL_CHECKS` (phụ thuộc T018)
- [x] T022 [US1] `src/ai_live/ops/readiness.py`: `run_readiness(ctx)` gom trạng thái từ `AppContext` (renderer, `LipsyncHealth`,
  chế độ nhân vật, catalog, cảnh, `ChainReplyEngine.snapshot()` không gọi mạng, sheet video dự phòng mới nhất) + `GET
  {LIVETALKING_URL}/ailive/health` timeout 2 s; `run_offline(settings)` cho CLI (phụ thuộc T021, T010, T017)
- [x] T023 [US1] `src/ai_live/app/routes.py`: `GET /api/readiness` (ghi `readiness.jsonl` qua T008) và ba trường mới của `/health`
  (phụ thuộc T022)
- [x] T024 [US1] `src/ai_live/ops/__main__.py`: lệnh `readiness [--url] [--json]` gọi API, rơi về `run_offline` khi không nối được
  (phụ thuộc T022, T020)
- [x] T025 [US1] Trang điều khiển: nút "Kiểm tra trước demo" và bảng kết quả (trạng thái màu, lời nhắn, việc cần làm, việc tự xác nhận)
  trong `src/ai_live/app/static/control.html`, `control.js`, `style.css` (phụ thuộc T023)
- [x] T026 [US1] Kiểm bằng trình duyệt (trang mới qua Chrome DevTools MCP, không đụng trang 1, 2 của người dùng): app static fake →
  bấm nút, thấy các mục Lỗi đúng quickstart §1; ghi kết quả vào quickstart "Kết quả kiểm chứng"

**Checkpoint:** US1 chạy và test độc lập được.

---

## Phase 4: User Story 2: Canh show khi đang chạy (P2)

**Mục tiêu:** cảnh báo trên trang điều khiển khi host im lặng, hình đứng, mất tiếng, fork mất, host đóng, chuyển dự phòng/ảnh tĩnh;
tự bỏ câu kẹt một lần.
**Kiểm thử độc lập:** giả lập từng lỗi trong show → cảnh báo đúng loại trong ≤ 1 s, tự tắt khi hết (spec US2).

### Test cho US2 (viết trước, phải FAIL trước khi implement)

- [x] T027 [P] [US2] Test logic `ShowWatchdog` với đồng hồ giả trong `tests/unit/test_watchdog.py`: mở/đóng từng loại theo bảng R2;
  cảnh báo gốc che cảnh báo con (`covered`, không mở lại khi gốc còn); tạm dừng đóng `silence`/`frozen`/`audio_missing` (`paused`) và đặt
  lại mốc im lặng; show kết thúc đóng hết (`show_ended`); không canh khi không có show; `silence` không tính lúc câu đang phát; tự bỏ câu
  đúng một lần ở `autoskip_s` rồi nâng `operator` sau thêm `silence_s` (R3); hình đứng chỉ từ hai nhịp có `frames` bằng nhau cách nhau
  quá ngưỡng, thiếu nhịp không cảnh báo (R9); `audio_missing` khi câu đã gửi không có xác nhận phát trong `audio_ack_s` hoặc nhịp báo
  `audio != running`; ngưỡng lấy từ cấu hình (FR-011); `message` có số giây, `action` theo runbook §4
- [x] T028 [P] [US2] Test tích hợp trong `tests/integration/test_watchdog_show.py` (static, TTS giả, fake engine): (a) lỗi giả `tts`
  `timeout` → `silence` mở ≤ 1 tick sau 5 s, tự bỏ câu ở 15 s (`auto_action="skip"`, log `watchdog_auto_skip`), im lặng ≤ 17 s (SC-003);
  (b) đóng WebSocket host → `host_closed`, không kèm `silence`; nối lại → đóng; (c) show bình thường vài phút (đồng hồ thật, ngưỡng thu
  nhỏ) → 0 cảnh báo (SC-002); (d) tạm dừng lâu hơn ngưỡng → 0 cảnh báo; (e) `alerts.jsonl` đủ `open`/`auto_skip`/`close`; sự kiện
  `alert` trên `/ws/control`; `GET /api/state.alerts` liệt kê cảnh báo đang mở (FR-008, FR-009); (f) `WATCHDOG_ENABLED=false` → không
  có task canh
- [x] T029 [US2] Test `fork_lost`/`static_mode`/`frozen` với renderer `livetalking` + fork giả trong
  `tests/integration/test_watchdog_show.py`: tắt fork giả → `fork_lost` (che `frozen`, `silence`); `host_status` có `frames` đứng yên →
  `frozen`; `frames` tăng lại → đóng

### Implement US2

- [x] T030 [US2] `src/ai_live/ops/watchdog.py`: `AlertKind`, `AlertLevel`, `Alert`, `HostStatus`, `ShowWatchdog` thuần (nhận sự
  kiện + `now`, trả danh sách thay đổi), bảng gốc, lời nhắn/việc cần làm tiếng Việt (phụ thuộc T027)
- [x] T031 [US2] `src/ai_live/ops/watchdog.py`: `run_watchdog(...)` đăng ký bus (`SHOW_STATE`, `SENTENCE`, `HOST_CONNECTION`,
  `LIPSYNC_HEALTH`, `AVATAR_MODE`, `HOST_STATUS`), listener `PlaybackNotifier` (bắt lỗi, không chặn), tick `watchdog_tick_s`; mỗi thay
  đổi: publish `ALERT`, ghi `alerts.jsonl`, gọi `director.skip_current()` khi tự bỏ câu (phụ thuộc T030, T006, T008)
- [x] T032 [US2] `src/ai_live/app/main.py`, `context.py`: tạo watchdog khi `watchdog_enabled`, giữ danh sách cảnh báo đang mở trong
  `AppContext`, hủy task lúc tắt app; `build_state` trong `context.py` thêm `alerts` (`GET /api/state` và tin `state` đầu tiên của
  `/ws/control`); sự kiện `ALERT` tự tới `/ws/control` qua `_forward` của `ws.py` (phụ thuộc T031)
- [x] T033 [P] [US2] `src/ai_live/app/static/host.js`: sau "Bắt đầu" gửi `host_status` mỗi 1 s (`framesDecoded` từ `getStats`
  `inbound-rtp` video ở chế độ nhép miệng, trạng thái `AudioContext`, `muted`/`paused` của thẻ `<video>`, `visibilityState`); dừng khi
  WebSocket đóng (`contracts/api.md` §4, phụ thuộc T015)
- [x] T034 [US2] Trang điều khiển: banner cảnh báo trên cùng (vàng `warning`, đỏ `operator`, mỗi cảnh báo một dòng, tự ẩn khi đóng,
  không phát âm thanh) trong `src/ai_live/app/static/control.html`, `control.js`, `style.css` (phụ thuộc T032)
- [x] T035 [US2] Kiểm bằng trình duyệt (trang mới qua Chrome DevTools MCP): quickstart §2 ở chế độ static: lỗi giả TTS → banner im lặng
  rồi "đã tự bỏ câu"; đóng tab host → banner đỏ; mở lại → tắt; tạm dừng 20 s → không banner; ghi vào quickstart "Kết quả kiểm chứng"
  (phụ thuộc T033, T034)

**Checkpoint:** US2 chạy và test độc lập được.

---

## Phase 5: User Story 3: Báo cáo phiên tổng duyệt 30 phút (P3)

**Mục tiêu:** một lệnh xuất báo cáo một show với kết luận PRD tiêu chí 3, 4, kể cả khi app sập giữa chừng.
**Kiểm thử độc lập:** báo cáo của các bộ log mẫu cho đúng kết luận (spec US3, SC-005).

### Test cho US3 (viết trước, phải FAIL trước khi implement)

- [x] T036 [P] [US3] Bộ dựng log phiên mẫu `tests/fixtures/session_logs.py`: viết `session.json`, `gaps.jsonl`, `alerts.jsonl`,
  `script_sentences.jsonl`, `show_summary_<show>.json`, `avatar.jsonl` theo tham số (thời lượng, khoảng lặng, tạm dừng, có/không summary)
- [x] T037 [US3] Test trong `tests/unit/test_rehearsal.py` với 5 bộ log mẫu SC-005: đạt (tiêu chí 3 PASS, 4 PASS); thiếu thời lượng
  (4 SHORT); khoảng lặng 7 s (3 FAIL, có trong `over_5s` kèm câu liền trước); tạm dừng dài (không tính, 3 PASS); app tắt giữa chừng (không
  summary → 4 FAIL, vẫn ra báo cáo từ `gaps.jsonl`); thêm: không khoảng nào → 3 FAIL "không đủ dữ liệu"; `fake_run` có ghi chú "chưa phải
  tổng duyệt thật"; cảnh báo `frozen`/`audio_missing` → 4 FAIL; điều kiện chạy có `mouth_method`, `power` (FR-014…FR-016) (phụ thuộc T036)
- [x] T038 [P] [US3] Test lệnh `report` trong `tests/unit/test_ops_cli.py`: `<session_dir|id>`, `--show`, mặc định show cuối, `--json`,
  mã thoát 0/1/2, ra `rehearsal_<show_id>.md/.json` cạnh log (FR-017, `contracts/cli.md`) (phụ thuộc T036)

### Implement US3

- [x] T039 [US3] `src/ai_live/ops/rehearsal.py`: `Verdict`, `RehearsalReport`, `load_show_logs`, `build_report` (quy tắc data-model
  §4) (phụ thuộc T037)
- [x] T040 [US3] `src/ai_live/ops/rehearsal.py`: `render_markdown` (tiếng Việt, `contracts/files.md` §5) và `write_report` (phụ thuộc T039)
- [x] T041 [US3] `src/ai_live/ops/__main__.py`: lệnh `report` (phụ thuộc T040, T038)
- [x] T042 [US3] Chạy `report` trên một phiên static thật vài phút (quickstart §3), đối chiếu bằng tay p95/max với `gaps.jsonl`

**Checkpoint:** US3 chạy và test độc lập được.

---

## Phase 6: User Story 4: Làm video dự phòng 2–3 phút (P4)

**Mục tiêu:** một lệnh chạy show thật ở nội dung `verbatim`, ghi bằng recorder fork, kiểm và ra video + tờ mô tả.
**Kiểm thử độc lập:** chạy lệnh → video 120–180 s, có tiếng, có nhãn "AI", tờ mô tả đúng (spec US4).

### Test cho US4 (viết trước, phải FAIL trước khi implement)

- [x] T043 [P] [US4] Test nội dung `verbatim` trong `tests/integration/test_show_verbatim.py`: `POST /api/show/start
  {"content":"verbatim"}` → engine đếm 0 lượt gọi; câu phát là nguyên văn `intro` rồi `description`, sản phẩm chính trước rồi sản phẩm
  phụ; đoạn kết dùng `CLOSING_FALLBACK_SENTENCE`; chế độ show `normal` (không cảnh báo `fallback_mode`); `GET /api/show.content_source`
  = `verbatim`; thân khác → 422; show đang chạy → `already_running`, nguồn không đổi; không thân → như 004 (FR-020)
- [x] T044 [US4] Test FR-021 trong `tests/integration/test_show_verbatim.py`: không route nào của app trả `video/*` hay đọc file
  trong `BACKUP_VIDEO_DIR` (duyệt `app.routes`)
- [x] T045 [P] [US4] Test `BackupVideoMaker` trong `tests/unit/test_backup_video.py` (client app/fork giả, chạy analyze giả, đồng hồ
  giả): đúng thứ tự R7; từ chối khi ảnh tĩnh, khi show đang chạy, khi host chưa sẵn sàng, khi fork không bật ghi (mã 2); `--seconds`
  ngoài 120–180 → lỗi; sheet `ok` chỉ khi độ dài/tiếng/nhãn đạt, `problems` tiếng Việt khi không; tên `backup_<YYYYmmdd-HHMM>_<khách>`;
  chép mp4 nguyên vẹn; `.sheet.json` + `.sheet.md` có `note` "chỉ dùng ngoài Shopee"; luôn dừng ghi và kết thúc show khi có lỗi giữa
  chừng (FR-018, FR-019)

### Implement US4

- [x] T046 [US4] `src/ai_live/core/models.py`: `ShowSession.content_source` (`script` | `verbatim`, mặc định `script`) và
  `ShowSnapshot.content_source`; `src/ai_live/director/show_director.py`: `start_show(t_mono, content=...)` (phụ thuộc T043)
- [x] T047 [US4] `src/ai_live/director/script_runner.py`: `verbatim` đi thẳng `_prepare_fallback`, đoạn kết dùng
  `CLOSING_FALLBACK_SENTENCE`, không gọi engine, giữ `ShowMode.NORMAL` (phụ thuộc T046)
- [x] T048 [US4] `src/ai_live/app/routes.py`: `POST /api/show/start` nhận thân tùy chọn `{"content": ...}` (phụ thuộc T046)
- [x] T049 [US4] `src/ai_live/ops/backup_video.py`: `BackupVideoSheet`, `BackupVideoMaker` (client app + fork, chạy show, dừng ghi,
  gọi `ailive_ext.analyze` bằng python của fork, đọc `report.json`, chép video, viết tờ mô tả) (phụ thuộc T045, T048, T017)
- [x] T050 [US4] `src/ai_live/ops/__main__.py`: lệnh `backup-video [--seconds 150] [--content verbatim|script] [--url]` (phụ thuộc T049)

**Checkpoint:** US4 test được không GPU; chạy thật ở đợt GPU (T055).

---

## Phase 7: Hoàn thiện và việc chung

- [x] T051 [P] Cập nhật `docs/RUNBOOK.md`: T-1 ngày/T-1 giờ dùng lệnh `readiness`; bảng sự cố §4 khớp đúng chữ banner cảnh báo; §5 video
  dự phòng bằng lệnh `backup-video` (bật/tắt `AILIVE_RECORD_DIR`); §6 biến `WATCHDOG_*`; sau buổi demo chạy `report`
- [x] T052 [P] Cập nhật `docs/ARCHITECTURE.md` (gói `ops`, tin `host_status`, sự kiện `alert`, file log phiên mới), `docs/RISKS.md`
  (video dự phòng chứa mặt/giọng người mẫu; quên tắt ghi luồng; điều tiết timer tab nền), `src/README.md` (gói `ops`)
- [x] T053 Chạy `uv run ruff check . && uv run ruff format --check .`, `uv run pytest`, test fork
  (`vendor/livetalking/.venv/Scripts/python.exe -m pytest -q ailive_ext/tests`) đều sạch
- [x] T054 [GPU] SC-004: show 30 phút `REPLY_ENGINE=fake TTS_PROVIDER=vieneu AVATAR_MODE=livetalking` với canh show bật (quickstart §6);
  `report` của show đó; so lặng p95 và câu đầu với 005 T073; đếm cảnh báo sai (SC-002 phần show không lỗi); ghi vào quickstart
- [x] T055 [GPU] SC-006 phần máy: làm video dự phòng bằng `backup-video` (quickstart §5, `verbatim`, fork bật `AILIVE_RECORD_DIR`), kiểm
  tờ mô tả `ok`; tắt fork bật lại không ghi, `readiness` mục `recording` về Đạt
- [x] T056 [GPU] SC-002 trên GPU: giữa show tắt fork → `fork_lost`; bật lại → đóng; ghi thời gian báo/tắt vào quickstart
- [x] T057 SC-007: kiểm log phiên của mọi lần chạy trong feature không có lượt gọi chuỗi model (`REPLY_ENGINE=fake`, không có
  `llm_chain` trong log); ghi vào quickstart
- [ ] T058 Chờ người dùng: xem lại video dự phòng (tiếng khớp miệng, nhãn "AI") và thử phát qua Meet có tiếng (SC-006 phần người);
  xác nhận ADR-057; ghi vào `progress/OPEN.md` §4 (đã ghi 2026-11-13, chờ người dùng)
- [x] T059 Chạy `/update-context`

## Phụ thuộc và thứ tự

- Setup (T001–T004) → Foundational (T005–T017) → US1 → US2 → US3 → US4 → Hoàn thiện. US3 và US4 không phụ thuộc US2 về code (chỉ đọc
  `alerts.jsonl` nếu có), nên làm được trước US2 nếu cần.
- T012 cần T008; T022 cần T010, T017; T031 cần T006, T008; T033 cần T015; T049 cần T048, T017.
- T054–T056 cần US1–US4 xong; T058 cần T055.

## Chạy song song

- Foundational: T005, T007, T009, T014, T016 (test, khác file).
- US1: T018, T019, T020. US2: T027, T028 (T029 cùng file, làm sau T028), T033. US3: T036 rồi T037, T038. US4: T043 (T044 cùng file, làm sau), T045.

## Đợt GPU

- T054, T055, T056 chạy liền một lần bật fork trên GPU laptop (ADR-023); không RunPod. T055 bật fork với `AILIVE_RECORD_DIR`, T054 và T056
  bật lại không ghi.

## Chiến lược MVP

- MVP = Setup + Foundational + US1: có ngay nút/lệnh kiểm tra trước demo. US2 thêm an toàn lúc chạy; US3 phục vụ tổng duyệt 30 phút
  (PRD tiêu chí 3, 4); US4 cho video dự phòng (PRD tiêu chí 5).

## Phủ FR / SC

| Yêu cầu | Task |
|---|---|
| FR-001 | T019, T020, T023, T024, T025 |
| FR-002 | T018, T021 |
| FR-003 | T016, T017, T018, T021, T022 |
| FR-004 | T019 |
| FR-005 | T018, T021 |
| FR-006 | T007, T019, T023 |
| FR-007 | T014, T015, T027, T029, T030, T033 |
| FR-008 | T028, T032, T034 |
| FR-009 | T007, T028, T031 |
| FR-010 | T027, T028, T031 |
| FR-011 | T002, T003, T027 |
| FR-012 | T031 (không chặn), T054 |
| FR-013 | T011, T012, T013, T037, T039 |
| FR-014 | T037, T039 |
| FR-015 | T037, T040 |
| FR-016 | T013, T037, T039 |
| FR-017 | T038, T040 |
| FR-018 | T045, T049, T050, T055 |
| FR-019 | T045, T049 |
| FR-020 | T043, T046, T047, T048 |
| FR-021 | T044 |
| SC-001 | T018, T019, T026 |
| SC-002 | T027, T028, T029, T035, T054, T056 |
| SC-003 | T028 |
| SC-004 | T054 |
| SC-005 | T036, T037 |
| SC-006 | T055, T058 |
| SC-007 | T019, T043, T057 |
