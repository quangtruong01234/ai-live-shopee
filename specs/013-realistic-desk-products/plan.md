# Kế hoạch triển khai: Sản phẩm đứng trên bàn như đồ thật

- **Feature ID:** `013-realistic-desk-products` · **Ngày:** 2026-11-22 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/013-realistic-desk-products/spec.md` (làm rõ 2026-11-22: FR-013 nền phức tạp dùng model tách nền
  chạy trên máy; FR-019 mặc định không thẻ; bỏ FR-019a nhắc ghim vì không có người trực; 3 user story, FR-001–FR-024, SC-001–SC-007)

## Tóm tắt

Hiện nay (009) sản phẩm xếp thành hàng ở mép dưới khung, có thẻ tên/giá dưới từng món, món chính đứng giữa che tay host. Feature này thêm
**cách bày "như thật"** (`layout.mode = "realistic"` trong `scene.json`): món đứng hai bên tay host, đáy chạm mặt bàn, món sau nhỏ hơn và lùi
về sau, có bóng đổ mềm, mức sáng chỉnh đều theo bộ cảnh, mặc định không thẻ. Bố cục mới là một hàm cùng kiểu trả về `SceneLayout` của 009, nên
lớp `base`, `punch`, gửi lớp cho fork và luồng đổi món nổi giữ nguyên. Nhân vật khai thêm `hands_zone` cạnh `desk_top` đã có. Phần thứ hai là
**bỏ nền ảnh tải lên** (012): nền trơn bỏ bằng loang màu từ viền (Pillow + numpy, < 1 s); nền phức tạp chạy model tách nền IS-Net (ONNX,
`onnxruntime` đã có trong `uv.lock`) trong **tiến trình con ưu tiên thấp, 2 luồng**, để VieNeu không bị giật. Bản đã bỏ nền lưu thành **một
phiên bản ảnh mới** trong kho 012, nên áp dụng, hoàn tác, bộ chuẩn bị, xác nhận quyền dùng chạy không đổi. Hệ thống tự kiểm độ chắc của bản
bỏ nền và không bao giờ chọn sẵn bản lỗi. Không dịch vụ trả phí, ảnh không rời máy.

**Bổ sung 2026-11-23 (ADR-079, FR-025–FR-028, tasks Phase 7):** cách bày thứ ba `showcase` (`compute_showcase_layout`, cùng kiểu
`SceneLayout`): món chính to giữa khung trước host, món phụ phía sau che ≤ 40% (đổi bởi ADR-081: không món nào che món nào), được che tay (bỏ `hands_zone` khỏi vật cản và khỏi ánh sáng
làm nổi), không chạm vùng cấm 009. Bục trắng và sticker giá vẽ bằng Pillow, bật bằng `layout.riser`/`layout.sticker`. Cảnh báo ảnh nhỏ
`art_low_resolution` sau mọi cách bày trong `compute_scene_layout` và lúc tải ảnh; `ART_MAX_SIDE` nâng 640 → 960 px.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, `.python-version`, ADR-020)
- **Phụ thuộc chính:** Pillow (ADR-051), FastAPI, pydantic-settings
- **Phụ thuộc MỚI cần duyệt (ADR-074):**
  - Khai trực tiếp `onnxruntime>=1.31.1` và `numpy` trong `pyproject.toml`. Cả hai **đã có trong `uv.lock` và `.venv`** do `vieneu` kéo theo
    (ADR-024); không tải gói mới, chỉ biến phụ thuộc ngầm thành phụ thuộc khai báo (research R6).
  - **Tải model** `isnet-general-use.onnx` (khoảng 170 MB, TODO: ghi kích thước và sha256 khi tải) từ release rembg, md5
    `fc16ebd8b0c10d971d3513d564d01e29`, lưu ngoài git ở `models/matting/`. Chỉ tải sau khi người dùng duyệt ADR-074.
  - Biến môi trường mới: `MATTING_MODEL_PATH` (mặc định rỗng = tắt model, chỉ bỏ nền phẳng), `MATTING_DURING_SHOW` (mặc định `true`).
  - **Không** cài `rembg` (kéo OpenCV, scikit-image, scipy, pymatting; research R6).
- **Lưu trữ:** kho ảnh 012 trong bộ cảnh của khách (`SCENE_DIR/uploads/`, ngoài git): bản bỏ nền là một file `uploads/<pid>/<vid>.png` và một
  phiên bản trong `images.json` với trường mới `derived_from`, `bg_removal`, `cutout_version`. `scene.json` thêm khóa `layout.mode`,
  `layout.cards`, `layout.brightness`; `character.json` thêm `scene.hands_zone`. Model ở `models/matting/` (`.gitignore` đã có
  `models/`)
- **Kiểm thử:** pytest, không GPU: ảnh thử sinh bằng Pillow trong `tmp_path` (nền trắng, nền một màu, sản phẩm có phần trắng, nền nhiễu);
  model tách nền thay bằng **tiến trình con giả** (script trả mặt nạ cố định) và một test `@pytest.mark.matting_model` bị bỏ qua mặc định khi
  không có file model; `TestClient` cho API; renderer giả và fork giả như 012. SC-001, SC-002 duyệt bằng ảnh chụp; SC-003 đo trên bộ ≥ 20 ảnh;
  SC-005 đo trên GPU laptop
- **Nơi chạy:** laptop `AVATAR_MODE=static` cho mọi logic và ảnh chụp bố cục; GPU laptop lip-sync (`demo_host_02`, ADR-023) cho SC-001 và
  SC-005. Model tách nền chạy CPU. Không RunPod
- **Adapter liên quan:** không có Protocol mới hay đổi. `AvatarRenderer.set_scene_layer` không đổi. Mở rộng `scene/` (bố cục, vẽ, bộ nạp,
  kho ảnh 012) và `avatar/character.py` (đọc `hands_zone`)
- **Mục tiêu hiệu năng:**
  - Ghép khung: `scene_ms` trung vị và FPS gửi đi lệch ≤ 10% so với cách bày hàng (SC-005); bố cục mới chỉ tính lại khi đổi món nổi
  - Tải ảnh → xem trước bản bỏ nền: ≤ 5 s nền trơn, ≤ 20 s nền phức tạp (SC-006) (ước tính: nền phẳng < 0,5 s; model nạp 1–3 s + chạy vài
    giây ở 2 luồng; TODO đo)
  - Áp dụng bản bỏ nền lên khung ≤ 2 s (như 012 FR-009)
  - Bỏ nền giữa show: lặng p95 không tăng quá 0,1 s (SC-005 / FR-016)
- **Ràng buộc khác:** vùng cấm 009 (mặt, nhãn AI, watermark) giữ nguyên; vùng tay là vùng cấm của bố cục; bỏ nền chỉ đổi kênh alpha, không đổi
  màu/chữ/logo (FR-015); ảnh không rời máy; không dịch vụ trả phí (ràng buộc chi phí, memory "ask before paid services")

## Kiểm tra Constitution (cổng)

**Lần 1 (trước Phase 0):**

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt | Ảnh tĩnh ghép lúc phát như 009; không video dựng sẵn; nhãn AI và watermark vẫn là vùng cấm; bỏ nền làm trước lúc áp, không tạo nội dung dựng sẵn |
| II. Đồng ý và bảo mật | Đạt | Ảnh là dữ liệu khách, chỉ trong `SCENE_DIR`; model chạy trên máy, ảnh không gửi đi đâu (FR-013); không ảnh người |
| III. Trả lời có căn cứ | Đạt | Bỏ nền chỉ đổi alpha, kênh màu giữ nguyên (FR-015) nên không đổi chữ/giá/logo trên bao bì; chữ thẻ vẫn nguyên văn file (FR-020); chỉnh sáng nhân đều không đổi sắc độ (FR-006) |
| IV. Adapter trước | Đạt | Không sửa lõi show, ReplyEngine, TTS hay fork; bố cục mới là một hàm chọn theo `layout.mode`; model đặt bằng biến môi trường |
| V. Test trước | Đạt | Mọi FR có test không GPU; model thật thay bằng tiến trình con giả trong test mặc định |
| VI. Ngân sách độ trễ | Đạt, có ghi chú | Bỏ nền không nằm trên đường câu → tiếng, nhưng model tranh CPU với VieNeu → tiến trình con ưu tiên thấp, 2 luồng, một ảnh một lúc, công tắc `MATTING_DURING_SHOW` (R7); đo SC-005 |
| VII. Đơn giản trước | Đạt, cần duyệt | Không gói mới tải về; khai trực tiếp hai gói đã khóa + một file model → ADR-074 chờ duyệt. Chọn tự viết tiền/hậu xử lý thay vì `rembg` để tránh 5 gói nặng |
| VIII. Quan sát được | Đạt | Log `scene_bg_removed` (cách, kết quả, lý do, ms, model); log `scene_rendered` thêm `layout_mode`; kiểm trước demo thêm 5 cảnh báo (R10) |
| IX. Ngôn ngữ và tài liệu | Đạt | Code/comment tiếng Anh; tài liệu, lý do lỗi bỏ nền, chữ trên trang tiếng Việt |

**Lần 2 (sau Phase 1):** giữ nguyên kết quả lần 1. Thiết kế không đổi Protocol; hợp đồng bộ cảnh 009/012 chỉ thêm khóa tùy chọn (bộ cảnh cũ
chạy y như trước). Điều VI dựa vào cách ly tiến trình con, có phương án lùi `MATTING_DURING_SHOW=false` nếu SC-005 không đạt. Điều VII chờ
người dùng duyệt ADR-074 trước khi làm các task chạm `pyproject.toml` hay tải model; các task bố cục, bóng, thẻ và bỏ nền phẳng làm được
không cần ADR-074 (numpy hiện vẫn có qua `vieneu`; nếu ADR-074 bị từ chối, bỏ nền phẳng viết lại chỉ bằng Pillow). Không có vi phạm cần
biện minh.

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| Câu kịch bản → tiếng → hình (câu đầu ≤ 5 s, lặng p95 ≤ 1,5 s) | không đổi | Không đụng đường này. Model tách nền chạy tiến trình con ưu tiên thấp 2 luồng, có thể tranh CPU với VieNeu khi tải ảnh nền phức tạp giữa show | SC-005: show 10 phút có 3 lần tải ảnh nền phức tạp, so lặng p95 với show không tải (≤ +0,1 s); không đạt → `MATTING_DURING_SHOW=false` |
| Ghép cảnh mỗi khung (009: `scene_ms` trung vị 4,66 ms) | lệch ≤ 10% so với cách bày hàng (SC-005) | Lớp `base` vẽ nhiều lớp bóng/ánh sáng hơn nhưng chỉ vẽ lại khi đổi món nổi; ghép mỗi khung không đổi | `scene_ms` và FPS trong log 009, show cùng cấu hình hai cách bày |
| Tải ảnh → xem trước bản bỏ nền | ≤ 5 s nền trơn, ≤ 20 s nền phức tạp (SC-006, mới) | Thêm bước bỏ nền trong request tải lên (luồng phụ hoặc tiến trình con) | `scene_bg_removed.ms` + `scene_image_uploaded`; quickstart US2 bấm giờ |
| Áp dụng bản bỏ nền | ≤ 2 s (012 FR-009) | Không đổi: là áp một phiên bản 012 | `scene_image_changed.to_frame_ms` |
| Đổi món nổi | như 009 | Bố cục mới tính lại với `highlight_scale` 1,08 và (nếu `cards = one`) thẻ của món nổi | `scene_ms` khi đổi, test đơn vị thời gian bố cục |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/013-realistic-desk-products/
├── spec.md
├── plan.md          # file này
├── research.md      # R1–R10
├── data-model.md
├── contracts/
│   ├── scene-set.md # khóa mới trong scene.json, character.json, uploads/images.json
│   └── api.md       # thay đổi API tải ảnh, xem trước gỡ lỗi, log, CLI tách nền
├── quickstart.md
└── tasks.md         # /sdd.tasks
```

