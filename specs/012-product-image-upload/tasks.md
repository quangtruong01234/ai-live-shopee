# Tasks: Đổi ảnh sản phẩm ngay trên trang điều khiển giữa phiên live

- **Feature ID:** `012-product-image-upload` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [contracts/scene-set.md](./contracts/scene-set.md),
  [quickstart.md](./quickstart.md) · ADR-071, ADR-072 (Chấp nhận 2026-11-20) · Không thêm thư viện.

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[GPU]**: cần GPU; chạy trên GPU laptop (ADR-023), không dùng RunPod; gom vào đợt GPU (xem cuối file)
- **[US#]**: thuộc user story nào. Phase Setup, Foundational và Hoàn thiện không gắn nhãn này.
- Agent làm chủ (plan, WORKFLOW §2b): ai-media cho `src/ai_live/scene/`; ai-orchestrator cho `src/ai_live/app/`, `director/`,
  `ops/readiness.py`; ai-brain cho `src/ai_live/products/`; ai-qa cho `tests/`.

## Phase 1: Setup

- [x] T001 [P] Thêm hàm sinh ảnh thử bằng Pillow (không commit ảnh) vào `tests/fixtures/scene_builder.py`: `image_bytes(fmt, size, alpha,
  color)` cho PNG/WebP/JPEG, PNG RGB không alpha, JPEG có EXIF xoay 90°, MPO hai khung, GIF và WebP động, PNG trong suốt hoàn toàn, PNG
  có < 1% điểm có alpha, PNG hỏng (cắt đôi), file văn bản đặt tên `.png`, ảnh 4100×300, thân > 10 MB; và `write_manifest(scene_dir,
  data)` ghi tay `uploads/images.json` (dùng cho SC-004 và các ca sổ hỏng)
- [x] T002 [P] Kiểm `.gitignore` đã chặn `assets/scenes/` (gồm `uploads/`) và `out/`; thêm dòng còn thiếu (ảnh tải lên là dữ liệu khách,
  hiến pháp ràng buộc 6)

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

### Test nền (viết trước, phải FAIL trước khi implement)

- [x] T003 [P] Test kiểm và chuẩn hóa ảnh trong `tests/unit/test_scene_uploads.py` (research R2, contracts/api.md §6): mỗi file sai của T001
  trả đúng mã (`too_large`, `bad_image`, `bad_format`, `too_big`, `animated`, `empty`) kèm câu tiếng Việt đúng bảng §6, theo thứ tự kiểm
  R2; JPEG/PNG RGB thành RGBA đặc với `has_alpha=false`; EXIF xoay đúng chiều; MPO dùng khung đầu; cắt theo vùng alpha và cạnh dài
  ≤ 1280 px; `version_id` = 12 ký tự hex đầu SHA-256 của PNG đã chuẩn hóa, cùng ảnh cho cùng id (FR-002, FR-003, FR-004, SC-004)
- [x] T004 Test mã định danh và sổ ảnh trong `tests/unit/test_scene_uploads.py` (sau T003, cùng file): `product_id`/`version_id` sai dạng
  (contracts/scene-set.md §1) → lỗi `bad_id` trước khi ghép đường dẫn, đường dẫn luôn nằm trong `uploads/`; `ProductImageStore` lưu phiên
  bản (`reused=true` khi trùng, không nhân bản file), tạo `uploads/` và `images.json` `schema_version` 1 với `customer_id` khi tải lần đầu,
  đọc lại sổ sau khi tạo store mới (FR-012); ghi sổ qua file tạm + `os.replace`, giả lỗi `os.replace` thì sổ trong bộ nhớ và trên đĩa giữ
  như cũ và báo `save_failed` (FR-011)
- [x] T005 [P] Test luật nạp ảnh tải lên trong `tests/unit/test_scene_loader_uploads.py` theo bảng contracts/scene-set.md §3: không có
  `uploads/` thì y như 009; mục `"kit"`; `"<vid>"` có `rights_confirmed_at` → ảnh từ `uploads/`, không đòi `provenance.json` hay ảnh gốc,
  `ProductArt.source="upload"` và `version_id`; thiếu `rights_confirmed_at` → `error missing_confirmation`, không vẽ ảnh (SC-003); file
  thiếu/hỏng/không có trong `versions` → `error bad_uploads`, không vẽ ảnh; `null` → `warning missing_image`; file `products/` của sản phẩm
  sổ đang quản không vẽ, không báo `orphan_image`; JSON hỏng hay `schema_version` ≠ 1 → `bad_uploads`, bỏ cả sổ; `customer_id` khác →
  `customer_mismatch`, bộ cảnh không dùng được (FR-007); thư mục `uploads/<id>/` của sản phẩm ngoài catalog bị bỏ qua (FR-005, FR-014)
- [x] T006 [P] Test `SceneController.reload()` và `preview()` trong `tests/unit/test_scene_controller.py` (research R4, R5): `reload()` chỉ
  trả khi một lần vẽ **bắt đầu sau lời gọi** đã xong và trả `version` mới; hai lần gọi sát nhau dồn vào một lần nạp lại và cả hai thấy sổ
  mới nhất; `preview()` trả PNG với ảnh ứng viên của một sản phẩm ở đúng ô `compute_layout` của live, giữ sản phẩm đang nổi, không đổi
  `version`, `_base` hay lớp gửi cho renderer giả; log `scene_preview` có `render_ms`

### Implement nền

- [x] T007 [P] Thêm `ProductArt.source: Literal["kit", "upload"] = "kit"`, `ProductArt.version_id: str | None = None` và hai mã lỗi
  `missing_confirmation`, `bad_uploads` (mức `error`, không vào `WARNING_CODES`) trong `src/ai_live/scene/models.py` (data-model §3)
- [x] T008 Viết hằng số và hàm kiểm ảnh trong `src/ai_live/scene/uploads.py` (MỚI): regex `PRODUCT_ID_RE`, `VERSION_ID_RE`, hàm đường dẫn
  có kiểm nằm trong `uploads/`; `UploadRejected(code, message)`; `validate_and_normalize(data: bytes) -> NormalizedImage` theo 8 bước R2,
  dùng lại `MAX_IMAGE_BYTES`, `MAX_IMAGE_SIDE` của 009, `UPLOAD_MAX_SIDE = 1280`, `EMPTY_ALPHA_RATIO = 0.01` (làm T003 xanh)
- [x] T009 Viết `ProductImageStore` trong `src/ai_live/scene/uploads.py` (sau T008): đọc/ghi `images.json` (data-model §2) trong luồng phụ,
  `asyncio.Lock`, ghi nguyên tử + khôi phục bản trong bộ nhớ khi lỗi, `save_version(pid, image, source_name)` (ghi PNG qua file tạm,
  `reused`), `entry(pid)`, `customer_id` từ `CUSTOMER_ID` (làm T004 xanh)
- [x] T010 Đọc `uploads/images.json` trong `load_scene_set` của `src/ai_live/scene/loader.py` theo bảng contracts/scene-set.md §3 (dùng
  lại `_load_art` để cắt alpha và thu ≤ 640 px; bỏ kiểm provenance và `orphan_image` cho sản phẩm sổ đang quản) (làm T005 xanh)
- [x] T011 Thêm `reload()` (đếm thế hệ vẽ, trả `version`) và `preview(catalog, overrides, highlight) -> bytes` (bản sao `SceneSet` qua
  `dataclasses.replace`, `compute_layout` → `render_base` → `compose_still` trong luồng phụ, log `scene_preview`) vào
  `src/ai_live/scene/controller.py`; log `scene_loaded` thêm `uploads` (số ảnh tải lên đang dùng) (làm T006 xanh)
- [x] T012 Thêm `images: ProductImageStore` vào `AppContext` trong `src/ai_live/app/context.py` và tạo nó trong `src/ai_live/app/main.py`
  từ `SCENE_DIR`, `CUSTOMER_ID` (tạo cả khi `SCENE_ENABLED=false`, để trang vẫn xem và chuẩn bị ảnh)

**Checkpoint:** nền tảng sẵn sàng: `uv run pytest tests/unit/test_scene_uploads.py tests/unit/test_scene_loader_uploads.py
tests/unit/test_scene_controller.py` xanh, mọi test 009 cũ vẫn xanh.

---

## Phase 3: User Story 1: Thay ảnh một sản phẩm đang bày trên bàn giữa phiên (P1) 🎯 MVP

**Mục tiêu:** chọn món, tải ảnh, xem trước cạnh ảnh live, tích xác nhận quyền dùng, "Áp dụng" → ảnh lên khung hình ≤ 2 s, show không dừng,
ảnh còn sau khi mở lại phiên.
**Kiểm thử độc lập:** show kịch bản với file demo 3 sản phẩm, thay ảnh một món giữa show; kiểm khung hình, thời gian, show không dừng,
mở lại phiên vẫn dùng ảnh mới (spec US1).

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [x] T013 [P] [US1] Test áp ảnh ở sổ trong `tests/unit/test_scene_uploads.py`: `apply(pid, vid, confirmed_at)` đẩy `active` cũ vào
  `history`, ghi `applied_at` và `rights_confirmed_at`, áp lại đúng `vid` đang dùng chỉ cập nhật thời điểm, `vid` không có trong `versions`
  → lỗi `unknown_version` (data-model §2 "Chuyển trạng thái")
- [x] T014 [P] [US1] Test đọc và tải ảnh trong `tests/integration/test_image_api.py` (MỚI): `GET /api/scene/images` theo thứ tự catalog live
  với `state`, `thumb_url`, `can_revert`, `issues` (FR-001), chạy được khi cảnh tắt; `POST /api/scene/uploads` trả 201 với `reused`,
  `has_alpha`, cảnh báo `has_background` cho JPEG (FR-004), mỗi file sai của T001 trả đúng HTTP + mã + câu tiếng Việt, không ghi file,
  log `scene_image_rejected` (FR-003, SC-004); `unknown_product` 404, `bad_id` 400, `customer_mismatch` 409 (FR-007);
  `GET .../versions/{vid}.png` có `Cache-Control: immutable`; `GET .../kit.png`; tải lên không đổi live (lớp gửi renderer giữ nguyên)
- [x] T015 [US1] Test xem trước và áp dụng trong `tests/integration/test_image_api.py` (sau T014): `GET /api/scene/preview.png` 200
  `no-store`, không đổi `scene_version` (FR-008), 409 `scene_disabled` / `scene_unusable`, 404 `unknown_version`; `apply` không có
  `rights_confirmed=true` → 422 `rights_not_confirmed`, sổ và live không đổi (FR-006, SC-003); `apply` hợp lệ → 200 có `to_frame_ms`
  < 2000, renderer giả nhận lớp `base` mới, sự kiện bus `scene` `image_changed`, log `scene_image_changed` đủ trường data-model §9
  (FR-009, FR-019); với renderer ảnh tĩnh (`AVATAR_MODE=static`) `/api/scene/still.png` đổi theo ảnh mới
  (FR-009, edge case ảnh tĩnh); hai `apply` gửi sát nhau (`asyncio.gather`) → ảnh của lần sau thắng, sổ và live khớp nhau (edge case);
  áp giữa show kịch bản giả thì show vẫn `running` và câu vẫn phát tiếp (FR-010); sản phẩm đang nổi vẫn nổi với ảnh mới
  (kịch bản 6); giả lỗi ghi sổ → 500 `save_failed`, live giữ ảnh cũ (FR-011); khởi động lại app với cùng `SCENE_DIR` → `/api/scene` vẫn
  báo `source="upload"` và đúng `version_id` (FR-012, kịch bản 7)
- [x] T016 [P] [US1] Test `check_scene` trong `tests/unit/test_readiness.py`: issue `missing_confirmation` hay `bad_uploads` → mục "Cảnh
  live" mức LỖI; các issue `error` khác của bộ cảnh giữ mức CẢNH BÁO như 009/007 (FR-019, contracts/scene-set.md §4)
- [x] T017 [P] [US1] Test lệnh `python -m ai_live.scene check` trong `tests/unit/test_scene_loader_uploads.py` (sau T005, cùng file): bộ cảnh
  có ảnh tải lên đã xác nhận thì không báo thiếu `provenance.json` cho món đó và in dòng `Ảnh tải lên: N đang dùng, M thiếu xác nhận, K đã
  gỡ`; thiếu xác nhận thì mã thoát 1 (FR-005, contracts/scene-set.md §5)
- [x] T018 [P] [US1] Test khối "Ảnh sản phẩm" của trang điều khiển trong `tests/integration/test_control_page.py` (MỚI, kiểu
  `test_show_api.py` đọc `/static/control.html`): có danh sách ảnh, ô chọn file nhận `image/png,image/webp,image/jpeg`, ô xác nhận quyền dùng
  với câu FR-006, nút "Xem trước", ảnh xem trước đặt cạnh ảnh live `/api/scene/still.png`, nút "Áp dụng"

### Implement US1

- [x] T019 [US1] Thêm `ProductImageStore.apply(pid, vid, confirmed_at)` trong `src/ai_live/scene/uploads.py` (làm T013 xanh)
- [x] T020 [US1] Thêm `source` và `version_id` vào mỗi mục `images` của `SceneController.status()` trong `src/ai_live/scene/controller.py`
  (contracts/api.md §4)
- [x] T021 [US1] Thêm route `GET /api/scene/images` (dựng `ProductImageStatus` data-model §4 từ catalog live, sổ và issue của bộ cảnh, kèm
  `uploads_bytes`), `GET /api/scene/images/{pid}/versions/{vid}.png`, `GET /api/scene/images/{pid}/kit.png` trong
  `src/ai_live/app/routes.py`
- [x] T022 [US1] Thêm route `POST /api/scene/uploads?product_id=` trong `src/ai_live/app/routes.py`: thân thô + `X-Filename` (research R3),
  dừng đọc khi quá 10 MB, kiểm `pid` trong catalog live (bộ chuẩn bị thêm ở US2), `customer_mismatch`, gọi `validate_and_normalize` và
  `save_version` trong luồng phụ, log `scene_image_uploaded` / `scene_image_rejected` (không log tên file ở mức INFO) (làm T014 xanh)
- [x] T023 [US1] Thêm route `GET /api/scene/preview.png` (`target=live`) và `POST /api/scene/images/{pid}/apply` trong
  `src/ai_live/app/routes.py`: kiểm `rights_confirmed`, `unknown_product`, `customer_mismatch`; `store.apply` → `scene.reload()`; trả
  `to_frame_ms` tính từ lúc nhận request (null khi cảnh tắt); phát bus `scene` `image_changed`; log `scene_image_changed` (làm T015 xanh)
- [x] T024 [P] [US1] Đưa `missing_confirmation` và `bad_uploads` lên mức LỖI trong `check_scene` của `src/ai_live/ops/readiness.py`
  (làm T016 xanh)
- [x] T025 [P] [US1] In dòng tóm tắt ảnh tải lên trong `src/ai_live/scene/__main__.py` (làm T017 xanh)
- [x] T026 [US1] Thêm khối "Ảnh sản phẩm" vào `src/ai_live/app/static/control.html` và kiểu trong `src/ai_live/app/static/style.css`:
  danh sách món (ảnh nhỏ, trạng thái "ảnh bộ cảnh / ảnh tải lên / đã gỡ / chưa có ảnh"), ô chọn file, cảnh báo "ảnh còn nền", ô xác nhận
  quyền dùng, ảnh xem trước cạnh ảnh live, nút "Xem trước", "Áp dụng", vùng báo lỗi; câu "cảnh đang tắt, ảnh chưa hiện trên live" khi
  cảnh tắt (làm T018 xanh)
- [x] T027 [US1] Viết hành vi khối "Ảnh sản phẩm" trong `src/ai_live/app/static/control.js`: tải `GET /api/scene/images`, gửi file bằng
  `fetch(..., {body: file})` với `X-Filename`, hiện câu lỗi tiếng Việt của API, khóa "Áp dụng" khi chưa tích xác nhận, bấm "Xem trước" nạp
  `preview.png`, "Áp dụng" gọi `apply` rồi làm mới ảnh live; tải lại danh sách khi nhận `scene` `image_changed` qua `/ws/control` (hai tab); đang xem trước món nào mà món đó đổi ảnh
  hay catalog đổi thì hủy xem trước kèm câu báo (edge case)

**Checkpoint:** US1 chạy và test độc lập được: test T013–T018 xanh, chạy quickstart §1, §2, §6 (không GPU). Dừng lại, báo người dùng, demo.

---

## Phase 4: User Story 2: Đổi bộ sản phẩm nhanh: nạp file mới rồi gán ảnh cho món mới (P2)

**Mục tiêu:** chuẩn bị file nội dung mới và ảnh cho từng món mà live không đổi; "Áp dụng bộ mới" đổi thẻ và ảnh trong một lần ≤ 2 s, không
khung hình trộn; hủy chuẩn bị không mất ảnh; ảnh cũ được dùng lại.
**Kiểm thử độc lập:** đang show file demo, chuẩn bị file 3 món chưa có ảnh, gán ảnh cả 3 (live không đổi), áp bộ mới; kiểm khung hình
đổi một lần, giữ khi mở lại phiên, dùng lại ảnh khi nạp lại file cũ (spec US2).

### Test cho US2 (viết trước, phải FAIL trước khi implement)

- [x] T028 [P] [US2] Test `StagedSet` trong `tests/unit/test_staging.py` (MỚI, data-model §6): trạng thái ảnh mỗi món theo ưu tiên
  `staged` > `reused_upload` (kể cả món không có trong catalog live, FR-014) > `reused_kit` > `removed` > `missing`; gán cần xác nhận quyền
  dùng; món không có trong bộ → `unknown_product`; `staged_id` lệch → `staging_changed`; `missing` gồm cả `removed`; `live_changed` khi
  `catalog.version` live khác lúc tạo; gán chỉ thắng khi `assigned_at` mới hơn `updated_at` của món trong sổ
- [x] T029 [P] [US2] Test áp nhiều ảnh một lần ở sổ trong `tests/unit/test_scene_uploads.py`: `apply_many(assignments)` ghi mọi gán trong
  **một** lần ghi sổ, lỗi ghi thì không gán nào được ghi
- [x] T030 [P] [US2] Test `SceneController.hold()` trong `tests/unit/test_scene_controller.py`: trong lúc giữ khóa không lần vẽ nào chạy
  (kể cả do phụ đề), vào khóa chờ lần vẽ đang chạy xong, thả khóa rồi `reload()` vẽ đúng một lần với catalog và sổ mới
- [x] T031 [P] [US2] Test tạo, xem, gán, hủy bộ chuẩn bị trong `tests/integration/test_staging_api.py` (MỚI): `POST /api/content/staging`
  với file 3 món trả danh sách trong < 2 s, catalog live và lớp gửi renderer không đổi (FR-013); file lỗi trả cùng mã như `PUT /api/content`;
  tạo lần hai thay bộ cũ; `GET` / `DELETE` (204, 404 `no_staging`), hủy xong ảnh đã tải vẫn trong sổ (FR-015a); tải ảnh cho món chỉ có
  trong bộ chuẩn bị qua `POST /api/scene/uploads` rồi gán (422 `rights_not_confirmed`, 404 `unknown_version`, 409 `staging_changed`);
  món có ảnh trong sổ từ trước tự `reused_upload` / `reused_kit` (FR-014, kịch bản 2); `preview.png?target=staging`; `PUT /api/content`
  giữa lúc chuẩn bị → `live_changed: true`; `/api/state` có khối `staging`
- [x] T032 [US2] Test áp bộ mới trong `tests/integration/test_staging_api.py` (sau T031): còn món thiếu ảnh mà không `confirm_missing` →
  409 `missing_images` kèm tên món, không đổi gì (kịch bản 4); `confirm_missing=true` → 200 với `version`, `products`, `images_written`,
  `missing_images`, `to_frame_ms` < 2000; ghi lại mọi lớp `base` gửi renderer giả cùng catalog và ảnh của lần vẽ: không lớp nào có thẻ của
  bộ mới với ảnh của bộ cũ (FR-015, SC-006 phần logic); `director.on_catalog_replaced` được gọi; bộ chuẩn bị bị bỏ, sự kiện `scene`
  `staging` `applied`, log `scene_staging_applied`; giả lỗi ghi sổ → 500, live giữ bộ cũ, bộ chuẩn bị giữ nguyên; giả lỗi `install` → sổ
  về bản cũ; khởi động lại app → ảnh các món mới vẫn còn (kịch bản 3)
- [x] T033 [US2] Test khối "Chuẩn bị bộ mới" trong `tests/integration/test_control_page.py` (sau T018): có ô chọn file `.docx`, danh sách
  món với trạng thái ảnh, nút "Xem trước bộ mới", "Áp dụng bộ mới", "Hủy chuẩn bị", dòng báo "bộ đang live đã đổi"

### Implement US2

- [x] T034 [P] [US2] Viết `StagedSet`, `StagedAssignment` và `view()` (`StagedSetView` contracts/api.md §2) trong
  `src/ai_live/app/staging.py` (MỚI) (làm T028 xanh)
- [x] T035 [US2] Thêm `ProductImageStore.apply_many(assignments)` và hàm trả trạng thái ảnh đang dùng của một `pid` bất kỳ (cho
  `reused_upload` / `reused_kit` / `removed`) trong `src/ai_live/scene/uploads.py` (làm T029 xanh)
- [x] T036 [US2] Thêm `hold()` (async context manager quanh khóa mà `_work` giữ khi `_redraw`) vào `src/ai_live/scene/controller.py`
  (làm T030 xanh)
- [x] T037 [US2] Thêm `staging` vào `AppContext` và khối `staging` (`staged_id`, `source_name`, `missing`) vào `build_state` trong
  `src/ai_live/app/context.py`; khởi tạo trong `src/ai_live/app/main.py`
- [x] T038 [US2] Thêm route `POST`/`GET`/`DELETE /api/content/staging`, `POST /api/content/staging/images/{pid}` trong
  `src/ai_live/app/routes.py` (đọc file bằng `store.parse`, không `install`; giới hạn `CONTENT_MAX_BYTES`); cho `POST /api/scene/uploads`
  nhận cả `pid` của bộ chuẩn bị; `preview.png?target=staging`; phát bus `scene` `staging` (`created|updated|cancelled`) (làm T031 xanh)
- [x] T039 [US2] Thêm route `POST /api/content/staging/apply` trong `src/ai_live/app/routes.py` theo research R7: `missing_images` /
  `staging_changed` / `customer_mismatch`; `async with scene.hold()` → `apply_many` → `store.install` → `director.on_catalog_replaced` →
  thả khóa → `scene.reload()`; khôi phục sổ khi `install` lỗi; log `scene_staging_applied`, bus `staging` `applied` (làm T032 xanh)
- [x] T040 [US2] Thêm khối "Chuẩn bị bộ mới" vào `src/ai_live/app/static/control.html` và `src/ai_live/app/static/style.css` (làm T033 xanh)
- [x] T041 [US2] Viết hành vi bộ chuẩn bị trong `src/ai_live/app/static/control.js`: tải `.docx`, liệt kê món với "ảnh mới / dùng lại ảnh
  cũ / đã gỡ / thiếu ảnh", tải và gán ảnh từng món (dùng lại ô xác nhận và cảnh báo của US1), xem trước bộ mới, hỏi lại (nêu tên món thiếu
  ảnh) khi nhận 409 `missing_images` rồi gửi `confirm_missing`, "Hủy chuẩn bị" có hỏi lại, báo `live_changed`, mở lại trang thì lấy bộ
  chuẩn bị từ `/api/state`; tải lại khi nhận `scene` `staging`

