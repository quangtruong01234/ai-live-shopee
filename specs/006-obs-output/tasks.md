# Tasks: Đưa AI host vào OBS

- **Feature ID:** `006-obs-output` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được · **[GPU]**: cần GPU laptop (ADR-023) · **[US#]**: thuộc user story nào

## Phase 1: Setup

- [x] T001 [P] Test `tests/unit/test_config.py`: `OUTPUT_MODE` mặc định `meet`; `obs`, ` OBS ` → `obs`; `webrtc` → `meet` và cờ
  legacy; `virtualcam`, `rtmp`, `abc` → lỗi cấu hình "OUTPUT_MODE chỉ nhận meet hoặc obs"
- [x] T002 `OUTPUT_MODE` trong `src/ai_live/core/config.py` (validator chuẩn hóa, giữ cờ legacy); log `output_mode_legacy` (WARNING)
  một lần lúc khởi động trong `src/ai_live/app/main.py`; `.env.example` dòng `OUTPUT_MODE=meet # meet | obs` kèm chú thích `webrtc` cũ

## Phase 2: Foundational (vai kết nối, dùng cho mọi story)

- [x] T003 Test `tests/unit/test_host_roles.py` với kết nối giả: đủ 5 dòng bảng chuyển trạng thái (data-model §2); mã 4000/4001 và
  `reason` `obs_active`; kết nối bị từ chối gửi `ready` hay `playback_started` bị bỏ qua, không phát `HOST_CONNECTION`; `host_role`
  đúng sau mỗi bước và về None khi kết nối phát đóng; trang host bị nhường không tự lấy lại khi `obs` đóng; payload `HOST_CONNECTION`
  có `role` (`null` khi `connected` false)
- [x] T004 `CLOSE_YIELDED = 4001`, `attach(conn, role)` theo luật obs > host, `host_role`, `role` trong payload `HOST_CONNECTION` ở
  `src/ai_live/avatar/static_renderer.py`; log `host_role_yielded`
- [x] T005 Chuyển tiếp `attach(..., role)` và `host_role` qua `src/ai_live/avatar/switching_renderer.py`,
  `src/ai_live/avatar/livetalking_renderer.py` (và `src/ai_live/core/protocols.py` nếu Protocol khai báo `attach`); test renderer hiện
  có vẫn qua với `role` mặc định `host`
- [x] T006 `src/ai_live/app/ws.py`: đọc query `role` của `/ws/host` (thiếu hoặc lạ → `host`) và truyền vào `attach`

**Checkpoint:** server giữ đúng một kết nối phát theo vai; `/host` cũ chạy y như trước.

---

## Phase 3: User Story 1: Thêm AI host vào OBS thành một nguồn có tiếng (P1) 🎯 MVP

**Kiểm thử độc lập:** OBS (hoặc Chrome mô phỏng CEF) mở `/obs`, có hình + tiếng không bấm gì, nhãn "AI" luôn trong khung, co giãn
không cắt.

### Test (viết trước)

- [x] T007 [P] [US1] `tests/integration/test_obs_page.py`: `GET /obs` trả HTML có `<body class="host obs">`, nhãn "AI" đã thay chữ và vị
  trí, `Cache-Control: no-store`; query `?ai_label=0`, `?label=off`, `?obs=0` không đổi HTML (Điều I); `/host` vẫn `<body class="host">`;
  `/api/host-config` có `output_mode`; không route nào trả file video (007 FR-021 giữ nguyên)
- [x] T008 [US1] Thêm vào `tests/integration/test_obs_page.py`: `/ws/host?role=obs` nhận tin `scene`, `mode`, PCM của câu khi show chạy
  (renderer tĩnh), `/ws/host?role=host` mở sau đó bị đóng 4001

### Triển khai

- [x] T009 [US1] `GET /obs` trong `src/ai_live/app/routes.py`: dùng chung hàm dựng trang với `/host` (tham số lớp body), cùng chờ cảnh
  `HOST_SCENE_WAIT_S`; `output_mode` trong `/api/host-config`; truyền `output_mode` qua `src/ai_live/app/context.py`
- [x] T010 [P] [US1] `src/ai_live/app/static/style.css`: `body.obs` ẩn `#start-overlay`, `#host-status`, `#subtitle`, nền đen, không thanh
  cuộn; giữ `.stage.scene-on` 480×832 ở giữa và `object-fit: contain` (FR-004)
- [x] T011 [US1] `src/ai_live/app/static/host.js` chế độ obs (`document.body.classList.contains("obs")`): tự tạo `AudioContext` và bắt
  đầu khi tải (không chờ nút), mở `/ws/host?role=obs`; trang `/host` mở `?role=host`; không ghi chữ trạng thái khi obs
- [x] T012 [US1] Kiểm bằng Chrome DevTools MCP với Chrome `--autoplay-policy=no-user-gesture-required` (quickstart §4): `/obs` có
  `AudioContext` `running` không bấm, ack `playback_started` tới server khi show `verbatim`/fake chạy, ảnh chụp có nhãn "AI" và không có
  chữ giao diện, đổi cỡ cửa sổ 1280×720 và 720×1248 không cắt nhãn; trước khi show chạy trang hiện ảnh chờ + nhãn, không trống hay báo
  lỗi (US1 #5) (FR-002, FR-003, FR-004)

**Checkpoint:** MVP: OBS nhận hình + tiếng từ `/obs` ở chế độ ảnh tĩnh.

---

## Phase 4: User Story 2: Chạy lâu, tự nối lại, trang host không cướp tiếng (P2)

**Kiểm thử độc lập:** tắt/bật fork và app, mở `/host` song song, thêm nguồn `/obs` hai lần; OBS không mất tiếng, không nói đôi.

### Test (viết trước)

- [x] T013 [P] [US2] Thêm vào `tests/unit/test_host_roles.py`: chuỗi host → obs → host → obs-mới → obs đóng: đúng kết nối phát và đúng mã
  đóng từng bước; lượt nói đang phát khi bị nhường dừng sạch (ack chờ được hủy như `_drop_connection` hiện nay), show chuyển sang trang
  mới không treo
- [x] T014 [US2] Thêm vào `tests/integration/test_obs_page.py`: show đang chạy qua `/ws/host?role=host`, mở `?role=obs` → câu kế
  tiếp phát ở obs, trang host nhận 4001; đóng obs rồi mở obs mới → nhận lại cảnh hiện tại (`scene`) và `mode`

### Triển khai

- [x] T015 [US2] `host.js`: khi ws đóng 4000/4001 (cả hai vai) dừng Web Audio, tắt tiếng + `pause()` `<video>`, đóng `RTCPeerConnection`,
  hủy hẹn giờ `/offer` lại, dừng nhịp `host_status`, không nối lại (R5); trang `/host` nhận 4001 hiện "Đang phát qua OBS, xem trong cửa sổ
  OBS. Tải lại trang nếu muốn phát ở đây."; `/obs` nhận 4000 im lặng giữ ảnh tĩnh + nhãn
- [x] T016 [US2] `host.js` chế độ obs: mất ws với mã khác → thử nối lại mỗi 1 s, nối được sau một lần mất thì `location.reload()` (R6)
- [x] T017 [US2] Kiểm bằng MCP (quickstart §4): `/host` bị `/obs` nhường → peer đóng, `<video>` dừng, không gọi `/offer` nữa; tắt và bật
  lại app (port riêng) → trang `/obs` tự tải lại và có tiếng ≤ 15 s; hai trang `/obs` → trang cũ im (FR-005, FR-006, FR-007, FR-008)
- [ ] T018 [GPU] [US2] Đo thời gian fork xóa phiên WebRTC sau khi trang cũ đóng peer (R5 TODO, Q31): `/host` có hình nhép miệng →
  mở `/obs` → thời điểm `/obs` có `framesDecoded` > 0; lặp 5 lần; > 8 s thì dừng lại ghi đề xuất ADR cờ `ailive_takeover` cho người dùng
- [ ] T019 [GPU] [US2] Fork tắt/bật giữa show khi `/obs` đang phát: về hình nhép miệng ≤ 10 s sau khi fork sẵn sàng, 5 lần (SC-004)

**Checkpoint:** OBS chạy lâu không cần chạm; trang host không cướp tiếng.

---

## Phase 5: User Story 3: Biết đầu ra OBS có đang nhận không (P3)

**Kiểm thử độc lập:** `OUTPUT_MODE=obs`, chưa có nguồn / có trang host / có nguồn OBS / nguồn đóng giữa show.

### Test (viết trước)

- [x] T020 [P] [US3] Test kiểm tra trước demo (file test readiness hiện có của 007): mỗi dòng bảng contracts §7 cho `obs`; `meet` và
  `webrtc` giữ đúng lời 007
- [x] T021 [P] [US3] Test canh show (file test watchdog hiện có của 007): `obs` + kết nối `host` nhận quyền → mở `host_closed`; `obs`
  đóng → `host_closed` "Nguồn OBS đã ngắt" ≤ 10 s; `obs` nối lại → tự tắt; `obs` còn nối nhưng không nhịp > `WATCHDOG_HOST_STALE_S`
  → `host_closed` chi tiết `stale`, nhịp tới lại → tự tắt; `meet` không có luật nhịp; lời `frozen`, `audio_missing` theo chế độ
  (contracts §8); chế độ `meet`: trang mới thay trang cũ không để `host_closed` mở sau khi trang mới `ready`
- [x] T022 [US3] Test `/api/state` và snapshot `/ws/control` có `output_mode`, `host_role` (thêm vào `tests/integration/test_obs_page.py`)

### Triển khai

- [x] T023 [US3] `src/ai_live/ops/readiness.py` `check_host` theo `OUTPUT_MODE` và `host_role` (contracts §7); ghi `output_mode` vào
  kết quả kiểm tra
- [x] T024 [US3] `src/ai_live/ops/watchdog.py`: "đầu ra đang nối" theo vai khi `obs`, luật nhịp ngừng `WATCHDOG_HOST_STALE_S` (cấu hình
  mới trong `src/ai_live/core/config.py` + `.env.example`, mặc định 10), lời nhắn và việc cần làm theo chế độ (contracts §8)
- [x] T025 [US3] `/api/state` + snapshot thêm `output_mode`, `host_role` (`src/ai_live/app/routes.py`, `ws.py`); `control.js` hiện dòng
  "Đầu ra: OBS (đã nối)" / "Đầu ra: Meet — trang host (đã nối)" / "(chưa nối)"
- [x] T026 [US3] Kiểm bằng MCP: quickstart §3 bước 1–5 trên trang điều khiển (SC-007 phần máy, 3/3)

**Checkpoint:** người vận hành biết OBS có đang nhận hay không.

---

## Phase 6: Hoàn thiện

- [x] T027 [P] `docs/RUNBOOK.md` §8 "Phát qua OBS": thêm Browser Source (URL, 720×1248, "Control audio via OBS", bỏ "Shutdown source when
  not visible", Monitor Off), bật app trước OBS, Refresh khi lỗi, không mở `/obs` trên Chrome, không mở `/host` khi đang phát OBS, tắt chế
  độ ngủ và tắt màn hình của Windows trước phiên dài (FR-011, Q28–Q32, trường hợp biên của spec)
- [x] T028 [P] `docs/ARCHITECTURE.md` (đầu ra: `OUTPUT_MODE=meet|obs`, trang `/obs`, vai trên `/ws/host`; `OutputSink` vẫn để sau),
  `src/README.md`, 005 `contracts/api.md` hoặc 001 `contracts/api.md` dòng trỏ tới 006 cho `/ws/host?role=`
- [~] T029 Dựng OBS portable (ADR-059) ở `%LOCALAPPDATA%\ai-live\obs`: collection `ailive` một Browser Source `/obs` 720×1248, profile
  ghi Fragmented MP4; chạy `--portable --collection ailive --startrecording`, ghi 2 phút ảnh tĩnh + show fake; kiểm tiếng vào bản ghi và
  `framesDecoded` (R3 TODO); kiểm `lipsync_check.py` đọc được file (R10 TODO)
  *(2026-11-13: đã tải OBS 33.0.1 zip, giải nén, dựng `config/obs-studio` portable (collection + profile `ailive`, Fragmented MP4 ra
  `out/006_obs/`); lần chạy `obs64.exe` bị bộ phân quyền của Claude Code chặn nên chưa ghi. Chuyển vào gói duyệt, quickstart §5)*
- [ ] T030 [GPU] SC-002, SC-003: OBS portable ghi show 30 phút có nhép miệng (`REPLY_ENGINE=fake` hoặc `verbatim`), chấm nhãn ≥ 60 khung
  và lệch hình–tiếng so với bản ghi của fork (`AILIVE_RECORD_DIR`) cùng show
- [ ] T031 [GPU] SC-005, SC-006: cùng show 30 phút qua `/host` và qua OBS, so lặng p95 bằng `python -m ai_live.ops report`; trong show OBS mở/đóng
  `/host` 5 lần (MCP), đếm câu nói đôi và câu mất trong bản ghi
- [x] T032 FR-012, FR-013: kiểm `/obs` không có đường nào phát file ghi sẵn (grep `host.js` + test T007); bảng độ trễ `/api/latency` có
  đủ mốc cho show qua OBS (log `avatar_first_frame`, `playback_started`)
- [x] T033 `uv run ruff check . && uv run ruff format --check .`, `uv run pytest`
- [x] T034 Ghi kết quả vào quickstart §5; gói duyệt cho người dùng: thêm nguồn trong OBS thật của mình theo runbook §8 và bấm giờ
  (SC-001), xem/nghe bản ghi OBS, xác nhận ADR-058/059
- [x] T035 `/update-context` (CLAUDE.md, ROADMAP M2, DECISIONS, FEATURES)

## Phụ thuộc

Setup (T001–T002) → Foundational (T003–T006) → US1 → US2 → US3 → Hoàn thiện. US3 (T020–T025) chỉ cần Foundational và T002, làm song
song với US1/US2 được. T015–T016 cùng sửa `host.js` với T011, làm tuần tự.

## Đợt GPU

T018, T019, T030, T031: GPU laptop, cùng một lần bật fork (`scripts/livetalking/run.ps1`), `REPLY_ENGINE=fake` hoặc `verbatim`.

## Chiến lược MVP

Setup + Foundational + US1: OBS có AI host ảnh tĩnh có tiếng. US2 sửa lỗi nói đôi khi trang bị thay (cần cả cho Meet), nên làm ngay sau.
US3 đổi lời kiểm tra và canh show.

## Bảng phủ FR/SC

| Mục | Task |
|-----|------|
| FR-001 | T007, T009, T011 |
| FR-002 | T010, T012 |
| FR-003 | T007, T012, T030 |
| FR-004 | T010, T012 |
| FR-005 | T016, T017, T019 |
| FR-006 | T003, T004, T013, T014 |
| FR-007 | T008, T015, T017 |
| FR-008 | T003, T015, T017 |
| FR-009 | T020, T023 |
| FR-010 | T021, T024 |
| FR-011 | T027 |
| FR-012 | T007, T032 |
| FR-013 | T032, T031 |
| FR-014 | T001, T002 |
| SC-001 | T027, T034 |
| SC-002 | T030 |
| SC-003 | T030 |
| SC-004 | T017, T019 |
| SC-005 | T031 |
| SC-006 | T017, T031 |
| SC-007 | T020, T021, T026 |