### Mã nguồn
```
src/ai_live/scene/matting.py          # MỚI: remove_flat_background, assess_cut, run_model (ISNet/BiRefNet tiền/hậu xử lý),
                                      #      remove_background() async (luồng phụ + tiến trình con), CLI `python -m ai_live.scene.matting`
src/ai_live/scene/layout.py           # compute_realistic_layout (chỗ đứng, khoảng đặt, thu nhỏ, chồng), đặt thẻ theo layout.cards
src/ai_live/scene/render.py           # bóng hai lớp, chỉnh sáng, ánh sáng làm nổi ấm, thứ tự vẽ xa→gần, chế độ thẻ, vẽ bàn khi không có bàn,
                                      #      draw_debug_zones thêm vạch mép bàn + vùng tay
src/ai_live/scene/models.py           # LayoutParams: mode, cards, brightness; FrameGeometry.hands_zone; mã cảnh báo mới
src/ai_live/scene/loader.py           # nhận layout.mode/cards/brightness, giới hạn highlight_scale theo mode, cards_ignored
src/ai_live/scene/controller.py       # chọn hàm bố cục theo mode, truyền hands_zone, xem trước debug, art_has_background
src/ai_live/scene/uploads.py          # phiên bản bỏ nền: derived_from, bg_removal, cutout_version; dùng lại bản cũ khi tải lại
src/ai_live/scene/__main__.py         # `preview`: đọc desk_top/hands_zone của nhân vật; `--debug-zones` vẽ thêm mép bàn, vùng tay
src/ai_live/avatar/character.py       # scene.hands_zone (kiểm 0–1, x1<x2, y1<y2)
assets/avatars/demo_host_02/character.json  # desk_top đo lại (~0,868), hands_zone đo
src/ai_live/app/image_routes.py       # POST /api/scene/uploads trả thêm bg_removal, cutout, recommended_version; preview.png?debug=1
src/ai_live/app/static/control.html|js|css  # "Đang bỏ nền…", hai ảnh cạnh nhau trên nền ô cờ, chọn bản dùng, lý do lỗi
src/ai_live/core/config.py, .env.example  # MATTING_MODEL_PATH, MATTING_DURING_SHOW
src/ai_live/ops/readiness.py          # hands_zone_missing, art_has_background, matting_model_missing, card_no_room, cards_ignored
pyproject.toml                        # onnxruntime, numpy trực tiếp (sau khi ADR-074 được duyệt)
tests/unit/test_scene_matting.py      # MỚI: nền phẳng, giữ màu, khoét trong lòng, assess_cut, tiến trình con giả, hết giờ, MATTING_DURING_SHOW
tests/unit/test_realistic_layout.py   # MỚI: hai bên tay, đáy trên mặt bàn, xa nhỏ/cao hơn, không chạm vùng cấm/tay, 1–5 món, quá rộng, chồng
tests/unit/test_scene_render.py, test_scene_loader.py, test_scene_uploads.py, test_character.py, test_readiness.py, test_config.py  # thêm ca
tests/integration/test_image_api.py   # US2 qua API: tải → bỏ nền → chọn → áp → hoàn tác
tests/fixtures/fake_matting.py        # MỚI: "model" giả cho tiến trình con (mặt nạ cố định / chậm / lỗi)
```