**Checkpoint:** US2 chạy và test độc lập được: T028–T033 xanh, US1 vẫn xanh, chạy quickstart §4 (không GPU). Dừng lại, báo người dùng.

---

## Phase 5: User Story 4: Xem AI đang nói gì và dữ liệu sản phẩm đã nạp (P2)

**Mục tiêu:** danh sách "AI vừa nói" cập nhật ≤ 1 s, còn sau khi tải lại trang; xem nguyên văn dữ liệu một sản phẩm của bộ live hay bộ
chuẩn bị.
**Kiểm thử độc lập:** show kịch bản ảnh tĩnh với file demo 2 phút; so danh sách với nhật ký phiên; mở chi tiết từng sản phẩm so với file
(spec US4).

### Test cho US4 (viết trước, phải FAIL trước khi implement)

- [x] T042 [P] [US4] Test `SpokenLog` trong `tests/unit/test_spoken_log.py` (MỚI, data-model §7): chỉ nhận `sentence` có `segment_id`;
  `product_name` tra catalog lúc nhận (đổi catalog sau không đổi mục cũ); giữ tối đa 100, ≥ 50 câu gần nhất luôn có (FR-020); mới nhất
  trước; xóa khi show chuyển `running` từ `idle`/`ended`, giữ khi show `ended`; sự kiện `guard_blocked` không vào danh sách
