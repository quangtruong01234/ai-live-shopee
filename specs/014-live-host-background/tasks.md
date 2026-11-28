# Tasks: Nền sau người dẫn giống phòng live của shop

- **Feature ID:** `014-live-host-background` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/) (fork-protocol, adapters, prepare-cli, api, events),
  [quickstart.md](./quickstart.md) · ADR-083, ADR-084 (Đề xuất) · Không gói pip mới; không tải model (cách `plate` mặc định).

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[GPU]**: cần GPU; chạy trên GPU laptop (ADR-023), RunPod chỉ khi laptop không chạy được và chủ dự án đồng ý chi phí; chỉ nằm trong
  phần "Đợt GPU"
- **[US#]**: thuộc user story nào. Phase Setup, Foundational và Hoàn thiện không gắn nhãn này.
- Agent làm chủ (plan): ai-media cho `vendor/livetalking/` (fork, repo git riêng), `src/ai_live/scene/`, `src/ai_live/avatar/`;
  ai-orchestrator cho `src/ai_live/core/`, `src/ai_live/app/`, `src/ai_live/ops/`, `.env.example`; ai-qa cho `tests/` và các buổi đo.
- Mọi dòng sửa trong file gốc của fork đánh dấu `# ailive: 014`; code, comment, docstring tiếng Anh; chữ hiện cho người dùng tiếng Việt.

## Phase 1: Setup

- [x] T001 Kiểm môi trường không cài gì mới: `git -C vendor/livetalking log -1` (commit 477d4e4, cây sạch); venv fork
  `vendor/livetalking/.venv` import được `cv2` (có `cv2.copyTo`, `cv2.boxFilter`, `cv2.grabCut`), `numpy`, `mediapipe` 1.2.3 (ADR-053);
  `git check-ignore` xác nhận `assets/avatars/<id>/background/` và `assets/scenes/` bị chặn (không commit mặt nạ, khung người mẫu)
  — Ghi chú 2026-11-24: cây fork vẫn ở commit 477d4e4 nhưng chưa sạch (21 file sửa chưa commit từ các feature trước).
- [x] T002 [P] Thêm `BACKGROUND_SEGMENTER_MODEL: str = ""` vào `src/ai_live/core/config.py` và một dòng có chú thích trong `.env.example`
  (chỉ dùng cho `--method mediapipe` sau ADR-083, không tải model); test mặc định rỗng trong `tests/unit/test_config.py`
- [x] T003 [P] Bộ sinh khung tổng hợp cho test fork `vendor/livetalking/ailive_ext/tests/bg_synth.py` (không commit ảnh): phòng có vân (kệ
  trắng, dải vàng, mảng xanh), "người" là elip màu da/áo di chuyển và nghiêng qua N khung, mép bàn ở `desk_top_px`; trả khung BGR kèm mặt
  nạ đúng để so
- [x] T004 [P] Bộ dựng thư mục `background/` giả cho test app `tests/fixtures/background_builder.py`: `manifest.json` (hợp lệ / thiếu /
  `mismatch` / `reviewed` true-false), `preview_frame.png`, mặt nạ elip đúng cỡ khung (data-model §2)
- [x] T005 [P] Mở rộng `tests/fixtures/fake_fork.py`: tham số `background` cho khối `hello.background` (None = fork cũ không có 014), ghi
  lại các tin `scene_background` nhận được, trả `background_rejected` / `background_failed` theo lệnh của test, `stats.background_ms`

## Phase 2: Foundational

⚠️ Chưa xong phase này thì chưa làm user story nào.

- [x] T006 [P] Test loader `tests/unit/test_scene_background_loader.py` (data-model §1): thiếu khối → `style: "goc"` mặc định; đọc
  `ke_hang` kèm số; kiểu lạ → lỗi `bad_scene_json` của 009 và dùng `goc`; `softness_px` 12 → 8, `brightness` 0,5 → 0,8, `max_items` 0 → 1
  kèm log `background_clamped` (`field`, `value`, `clamped_to`); khoá lạ → `background_unknown_key` và bỏ qua; `bang_shop` / `anh_shop`
  đọc được
- [x] T007 Thêm `BackgroundConfig` (style, softness_px, brightness, max_items) và trường `background` mặc định `goc` vào `SceneSet` trong
  `src/ai_live/scene/models.py`
- [x] T008 Thêm `"background"` vào `_SCENE_KEYS` và đọc khối, kẹp khoảng, cảnh báo khoá lạ trong `src/ai_live/scene/loader.py` (để T006 đạt)
- [x] T009 [P] Test `tests/unit/test_render_protocols.py`: `BackgroundSink` kiểm được bằng `isinstance`; `StaticRenderer` không phải
  `BackgroundSink`; dựng `ForkBackgroundStatus` từ khối `hello.background`, thiếu khối → None (contracts/adapters.md)
- [x] T010 Thêm `ForkBackgroundStatus` và Protocol tuỳ chọn `BackgroundSink` (`set_scene_background(plate_png: bytes | None)`,
  `add_background_status_listener(callback)`) vào `src/ai_live/core/protocols.py`
- [x] T011 [P] Test trạng thái nền của fork `vendor/livetalking/ailive_ext/tests/test_background.py` (phần khung): `set_plate` PNG đúng cỡ →
  có `plate` và xoá `failed`; sai cỡ hoặc > 4 MB → từ chối kèm lý do; `None` → `plate=None` (phòng gốc); `apply` khi chưa có `plate` trả
  nguyên khung; không có `background/manifest.json` → `missing` / `not_prepared` (data-model §6)
- [x] T012 Tạo `vendor/livetalking/ailive_ext/background.py` phần khung: đối tượng trạng thái (`status`, `reason`, `plate`, `failed`, thống
  kê), `set_plate()` kiểm cỡ và 4 MB, thay `plate` nguyên tử, `hello_block()`, `pop_background_ms()`, `apply()` trả nguyên khung khi
  không có `plate`
- [x] T013 [P] Test `vendor/livetalking/ailive_ext/tests/test_ingest.py`: `hello` có khối `background` đủ trường (fork-protocol §2); tin
  `scene_background` hợp lệ / `png_b64: null` / base64 hỏng / sai cỡ → trả `background_rejected` đúng chỗ; `stats` có `background_ms`
  (`0.0` khi không khung nào được ghép)
- [x] T014 Sửa `vendor/livetalking/ailive_ext/ingest.py`: thêm `hello.background`, xử lý tin `scene_background`, gửi `background_rejected` /
  `background_failed`, thêm `background_ms` vào `stats` (để T013 đạt)
- [x] T015 [P] Test `tests/unit/test_livetalking_renderer.py`: đọc `hello.background` thành `ForkBackgroundStatus` và gọi listener;
  `set_scene_background(png)` gửi `{"type":"scene_background","png_b64":...}`, giữ ảnh nền cuối và gửi lại sau mỗi `hello` mới (`boot_id`
  mới); `None` gửi `png_b64: null`; `background_rejected` / `background_failed` → listener và log `scene_background_rejected` /
  `scene_background_failed`; log `scene_background_sent` có `plate_bytes`; fork cũ không có `background` → trạng thái None; `SwitchingRenderer`
  chuyển tiếp cả hai hàm
- [x] T016 Cài `BackgroundSink` trong `src/ai_live/avatar/livetalking_renderer.py` và chuyển tiếp trong
  `src/ai_live/avatar/switching_renderer.py` (để T009, T015 đạt)

**Checkpoint:** loader, Protocol, giao thức fork và renderer chạy test không GPU; bộ cảnh cũ (không có khối `background`) không đổi.

## Phase 3: User Story 1 - Kệ hàng sau host, không lọt phòng cũ (P1) 🎯 MVP

**Mục tiêu:** bộ cảnh chọn `ke_hang`, nhân vật đã chuẩn bị nền: khung live hiện kệ bày sản phẩm của shop sau host, người, mặt bàn, sản
phẩm 013 và nhãn AI giữ nguyên.

**Kiểm thử độc lập:** quickstart US1 bước 1–3 không GPU (chuẩn bị, `review.jpg`, ảnh xem trước); bước 4–6 trong Đợt GPU (T047–T049).

### Kiểm thử cho User Story 1 (viết trước, phải FAIL trước khi implement)

- [x] T017 [P] [US1] Test công cụ chuẩn bị `vendor/livetalking/ailive_ext/tests/test_background_prep.py` trên khung của T003: cách `plate`
  cho mặt nạ gần mặt nạ đúng (ngưỡng ghi trong test), không cờ lọt trên chuỗi sạch và có cờ khi cố ý chèn mảng phòng cạnh vai (R12); trung
  vị 3 khung nối vòng đầu-cuối (R4); dưới mép bàn luôn 255 với dốc 6 px (R6); giữ mảng lớn nhất, lấp lỗ; dấu vân `crc32` 8 hex, khung giống
  nhau ở hai thư mục avatar dùng chung một mặt nạ, `sources` ghi cả hai (R7); manifest đủ trường data-model §2 (`reviewed=false`,
  `light`, `leak`); có `review.jpg` và `preview_frame.png`; lỗi giữa chừng giữ nguyên thư mục cũ (ghi tạm rồi đổi tên); stdout đúng một
  dòng JSON (prepare-cli §2); `--method mediapipe` không có `--model` → lỗi; test chạy model thật `skip` khi không có file `.tflite`
- [x] T018 [P] [US1] Test ghép nền trong fork `vendor/livetalking/ailive_ext/tests/test_background.py` (phần nạp và ghép): `load()` hợp lệ →
  `valid`; các `mismatch` `frame_not_prepared:<n>`, `size_mismatch`, `character_mismatch`, `mask_unreadable:<file>`; `apply` thay đúng vùng
  nền bằng `plate`, vùng người (alpha 255) giữ nguyên từng bit, dải viền trộn số nguyên đúng (sai số ≤ 1), dưới mép bàn giữ khung gốc; cả
  khung đứng yên lẫn khung đang nói; ghép ném lỗi → `failed`, trả khung gốc, log một lần, báo `background_failed`; ảnh nền mới xoá `failed`;
  `pop_background_ms()` trả thời gian trung bình
- [x] T019 [P] [US1] Test `tests/unit/test_scene_backdrop.py`: `render_backdrop` trả PNG RGB đúng cỡ khung, không alpha; chỉ dán ảnh `art`
  của các món trong bộ cảnh (mỗi món một màu riêng, món không có trong bộ cảnh không xuất hiện); không vẽ chữ (gọi `ImageDraw.text` thì
  test hỏng); lặp vòng các món tới `max_items`, shop một món thì lặp món đó; không có ảnh → `png=None`, `reason="no_product_art"`;
  `softness_px` 0 và 3 cho độ nét khác nhau; độ sáng trung bình gần `room_luma × brightness`, chênh R−B dời về `room_rb` trong ±12 (R11);
  hai bộ cảnh hai khách → `items` khác nhau, không mang món của bộ trước
- [x] T020 [P] [US1] Test `tests/unit/test_background_controller.py` (đường chính): `ke_hang` + manifest hợp lệ + `hello.background`
  `valid` → vẽ trong `asyncio.to_thread` rồi `set_scene_background(png)`, `active=true`, `items` đúng; `goc` → không gửi ảnh nền,
  `fallback_reason="style_goc"`; log `scene_background_started` đủ trường contracts/events.md lúc khởi động và mỗi `hello` mới (FR-015); áp
  bộ sản phẩm mới (012) → vẽ lại và gửi ảnh mới; đổi sang bộ cảnh của khách khác → nền theo cấu hình mới, không còn món cũ (US1 kịch bản 3);
  `EventBus` phát `Event(EventType.SCENE, {"kind": "background", ...})` khi trạng thái đổi
- [x] T021 [P] [US1] Test `tests/unit/test_avatar_cli.py`: `background-prepare <id>` tìm `data/avatars/<id>__*` có `full_imgs`, gọi
  python của venv fork với đúng tham số (giả lập tiến trình con), in tiếng Việt số khung, cách tách, số khung có cờ lọt, đường dẫn
  `review.jpg`; mã thoát 0 / 1 / 2; `--mark-reviewed --by` đặt `reviewed`, `reviewed_by`, `reviewed_at`; `--method mediapipe` khi
  `BACKGROUND_SEGMENTER_MODEL` rỗng → báo tiếng Việt cách làm, mã 1; nhân vật không có thư mục avatar → mã 1
- [x] T022 [P] [US1] Test tích hợp `tests/integration/test_scene_fork.py` với fork giả (T005): bộ cảnh `ke_hang` → fork giả nhận đúng một
  `scene_background` đúng cỡ khung sau `hello`; fork khởi động lại (`boot_id` mới) → nhận lại; áp bộ sản phẩm mới → nhận ảnh mới; các lớp
  cảnh 009/013 và nhãn AI vẫn gửi như cũ (FR-005)

### Implement cho User Story 1

- [x] T023 [US1] Viết phần tách người trong `vendor/livetalking/ailive_ext/background_prep.py`: đọc khung bằng cùng hàm nạp của fork, cách
  `plate` (ảnh phòng trung vị, hiệu khung, GrabCut khởi tạo bằng mặt nạ gợi ý, R3), cách `mediapipe` (`ImageSegmenter`, gộp mọi lớp không
  phải nền, chỉ khi có `--model`), trung vị 3 khung (R4), guided filter bằng `cv2.boxFilter` và co 1 px (R5), mảng lớn nhất + lấp lỗ, dốc
  mép bàn từ `character.json` `scene.desk_top` (R6)
- [x] T024 [US1] Viết phần ghi kết quả trong `vendor/livetalking/ailive_ext/background_prep.py`: dấu vân từng khung (R7), đo ánh sáng
  người/phòng (R11), đo lọt R12 (ngưỡng 150 px, tỉ lệ 4), `manifest.json`, `masks/`, `preview_frame.png`, `review.jpg` (khung gốc | mặt nạ |
  ghép thử trên nền xám, mọi khung), ghi qua thư mục tạm rồi đổi tên, CLI `python -m ailive_ext.background_prep` in một dòng JSON (để T017 đạt)
- [x] T025 [US1] Viết `load(avatar, character_dir)` và `apply()` trong `vendor/livetalking/ailive_ext/background.py`: tính dấu vân
  `frame_list_cycle` và khung clip, tra mặt nạ, tách sẵn `bg_mask` / `edge_idx` / `edge_alpha`, đặt `valid | missing | mismatch` kèm lý do;
  `apply` bằng `cv2.copyTo` + trộn dải viền `uint16`, bắt lỗi thì đặt `failed` (R8, data-model §6) (để T018 đạt)
- [x] T026 [US1] Gắn vào `vendor/livetalking/avatars/base_avatar.py` (`# ailive: 014`): gọi `ailive_ext.background.load` lúc nạp avatar;
  gọi `apply` sau `ailive_fade` và trước `ailive_scene.apply` cho cả khung đứng yên và khung đang nói (sau khi dán miệng), khung đang
  crossfade dùng mặt nạ của khung đích (fork-protocol §4)
- [x] T027 [P] [US1] Viết `src/ai_live/scene/backdrop.py` `render_backdrop(config, art, size, desk_top_px, light) -> BackdropResult`: tường
  sáng ấm, hai khoang tủ, 4 tầng kệ trên mép bàn, LED ấm, bóng tầng kệ, ảnh `art` đang dùng của các món lặp vòng, phủ 20% màu tường, nhỏ
  hơn món trên bàn; không chữ, giá, logo; làm mềm `softness_px`, khớp ánh sáng R11 (R10) (để T019 đạt)
- [x] T028 [US1] Viết `src/ai_live/scene/background.py` `BackgroundController`: đọc manifest, nghe trạng thái fork qua `BackgroundSink`, vẽ
  ảnh nền trong `asyncio.to_thread`, gửi `set_scene_background`, giữ trạng thái data-model §5 (`status()`), log `scene_background_started`,
  phát sự kiện `EventBus`; `StaticRenderer` không có `BackgroundSink` thì không gửi gì (để T020 đạt)
- [x] T029 [US1] Nối trong `src/ai_live/app/context.py`: tạo `BackgroundController` khi cảnh live bật; vẽ lại khi áp bộ sản phẩm 012 (chỗ áp
  bộ trong `src/ai_live/app/image_routes.py` / `SceneController`) (để T022 đạt)
- [x] T030 [P] [US1] Thêm lệnh `background-prepare` vào `src/ai_live/avatar/__main__.py` theo contracts/prepare-cli.md §1: gọi fork CLI
  bằng python của venv fork (tiến trình riêng, ưu tiên thấp), `--method`, `--json`, `--mark-reviewed --by` (để T021 đạt)
- [x] T031 [US1] Thêm khối `"background": {"style": "ke_hang", "softness_px": 3.0, "brightness": 0.95}` vào `assets/scenes/demo/scene.json`
  trên máy demo (gitignored, chỉ đổi cấu hình)
- [x] T032 [US1] Chạy `uv run python -m ai_live.avatar background-prepare demo_host_02` trên CPU laptop; ghi thời gian chạy vào
  `contracts/prepare-cli.md` (thay `TODO:` đo thật) và số khung có cờ lọt, `max_blob_px` vào research R12
- [x] T033 [US1] **Người dùng làm tay:** xem `assets/avatars/demo_host_02/background/review.jpg` (mảng phòng cũ quanh vai, tóc, dải LED;
  chỗ bị khoét người; có cả khung host giơ tay / nghiêng người ra ngoài, trường hợp biên của spec). Đạt thì `--mark-reviewed --by "<tên>"`. Không đạt thì người dùng quyết duyệt ADR-083 để dùng `--method mediapipe`
  (xác minh giấy phép, tải model, ghi sha256 theo research R3)
  - Đã làm 2026-11-24: người dùng nhờ Claude duyệt thay; đạt có điều kiện, `reviewed_by` = "Claude (người dùng nhờ duyệt T033)". Kết quả ở research R12.
  - Duyệt lại cùng ngày sau khi sửa mép tóc (research R5): 20 cờ, đều là báo nhầm trên tóc, không có lọt mới. `reviewed_by` = "Claude (người dùng nhờ duyệt T033, sửa mép tóc)".
  - Duyệt lại cùng ngày sau khi bỏ mẩu chai cam cạnh tay áo (research R3, `drop_still_room`): vẫn 20 cờ báo nhầm trên tóc, ô chai cam sạch (≤ 1 px ở 2/162 khung). `reviewed_by` = "Claude (người dùng nhờ duyệt T033, bỏ đốm cam)".

**Checkpoint:** test app và fork của US1 đạt không GPU; `review.jpg` đã duyệt; US1 có thể demo sau khi T047–T049 đạt.

## Phase 4: User Story 2 - Rơi về an toàn, xem trước và cảnh báo (P2)

**Mục tiêu:** thiếu, hỏng, không khớp phần chuẩn bị hoặc dữ liệu thì live hiện phòng gốc, không vỡ hình; trang điều khiển và kiểm tra sẵn
sàng nói rõ lý do và cách sửa; có ảnh xem trước không cần fork.

**Kiểm thử độc lập:** quickstart US2 bước 1–3 (đổi tên thư mục `background`, bản sao avatar sửa 1 byte, bộ cảnh không ảnh sản phẩm) và
`/api/scene/background/preview.png`.

### Kiểm thử cho User Story 2 (viết trước, phải FAIL trước khi implement)

- [x] T034 [P] [US2] Thêm test rơi về vào `tests/unit/test_background_controller.py`, đúng thứ tự data-model §5: `style_goc`,
  `scene_disabled`, `style_not_available` (`bang_shop`, `anh_shop` trước US3), `no_product_art`, `plate_failed` (vẽ ném lỗi),
  `avatar_static`, `fork_unsupported`, `not_prepared`, `mismatch:<chi tiết>`, `rejected:<chi tiết>`, `failed:<chi tiết>`; mỗi trường hợp
  `active=false`, **không gọi `set_scene_background(png)`** khi `hello.background` là `missing`/`mismatch` (fork-protocol §3: app không gửi ảnh nền
  để fork phải từ chối), có `fallback_message` tiếng Việt kèm lệnh khắc phục, có sự kiện `EventBus`; `reviewed=false` không làm `active=false`
- [x] T035 [P] [US2] Test `tests/integration/test_background_routes.py`: `GET /api/scene/background` đủ trường contracts/api.md; `GET
  /api/scene` có khối `background`; `GET /api/scene/background/preview.png` trả PNG đúng cỡ khung, `Cache-Control: no-store`, vùng nền lấy
  từ ảnh nền, có nhãn AI; chưa chuẩn bị nền → 404 kèm lý do tiếng Việt; `SCENE_ENABLED=false` → `scene_disabled`, không 500; không có route
  POST đổi hay bật/tắt nền
- [x] T036 [P] [US2] Test `check_background` trong `tests/unit/test_readiness.py` theo bảng contracts/api.md: `ok` khi `goc` hoặc cảnh tắt;
  `warn` khi `missing` (kèm lệnh), `mismatch` (lý do + lệnh), `no_product_art`, `valid` chưa duyệt (kèm đường dẫn `review.jpg`); `ok` khi
  hợp lệ và đã duyệt; không bao giờ `fail`; đọc manifest từ đĩa khi fork không chạy
- [x] T037 [P] [US2] Test `tests/integration/test_control_page.py`: trang có dòng "Nền sau host" (kiểu nền, trạng thái hợp lệ / chưa chuẩn bị
  / không khớp / chưa duyệt, lý do rơi về, ảnh xem trước nhỏ bấm xem cỡ thật); JS đọc `/api/scene/background` và cập nhật khi có sự kiện
  `SCENE` `kind: "background"`
- [x] T038 [P] [US2] Test `tests/integration/test_watchdog_show.py`: fork giả trả `background_failed` → banner cảnh báo trên trang điều khiển
  như các lỗi cảnh khác, show không dừng, khung vẫn phát (contracts/events.md)

### Implement cho User Story 2

- [x] T039 [US2] Bổ sung `src/ai_live/scene/background.py`: chuỗi kiểm lý do rơi về theo thứ tự data-model §5, câu tiếng Việt
  `fallback_message`, gửi `set_scene_background(None)` khi đang có ảnh nền mà phải rơi về, `preview_png()` = `preview_frame.png` + ảnh nền theo
  mặt nạ + lớp `base` 009/013 + nhãn AI (R13) (để T034 đạt)
- [x] T040 [US2] Thêm `GET /api/scene/background`, `GET /api/scene/background/preview.png` và khối `background` trong `GET /api/scene` vào
  `src/ai_live/app/routes.py` (để T035 đạt)
- [x] T041 [US2] Thêm dòng "Nền sau host" vào khối cảnh live trong `src/ai_live/app/static/control.html`, `control.js`, `style.css` (để T037
  đạt)
- [x] T042 [US2] Thêm `check_background` vào `src/ai_live/ops/readiness.py` và đưa vào danh sách kiểm của `/api/readiness` và
  `python -m ai_live.ops`, dùng lại lý do rơi về và câu `fallback_message` của T039 (không viết câu riêng) (sau T039; để T036 đạt)
- [x] T043 [P] [US2] Cho `scene_background_failed` / `scene_background_rejected` hiện thành banner trong `src/ai_live/ops/watchdog.py` theo cơ
  chế lỗi cảnh đã có, không thêm luật mới (để T038 đạt). *Lệch khi làm (2026-11-24):* `watchdog.py` không đổi; `BackgroundController`
  phát sự kiện `scene` `kind:"error"` "Nền sau host: …" (cơ chế lỗi cảnh 009 sẵn có), trang điều khiển hiện chữ đỏ ở dòng cảnh, không
  có cảnh báo watchdog vì show vẫn chạy (FR-010)

**Checkpoint:** mọi lý do rơi về có test; trang điều khiển, xem trước và readiness chạy không GPU; kiểm live ở T050–T051.

## Phase 5: User Story 4 - Công cụ đo độ thật đo phần nền (P3)

**Mục tiêu:** `realism_report.py` đo thêm chỗ lọt phòng cũ, độ mềm nền so với người, độ sáng và màu ánh sáng, kèm tờ so sánh các kiểu nền;
chỉ dựng ảnh thử, không sửa cấu hình hay code.

**Kiểm thử độc lập:** quickstart US4: chạy trên khung có lọt cố ý, khung sạch và khung phòng gốc.

### Kiểm thử cho User Story 4 (viết trước, phải FAIL trước khi implement)

- [x] T044 [P] [US4] Test `tests/unit/test_realism_background.py` (nạp script bằng `importlib`, khung tổng hợp): chèn mảng phòng cũ cạnh vai →
  cờ lọt (mảng > 150 px) kèm ảnh đánh dấu đỏ; khung sạch → không cờ; nền sắc hơn người → cờ "nền sắc hơn người"; lệch độ sáng / chênh R−B
  vượt ngưỡng → cờ; khung phòng gốc (không có nền mới) → không báo lọt nhầm; có tờ so sánh các kiểu nền đặt cạnh nhau; script không ghi gì
  ngoài `--out`

### Implement cho User Story 4

- [x] T045 [US4] Thêm cờ `--background-frames` vào `.claude/skills/live-scene-realism/scripts/realism_report.py`: chỉ số lọt R12 (biểu đồ
  màu phòng cũ / người từ khung gốc `full_imgs` của fork và mặt nạ khớp crc32 trong `assets/avatars/<id>/background/`; khung chụp từ `/host`
  chỉ dùng cho độ nét, độ sáng, màu ánh sáng vì không có mặt nạ riêng, mảng 8 hướng, ngưỡng 150 px, tỉ lệ 4), tỉ lệ độ nét
  nền/người, lệch độ sáng và R−B (±12), tờ so sánh kiểu nền (dùng `contact_sheet.py`) (để T044 đạt)
- [x] T046 [P] [US4] Cập nhật `.claude/skills/live-scene-realism/REFERENCE.md` (chỉ số nền, ngưỡng, cách đọc cờ) và quy trình trong
  `.claude/skills/live-scene-realism/SKILL.md` (đo nền khi chỉnh cảnh cho khách mới)

**Checkpoint:** công cụ đo cho số liệu nền dùng được cho T048.

## Đợt GPU

Chạy chung một buổi trên GPU laptop (ADR-023): `powershell scripts/livetalking/run.ps1`, `AVATAR_MODE=livetalking`, rồi chạy app.
RunPod chỉ khi laptop không chạy được và chủ dự án đồng ý chi phí (`docs/RUNPOD.md`).

- [ ] T047 [GPU] [US1] Live trên `/host` với `ke_hang` (quickstart US1 bước 4): kệ bày ảnh sản phẩm của shop, không chữ, không logo lạ;
  mặt bàn, sản phẩm, thẻ 013 giữ nguyên; nhãn "AI-GENERATED CONTENT" trên cùng; miệng vẫn mấp máy theo lời; log `scene_background_started`
  có `active=true`, `hello.background` `valid`
- [ ] T048 [GPU] [US1] Chụp 20 khung rải đều đoạn lặp (có khung nghiêng đầu), chạy `realism_report.py --background-frames`, đếm khung lọt
  (SC-001) và khung bị khoét người (SC-002), kể cả khung host giơ tay (trường hợp biên của spec); người dùng xem bằng mắt; ghi kết quả vào quickstart và research R12 (chỉnh ngưỡng nếu mắt
  không đồng ý)
- [ ] T049 [GPU] [US1] `OUTPUT_MODE=obs`, mở `/obs`: cùng nền như `/host` (FR-014)
- [ ] T050 [GPU] [US2] Rơi về khi live (quickstart US2 bước 1–2): đổi tên tạm thư mục `background` → phòng gốc, trang điều khiển và
  `/api/readiness` báo `warn`; bản sao avatar sửa 1 byte → `mismatch` `frame_not_prepared:<n>`, phòng gốc (SC-006)
- [ ] T051 [GPU] [US2] Show 5 phút `style: "goc"`, khởi động lại, 5 phút `style: "ke_hang"`: so fps trong `stats` và `background_ms` (≤ 4 ms,
  fps giảm ≤ 10%, SC-003); so `llm_first_sentence` và khoảng lặng p95 với trước 014 (SC-004); ghi số vào plan (bảng độ trễ) và RISKS Q43

## Phase 6: Hoàn thiện

- [ ] T052 [P] Cập nhật `docs/ARCHITECTURE.md` §3 và sơ đồ cảnh: Protocol `BackgroundSink`, tin `scene_background` / `hello.background`,
  thứ tự ghép trong fork (fork-protocol §6)
- [ ] T053 [P] Cập nhật `docs/RISKS.md` (Q43, Q44, Q46, L16) theo số đo T048–T051 và quyết định ADR-083
- [ ] T054 Chạy lại toàn bộ phần không GPU của `quickstart.md` (§0, US1 bước 1–3, US2 bước 1–3, US4), sửa chỗ lệch với code
- [ ] T055 Chạy `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, và
  `vendor/livetalking/.venv/Scripts/python.exe -m pytest vendor/livetalking/ailive_ext/tests`; tất cả xanh. Commit trong repo fork và repo
  chính chỉ khi người dùng yêu cầu
- [ ] T056 **Người dùng làm tay:** xem trên cỡ điện thoại khung phòng gốc và khung kệ hàng (từ T048), kết luận kệ hàng hợp chủ đề hơn hay
  không (SC-005); ghi vào quickstart
- [ ] T057 **Người dùng làm tay:** bấm giờ đổi sang khách thứ hai: chép `assets/scenes/demo` thành bộ cảnh mới, đổi `customer_id`, sản phẩm,
  khối `background`, khởi động lại, xem `/api/scene/background/preview.png`; dưới 10 phút, không sửa code (SC-007, FR-013)
- [ ] T058 Chạy `/update-context`: `CLAUDE.md`, `docs/DECISIONS.md` (trạng thái ADR-083/084), `docs/ROADMAP.md`, `progress/`

## Phase 7: User Story 3 - Bảng shop và ảnh shop (P4, sau demo)

Không chặn mốc M1d (làm rõ 2026-11-23). Chỉ làm khi người dùng yêu cầu sau buổi demo.

**Mục tiêu:** kiểu `bang_shop` (bảng màu chủ đạo, tên shop từ file dữ liệu) và `anh_shop` (ảnh shop thật đã xác nhận quyền dùng).

**Kiểm thử độc lập:** quickstart US3; xem `/api/scene/background/preview.png` cho từng kiểu.

### Kiểm thử cho User Story 3 (viết trước, phải FAIL trước khi implement)

- [ ] T059 [P] [US3] Test bộ đọc file dữ liệu trong `tests/unit/test_docx_loader.py`: dòng "Tên shop: …" trước sản phẩm đầu tiên →
  `ProductCatalog.shop_name`; không có → None; dòng sau sản phẩm đầu tiên không tính; prompt LLM và guard không đổi
- [ ] T060 [P] [US3] Thêm test vào `tests/unit/test_scene_backdrop.py`: `bang_shop` dùng `accent_color`, tên shop đúng dữ liệu nằm trên đỉnh
  đầu cao nhất của mọi mặt nạ (không bị đầu che), không tên → bảng không chữ và cảnh báo `background_no_shop_name`, không logo; `anh_shop` không có ảnh → phòng gốc, lý do `no_shop_photo`
  (FR-011); `anh_shop`
  phủ kín bằng cắt giữa giữ tỷ lệ (không kéo méo), áp độ mềm và ánh sáng
- [ ] T061 [P] [US3] Test ảnh shop trong `tests/integration/test_background_routes.py`: có ảnh + `shop_photo.json` hợp lệ → dùng được; thiếu
  xác nhận hoặc sha256 không khớp → không áp, lý do `shop_photo_unconfirmed` hiện trên trang; `bang_shop` / `anh_shop` không còn
  `style_not_available`

### Implement cho User Story 3

- [ ] T062 [US3] Thêm `shop_name: str | None` vào `ProductCatalog` trong `src/ai_live/products/models.py` và đọc dòng "Tên shop:" trong bộ đọc
  file dữ liệu ở `src/ai_live/products/` (để T059 đạt)
- [ ] T063 [US3] Vẽ `bang_shop` trong `src/ai_live/scene/backdrop.py` (bảng màu, tên shop, hai bên kệ hàng); trang điều khiển chỉ hiển thị
  tên shop, không sửa (FR-008)
- [ ] T064 [US3] Bổ sung route tải và xác nhận quyền dùng ảnh shop vào `contracts/api.md` trước (hợp đồng chưa có), rồi làm trong
  `src/ai_live/app/image_routes.py` và `src/ai_live/scene/uploads.py`: lưu `assets/scenes/<scene_id>/background/shop_photo.<ext>` +
  `shop_photo.json` (sha256, `confirmed_by`, `confirmed_at`), xác nhận như ảnh sản phẩm 012 (ADR-071/072)
- [ ] T065 [US3] Vẽ `anh_shop` trong `src/ai_live/scene/backdrop.py` (cắt giữa giữ tỷ lệ, mềm, khớp ánh sáng) và bỏ `style_not_available`
  cho hai kiểu này trong `src/ai_live/scene/background.py` (để T060, T061 đạt). Phần `anh_shop` xong ở T084 (Phase 10); còn `bang_shop`
- [ ] T066 [US3] **Người dùng làm tay:** xem ảnh xem trước của `bang_shop` (tên đọc được, không bị đầu che) và `anh_shop` (phủ kín, không méo);
  xác nhận quyền dùng ảnh shop thật của khách trước khi live

**Checkpoint:** cả ba kiểu nền mới chạy được theo cấu hình bộ cảnh; chạy lại T055 và `/update-context`.

## Phase 8: Bổ sung 2026-11-25 - Kệ hàng đầy có chiều sâu, nhãn AI tránh vùng che của app Shopee

**Mục tiêu**: cảnh gần mức live AI thật trên Shopee mà người dùng đưa làm chuẩn (FR-018, FR-019, SC-008, ADR-085).

### Kiểm thử (viết trước, phải FAIL trước khi implement)

- [x] T067 [P] Test ở fork `vendor/livetalking/ailive_ext/tests/test_label.py`: vị trí `shopee-top` là mặc định; nhãn ở giữa, mép trên
  12,5% chiều cao, rộng ≤ 30% bề ngang, "AI-GENERATED CONTENT" thành hai dòng; các vị trí cũ giữ nguyên
- [x] T068 [P] Test ở app `tests/unit/test_scene_layout.py` (hoặc file test layout hiện có): `estimate_label_box` với `shopee-top` khớp hộp của
  fork (±4 px); `AI_LABEL_POSITIONS` có `shopee-top` và là mặc định
- [x] T069 [P] Test `tests/unit/test_shopee_overlay.py`: bảng vùng che quy về khung 480×832 theo giả định phủ kín; hộp nhãn mặc định không
  giao vùng nào và nằm trên đỉnh đầu (SC-008)
- [x] T070 [P] Test `tests/unit/test_realism_overlay.py`: `realism_report.py` báo phần trăm nhãn AI và sản phẩm nằm trong vùng che, có cờ
  khi vượt ngưỡng, và tô vùng lên `_zones.png`
- [x] T071 [P] Test thêm vào `tests/unit/test_scene_backdrop.py`: kệ hàng kín bề ngang, có kệ hai bên và kệ cuối tối hơn, độ tương phản
  không bạc sau khi khớp ánh sáng, vẫn chỉ ảnh của shop, không chữ, cùng kết quả mỗi lần (FR-018)

### Implement

- [x] T072 Nhãn `shopee-top` ở fork `ailive_ext/label.py` (+ `analyze.py` truyền vị trí), đổi mặc định (ADR-085)
- [x] T073 App: `core/config.py`, `scene/layout.py`, CSS `.label-shopee-top`, `.env.example`; sửa mọi chỗ còn ghi `top-center` là mặc định
- [x] T074 Module `src/ai_live/scene/shopee_overlay.py` và phần vùng che trong `realism_report.py`; cập nhật `REFERENCE.md`, `SKILL.md`
- [x] T075 Viết lại kệ hàng trong `src/ai_live/scene/backdrop.py` (kệ dày, chiều sâu, khớp ánh sáng không bạc màu), chỉnh mặc định độ mềm (ADR-086: 1,5)
- [x] T076 Dựng ảnh trước/sau ở cỡ điện thoại (có vẽ vùng che) cho người dùng xem
- [ ] T077 **Người dùng làm tay:** xem ảnh trước/sau, so với ảnh live chuẩn; kiểm vùng che bằng live thử hay điện thoại thật (TODO của
  FR-019)

**Checkpoint**: test và ruff xanh, ảnh trước/sau đã gửi người dùng.

## Phase 9: Bổ sung 2026-11-25 - Sản phẩm né vùng bình luận, công cụ đo mép bàn đúng

**Mục tiêu**: không sản phẩm nào trên bàn nằm dưới bình luận và ô chat của app (FR-019, SC-008, ADR-087); công cụ đo tìm đúng mép bàn.

### Kiểm thử (viết trước, phải FAIL trước khi implement)

- [x] T078 [P] Test `tests/unit/test_realism_desk_edge.py`: `_desk_edge` bỏ qua bậc màu áo/tay ở giữa khung, tìm mép bàn kéo hết bề ngang
- [x] T079 [P] Test thêm vào `tests/unit/test_showcase_layout.py`: bật `avoid_app_overlay` thì không hộp ảnh sản phẩm nào giao vùng
  `comments`, `chat_bar`; món chính vẫn đứng trước (chân thấp nhất); mọi chân dưới mép bàn; tắt thì như cũ; loader đọc khóa

### Implement

- [x] T080 `realism_report.py`: đo mép bàn chỉ ở hai dải mép khung (12% bề ngang mỗi bên)
- [x] T081 `LayoutParams.avoid_app_overlay`, loader, co chiều sâu cụm `showcase` trong `scene/layout.py`; sửa docstring
  `shopee_overlay.py`; bật khóa trong bộ cảnh demo; đo lại bằng `realism_report.py` (ADR-087)

**Checkpoint**: test và ruff xanh; báo cáo độ thật không còn sản phẩm trong vùng che.

## Phase 10: Bổ sung 2026-11-28 - Ảnh shop sau host, cho phép ảnh do AI tạo (ADR-100)

**Mục tiêu:** làm phần `anh_shop` của US3 trước buổi demo: ảnh shop (chụp thật hoặc AI tạo cảnh shop chung) phủ sau host, mềm, khớp
sáng; sản phẩm trên bàn vẫn là ảnh thật của khách. Xác nhận quyền dùng bằng lệnh CLI, route trên trang điều khiển (T064) để sau.

- [x] T082 Spec: US3 kịch bản 5, FR-009a, phiên làm rõ 2026-11-28; data-model §1/§3/§5, research R15, `contracts/adapters.md` §2,
  quickstart; ADR-100
- [x] T083 [P] Test `tests/unit/test_shop_photo.py`: đọc/lưu và xác nhận (thiếu trường, sha256 lệch, thay định dạng), phủ kín không méo,
  ảnh AI luôn mềm tối thiểu, thiếu ảnh hay chưa xác nhận thì không vẽ, loader chỉ đọc ảnh với `anh_shop`, bộ điều khiển rơi về và bật
  đúng, câu báo lỗi, lệnh CLI; sửa `test_scene_backdrop.py`, `test_background_controller.py`, `test_readiness.py` theo lý do mới
- [x] T084 Module `src/ai_live/scene/shop_photo.py`; nhánh `anh_shop` trong `scene/backdrop.py`; `SceneSet.shop_photo` và loader;
  `BackgroundController` truyền ảnh, câu báo `no_shop_photo` / `shop_photo_unconfirmed`; lệnh `shop-photo` trong `scene/__main__.py`
- [x] T085 Cài ảnh shop Gemini (xác nhận `ai_generated`) vào bộ cảnh demo, đổi `style` sang `anh_shop`; xem live trên `/obs` qua
  Chrome DevTools: ảnh phủ kín sau host, không lộ phòng gốc, nhãn AI rõ, sản phẩm thật trên bàn
- [ ] T086 **Người dùng làm tay:** xem khung live `anh_shop` trong OBS thật; kiểm ảnh AI không còn chữ/logo đọc được ở cỡ điện thoại;
  quyết giữ `anh_shop` hay quay lại `ke_hang` cho buổi demo

**Checkpoint**: test và ruff xanh; `GET /api/scene/background` báo `style: anh_shop, active: true`.

## Phụ thuộc và thứ tự

- Setup (T001–T005) → Foundational (T006–T016) → US1 (T017–T033) → US2 (T034–T043) → US4 (T044–T046) → Đợt GPU (T047–T051) → Hoàn
  thiện (T052–T058). US3 (T059–T066) sau buổi demo.
- Trong Foundational: T007 → T008; T010 trước T016; T012 → T014 (ingest gọi đối tượng nền).
- Trong US1: T023 → T024 (cùng file); T012 → T025 → T026; T027 → T028 → T029; T030 dùng lệnh fork của T024 (test giả lập tiến trình con
  nên viết song song được); T024 + T030 → T032 → T033.
- US2 dựa vào `BackgroundController` của T028. US4 cần mặt nạ thật của T032 cho số đo, test chỉ cần khung tổng hợp.
- Đợt GPU cần T033 (đã duyệt `review.jpg`), T041, T045. T048 → T056; T051 → T053.

## Chạy song song

- Setup: T002–T005 cùng lúc.
- Foundational: các test T006, T009, T011, T013, T015 cùng lúc; sau đó nhánh app (T007–T008, T010, T016) và nhánh fork (T012, T014) song
  song.
- US1: các test T017–T022 cùng lúc; nhánh fork (T023–T026) song song nhánh app (T027–T030).
- US2: các test T034–T038 cùng lúc; T043 song song với T039–T041; T042 sau T039 (dùng lại câu rơi về).
- Hoàn thiện: T052, T053 cùng lúc.

## Đợt GPU (tóm tắt)

- T047–T051 chạy một buổi trên GPU laptop. Phần chuẩn bị nền (T032) chạy CPU, không cần GPU; nếu phải dùng RunPod thì chép thư mục
  `background/` lên pod và tắt pod ngay khi xong.

## Chiến lược MVP

1. Setup + Foundational (T001–T016) → 2. US1 (T017–T033) → **dừng, người dùng xem `review.jpg` và ảnh xem trước** → 3. US2 (rơi về an toàn,
   cần cho buổi demo) → 4. Đợt GPU T047–T051 → 5. US4, Hoàn thiện. US3 sau demo.

## Bảng phủ yêu cầu

| Yêu cầu | Task |
|---------|------|
| FR-001 | T006, T007, T008, T020, T031, T034 |
| FR-002 | T018, T026, T047 |
| FR-003 | T017, T023, T024, T030, T032 |
| FR-004 | T017, T018, T023, T025, T048 |
| FR-005 | T018, T022, T026, T047 |
| FR-006 | T019, T027, T044, T045 |
| FR-007 | T019, T027, T047 |
| FR-008 | T059, T060, T062, T063 |
| FR-009 | T060, T061, T064, T065, T066 |
| FR-010 | T011, T018, T025, T034, T039, T050 |
| FR-011 | T019, T034, T039 |
| FR-012 | T035, T037, T039, T040, T041 |
| FR-013 | T019, T020, T022, T057 |
| FR-014 | T049 |
| FR-015 | T015, T020, T028, T036, T042 |
| FR-016 | T044, T045, T046 |
| FR-018 | T071, T075, T076 |
| FR-019 | T067, T068, T069, T070, T072, T073, T074, T077 |
| SC-001 | T017, T033, T048 |
| SC-002 | T018, T033, T048 |
| SC-003 | T051 (T018 chỉ kiểm thời gian ghép mỗi khung, không đo fps) |
| SC-004 | T051 |
| SC-005 | T056 |
| SC-006 | T034, T036, T050 |
| SC-007 | T020, T057 |
| SC-008 | T069, T076, T077 |