Phân việc theo agent: `ai-media` (scene/: matting, layout, render, models, loader, controller, uploads, `__main__`; `avatar/character.py`;
đo `desk_top`/`hands_zone` của `demo_host_02`), `ai-orchestrator` (`app/image_routes.py`, trang điều khiển, `core/config.py`,
`.env.example`, `ops/readiness.py`, `pyproject.toml` sau duyệt), `ai-qa` (test liên khâu, bộ ảnh SC-003, đo SC-005).

## Phase 0: Nghiên cứu → [research.md](./research.md)

R1 cách bày "như thật" (bảng 5 chỗ đứng hai bên tay, thu nhỏ, chồng, thứ tự vẽ); R2 vạch mép bàn + vùng tay khai trong `character.json`,
lớp gỡ lỗi; R3 bóng hai lớp, chỉnh sáng nhân đều (không đổi sắc độ), làm nổi ấm neo đáy; R4 chế độ thẻ `none|one|all` và vị trí thẻ "one";
R5 bỏ nền phẳng bằng loang từ viền; R6 model IS-Net qua `onnxruntime`, không `rembg`, giấy phép; R7 tiến trình con ưu tiên thấp;
R8 kiểm độ chắc; R9 bản bỏ nền là phiên bản 012; R10 cảnh báo và log.