- [x] T043 [P] [US4] Test khóa `topic` trong `tests/integration/test_script_runner.py`: mỗi sự kiện `sentence` của show kịch bản có `topic`
  bằng `segment.topic.value`, các khóa cũ giữ nguyên; câu bị guard chặn không phát `sentence` (FR-020)
- [x] T044 [P] [US4] Test `product_detail()` trong `tests/unit/test_docx_loader.py`: trả nguyên văn `id`, `name`, `is_primary`,
  `description`, `intro`, `price`, `variants`, `specs`, `faq`, `promotions`, `forbidden_claims` của sản phẩm trong file demo, không có
  `link` (FR-022, data-model §8)
- [x] T045 [P] [US4] Test API trong `tests/integration/test_api.py`: `GET /api/state` và tin `state` đầu của `/ws/control` có `spoken` (mới
  nhất trước) (FR-021); `/ws/control` chuyển `sentence` có `topic` tới trang (FR-020); `GET /api/content/products/{pid}` có `source="live"`,
  404 `unknown_product`; `GET /api/content/staging/products/{pid}` có `source="staging"`, 404 `no_staging` (FR-023, cần US2)
- [x] T046 [US4] Test SC-007 trong `tests/integration/test_show_api.py`: chạy show kịch bản giả, so `spoken` trong `/api/state` với các
  `sentence` có `segment_id` trong nhật ký phiên: đủ, đúng thứ tự, không câu nào có `guard_blocked`
