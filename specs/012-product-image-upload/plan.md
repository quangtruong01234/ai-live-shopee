# Kế hoạch triển khai: Đổi ảnh sản phẩm ngay trên trang điều khiển giữa phiên live

- **Feature ID:** `012-product-image-upload` · **Ngày:** 2026-11-20 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/012-product-image-upload/spec.md` (3 câu hỏi, 2026-11-20; 4 user story, FR-001–FR-023 kèm FR-015a, SC-001–SC-007)

## Tóm tắt

Ảnh sản phẩm đã được ghép vào khung hình lúc phát (009), nên đổi ảnh chỉ là: lưu ảnh mới vào bộ cảnh của khách, rồi cho
`SceneController` nạp lại bộ cảnh và vẽ lại lớp `base` (đường có sẵn khi nạp file nội dung, 009 FR-013). Không đụng fork, clip nhân vật
hay đường câu → tiếng. Phần mới: (1) **kho ảnh tải lên** trong bộ cảnh (`SCENE_DIR/uploads/`): mỗi lần tải là một phiên bản PNG đã chuẩn hóa
(xoay theo EXIF, đổi sang RGBA, thu ≤ 1280 px), một file `uploads/images.json` ghi ảnh nào đang dùng cho từng sản phẩm, lịch sử để hoàn
tác, lúc tải/áp/xác nhận; bộ nạp cảnh 009 ưu tiên ảnh trong `images.json` và coi lúc xác nhận quyền dùng là đủ thay cho `provenance.json`
(FR-005). (2) **Xem trước** vẽ cả khung hình tĩnh với ảnh ứng viên bằng đúng hàm vẽ của 009, không gửi đi đâu. (3) **Bộ chuẩn bị** giữ trong
bộ nhớ: file nội dung đã đọc nhưng chưa nạp + ảnh gán cho từng món; "Áp dụng bộ mới" ghi `images.json` và nạp catalog trong lúc cảnh đang giữ
khóa vẽ, nên chỉ có một lần vẽ với cả bộ mới. (4) **"AI vừa nói"** là vòng đệm 100 câu kịch bản (từ sự kiện `sentence`) đưa vào `/api/state`,
và chi tiết sản phẩm đọc nguyên văn từ catalog. Không phụ thuộc mới, không biến môi trường mới.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, `.python-version`, ADR-020)
- **Phụ thuộc chính:** FastAPI, Pillow (ADR-051), pydantic-settings · **Phụ thuộc MỚI cần duyệt:** không có. Tải ảnh dùng thân request
  thô như `PUT /api/content` (001 research R13), không cần `python-multipart` (research R3)
- **Lưu trữ:** file trong bộ cảnh của khách (`SCENE_DIR`, ngoài git): `uploads/images.json` (JSON, ghi nguyên tử bằng file tạm +
  `os.replace`) và `uploads/<product_id>/<version_id>.png`. Bộ chuẩn bị và "AI vừa nói" chỉ trong bộ nhớ của phiên
- **Kiểm thử:** pytest, không GPU: ảnh thử sinh bằng Pillow trong `tmp_path`, `SceneController` với renderer giả và fork giả
  (`tests/fixtures/fake_fork.py`), `TestClient` cho API; trang điều khiển kiểm bằng test HTML/JS hiện có (chuỗi, id phần tử). SC-001 và SC-006
  đo trên GPU laptop (ADR-023), có bước ở quickstart
- **Nơi chạy:** laptop `AVATAR_MODE=static` cho mọi logic; GPU laptop lip-sync cho SC-001, SC-006. Không RunPod
- **Adapter liên quan:** `ProductStore` (thêm dùng `parse` không `install` cho bộ chuẩn bị, đã có), `AvatarRenderer.set_scene_layer`
  (không đổi), bộ nạp cảnh 009 (`scene/loader.py`, đọc thêm `uploads/images.json`)
- **Mục tiêu hiệu năng:** ảnh lên khung hình gửi đi ≤ 2 s sau "Áp dụng" (FR-009; ước tính: ghi file + nạp lại bộ cảnh + vẽ `base` ≈ 0,1–0,5 s,
  research R5); xem trước ≤ 1 s; bộ chuẩn bị liệt kê sản phẩm ≤ 2 s (FR-013, đọc docx như hiện có); câu mới vào "AI vừa nói" ≤ 1 s (FR-020,
  qua `/ws/control` có sẵn); lặng p95 không tăng quá 0,1 s (SC-001)
- **Ràng buộc khác:** vùng cấm mặt/nhãn/watermark của 009 giữ nguyên (fork vẫn từ chối lớp chạm vùng cấm); ảnh không bao giờ rời máy;
  không có đường ghi ra ngoài `SCENE_DIR`; `product_id` và `version_id` kiểm bằng biểu thức chặt trước khi thành đường dẫn

## Kiểm tra Constitution (cổng)

**Lần 1 (trước Phase 0):**

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt | Ảnh tĩnh ghép lúc phát như 009, không video dựng sẵn; vùng cấm 009 giữ nguyên; ảnh chỉ vào bộ cảnh của đúng khách (`CUSTOMER_ID`, FR-007) |
| II. Đồng ý và bảo mật | Đạt | Ảnh là dữ liệu khách, nằm trong `SCENE_DIR` (đã gitignore); không ảnh người thật (ô xác nhận FR-006); không bí mật nào lên trang |
| III. Trả lời có căn cứ | Đạt, có ghi chú | Ảnh do khách cung cấp, người vận hành xác nhận; bỏ hồ sơ nguồn chi tiết (làm rõ 2026-11-20) làm yếu bằng chứng khi tranh chấp → rủi ro mới Q37. Thẻ tên/giá vẫn nguyên văn từ file; chi tiết sản phẩm hiện nguyên văn, không qua LLM |
| IV. Adapter trước | Đạt | Mở rộng bộ nạp cảnh và `SceneController` của 009, thêm route; không sửa lõi show, ReplyEngine, TTS hay renderer |
| V. Test trước | Đạt | Mọi FR có test không GPU; SC-001/SC-006 đo trên GPU laptop |
| VI. Ngân sách độ trễ | Đạt | Đổi ảnh không nằm trên đường câu → tiếng; vẽ trong luồng phụ như 009 (`scene_ms` trung vị 4,66 ms, SC-004 của 009) |
| VII. Đơn giản trước | Đạt | Không phụ thuộc, dịch vụ, CSDL hay biến môi trường mới; JSON + PNG trong thư mục có sẵn |
| VIII. Quan sát được | Đạt | Log `scene_image_changed` (thao tác, sản phẩm, kết quả, `to_frame_ms`), `scene_staging_applied`; kiểm trước demo báo ảnh thiếu xác nhận (FR-019) |
| IX. Ngôn ngữ và tài liệu | Đạt | Code/comment tiếng Anh; tài liệu, chữ trên trang, lỗi API tiếng Việt |

**Lần 2 (sau Phase 1):** giữ nguyên kết quả lần 1. Thiết kế không thêm phụ thuộc hay hạ tầng; thay đổi duy nhất với hợp đồng 009 là luật
nguồn gốc cho ảnh tải từ trang điều khiển (contracts/scene-set.md) → ADR-071 đề xuất; Điều III ghi chú như trên, có rủi ro Q37 theo dõi.
Không có vi phạm cần biện minh.

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| Câu kịch bản → tiếng → hình (câu đầu ≤ 5 s, lặng p95 ≤ 1,5 s) | không đổi | Không đụng đường này. Nạp lại bộ cảnh + vẽ `base` chạy trong luồng phụ, tranh CPU với VieNeu vài trăm ms mỗi lần đổi | SC-001: show 10 phút có 10 lần thay ảnh so với show không thay, cùng cấu hình (`ai_live.ops` báo cáo tổng duyệt) |
| Cảnh: đổi ảnh → khung hình gửi đi | ≤ 2 s (FR-009, mới) | Ghi `images.json` → `SceneController.reload()` → nạp bộ cảnh → vẽ `base` → `scene_layer` tới fork (khung kế tiếp) | `to_frame_ms` trong log `scene_image_changed` (tới lúc gửi lớp); quickstart US1 bấm giờ trên màn hình `/host` |
| Áp bộ mới | ≤ 2 s (FR-015) | Như trên + `store.install` + `on_catalog_replaced` (có sẵn) | log `scene_staging_applied.to_frame_ms` |
| Xem trước | ≤ 1 s (mục tiêu plan) | Vẽ khung tĩnh trong luồng phụ, không gửi fork | log `scene_preview.render_ms` |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/012-product-image-upload/
├── spec.md
├── plan.md          # file này
├── research.md      # R1–R12
├── data-model.md
├── contracts/
│   ├── api.md       # HTTP + sự kiện /ws/control mới
│   └── scene-set.md # phần thêm vào hợp đồng bộ cảnh 009 (uploads/)
├── quickstart.md
└── tasks.md         # /sdd.tasks
```