## Phase 1: Thiết kế

- [data-model.md](./data-model.md): `LayoutParams` (mode, cards, brightness, `highlight_scale` theo mode), `CharacterScene.hands_zone`,
  `FrameGeometry.hands_zone`, `DeskStation`, `CutResult`, `BgRemoval`, phần thêm vào `UploadedImage`, chuyển trạng thái bỏ nền, mã cảnh báo.
- [contracts/scene-set.md](./contracts/scene-set.md): khóa mới trong `scene.json` và `character.json`, trường mới trong `uploads/images.json`.
- [contracts/api.md](./contracts/api.md): phản hồi `POST /api/scene/uploads` thêm `bg_removal`/`cutout`/`recommended_version`;
  `GET /api/scene/images` thêm trường phiên bản; `preview.png?debug=1`; log `scene_bg_removed`; CLI tiến trình con.
- [quickstart.md](./quickstart.md): từng user story, bước nào cần GPU.

So với `docs/ARCHITECTURE.md` §3: không thêm hay đổi Protocol nào. Bố cục, vẽ cảnh và tách nền là mã nội bộ của `scene/`, không phải adapter.
Model tách nền đặt bằng biến môi trường (Điều IV) nhưng không cần Protocol vì chỉ có một cách chạy (ONNX trong tiến trình con); nếu sau này có
cách thứ hai thì tách Protocol.