- [x] T047 [US4] Test khối "AI vừa nói" và "Nội dung sản phẩm" trong `tests/integration/test_control_page.py` (sau T033): có danh sách câu
  (giờ, món, chủ đề), có bảng chi tiết sản phẩm, có nhãn "bộ chuẩn bị" khi xem món của bộ chuẩn bị

### Implement US4

- [x] T048 [P] [US4] Thêm khóa `topic` (`segment.topic.value`) vào payload sự kiện `sentence` trong
  `src/ai_live/director/script_runner.py` (làm T043 xanh)
- [x] T049 [P] [US4] Viết `product_detail(product) -> dict` trong `src/ai_live/products/models.py` (làm T044 xanh)
- [x] T050 [P] [US4] Viết `SpokenLog` (subscriber bus, `deque(maxlen=100)`, xóa theo `show_state`) trong `src/ai_live/app/spoken.py`
  (MỚI) (làm T042 xanh)
- [x] T051 [US4] Thêm `spoken` vào `AppContext` và `build_state` trong `src/ai_live/app/context.py`; khởi động và dừng `SpokenLog` trong
  `src/ai_live/app/main.py`
- [x] T052 [US4] Thêm route `GET /api/content/products/{pid}` và `GET /api/content/staging/products/{pid}` trong
  `src/ai_live/app/routes.py` (làm T045, T046 xanh)