### Mã nguồn
```
src/ai_live/scene/uploads.py          # MỚI: kiểm + chuẩn hóa ảnh tải lên, ProductImageStore (images.json, phiên bản, áp/hoàn tác/gỡ)
src/ai_live/scene/loader.py           # đọc uploads/images.json: ảnh đang dùng, luật xác nhận thay provenance, không báo orphan
src/ai_live/scene/models.py           # mã lỗi mới (missing_confirmation, bad_uploads), ProductArt.source
src/ai_live/scene/controller.py       # reload() chờ vẽ xong, hold() giữ khóa vẽ khi áp bộ mới, preview()
src/ai_live/scene/__main__.py         # `check` in số ảnh tải lên / ảnh thiếu xác nhận
src/ai_live/app/staging.py            # MỚI: StagedSet (bộ chuẩn bị trong bộ nhớ)
src/ai_live/app/spoken.py             # MỚI: SpokenLog (vòng đệm "AI vừa nói")
src/ai_live/app/routes.py             # route ảnh, xem trước, bộ chuẩn bị, chi tiết sản phẩm
src/ai_live/app/context.py            # AppContext thêm images/staging/spoken; build_state thêm `spoken`, `staging` (ảnh từng món lấy qua `GET /api/scene/images`)
src/ai_live/app/main.py               # tạo và khởi động SpokenLog, ProductImageStore, StagedSet
src/ai_live/director/script_runner.py # sự kiện `sentence` thêm `topic` (khóa mới, không đổi khóa cũ)
src/ai_live/products/models.py        # product_detail(): dict nguyên văn, bỏ `link`
src/ai_live/ops/readiness.py          # check_scene: `missing_confirmation`, `bad_uploads` → LỖI
src/ai_live/app/static/control.html|js|css  # khung ảnh sản phẩm, xem trước, bộ chuẩn bị, "AI vừa nói", chi tiết sản phẩm
tests/unit/test_scene_uploads.py      # MỚI
tests/unit/test_scene_loader_uploads.py  # MỚI
tests/unit/test_staging.py, tests/unit/test_spoken_log.py  # MỚI
tests/unit/test_scene_controller.py, test_readiness.py, test_script_runner.py  # thêm ca
tests/integration/test_image_api.py   # MỚI: luồng US1–US3 qua API + fork giả
tests/integration/test_staging_api.py # MỚI: US2 (áp một lần, không khung hình trộn)
tests/integration/test_api.py, test_control_page.py (hoặc tương đương)  # US4
```

