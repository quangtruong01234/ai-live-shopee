# Tasks: Bố cục cảnh live quanh AI host

- **Feature ID:** `009-live-scene-layout` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/)

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được · **[GPU]**: cần GPU laptop (ADR-023) · **[US#]**: thuộc user story nào

## Phase 1: Setup

- [x] T001 Khai báo `pillow` trong `pyproject.toml` (ADR-051), `uv lock` không tải gói mới; thêm `assets/scenes/` vào `.gitignore`
- [x] T002 [P] `SCENE_ENABLED`, `SCENE_DIR`, `SCENE_SUBTITLES`, `SCENE_FONT_PATH` trong `src/ai_live/core/config.py` và `.env.example`
- [x] T003 [P] `scripts/make_demo_scene.py`: vẽ bàn gỗ, ảnh "ẢNH MẪU" cho từng sản phẩm trong `PRODUCT_DATA_PATH`, `scene.json`,
  `provenance.json` (`placeholder: true`, bàn `drawn`) ra `assets/scenes/demo/`

## Phase 2: Foundational

- [x] T004 Kiểu dữ liệu `src/ai_live/scene/models.py` (SceneSet, ProductArt, Provenance, SceneIssue, FrameGeometry, LayoutParams,
  SceneLayer) theo data-model
- [x] T005 [P] `src/ai_live/scene/fonts.py`: tìm font theo `SCENE_FONT_PATH` → font hệ thống; lỗi tiếng Việt khi không có
- [x] T006 [P] `EventType.SCENE` trong `src/ai_live/core/events.py`; `PlaybackListener`, `PlaybackSource`, `SceneSink` trong
  `src/ai_live/core/protocols.py` (contracts/adapters.md)
- [x] T007 Test `tests/unit/test_playback_listener.py`: StaticRenderer, LiveTalkingRenderer (fork giả), SwitchingRenderer gọi
  `playback_started/ended/stopped` đúng lúc; lỗi trong listener không hỏng lượt nói
- [x] T008 Cài `add_playback_listener` trong `src/ai_live/avatar/static_renderer.py`, `livetalking_renderer.py`, `switching_renderer.py`
- [x] T009 Thêm `product_id` vào payload `sentence` của câu kịch bản (`src/ai_live/director/script_runner.py`) + test trong
  `tests/unit/` của 004 hiện có

**Checkpoint:** renderer báo phát được; lõi show có product_id.

---

## Phase 3: User Story 1: Bàn bày sản phẩm kèm thẻ tên/giá (P1) 🎯 MVP

**Kiểm thử độc lập:** bộ cảnh mẫu + dữ liệu demo, chế độ ảnh tĩnh và nhép miệng, ảnh chụp không che mặt/nhãn/watermark.

### Test (viết trước)

- [x] T010 [P] [US1] `tests/unit/test_scene_loader.py`: bộ đủ ảnh; JPEG → `no_alpha`; ảnh hỏng; thiếu ảnh; ảnh mồ côi; overflow;
  thiếu provenance; edit cấm; `customer_mismatch`; thiếu `scene.json`; thiếu thư mục (không ném lỗi)
- [x] T011 [P] [US1] `tests/unit/test_scene_layout.py`: chính ở giữa; thứ tự phụ; mọi hộp dưới vùng cấm mặt và ngoài hộp nhãn/watermark
  ở cả 4 vị trí nhãn; thẻ tên ≤ 2 dòng + "…"; khoảng giá; `desk_top` sai → mặc định; face_bottom thấp → `layout_keep_out`
- [x] T012 [P] [US1] `tests/unit/test_scene_render.py`: lớp base RGBA, alpha = 0 trong vùng cấm; chữ có dấu vẽ được; vẽ < 300 ms;
  ảnh tĩnh 480×832; thẻ không có số nào ngoài số trong file;
  mọi `scene.json` hợp lệ đều không đụng hộp nhãn "AI" (FR-020)
- [x] T013 [P] [US1] `tests/unit/test_scene_controller.py`: CONTENT_REPLACED vẽ lại từ một snapshot; gửi lớp cho sink; tắt cảnh không
  làm gì; geometry từ fork khác ước lượng → vẽ lại; lỗi vẽ → sự kiện `scene` error, phiên chạy tiếp
- [x] T014 [P] [US1] `tests/integration/test_scene_api.py`: `/api/scene`, `/api/scene/still.png`, `/api/host-config.scene`, `/host`
  dùng ảnh cảnh khi bật, giữ nguyên khi tắt; tin `scene` trên `/ws/host`
- [x] T015 [P] [US1] `tests/integration/test_scene_fork.py`: fork giả nhận `scene_layer`; gửi lại khi `hello`; `scene_rejected` không
  hỏng lượt nói; `hello.scene` cập nhật geometry; `stats.scene_ms` vào `/api/latency`

### Implement

- [x] T016 [US1] `src/ai_live/scene/loader.py` (contracts/scene-set.md)
- [x] T017 [US1] `src/ai_live/scene/layout.py` (thuần, research R4)
- [x] T018 [US1] `src/ai_live/scene/render.py` (lớp base, ảnh tĩnh, đục vùng cấm)
- [x] T019 [US1] `src/ai_live/scene/controller.py` (CONTENT_REPLACED, geometry, vẽ trong thread, sink, ảnh tĩnh, sự kiện, log)
- [x] T020 [US1] `src/ai_live/scene/__main__.py`: `check`, `preview` (`--highlight`, `--subtitle`, `--debug-zones`)
- [x] T021 [US1] `LiveTalkingRenderer`: `set_scene_layer`, gửi lại khi hello, `hello.scene` → listener geometry, `scene_rejected` không
  gọi `_fail_waiters`, `stats.scene_ms`; `SwitchingRenderer` chuyển tiếp; `RenderTurnStats.scene_ms`, `TurnLatency.scene_ms`
- [x] T022 [US1] Fork `vendor/livetalking/ailive_ext/scene.py` + `ailive_ext/tests/test_scene.py` (contracts/fork-protocol.md §2, §5)
- [x] T023 [US1] Fork: `ingest.py` nhận `scene_layer`, `hello.scene`, `stats.scene_ms`; móc `# ailive: scene` trong
  `avatars/base_avatar.py`
- [x] T024 [US1] App: `main.py` dựng controller, `context.py`, `routes.py` (`/api/scene`, still, host-config, `/host`), `/ws/host` tin
  `scene`; `host.js` đổi ảnh; `control.html/js` dòng "Cảnh"
- [x] T025 [US1] Chụp `/host` bằng Chrome DevTools MCP (static), tinh chỉnh bố cục cho live, chụp lại
- [x] T026 [GPU] [US1] Chạy fork trên GPU laptop: cảnh trong WebRTC, watermark + nhãn trên cùng, về ảnh tĩnh giữ cảnh (quickstart §6)

**Checkpoint:** US1 demo được.

---

## Phase 4: User Story 2: Làm nổi sản phẩm đang nói (P2)

- [x] T027 [P] [US2] Test controller: đổi nổi theo `playback_started` (không theo `sentence`); phân đoạn chung bỏ nổi; comment giữ nguyên;
  pause giữ; idle/ended bỏ; sản phẩm không có chỗ → không nổi; log `scene_highlight` (trong `tests/unit/test_scene_controller.py`)
- [x] T028 [P] [US2] Test layout/render: món nổi ×scale vẫn dưới vùng cấm; khuyến mãi đầu tiên chỉ trên thẻ món nổi; món khác dịu
  (trong `test_scene_layout.py`, `test_scene_render.py`)
- [x] T029 [US2] Controller: bản đồ utterance → product_id, PlaybackListener, SHOW_STATE; render: glow, viền thẻ, làm dịu
- [x] T030 [US2] Chụp màn hình lúc đổi sản phẩm nổi, tinh chỉnh hiệu ứng

---

## Phase 5: User Story 3: Phụ đề trong khung (P3)

- [x] T031 [P] [US3] Test: `SCENE_SUBTITLES` bật → lớp `subtitle` khi phát, xóa khi xong/dừng; ≤ 2 dòng; host-config báo để ẩn phụ đề web
- [x] T032 [US3] Controller + render lớp subtitle; `host.js` ẩn phụ đề web khi bật

---

## Phase 6: Hoàn thiện

- [x] T033 `uv run ruff check . && uv run ruff format --check .`, `uv run pytest`, test fork
- [x] T034 [GPU] Đo SC-004 (quickstart §7), ghi ADR-052 và card
- [x] T035 SC-001: chụp ≥ 20 ảnh, kiểm vùng cấm (quickstart §8)
- [x] T036 [P] `docs/ARCHITECTURE.md` (lớp cảnh, PlaybackListener), 005 `fork-protocol.md` dòng trỏ tới 009, `src/README.md`
- [x] T037 `/update-context`; gói duyệt (quickstart §9)
- [x] T038 SC-002, SC-003, SC-005: show có cảnh (ảnh tĩnh hoặc fork), thay file giữa phiên, đối chiếu log `scene_highlight` với
  `playback_started` câu đầu mỗi phân đoạn (≥ 10 lần đổi), thẻ ↔ file; ghi kết quả vào card (thêm sau `/sdd.analyze`)

## Phụ thuộc

Setup → Foundational (T004–T009) → US1 → US2 → US3 → Hoàn thiện. T022–T023 (fork) độc lập với T016–T020 (app) trừ hợp đồng.

## Đợt GPU

T026, T034: GPU laptop, cùng một lần bật fork.

## Chiến lược MVP

US1 đủ demo (bàn + thẻ). US2 làm ngay sau vì bố cục đã tính cỡ món nổi. US3 mặc định tắt.