- [x] T053 [US4] Thêm khối "AI vừa nói" và khung "Nội dung sản phẩm" vào `src/ai_live/app/static/control.html` và
  `src/ai_live/app/static/style.css` (làm T047 xanh)
- [x] T054 [US4] Viết hành vi trong `src/ai_live/app/static/control.js`: dựng "AI vừa nói" từ `spoken` của tin `state`, chèn đầu danh sách
  khi nhận `sentence` có `segment_id` (giờ, tên món, chủ đề bằng tiếng Việt), giữ ≤ 100 dòng; bấm tên món ở khối ảnh hay bộ chuẩn bị mở
  bảng chi tiết nguyên văn (ghi rõ "bộ chuẩn bị" khi `source="staging"`)

**Checkpoint:** US4 chạy và test độc lập được: T042–T047 xanh, chạy quickstart §5 (không GPU). Dừng lại, báo người dùng.

---

## Phase 6: User Story 3: Hoàn tác hoặc gỡ ảnh (P3)

**Mục tiêu:** "Về ảnh trước" và "Gỡ ảnh" (có hỏi lại) đổi live ≤ 2 s; xem lúc áp và lúc xác nhận quyền dùng.
**Kiểm thử độc lập:** thay ảnh một món 2 lần, hoàn tác 1 lần, gỡ ảnh; mỗi bước kiểm khung hình và thông tin ảnh (spec US3).