Phân việc theo agent: `ai-media` (scene/: uploads, loader, controller, models, `__main__`), `ai-orchestrator` (app/: routes, context,
staging, spoken, control page; `script_runner` thêm `topic`), `ai-brain` (`product_detail` trong products/), `ai-qa` (test liên khâu, bộ
file ảnh sai cho SC-004). Phần `readiness.py` (ops/) do ai-orchestrator.

## Phase 0: Nghiên cứu → [research.md](./research.md)

R1 nơi lưu ảnh (`uploads/` + `images.json`, không chép đè `products/`); R2 kiểm và chuẩn hóa ảnh (EXIF, MPO, ảnh động, gần trong suốt,
không nền); R3 cách tải (thân thô, không `python-multipart`); R4 xem trước; R5 áp ảnh và đo ≤ 2 s; R6 luật nguồn gốc mới (ADR-071); R7
áp bộ mới một lần (khóa vẽ); R8 hoàn tác/gỡ (ngăn xếp trạng thái, có "ảnh bộ cảnh 009"); R9 giữ phiên bản, không dọn tự động; R10 "AI vừa
nói"; R11 chi tiết sản phẩm; R12 khách và bảo mật đường dẫn.

## Phase 1: Thiết kế

- [data-model.md](./data-model.md): `UploadedImage`, `ImageManifest`/`ProductImageEntry`, `ImageState`, `PreviewRequest`, `StagedSet`,
  `SpokenSentence`, `ImageChange` (nhật ký), mã lỗi.
