# Tasks: Sản phẩm đứng trên bàn như đồ thật

- **Feature ID:** `013-realistic-desk-products` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/scene-set.md](./contracts/scene-set.md), [contracts/api.md](./contracts/api.md),
  [quickstart.md](./quickstart.md) · ADR-074 (Chấp nhận 2026-11-22) · Phụ thuộc khai mới: `onnxruntime`, `numpy` (đã có trong `uv.lock`).

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[GPU]**: cần GPU; chạy trên GPU laptop (ADR-023), không dùng RunPod; gom vào đợt GPU (xem cuối file)
- **[US#]**: thuộc user story nào. Phase Setup, Foundational và Hoàn thiện không gắn nhãn này.
- Agent làm chủ (plan): ai-media cho `src/ai_live/scene/`, `src/ai_live/avatar/character.py` và việc đo `demo_host_02`; ai-orchestrator
  cho `src/ai_live/app/`, `core/config.py`, `.env.example`, `ops/readiness.py`, `pyproject.toml`; ai-qa cho `tests/` và các buổi đo.

## Phase 1: Setup

- [x] T001 Khai trực tiếp `onnxruntime>=1.31.1` và `numpy` trong `[project].dependencies` của `pyproject.toml` (ADR-074), chạy `uv lock` +
  `uv sync` và xác nhận `uv.lock` không thêm gói mới (chỉ đổi phần khai báo); thêm marker pytest `matting_model` ("chạy model tách nền thật,
  cần file model") vào `markers` và loại nó trong `addopts` như `live_llm`
- [ ] T002 [P] **Người dùng làm tay:** tải `isnet-general-use.onnx` từ release rembg vào `models/matting/` (quickstart §0), kiểm md5
  `fc16ebd8b0c10d971d3513d564d01e29`, ghi kích thước và sha256 vào `specs/013-realistic-desk-products/research.md` R6 và ADR-074 trong
  `docs/DECISIONS.md`; kiểm `.gitignore` đã chặn `models/` (không commit trọng số)
- [x] T003 [P] Thêm hàm sinh ảnh thử bằng Pillow vào `tests/fixtures/scene_builder.py` (không commit ảnh): sản phẩm trên nền trắng, trên nền
  một màu (xám, xanh), sản phẩm có ô trắng trong lòng (hộp trắng in chữ), hộp trắng trên nền trắng, sản phẩm có bóng đổ sẵn trên nền trắng,
  nền nhiễu nhiều màu, PNG đã trong suốt, ảnh rất rộng (5:1) và rất cao (1:4)
- [x] T004 [P] Thêm tham số `desk_in_image`, `desk_top`, `hands_zone` cho hàm dựng nhân vật thử trong `tests/fixtures/character_builder.py`
- [x] T005 [P] Viết "model" giả `tests/fixtures/fake_matting.py`: nhận đúng tham số CLI của contracts/api.md §6 (`--model --in --out
  --threads`), chế độ chọn qua biến môi trường: mặt nạ cố định (elip giữa ảnh), mặt nạ nửa vời (nhiều điểm alpha 26–229), ngủ lâu hơn hạn giờ,
  thoát mã 3 / 4 / 5 với một dòng stderr

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

### Test nền (viết trước, phải FAIL trước khi implement)

- [x] T006 [P] Test biến môi trường mới trong `tests/unit/test_config.py`: `MATTING_MODEL_PATH` mặc định rỗng, `MATTING_DURING_SHOW` mặc định
  `true`, đọc được `false` (contracts/api.md §7)
- [x] T007 [P] Test bộ nạp `layout` trong `tests/unit/test_scene_loader.py` theo bảng contracts/scene-set.md §1 và data-model §1: không có
  `mode` → `LayoutParams` y như 009 (FR-001); `mode` lạ → issue `error` `bad_layout` và cảnh vẫn ở `rows`; `cards` mặc định `none`
  (`realistic`) / `all` (`rows`); `rows` + `cards: none|one` → `all` + `warning` `cards_ignored`; `brightness` 0,5 / 1,5 → kẹp 0,85 / 1,10 +
  `layout_clamped`; `highlight_scale` mặc định 1,04 ở `realistic`, kẹp 1,00–1,10 (và 1,0–1,6 ở `rows`); `max_slots: 7` ở `realistic` → 5 +
  `layout_clamped` (FR-019)
- [x] T008 [P] Test `scene.hands_zone` trong `tests/unit/test_character.py` (contracts/scene-set.md §2): đọc đúng 4 số; thiếu → `None`; số
  ngoài 0–1, `x1 >= x2`, `y1 >= y2`, sai độ dài, không phải số → `PrepareError("bad_character", …)` như `desk_top` (FR-003)
- [x] T009 [P] Test sổ ảnh đọc trường mới trong `tests/unit/test_scene_uploads.py` (contracts/scene-set.md §3): phiên bản có `bg_removal`,
  `cutout_version`, `derived_from` đọc ra đúng; phiên bản 012 cũ thiếu ba trường → `None`; khóa lạ khác trong phiên bản bị bỏ qua, không làm
  hỏng sổ (TODO của contracts §3); `derived_from` trỏ tới phiên bản không có → `warning`, ảnh vẫn dùng được
- [x] T010 [P] Test `FrameGeometry.hands_zone` trong `tests/unit/test_scene_layout.py` (data-model §3): tỷ lệ → điểm ảnh theo (W, H);
  `same_frame()` khác khi `hands_zone` khác; `hands_zone` không nằm trong `keep_out_boxes()` và không bị `punch`

### Implement nền

- [x] T011 [P] Thêm `matting_model_path: Path | None` và `matting_during_show: bool = True` vào `src/ai_live/core/config.py`, ghi hai biến kèm
  chú thích vào `.env.example` (làm T006 xanh)
- [x] T012 Mở rộng `src/ai_live/scene/models.py` theo data-model §1, §3, §5, §10: `LayoutParams.mode/cards/brightness`,
  `FrameGeometry.hands_zone` + `same_frame`, `Slot.station`, `Slot.card_box: Box | None`, `Slot.shadow_box`, `SceneLayout.mode`,
  `SceneLayout.draw_order`; thêm `hands_zone_missing`, `art_has_background`, `matting_model_missing`, `card_no_room`, `cards_ignored`,
  `layout_clamped` vào `WARNING_CODES`; mã lỗi `bad_layout` (mức `error`). Cách bày `rows` vẫn điền `card_box` như 009 (làm T010 xanh)
- [x] T013 Đọc và kẹp `layout.mode/cards/brightness/highlight_scale/max_slots` trong `src/ai_live/scene/loader.py` (sau T012; làm T007 xanh);
  giữ luật 009 `scene check` thoát mã 1 khi có issue `error` (`bad_layout`) và ghi quyết định đó vào data-model §1 thay cho TODO
- [x] T014 [P] Đọc và kiểm `scene.hands_zone` trong `src/ai_live/avatar/character.py` (làm T008 xanh)
- [x] T015 [P] Đọc `bg_removal`, `cutout_version`, `derived_from` (mặc định `None`, bỏ qua khóa lạ) trong `ProductImageStore` của
  `src/ai_live/scene/uploads.py` và báo `derived_from` sai bằng `warning` khi nạp sổ (làm T009 xanh)

**Checkpoint:** `uv run pytest tests/unit/test_config.py tests/unit/test_scene_loader.py tests/unit/test_character.py
tests/unit/test_scene_uploads.py tests/unit/test_scene_layout.py` xanh; bộ cảnh 009/012 cũ vẫn nạp như trước.

## Phase 3: User Story 1: Sản phẩm đứng trên mặt bàn hai bên host, như đồ thật (P1) 🎯 MVP

**Mục tiêu:** `layout.mode = realistic` bày món hai bên tay trên mặt bàn, có chiều sâu, bóng mềm, không thẻ; `rows` giữ y như 009.
**Kiểm độc lập:** quickstart §1, §2.

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [x] T016 [P] [US1] Test bất biến bố cục trong `tests/unit/test_realistic_layout.py` (MỚI) cho 1–5 món × mọi trạng thái nổi × hai cỡ khung
  (khung lip-sync 832 cao và khung ảnh tĩnh), theo data-model §4–§5 và research R1: đáy mỗi món ∈ `[desk_y, H]` (FR-002, US1 #1); không tâm
  món nào nằm trong `[hands_x1, hands_x2]`; hộp món ∪ `shadow_box` không giao `face_zone`, `keep_out_boxes()`, `hands_zone` (FR-003, FR-005,
  FR-007, US1 #3); món chính ở chỗ `P` bên phải, cao nhất và đáy thấp nhất; với i < j chiều cao và `depth` giảm (FR-004, US1 #2); tỷ lệ ảnh giữ
  nguyên (sai ≤ 1 px); bảng `DeskStation` thỏa luật bất biến của data-model §4
- [x] T017 [US1] Test trường hợp biên trong `tests/unit/test_realistic_layout.py` (sau T016, cùng file): 1 món → chỗ `P` bên phải, bên trái
  trống; 6 món → món thứ 6 không có chỗ + cảnh báo `overflow`; ảnh 5:1 thu nhỏ vừa một bên, dưới `MIN_ART_HEIGHT` → `art_too_wide`; chai
  1:4 thu nhỏ để đỉnh dưới `face_zone`; hai món chồng: che ≤ nửa món sau thì giữ, quá nửa thì thu cả hai 10% mỗi bước rồi bỏ món sau với
  `no_room`; `draw_order` xa → gần và món nổi **không** dời xuống cuối; nhân vật không khai `hands_zone` → vùng mặc định
  `[0.30, desk_top − 0.10, 0.70, 1.0]`
- [x] T018 [P] [US1] Test vẽ trong `tests/unit/test_scene_render.py`: **trước khi sửa `render.py`**, ghi mã băm PNG của một bộ cảnh `rows`
  (1 chính + 3 phụ, có và không món nổi) vẽ bằng mã 009 hiện tại làm chuẩn, rồi test cảnh thiếu `mode` vẽ ra đúng mã băm đó (US1 #6, FR-001);
  `realistic`: có điểm bóng mờ ngay dưới đáy mỗi món và rộng theo cỡ món (FR-005); `brightness` 0,9 / 1,1 nhân đều R, G, B, alpha không đổi,
  sắc độ đổi ≤ 1° ở điểm không bị cắt ngưỡng (FR-006); `cards = none` → không thẻ nào (US1 #5); `desk_in_image=false` → có bàn vẽ thêm như 009,
  `true` → không vẽ bàn (FR-009, US1 #7); `draw_debug_zones` vẽ vạch mép bàn xanh lá và khung vùng tay tím chỉ trên ảnh gỡ lỗi (FR-008)
- [x] T019 [P] [US1] Test `SceneController` trong `tests/unit/test_scene_controller.py`: `mode = realistic` dùng `compute_realistic_layout`,
  `rows` dùng `compute_layout`; `hands_zone` của nhân vật vào `FrameGeometry`; thiếu → `warning` `hands_zone_missing`; `preview(debug=True)`
  có lớp gỡ lỗi nhưng không đổi `version`, `_base` hay lớp gửi renderer giả; log `scene_rendered` có `layout_mode`, `cards`, `stations`
  (FR-024); một món ảnh lỗi → món đó không vẽ, các món khác vẫn vẽ, có issue (FR-023)
- [x] T020 [P] [US1] Test `GET /api/scene/preview.png?debug=1` trong `tests/integration/test_image_api.py` (contracts/api.md §3): trả PNG
  khác `debug=0`, `version` cảnh live không đổi, renderer giả không nhận lớp mới; thiếu `debug` → như 012
- [x] T021 [P] [US1] Test kiểm tra trước demo trong `tests/unit/test_readiness.py`: `realistic` + nhân vật không khai `hands_zone` →
  `warning` `hands_zone_missing`; `rows` thì không; `bad_layout` hiện như issue `error` của 009 (FR-003)

### Implement US1

- [x] T022 [US1] Viết `DeskStation` (bảng chỗ đứng research R1) và `compute_realistic_layout(...) -> SceneLayout` trong
  `src/ai_live/scene/layout.py`: khoảng đặt trái `[12, hands_x1 − 8]`, phải `[hands_x2 + 8, W − 12]`, đáy `desk_y + depth × (H − desk_y)`,
  thu nhỏ khi chạm `face_zone`/tràn bên/chạm vùng cấm hoặc tay, `MIN_ART_HEIGHT = 0.06H`, luật chồng, `draw_order`, `shadow_box`, `station`,
  `card_box = None` (làm T016, T017 xanh)
- [x] T023 [US1] Sửa `src/ai_live/scene/render.py`: bóng hai lớp (tiếp xúc 0,9w × 6 px, mờ 3, alpha 140; mềm 1,25w × 0,10h, mờ 8, alpha 70;
  research R3), chỉnh sáng bằng `ImageEnhance.Brightness` theo `layout.brightness`, vẽ theo `draw_order`, bỏ thẻ khi `card_box is None`, vẽ
  bàn 009 khi nhân vật không có bàn trong ảnh, `draw_debug_zones` thêm vạch mép bàn và vùng tay; nhánh `rows` không đổi (làm T018 xanh)
- [x] T024 [US1] Sửa `src/ai_live/scene/controller.py`: chọn hàm bố cục theo `layout.mode`, tính `hands_zone` (khai hoặc mặc định + cảnh báo)
  vào `FrameGeometry`, `preview(..., debug=False)`, thêm `layout_mode`, `cards`, `stations` vào log `scene_rendered` (làm T019 xanh)
- [x] T025 [US1] Sửa `src/ai_live/scene/__main__.py`: `preview` đọc `desk_in_image`, `desk_top`, `hands_zone` của nhân vật theo `AVATAR_DIR`
  để bố cục giống live; `--debug-zones` vẽ thêm vạch mép bàn và vùng tay; `check` in `layout_mode`, chế độ thẻ và cảnh báo mới
  (contracts/scene-set.md §4)
- [x] T026 [P] [US1] Thêm tham số `debug` cho `GET /api/scene/preview.png` trong `src/ai_live/app/image_routes.py` (làm T020 xanh)
- [x] T027 [P] [US1] Thêm `hands_zone_missing` vào `src/ai_live/ops/readiness.py` (làm T021 xanh)
- [x] T028 [US1] Đo `desk_top` và `hands_zone` của `demo_host_02` bằng `preview --debug-zones` trên ảnh chờ và vài khung của các clip `talk`
  (quickstart §2), ghi vào `assets/avatars/demo_host_02/character.json`; vạch mép bàn sai ≤ 1% chiều cao khung, khung tím ôm cả hai tay
  (FR-010); `uv run python -m ai_live.ops readiness` không còn `hands_zone_missing`
- [x] T029 [US1] Chụp ảnh tĩnh `AVATAR_MODE=static` theo quickstart §1 bước 1–4 vào `out/013/` (1 → 5 món, mỗi món nổi, `brightness` 0,9 và
  1,1, `rows` để so): ít nhất 10 ảnh cho nửa ảnh tĩnh của SC-001; người dùng duyệt vị trí các chỗ đứng (TODO research R1) và độ sáng

**Checkpoint:** US1 chạy độc lập ở `AVATAR_MODE=static`; bộ cảnh không có `mode` y như 009. Dừng, cho người dùng xem ảnh `out/013/` (MVP).

## Phase 4: User Story 2: Tự bỏ nền phẳng khi tải ảnh sản phẩm (P2)

**Mục tiêu:** tải ảnh không trong suốt → bỏ nền (phẳng hoặc model) thành một phiên bản 012 mới, xem hai ảnh cạnh nhau, chọn bản dùng.
**Kiểm độc lập:** quickstart §3.

### Test cho US2 (viết trước, phải FAIL trước khi implement)

- [x] T030 [P] [US2] Test bỏ nền phẳng trong `tests/unit/test_scene_matting.py` (MỚI; research R5): nền trắng và nền một màu → `removed`
  (`flat`), viền ảnh trong suốt; mọi điểm có alpha > 0 giữ nguyên R, G, B so với ảnh vào (FR-015, US2 #5); ô trắng trong lòng sản phẩm còn
  nguyên (US2 #4); làm mềm mép chỉ đổi alpha vài điểm ảnh quanh mép; kết quả cắt theo hộp alpha; viền < 90% điểm gần màu nền (khoảng
  Chebyshev 28) → không coi là nền phẳng; PNG đã trong suốt → `kept` (`already_transparent`, US2 #2)
- [x] T031 [US2] Test `assess_cut` trong `tests/unit/test_scene_matting.py` (sau T030, cùng file; research R8): từng ngưỡng (`fg_ratio` < 5% /
  > 95%, tiền cảnh ở viền > 25%, alpha lưng chừng > 12% tiền cảnh, mảng lớn nhất < 85% với cách phẳng) cho `failed` kèm câu tiếng Việt;
  hộp trắng trên nền trắng → `failed`, không ra ảnh bị khoét (FR-014, US2 #4); `metrics` có đủ 4 chỉ số
- [x] T032 [US2] Test chạy model trong `tests/unit/test_scene_matting.py` (sau T031, cùng file; research R6, R7) dùng T005: tiền/hậu xử lý
  `isnet-*` và `birefnet-*` trên mảng numpy (cỡ 1024², chia max, trừ 0,5; sigmoid / min-max; đổi lại cỡ ảnh); tên model khác → mã 3; CLI tham
  số sai → mã 2; `remove_background()` theo sơ đồ data-model §9: nền phức tạp + model giả → `removed` (`model`); `MATTING_MODEL_PATH` rỗng
  hoặc file không có → `failed` "chưa cài model tách nền"; show đang chạy + `MATTING_DURING_SHOW=false` → `failed` "đang live…" nhưng nền
  phẳng vẫn bỏ; hết giờ (rút ngắn trong test) → giết tiến trình, `failed` "tách nền quá lâu"; mã 3/4/5 → `failed`; mặt nạ nửa vời → `failed`
  "model không chắc"; hai lời gọi cùng lúc chạy lần lượt (`Semaphore(1)`); tiến trình con được hạ ưu tiên (Windows `creationflags`
  `BELOW_NORMAL_PRIORITY_CLASS`, POSIX `os.nice`); bỏ nền phẳng chạy ngoài vòng sự kiện (FR-013, FR-016)
- [x] T033 [P] [US2] Test model thật `@pytest.mark.matting_model` trong `tests/unit/test_scene_matting_model.py` (MỚI): bỏ qua khi không có file
  ở `MATTING_MODEL_PATH`; chạy CLI trên ảnh nền nhiễu của T003, mặt nạ cùng cỡ ảnh vào, mã thoát 0
- [x] T034 [P] [US2] Test lưu bản bỏ nền trong `tests/unit/test_scene_uploads.py` (data-model §8–§9, research R9): `removed` → phiên bản mới có
  `derived_from`, ảnh tải lên có `cutout_version`, cả hai có `bg_removal`; `source_name` thêm " (đã bỏ nền)"; `vid` = 12 ký tự đầu sha256 PNG;
  tải lại ảnh y hệt trả kết quả cũ, không chạy lại; kết quả cũ `failed` vì "chưa cài model…" hoặc "đang live…" thì chạy lại; phiên bản có
  `derived_from` không bao giờ bị bỏ nền lại; bản bỏ nền không thừa hưởng `rights_confirmed_at` (FR-011, FR-017)
- [x] T035 [P] [US2] Test luồng API trong `tests/integration/test_image_api.py` (contracts/api.md §1–§2): tải ảnh nền trắng → 201,
  `bg_removal.result = removed`, có `cutout`, `recommended_version` = bản bỏ nền, không có `has_background`; PNG trong suốt → `kept`,
  `cutout: null`; nền phức tạp khi chưa có model → 201 `failed` + `has_background`, ảnh tải lên vẫn lưu (US2 #3); `too_wide` tính trên
  `recommended_version`; `GET /api/scene/images` có ba trường mới; áp bản bỏ nền (có xác nhận quyền dùng) rồi "Về ảnh trước", gỡ ảnh, áp vào
  bộ chuẩn bị đều chạy như 012 (FR-017, SC-004); chọn ảnh gốc rồi áp → món dùng ảnh gốc kèm cảnh báo còn nền (US2 #6)
- [x] T036 [P] [US2] Test kiểm tra trước demo trong `tests/unit/test_readiness.py` (research R10): `realistic` + ảnh đang dùng còn nền →
  `warning` `art_has_background`; `rows` thì không; `MATTING_MODEL_PATH` rỗng hoặc file không có → `warning` `matting_model_missing` (FR-018)
- [x] T037 [P] [US2] Test trang điều khiển trong `tests/integration/test_control_page.py`: trang có khung hai ảnh trên nền ô cờ, chữ
  "Đang bỏ nền…", nút áp bị khóa trong lúc chờ, lý do lỗi và gợi ý "xin khách ảnh nền trơn hoặc ảnh đã tách nền" (US2 #3), "Xem trước"/"Áp dụng"
  gửi `version_id` đang chọn (FR-012)

### Implement US2

- [x] T038 [US2] Viết `src/ai_live/scene/matting.py` (MỚI) phần không model: `CutResult` (data-model §6), `remove_flat_background` (viền 2 px,
  màu nền = trung vị viền, loang từ viền, `MinFilter(3)` + `GaussianBlur(0.8)` trên alpha, RGB giữ nguyên, cắt theo hộp alpha), `assess_cut`
  với các hằng số ngưỡng R8 (làm T030, T031 xanh)
- [x] T039 [US2] Viết phần model trong `src/ai_live/scene/matting.py` (sau T038): cấu hình tiền/hậu xử lý theo tên file, CLI `__main__` (mã
  thoát 0/2/3/4/5, `onnxruntime` với `intra_op_num_threads=2`, `inter_op_num_threads=1`, POSIX `os.nice(10)`), và
  `async remove_background(image, *, show_running, settings) -> CutResult` theo sơ đồ data-model §9 (`asyncio.to_thread` cho phần phẳng,
  `asyncio.create_subprocess_exec` hạ ưu tiên, `Semaphore(1)`, hết giờ 60 s) (làm T032, T033 xanh)
- [x] T040 [US2] Lưu bản bỏ nền thành phiên bản trong `src/ai_live/scene/uploads.py` (sau T015): ghi PNG + phiên bản mới, `derived_from`,
  `cutout_version`, `bg_removal` (data-model §7), luật dùng lại / chạy lại, ghi log `scene_bg_removed` đủ trường contracts/api.md §5
  (FR-024) (làm T034 xanh)
- [x] T041 [US2] Gọi bỏ nền trong `POST /api/scene/uploads` của `src/ai_live/app/image_routes.py` (sau T026): chờ bỏ nền xong rồi trả
  `bg_removal`, `cutout`, `recommended_version`; `has_background` chỉ khi `failed`; `too_wide` theo `recommended_version`; lấy trạng thái show
  đang chạy cho `MATTING_DURING_SHOW`; `GET /api/scene/images` trả ba trường mới; bỏ nền lỗi không làm request lỗi (làm T035 xanh)
- [x] T042 [US2] Sửa `src/ai_live/app/static/control.html`, `control.js`, `style.css`: "Đang bỏ nền…" và khóa nút áp tới khi có phản hồi, hai
  ảnh cạnh nhau trên nền ô cờ với cách bỏ nền và thời gian, chọn sẵn `recommended_version`, bấm chọn bản kia, `failed` hiện lý do và gợi ý
  (contracts/api.md §4; làm T037 xanh)
- [x] T043 [US2] Thêm `art_has_background` (trong `src/ai_live/scene/controller.py` → `issues` của `GET /api/scene/images`) và
  `matting_model_missing` vào `src/ai_live/ops/readiness.py` (làm T036 xanh)
- [ ] T044 [US2] Đo SC-003 và SC-004 (cần T002): bộ ≥ 20 ảnh sản phẩm thật ngoài git (10 nền trơn/một màu, 10 nền phức tạp, thêm ảnh khó:
  sản phẩm trắng trên nền trắng, chai trong suốt) tải qua trang điều khiển; ghi bảng từng ảnh (kết quả, `ms`, chỉ số R8, đạt/không) và ngưỡng
  cuối vào `specs/013-realistic-desk-products/research.md` R8, sửa hằng số trong `src/ai_live/scene/matting.py` nếu cần; người dùng chấm sạch
  và xác nhận chi tiết sản phẩm không đổi trên ảnh cạnh nhau (quickstart §3 bước 5–6)
- [ ] T045 [US2] Đo SC-006 trên laptop (cần T002): thời gian từ chọn ảnh tới lúc trang hiện hai ảnh với ảnh nền trơn và nền phức tạp tới
  2000 px mỗi cạnh, thời gian nạp model và RAM đỉnh của tiến trình con (Task Manager); ghi vào `specs/013-realistic-desk-products/research.md`
  R7 (quickstart §3 bước 1, 4; §5 bước 3)

**Checkpoint:** US2 chạy độc lập qua trang điều khiển ở `AVATAR_MODE=static`; ảnh gốc luôn còn và "Về ảnh trước" của 012 vẫn chạy.

## Phase 5: User Story 3: Thẻ sản phẩm và làm nổi hợp với cảnh thật (P3)

**Mục tiêu:** chế độ thẻ `none|one|all`, làm nổi bằng ánh sáng ấm và cỡ tăng nhỏ neo đáy. **Kiểm độc lập:** quickstart §4.

### Test cho US3 (viết trước, phải FAIL trước khi implement)

- [x] T046 [US3] Test thẻ và làm nổi trong `tests/unit/test_realistic_layout.py` (sau T017, cùng file; research R4, R3): `none` → mọi
  `card_box is None` (US3 #2); `all` → thẻ dưới mỗi món, thẻ chạm món khác/vùng tay thì bỏ thẻ đó + `card_no_room` (US3 #3); `one` → chỉ thẻ
  món đang nổi, nằm trên các món cùng bên và dưới dải phụ đề (40–48,5% H), không có chỗ thì góc dưới bên đó, không nữa thì `card_no_room`;
  không món nổi → không thẻ; thẻ không giao vùng cấm, vùng tay hay hộp món (US3 #1); món nổi phóng `highlight_scale` neo giữa đáy: đáy không
  đổi, vẫn không chạm vùng cấm (kẹp cỡ khi cần) (FR-022, US3 #4)
- [x] T047 [P] [US3] Test vẽ trong `tests/unit/test_scene_render.py`: quanh món nổi có điểm sáng ấm (255, 240, 210), vùng sáng không giao vùng
  cấm; món không nổi bị làm tối 0,92 nhưng vẫn rõ; chữ thẻ ở `one`/`all` lấy nguyên văn tên, giá hoặc khoảng giá, dòng khuyến mãi đầu tiên từ
  file nội dung (FR-020)
- [x] T048 [P] [US3] Test `SceneController` trong `tests/unit/test_scene_controller.py`: chế độ `one` hiện thẻ của X khi câu đầu của phân đoạn
  X bắt đầu phát, không sớm hơn, trong ≤ 1 s, ẩn ở phân đoạn chung (FR-021, US3 #1); đổi file nội dung giữa phiên → chữ thẻ đổi theo
  (FR-020, US3 #5); chuỗi phân đoạn giả lập một vòng 3 sản phẩm × `one`/`all`: mọi chữ thẻ trong log `scene_rendered`/lớp vẽ khớp file
  (SC-007)

### Implement US3

- [x] T049 [US3] Đặt thẻ theo `layout.cards` và làm nổi neo đáy (kẹp để không chạm vùng cấm) trong `src/ai_live/scene/layout.py`
  (sau T022; làm T046 xanh)
- [x] T050 [US3] Sửa `src/ai_live/scene/render.py` (sau T023): ánh sáng ấm làm nổi (mờ 12, alpha 120), làm tối món không nổi 0,92, vẽ thẻ theo
  `card_box`, cảnh báo `card_no_room` (làm T047 xanh)
- [x] T051 [US3] Nối chế độ thẻ `one` với luồng làm nổi 009 trong `src/ai_live/scene/controller.py` (sau T024): bố cục tính lại khi đổi món
  nổi, `cards` vào log `scene_rendered` (làm T048 xanh)
- [x] T052 [US3] Chụp ảnh tĩnh từng chế độ thẻ theo quickstart §4 vào `out/013/cards_*.png` (`none`, `one` với món chính/món phụ/không món
  nổi, `all`, `rows` + `none`); người dùng duyệt vị trí thẻ `one` (TODO research R4) và mức làm nổi 1,04
- [x] T053 [US3] Chạy show 30 phút `AVATAR_MODE=static` với `cards: one` (và một vòng `all`), đổi file nội dung một lần giữa phiên; so chữ thẻ
  trong ảnh chụp lúc đổi phân đoạn và log với file đang nạp, ghi kết quả SC-007 vào `progress/LOG.md`

**Checkpoint:** ba story chạy độc lập; mặc định `realistic` không thẻ.

## Phase 6: Hoàn thiện và việc chung

- [x] T054 [P] Thêm mục bố cục `realistic` và `scene/matting.py` (tiến trình con, biến môi trường, không đổi Protocol) vào
  `docs/ARCHITECTURE.md`; thêm `matting.py` vào `src/README.md`
- [x] T055 [P] Thêm vào `docs/RUNBOOK.md`: tải và kiểm model tách nền, `MATTING_DURING_SHOW`, đo `desk_top`/`hands_zone` khi làm nhân vật
  mới, bước M2 "ghim món chính một lần khi mở phiên Shopee" (spec Giả định)
- [x] T056 [P] Đọc điều khoản bộ dữ liệu DIS5K và LICENSE BiRefNet_lite, ghi kết quả vào `docs/RISKS.md` L15 (việc phải xong trước M2)
- [x] T057 Chuyển bộ cảnh demo `assets/scenes/demo/scene.json` sang `"layout": {"mode": "realistic"}`; `uv run python -m ai_live.scene check
  assets/scenes/demo` không có issue `error`
- [ ] T058 [GPU] SC-001 nửa lip-sync: show `demo_host_02`, `AVATAR_MODE=livetalking`, `OUTPUT_MODE=meet`, mở `/host`, chụp ≥ 10 ảnh lúc chờ,
  lúc nói, lúc đổi món nổi (cộng với ảnh T029 đủ ≥ 20); 100% ảnh đáy món trên mặt bàn, không che mặt/tay/nhãn AI/watermark; người dùng chấm
  "như đồ thật" (quickstart §1 bước 5)
- [ ] T059 [GPU] SC-002: quay hai đoạn 1 phút `rows` và `realistic` (chỉ để duyệt nội bộ, không phát lên Shopee), đặt tên ẩn bản; ≥ 3 người xem
  chọn đoạn giống phiên live hơn và trả lời "sản phẩm như đặt trên bàn"; ghi kết quả vào `progress/LOG.md`
- [ ] T060 [GPU] SC-005: show 10 phút `rows` rồi 10 phút `realistic` cùng cấu hình (so `scene_ms` trung vị, FPS lệch ≤ 10%, lặng p95 tăng ≤ 0,1 s);
  show 10 phút `realistic` có tải 3 ảnh nền phức tạp (có model) giữa show; không đạt → đặt mặc định `MATTING_DURING_SHOW=false` trong
  `src/ai_live/core/config.py` và `.env.example`, ghi vào `docs/RISKS.md` Q40 và research R7 (quickstart §5, FR-016)
- [x] T061 Chạy các bước không GPU của quickstart §0–§4, `uv run pytest`, `uv run ruff check .` và `uv run ruff format --check .` sạch
- [x] T062 Chạy `/update-context` (CLAUDE.md, `docs/DECISIONS.md`, `docs/ROADMAP.md` mốc M1d, `progress/`)
- [x] T063 [US1] [US3] Duyệt 2026-11-23 trên khung live thật với ảnh Coca (spec Làm rõ 2026-11-23): `src/ai_live/scene/layout.py` cao
  mục tiêu mới (P 0,25 H…), ngang S1/S2 dãn ra, luật cỡ FR-004 (món sau không lấn món trước cả hai chiều), thu cả bên chật theo bậc
  1,0–0,6, lật bố cục sang trái khi món chính ở đó to ≥ 1,15 ×; làm nổi alpha 230, món khác tối 0,85, `highlight_scale` mặc định 1,08
  (`loader.py`); `preview --host-frame` (`scene/__main__.py`); test trong `tests/unit/test_realistic_layout.py`, `test_scene_render.py`,
  `test_scene_loader.py`; ảnh duyệt `out/013/coca_live_v2_*.png`
  Sửa thêm cùng ngày theo nhận xét lúc live ("bóng như đang bay"): `render.py` `foot_line`, `defringe`, bóng theo đường đáy; test
  `test_realistic_shadow_follows_a_slanted_foot_without_a_gap`, `test_defringe_*`; ảnh `out/013/shadow_zoom_*.png`, `coca_live_v3.png`.

---

## Phase 7: Cách bày trưng bày `showcase` và cảnh báo ảnh nhỏ (FR-025–FR-028, ADR-079)

**Mục tiêu**: món chính to ở giữa ngay trước host như live thật, tối đa 3 món phụ phía sau, bục trắng và sticker giá tùy chọn; cảnh báo
ảnh nguồn nhỏ ở mọi cách bày và lúc tải ảnh.

- [x] T064 Mô hình và bộ nạp: `LayoutParams.riser`/`sticker`, `Sticker`, `SceneLayout.riser_box`/`sticker`, `mode = "showcase"` (cards mặc
  định `none`, `max_slots` 1–4, `highlight_scale` 1,00–1,10) trong `src/ai_live/scene/models.py`, `loader.py`
- [x] T065 Test `tests/unit/test_showcase_layout.py`: không hộp vẽ nào (ảnh, bóng, ánh sáng, bục, sticker, thẻ) chạm mặt/nhãn/watermark ở
  4 vị trí nhãn × 2 khung × có/không món nổi; món chính cao 0,33–0,40 H, giữa khung, vẽ sau cùng; món phụ bị che ≤ 40% (đổi bởi
  ADR-081, xem T072); quá 4 món →
  `overflow`; bục nâng món chính; sticker = `price_text` nguyên văn, không có khuyến mãi, không giá → `sticker_no_price`; `sticker_lines`
  ngắt sau dấu gạch; `art_too_wide`; mặt bàn chạm mặt → không vẽ; `art_low_resolution` ở cả 3 cách bày, xét cỡ lúc nổi, không báo khi ảnh
  đã đạt `ART_MAX_SIDE`; khóa bộ nạp; vẽ thử có bục và sticker vẫn sạch vùng cấm
- [x] T066 `compute_showcase_layout`, `_showcase_main`, `_showcase_back`, `_hiding_ok` (bỏ bởi ADR-081, T073), `_sticker_box`, `_showcase_cards`,
  `low_resolution_issues` và `compute_scene_layout` chọn theo mode trong `src/ai_live/scene/layout.py` (làm T065 xanh)
- [x] T067 Vẽ bục (`_draw_riser`) ngay trước món chính và sticker (`_draw_sticker`, `sticker_lines`) sau thẻ, ánh sáng làm nổi không cắt
  vùng tay ở `showcase` trong `src/ai_live/scene/render.py`
- [x] T068 Cảnh báo `low_resolution` lúc tải ảnh: `SceneController.low_resolution` (`controller.py`), `image_routes.py` trả `warnings` kèm
  `warning_messages`; kiểm tra sẵn sàng xét nền ảnh ở mọi cách bày trừ `rows` (`src/ai_live/ops/readiness.py`); test
  `test_a_small_picture_warns_it_will_look_soft` trong `tests/integration/test_image_api.py`
- [x] T069 Nâng `ART_MAX_SIDE` 640 → 960 px (`src/ai_live/scene/limits.py`, dùng chung cho bộ nạp và bố cục): món chính `showcase` nổi
  rộng khoảng 450 px trên khung 480×832 nên 640 px không đủ 1,5 lần (FR-028, ADR-079)
- [x] T070 Bộ cảnh demo `assets/scenes/demo/scene.json` chuyển sang `showcase` + `riser` + `sticker` (không commit, gitignore); ảnh duyệt
  bằng `preview --host-frame`: món chính thùng Coca trên bục, sticker "62.000đ – 235.000đ", 2 chai phía sau
- [ ] T071 [GPU] Người dùng duyệt `showcase` trên khung live thật (lip-sync chạy, tay host cử động sau cụm sản phẩm); thay ảnh thùng Coca
  to hơn (ảnh hiện tại 539×381 px nên có cảnh báo `art_low_resolution`). Cập nhật 2026-11-23: thùng đã thay bằng lốc 6 chai
  (ảnh 958×1145, hết cảnh báo, T075)

**Checkpoint**: `showcase` chạy với ảnh mẫu, mọi test xanh; chờ người dùng duyệt trên khung live thật (T071).

## Phase 7b: Không món nào che món nào, món chính demo là lốc 6 chai (FR-025 sửa 2026-11-23, ADR-081)

**Mục tiêu**: người dùng yêu cầu "đổi 1 thùng thành 1 lốc đi và các sản phẩm không bị che nhau": các món cách nhau ít nhất 8 px (khung
832), kể cả lúc một món được làm nổi; sticker giá không che món phụ; thiếu chỗ thì món chính nhỏ lại trước, rồi tới món phụ.

- [x] T072 Test `tests/unit/test_showcase_layout.py`: `test_no_product_hides_another` (2 khung × có/không bục và sticker × 5 trường hợp làm
  nổi: không ảnh nào chạm nhau, sticker không chạm món phụ), `test_a_wide_main_product_shrinks_to_make_room_beside_it` (lốc rộng nhỏ lại
  trong 0,22–0,38 H để 2 chai đứng đủ hai bên, món phụ giữ ≥ 85% cỡ), `test_a_crowded_desk_still_shows_every_product_whole`; bỏ test che
  ≤ 40%; các test cỡ món chính và sticker dùng bộ 3 món mảnh `SPARSE`
- [x] T073 `src/ai_live/scene/layout.py`: bỏ `SHOWCASE_MAX_HIDDEN`, `_hidden_share`, `_hiding_ok`; thêm `SHOWCASE_GAP_PX` 8,
  `SHOWCASE_MAIN_MIN_HEIGHT` 0,22, `SHOWCASE_MAIN_STEP` 0,95, `SHOWCASE_BACK_KEEP` 0,85, `SHOWCASE_BACK_MIN_SCALE` 0,3; `_touches`,
  `_lit_reserve` (chỗ món đã đặt chiếm khi được làm nổi), `_place_showcase` thử một cỡ, `compute_showcase_layout` thu món chính rồi món
  phụ; món nổi chỉ to lên khi không chạm món khác và ánh sáng không ra ngoài khung; sticker né món phụ; tên ô theo bên thật
- [x] T074 Dữ liệu demo `scripts/make_demo_content.py`: món chính "Lốc 6 chai Coca-Cola 355ml" giá 95.000đ (giá, khuyến mãi, câu hỏi là
  số demo; chai vì Commons không có ảnh lốc lon nền sạch), sinh lại `data/products/coca.docx` (mã món `loc-6-chai-coca-cola-355ml`)
- [x] T075 Ảnh lốc 6 chai cho `loc-6-chai-coca-cola-355ml`: tải qua kho ảnh 012 (bỏ nền), áp dụng, duyệt bằng `preview --host-frame` và trên
  khung live (Chrome); ảnh thùng cũ để nguyên trong kho (cảnh báo `orphan_image`, không xóa). Xong 2026-11-23: ảnh "6 Pack of
  Mexican Coca Cola" (Willis Lam, CC BY-SA 2.0) tô phẳng nền gỗ và tường trước khi tải vì chưa có model tách nền (T002), bản
  bỏ nền 958×1145 áp dụng; khung `/host` sau khi khởi động lại app: 3 món tách rời, sticker 95.000đ chỉ nằm ở góc lốc, nhãn AI hiện

**Checkpoint**: mọi test xanh, khung live không món nào che món nào; người dùng duyệt chung với T071.

## Phase 7c: Cảnh live giống thật hơn (FR-025 sửa, FR-029 thêm 2026-11-23, ADR-082)

**Mục tiêu**: người dùng: "hiện ảnh nhìn không được đẹp lắm bạn viết thêm skill để điều chỉnh bố cục live sao cho giống real nhất". Đo
khung bằng skill `live-scene-realism`, rồi sửa: chân sản phẩm đứng đúng mép bàn thấy trên hình, cỡ gần cỡ thật so với đầu host, sản
phẩm không sáng và nét hơn hình host, sticker nhỏ hơn.

- [x] T076 Skill `.claude/skills/live-scene-realism/` (`SKILL.md`, `REFERENCE.md`, `scripts/realism_report.py`, `scripts/contact_sheet.py`):
  báo cáo đo từng món (mép bàn thấy trên hình so với `desk_top`, cỡ so với đầu, độ sáng, độ nét, màu ánh sáng, mép) và ghép ảnh so sánh
  các phương án; chỉ ghi vào `out/realism/`
- [x] T077 Test `tests/unit/test_scene_render.py`: `test_camera_soften_*` (ảnh mềm hơn, mép alpha mềm, màu vùng đặc giữ nguyên,
  vùng trong suốt không làm đen mép); `tests/unit/test_showcase_layout.py`: món chính mặc định cao trong 0,26–0,30 H khi đủ chỗ, món phụ
  không cao hơn món chính
- [x] T078 `src/ai_live/scene/layout.py`: `SHOWCASE_MAIN_HEIGHT` 0,38 → 0,28, `SHOWCASE_BACK` (0,30/0,27/0,24 → 0,22/0,20/0,18),
  `STICKER_PX` 96 → 72; `src/ai_live/scene/render.py`: `camera_soften` (mờ 0,7 px nhân trước theo alpha, mép mềm 0,8 px, theo cỡ khung)
  sau `defringe` ở cách bày `realistic`/`showcase`
- [x] T079 Cấu hình cục bộ demo (không nằm trong git): `character.json` `scene.desk_top` 0,78 → 0,874 (mép gỗ đo trên `face.png` và khung
  `/host`; sửa cùng ngày: trả về 0,78 vì khung live thật của fork có mép bàn ở 0,775, `face.png` chỉ là ảnh xem trước), `scene.json` `layout.brightness` 0,9; duyệt bằng ảnh trước/sau `out/realism/sheet4.png` và khung `/host` sau khi khởi động lại

**Checkpoint**: mọi test xanh; người dùng duyệt chung với T071.

## Phase 7d: Bàn trưng bày kiểu hot live và thùng quà Tết (FR-030–FR-033 thêm 2026-11-26, ADR-095, ADR-096)

**Mục tiêu**: người dùng: "trình bày sản phẩm như 1 buổi hot live", rồi "không hiện giá trên này hoặc khuyến mãi chỉ có sản phẩm trên
bàn thôi => bạn coi sắp xếp lại sản phẩm trang trí đẹp, ví dụ dùng hộp quà hoặc sản phẩm nổi bật hiện nay nếu có".

- [x] T080 Test `tests/unit/test_hot_live_desk.py`: chọn kiểu nhóm theo hình dáng, nhóm chỉ lặp đơn vị và giữ màu, tem giá nguyên văn và
  không che món hay nhãn, băng khuyến mãi nguyên văn và bỏ nguyên câu, cờ tắt thì không vẽ gì (FR-030–FR-032)
- [x] T081 `src/ai_live/scene/merchandise.py` (nhóm hàng), `src/ai_live/scene/models.py` (`stock`, `price_tags`, `promo_banner` trong
  `LayoutParams`; `ProductArt.stock`) (FR-030)
- [x] T082 `src/ai_live/scene/layout.py` `_price_tags`, `_promo_banner`; `src/ai_live/scene/render.py` vẽ tem và băng
  (`promo_banner_lines`) (FR-031, FR-032)
- [x] T083 `scripts/make_demo_content.py`: thêm các món Coca vào dữ liệu demo, tạo lại `data/products/coca.docx` (ADR-095)
- [x] T084 `scripts/make_demo_content.py`: thùng 24 lon Coca-Cola Tết 320ml làm món chính, bỏ món lon 355ml, tạo lại `coca.docx` (ADR-096)
- [x] T085 `src/ai_live/scene/layout.py` `SHOWCASE_MAIN_MAX_WIDTH` 0,8 → 0,5; test
  `test_a_wide_gift_box_in_the_middle_leaves_the_bottles_room_beside_it`, sửa mức sàn trong
  `test_a_wide_main_product_shrinks_to_make_room_beside_it` (FR-033)
- [x] T086 Cấu hình cục bộ demo (không nằm trong git): `scene.json` `max_slots` 3, `stock` true, `price_tags` false, `promo_banner`
  false; so phương án bằng `out/realism/sheet_fin.png`, kiểm live `/host` bằng Chrome DevTools

**Checkpoint**: pytest 3595 passed, ruff sạch; người dùng duyệt chung với T071.

## Phase 7e: Bày bàn theo bậc trước–sau (FR-034 thêm 2026-11-26, ADR-097)

- [x] T087 Test `test_the_gift_box_stands_in_front_and_the_stock_steps_back_beside_it` (`tests/unit/test_hot_live_desk.py`, FR-034)
- [x] T088 `src/ai_live/scene/layout.py`: `SHOWCASE_MAIN_MAX_WIDTH` 0,5 → 0,42, `SHOWCASE_MAIN_DEPTH` 0,8 → 0,7 (FR-034)
- [x] T089 Cấu hình cục bộ demo (không nằm trong git): `scene.json` `avoid_app_overlay` false cho Meet; so phương án bằng
  `out/realism/sheet_disp1.png`, `sheet_disp2.png`, kiểm live `/host` bằng Chrome DevTools

**Checkpoint**: pytest và ruff sạch; người dùng duyệt chung với T071. Trước khi lên Shopee qua OBS: bật lại `avoid_app_overlay`.

## Phase 7f: Chai thành cụm hai hàng theo ảnh mẫu (FR-035 thêm 2026-11-26, ADR-098)

- [x] T090 Test `test_bottles_stand_as_two_staggered_rows_one_bottle_tall` (`tests/unit/test_hot_live_desk.py`, FR-035); sửa assert
  cuối của test độ sáng cho cụm mới
- [x] T091 `src/ai_live/scene/merchandise.py`: cụm hai hàng (`STOCK_ROW_FRONT` 2, `STOCK_ROW_BACK` 3, `STOCK_ROW_BACK_SCALE` 0,85,
  `STOCK_ROW_SPACING` 1,0; bỏ `STOCK_BACK_SHOWN`); `src/ai_live/scene/layout.py`: `SHOWCASE_MAIN_MAX_WIDTH` 0,42 → 0,38 (FR-034, FR-035)
- [x] T092 So phương án bằng `out/realism/sheet_e.png` (hàng sau nâng cao: chai co còn ~0,7 cỡ thật, loại) và `sheet_g.png`
  (đỉnh ngang: 3+2, 2+3, 3+3 ở 0,38; chọn 2+3); kiểm live `/host` bằng Chrome DevTools

**Checkpoint**: pytest 3597 passed, ruff sạch; người dùng duyệt chung với T071.

## Phụ thuộc và thứ tự

- Setup → Foundational → US1 (MVP) → US2 → US3 → Hoàn thiện. US2 chỉ cần Foundational (không cần US1) trừ T043 phần `art_has_background`
  (đọc `layout.mode`, cần T013). US3 cần US1 (T022–T024).
- Trong mỗi story: test trước (phải FAIL), rồi `scene/` → `app/` → trang điều khiển → đo.
- `src/ai_live/scene/layout.py`: T022 → T049. `render.py`: T018 (ghi mã băm trước) → T023 → T050. `controller.py`: T024 → T043 → T051.
  `uploads.py`: T015 → T040. `matting.py`: T038 → T039 → T044. `image_routes.py`: T026 → T041. `readiness.py`: T027 → T043.
- `tests/unit/test_realistic_layout.py`: T016 → T017 → T046. `test_scene_matting.py`: T030 → T031 → T032. `test_scene_uploads.py`: T009 →
  T034. `test_scene_controller.py`: T019 → T048. `test_scene_render.py`: T018 → T047. `test_readiness.py`: T021 → T036.
  `test_image_api.py`: T020 → T035.
- T044, T045, T060 cần T002 (file model). T028 cần T025. T057 cần US1 xong. T058–T060 cần mọi story xong và fork chạy trên GPU laptop.

## Chạy song song

- Setup: T002, T003, T004, T005 (T001 trước vì đổi `pyproject.toml`).
- Foundational: test T006–T010 cùng lúc; T011, T014, T015 song song với T012 → T013.
- US1: test T016, T018, T019, T020, T021 cùng lúc; T026 (route) và T027 (readiness) song song với T022 → T023 → T024.
- US2: test T030, T033, T034, T035, T036, T037 cùng lúc; T042 (trang điều khiển) song song với T038 → T039.
- US3: test T047, T048 song song với T046.
- Hoàn thiện: T054, T055, T056 cùng lúc.
- Theo agent (`/sdd.dispatch`): ai-media làm T012–T015, T022–T025, T028, T038–T040, T049–T051; ai-orchestrator làm T001, T011, T026, T027,
  T041–T043, T057; ai-qa làm các task test, T029, T044, T045, T052, T053, T058–T061.

## Đợt GPU

- T058 (SC-001), T059 (SC-002), T060 (SC-005) chạy chung một buổi trên GPU laptop (ADR-023): bật fork bằng
  `powershell scripts/livetalking/run.ps1`, `AVATAR_MODE=livetalking`, rồi chạy app. Không dùng RunPod.
- Model tách nền chạy CPU, không cần GPU; T060 đo nó chạy cùng lúc với fork và VieNeu.

## Chiến lược MVP

1. Setup + Foundational (T001–T015) → 2. US1 (T016–T029) → **dừng, người dùng xem ảnh `out/013/` (quickstart §1, §2), demo được với ảnh đã
   trong suốt** → 3. US2 → 4. US3 → 5. Hoàn thiện + đợt GPU.

## Bảng phủ yêu cầu

| Yêu cầu | Task |
|---------|------|
| FR-001 | T007, T013, T018, T023, T024, T057 |
| FR-002 | T016, T022 |
| FR-003 | T008, T014, T016, T021, T022, T024, T027, T028 |
| FR-004 | T016, T022 |
| FR-005 | T016, T018, T022, T023 |
| FR-006 | T018, T023, T029 |
| FR-007 | T016, T017, T022 |
| FR-008 | T018, T019, T020, T023, T025, T026 |
| FR-009 | T018, T023 |
| FR-010 | T028 |
| FR-011 | T034, T035, T040, T041 |
| FR-012 | T035, T037, T041, T042 |
| FR-013 | T001, T002, T032, T039, T044 |
| FR-014 | T031, T032, T035, T038, T042 |
| FR-015 | T030, T038, T044 |
| FR-016 | T032, T039, T060 |
| FR-017 | T034, T035, T040 |
| FR-018 | T036, T043 |
| FR-019 | T007, T013, T046, T049 |
| FR-020 | T047, T048, T050, T053 |
| FR-021 | T048, T051 |
| FR-022 | T046, T047, T049, T050 |
| FR-023 | T019, T024 |
| FR-024 | T019, T024, T040 |
| FR-025 | T064, T065, T066, T067, T070, T071, T072, T073, T075, T077, T078 |
| FR-026 | T064, T065, T066, T067 |
| FR-027 | T064, T065, T066, T067 |
| FR-028 | T065, T066, T068, T069 |
| FR-029 | T076, T077, T078, T079 |
| FR-030 | T080, T081, T083, T086 |
| FR-031 | T080, T082 |
| FR-032 | T080, T082 |
| FR-033 | T084, T085, T086 |
| FR-034 | T087, T088, T089, T091 |
| FR-035 | T090, T091, T092 |
| SC-001 | T016, T029, T058 |
| SC-002 | T059 |
| SC-003 | T044 |
| SC-004 | T035, T044 |
| SC-005 | T060 |
| SC-006 | T045 |
| SC-007 | T048, T053 |