### Test cho US3 (viết trước, phải FAIL trước khi implement)

- [x] T055 [P] [US3] Test hoàn tác và gỡ ở sổ trong `tests/unit/test_scene_uploads.py`: `revert` lấy phần tử cuối `history` (vid / `null`
  / `"kit"`), cập nhật `applied_at` khi về vid, `history` rỗng → `nothing_to_revert`; `remove` đẩy `active` vào `history`, đặt `null`, đã
  gỡ → `already_removed`; `history` giữ tối đa 20 (data-model §2, FR-016, FR-017)
- [x] T056 [P] [US3] Test API trong `tests/integration/test_image_api.py`: áp A rồi B, `revert` → A rồi `"kit"` rồi 409 `nothing_to_revert`;
  `remove` không `confirm=true` → 422 `remove_not_confirmed`; `remove` → lớp `base` không còn ảnh món đó, thẻ vẫn có, 409
  `already_removed` lần hai; mỗi bước có `to_frame_ms` < 2000, sự kiện `image_changed` với `action` đúng, log `scene_image_changed`;
  `GET /api/scene/images` có `uploaded_at`, `applied_at`, `rights_confirmed_at`, `versions` cho phần chi tiết (FR-018)
- [x] T057 [US3] Test nút "Về ảnh trước", "Gỡ ảnh" và phần chi tiết ảnh trong `tests/integration/test_control_page.py` (sau T047)