- [contracts/api.md](./contracts/api.md): 15 endpoint mới + thay đổi ở `/api/state`, `/api/scene` và sự kiện `sentence`, sự kiện `scene` mới
  (`image_changed`, `staging`), log JSONL.
- [contracts/scene-set.md](./contracts/scene-set.md): `uploads/` trong bộ cảnh, luật kiểm của `load_scene_set` và lệnh `check`.
- [quickstart.md](./quickstart.md): từng user story, bước nào cần GPU.

So với `docs/ARCHITECTURE.md` §3: không thêm hay đổi Protocol nào. `ProductStore.parse` đã có (001). Bộ nạp cảnh không phải adapter.
Khác biệt duy nhất là hợp đồng bộ cảnh 009 (ADR-071).

## ADR cần ghi

- **ADR-071 (Chấp nhận 2026-11-20):** ảnh tải từ trang điều khiển nằm ở `SCENE_DIR/uploads/` (PNG đã chuẩn hóa, mỗi lần tải một phiên bản) với
  `uploads/images.json` chọn ảnh đang dùng; bộ nạp cảnh ưu tiên `images.json` hơn `products/`, và với ảnh này thì lúc xác nhận quyền dùng
  thay cho mục `provenance.json` + ảnh gốc của 009 (`missing_confirmation` là lỗi). Ảnh không nền được nhận, chuyển sang RGBA đặc.
- **ADR-072 (Chấp nhận 2026-11-20):** "Áp dụng bộ mới" ghi `images.json` và nạp catalog trong lúc `SceneController` giữ khóa vẽ; bộ chuẩn bị chỉ ở
  bộ nhớ (mất khi tắt app, ảnh đã tải vẫn còn).

## Rủi ro mới

- **Q37** (ghi `docs/RISKS.md`): bỏ hồ sơ nguồn và ảnh gốc cho ảnh tải từ trang điều khiển; khi Shopee hay bên thứ ba khiếu nại logo/ảnh
  không có quyền (P14) chỉ còn file ảnh và lúc xác nhận. Giảm thiểu: giữ mọi phiên bản (R9), nhật ký đổi ảnh, ô xác nhận ghi rõ nội dung;
  TODO trước Shopee: có cần ghi lại người gửi ảnh không.
- **Q38**: người vận hành áp nhầm ảnh giữa live (nhầm món, ảnh còn logo, ảnh còn nền xấu); người xem thấy ngay. Giảm thiểu: xem trước cạnh
  ảnh live (FR-008), cảnh báo ảnh còn nền (FR-004), "Về ảnh trước" một thao tác ≤ 2 s (FR-016).
- **Q39**: nạp lại bộ cảnh đọc lại mọi ảnh; bộ cảnh 009 có ảnh lớn (tới 4000 px) làm mỗi lần đổi chậm và tranh CPU với VieNeu. Giảm thiểu:
  ảnh tải lên được thu ≤ 1280 px; đo `to_frame_ms` và lặng p95 (SC-001); nếu vượt thì nhớ ảnh đã giải mã theo (đường dẫn, mtime) (research R5).

## Theo dõi độ phức tạp

Không có vi phạm cần biện minh.