## ADR cần ghi

- **ADR-074 (Đề xuất 2026-11-22):** cách bày "như thật" (`layout.mode = realistic`, `hands_zone` trong `character.json`, mặc định không thẻ);
  bỏ nền ảnh tải lên: nền phẳng bằng loang màu từ viền, nền phức tạp bằng IS-Net ONNX chạy trên `onnxruntime` trong tiến trình con ưu tiên
  thấp; khai trực tiếp `onnxruntime` và `numpy` (đã khóa qua `vieneu`); tải `isnet-general-use.onnx` vào `models/matting/`; bản bỏ nền là một
  phiên bản ảnh 012. Loại: `rembg`, BRIA RMBG, dịch vụ trả phí, BiRefNet làm mặc định.

## Rủi ro mới

- **Q40**: model tách nền tranh CPU làm VieNeu chậm, gây lặng dài giữa show. Giảm thiểu: tiến trình con ưu tiên thấp, 2 luồng, một ảnh một
  lúc, hết giờ 60 s, `MATTING_DURING_SHOW=false` nếu SC-005 không đạt.
- **Q41**: bản bỏ nền khoét mất phần sản phẩm hoặc còn viền nền mà kiểm độ chắc không bắt được; người xem thấy sản phẩm bị cắt. Giảm thiểu:
  `assess_cut` chỉnh trên bộ ≥ 20 ảnh, xem trước hai ảnh cạnh nhau trên nền ô cờ, ảnh gốc luôn giữ, "Về ảnh trước" của 012.
- **Q42**: `desk_top`/`hands_zone` khai sai làm món che tay hoặc lơ lửng trên bàn. Giảm thiểu: lớp gỡ lỗi khi xem trước, cảnh báo
  `hands_zone_missing`, đo một lần khi làm nhân vật, ghi vào quickstart.
- **L15**: giấy phép trọng số IS-Net general-use (mã Apache-2.0, điều khoản bộ dữ liệu DIS5K chưa rõ), bản ONNX của rembg (MIT), BiRefNet_lite
  (thẻ ghi MIT, chưa đọc LICENSE). Hành động: đọc điều khoản DIS5K và LICENSE BiRefNet trước M2 (thu tiền).

## Theo dõi độ phức tạp

| Vi phạm / độ phức tạp thêm | Vì sao cần | Phương án đơn giản hơn bị loại vì |
|-----------------------------|------------|-----------------------------------|
| Tiến trình con cho model tách nền (thay vì gọi trong luồng phụ) | Hạ ưu tiên và giới hạn luồng riêng cho model, crash/thiếu RAM không kéo sập app đang live (FR-016) | Luồng phụ cùng tiến trình: onnxruntime ăn mọi lõi, không hạ ưu tiên riêng được, lỗi native làm sập app |