### Implement US3

- [x] T058 [US3] Thêm `ProductImageStore.revert(pid)` và `remove(pid)` trong `src/ai_live/scene/uploads.py` (làm T055 xanh)
- [x] T059 [US3] Thêm route `POST /api/scene/images/{pid}/revert` và `POST /api/scene/images/{pid}/remove` trong
  `src/ai_live/app/routes.py`, cùng đường ghi sổ + `reload()` + bus + log của `apply` (làm T056 xanh)
- [x] T060 [US3] Thêm nút "Về ảnh trước", "Gỡ ảnh" và phần chi tiết (lúc tải, lúc áp, lúc xác nhận, danh sách phiên bản, tổng dung lượng
  `uploads/`) vào `src/ai_live/app/static/control.html`, `src/ai_live/app/static/style.css` (làm T057 xanh)
- [x] T061 [US3] Viết hành vi trong `src/ai_live/app/static/control.js`: khóa "Về ảnh trước" khi `can_revert=false`, "Gỡ ảnh" hỏi lại rồi
  gửi `confirm=true`, mở phần chi tiết ảnh của món

**Checkpoint:** US3 chạy và test độc lập được: T055–T057 xanh, chạy quickstart §3 (không GPU). Dừng lại, báo người dùng.

---

## Phase 7: Hoàn thiện và việc chung

- [x] T062 [P] Cập nhật `docs/ARCHITECTURE.md`: phần cảnh live ghi `uploads/` + `images.json`, `ProductImageStore`, bộ chuẩn bị, `reload()` /
  `hold()` / `preview()`, "AI vừa nói"; ghi rõ không đổi Protocol adapter nào
- [x] T063 [P] Cập nhật `docs/RUNBOOK.md`: cách thay ảnh giữa live, đổi bộ sản phẩm, hoàn tác/gỡ, dọn tay `uploads/` (contracts/scene-set.md
  §6), mục sự cố "ảnh không đổi" (xem `scene_image_changed`, readiness `missing_confirmation`)
- [x] T064 [P] Thêm ghi chú "bổ sung bởi 012, ADR-071" (không sửa nội dung cũ) ở đầu `specs/009-live-scene-layout/contracts/scene-set.md`
- [x] T065 Chạy quickstart §0–§6 không GPU từ đầu tới cuối, gồm bấm giờ SC-002 (thay một ảnh ≤ 30 s, §1 bước 9) và SC-005 (3 món mới
  ≤ 3 phút, §4 bước 7) và độ trễ SC-007 (câu mới hiện trên "AI vừa nói" ≤ 1 s, §5); ghi số vào `progress/LOG.md`. Đã chạy bằng máy (trình duyệt headless + API); bấm giờ tay SC-002/SC-005 do người dùng làm lúc duyệt (T069)
- [x] T066 `uv run pytest` và `uv run ruff check . && uv run ruff format --check .` đều sạch
- [~] T067 [GPU] Đo SC-001 theo quickstart §7 trên GPU laptop (`AVATAR_MODE=livetalking`): show 10 phút không đổi ảnh, rồi show 10 phút với 10
  lần áp/hoàn tác; `to_frame_ms` cả 10 lần ≤ 2000, show không dừng, lặng giữa câu p95 tăng ≤ 0,1 s; ghi số vào `progress/LOG.md`
- [~] T068 [GPU] Chụp ≥ 20 khung `/host` quanh các lần đổi theo quickstart §8 (ảnh 300×1600, 1600×300, ảnh còn nền; có lần áp bộ mới); script
  so vùng như 009 quickstart §8: nhãn AI, watermark, mặt host không bị che, không khung nào ghép ảnh món này với thẻ món khác (SC-006);
  lưu ảnh vào `out/012_review/frames/`
- [~] T069 Soạn gói duyệt cho người dùng theo quickstart §9 trong `out/012_review/README.md`: ảnh chụp trang điều khiển (khối ảnh, bộ chuẩn
  bị, "AI vừa nói", chi tiết sản phẩm), câu ô xác nhận quyền dùng, số đo T067, ảnh T068. Chờ người dùng xem. Đã soạn (13 ảnh/file US1–US4,
  câu xác nhận, số T065); còn thiếu số T067 và ảnh T068 (chờ GPU) và lượt xem của người dùng
- [ ] T070 Chạy `/update-context`

## Phụ thuộc và thứ tự

- Setup → Foundational → US1 (MVP) → US2 → US4 → US3 → Hoàn thiện. US4 có thể làm trước US2 trừ T045 phần
  `GET /api/content/staging/products/{pid}` (cần T038) và phần "bộ chuẩn bị" của T054.
- Trong mỗi story: test trước (phải FAIL), rồi `scene/` → `app/` (route, context) → trang điều khiển.
- `src/ai_live/scene/uploads.py`: T008 → T009 → T019 → T035 → T058 (cùng file, nối tiếp).
- `src/ai_live/scene/controller.py`: T011 → T020 → T036.
- Route ảnh và bộ chuẩn bị: T021 → T022 → T023 → T038 → T039 → T059. Lúc implement đặt ở file mới
  `src/ai_live/app/image_routes.py` (router riêng, `main.py` gắn sau `routes.router`) thay vì `src/ai_live/app/routes.py` để file đó khỏi
  phình; đường dẫn API không đổi. T052 (`GET /api/content/products/{pid}`) vẫn ở `routes.py` cạnh `PUT /api/content`.
- `src/ai_live/app/context.py` / `main.py`: T012 → T037 → T051.
- `control.html` / `style.css`: T026 → T040 → T053 → T060; `control.js`: T027 → T041 → T054 → T061.
- `tests/unit/test_scene_uploads.py`: T003 → T004 → T013 → T029 → T055. `tests/integration/test_image_api.py`: T014 → T015 → T056.
  `tests/integration/test_control_page.py`: T018 → T033 → T047 → T057.
- T067, T068 cần mọi story xong và fork chạy trên GPU laptop. T069 cần T065, T067, T068.

## Chạy song song

- Setup: T001, T002.
- Foundational: test T003, T005, T006 cùng lúc; T007 song song với các test.
- US1: test T013, T014, T016, T017, T018 cùng lúc; T024 (ops) và T025 (scene CLI) song song với route.
- US2: test T028, T029, T030, T031 cùng lúc; T034 (`app/staging.py`) song song với T035/T036.
- US4: test T042, T043, T044, T045 cùng lúc; T048 (director), T049 (products), T050 (`app/spoken.py`) cùng lúc.
- US3: T055, T056 cùng lúc.
- Hoàn thiện: T062, T063, T064 cùng lúc.
- Theo agent (`/sdd.dispatch`): ai-media làm `scene/` (T007–T011, T019, T020, T025, T035, T036, T058), ai-orchestrator làm `app/`,
  `director/`, `ops/` (T012, T021–T024, T026, T027, T034, T037–T041, T048, T050–T054, T059–T061), ai-brain làm T049, ai-qa làm các task test.

## Đợt GPU

- T067 (SC-001) và T068 (SC-006) chạy chung một buổi trên GPU laptop (ADR-023): bật fork bằng `powershell scripts/livetalking/run.ps1`,
  `AVATAR_MODE=livetalking`, rồi chạy app. Không dùng RunPod.
- Nếu `to_frame_ms` vượt 1 s: xem thời gian trong log `scene_loaded`, cân nhắc nhớ ảnh đã giải mã (research R5, rủi ro Q39); đó là việc mới,
  báo người dùng trước khi làm.

## Chiến lược MVP

1. Setup + Foundational (T001–T012) → 2. US1 (T013–T027) → **dừng, kiểm chứng (quickstart §1, §2, §6), demo** → 3. US2 → 4. US4 → 5. US3
   → 6. Hoàn thiện + đợt GPU.

## Bảng phủ yêu cầu

| Yêu cầu | Task |
|---------|------|
| FR-001 | T014, T021, T026, T027 |
| FR-002 | T003, T008, T022 |
| FR-003 | T003, T014, T022, T027 |
| FR-004 | T003, T014, T026 |
| FR-005 | T005, T010, T017, T025 |
| FR-006 | T005, T015, T018, T023, T026, T027 |
| FR-007 | T005, T014, T022, T023 |
| FR-008 | T006, T011, T015, T023, T027 |
| FR-009 | T006, T011, T015, T023, T067 |
| FR-010 | T015, T067 |
| FR-011 | T004, T009, T015 |
| FR-012 | T004, T015, T032 |
| FR-013 | T031, T038, T041 |
| FR-014 | T005, T028, T031, T035 |
| FR-015 | T029, T030, T032, T036, T039, T041 |
| FR-015a | T031, T038, T041 |
| FR-016 | T055, T056, T058, T059, T061 |
| FR-017 | T055, T056, T058, T059, T061 |
| FR-018 | T056, T060, T061 |
| FR-019 | T015, T016, T023, T024 |
| FR-020 | T042, T043, T045, T048, T050, T054 |
| FR-021 | T045, T051, T054 |
| FR-022 | T044, T045, T049, T052, T054 |
| FR-023 | T045, T047, T052, T054 |
| SC-001 | T067 |
| SC-002 | T065 |
| SC-003 | T005, T015 |
| SC-004 | T001, T003, T014 |
| SC-005 | T032, T065 |
| SC-006 | T032, T068 |
| SC-007 | T046, T065 |
