# Kế hoạch triển khai: Bố cục cảnh live quanh AI host

- **Feature ID:** `009-live-scene-layout` · **Ngày:** 2026-11-13 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/009-live-scene-layout/spec.md`
- **Ghi chú quy trình:** người dùng giao toàn quyền chạy liên tục plan → tasks → analyze → implement (2026-11-13). Các quyết định dưới
  đây do mình tự chốt theo hướng tốt nhất; những gì cần mắt người được gom vào gói duyệt cuối (quickstart §9).

## Tóm tắt

Cảnh là các lớp ảnh RGBA (mặt bàn, ảnh sản phẩm, thẻ tên/giá, hiệu ứng làm nổi, phụ đề) do **app** vẽ bằng Pillow, chỉ vẽ lại khi trạng
thái đổi (nạp/thay file sản phẩm, đổi sản phẩm nổi, đổi phụ đề). Ở chế độ nhép miệng, app gửi các lớp này (PNG, đã cắt sát vùng có hình)
cho fork LiveTalking qua tin mới `scene_layer` trên `/ailive/ws`; fork trộn chúng vào **mọi khung** trong `process_frames`, sau bước
chuyển dần clip và **trước** watermark "LiveTalking" và nhãn "AI", nên hai thứ đó luôn nằm trên cùng. Ở chế độ ảnh tĩnh (kể cả khi tự về
ảnh tĩnh), app ghép ảnh tĩnh của nhân vật (cắt 9:16 như clip) với cùng các lớp thành một ảnh và trang host hiện ảnh đó. Sản phẩm nổi đổi
theo ack `playback_started` của câu kịch bản đầu phân đoạn (không theo lúc chuẩn bị), qua một Protocol nghe phát mới của renderer. Bộ
cảnh của khách nằm ngoài git (`SCENE_DIR`), có lệnh kiểm tra trước phiên. Tắt `SCENE_ENABLED` thì mọi thứ như cũ.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, ADR-020) cho app; venv riêng của fork cho phần `ailive_ext/scene.py`.
- **Phụ thuộc chính:** FastAPI, pydantic-settings, numpy (có sẵn), websockets (ADR-048) · **Phụ thuộc MỚI cần duyệt (ADR-051):**
  khai báo trực tiếp **Pillow** trong `pyproject.toml` của app. Pillow 12.3.0 đã nằm trong `uv.lock` (gói kéo theo), nên **không tải gì
  thêm**. Fork dùng `cv2` + numpy đã có trong venv fork. Không thêm model, không thêm font tải về (research R3).
- **Lưu trữ:** file trong `SCENE_DIR` (ngoài git): `scene.json`, `desk.png`, `products/<product_id>.png`, `originals/`,
  `provenance.json`. Không có DB.
- **Kiểm thử:** pytest app (không GPU, không fork thật: fork giả như 005), test fork trong venv fork (`ailive_ext/tests/test_scene.py`,
  khung giả). Ảnh dùng trong test được vẽ ngay trong test (không file nhị phân trong git).
- **Nơi chạy:** laptop. `AVATAR_MODE=static` cho mọi test logic và chụp màn hình đầu tiên; `AVATAR_MODE=livetalking` trên GPU laptop
  (ADR-023) để đo SC-004 và chụp màn hình có fork. Không cần RunPod.
- **Adapter liên quan:** `AvatarRenderer` (thêm Protocol tùy chọn `PlaybackListenerHost` và `SceneSink`), `ProductStore` (chỉ đọc).
  Không đổi `ReplyEngine`, `TTSEngine`, `CommentSource`, `CommentQueue`.
- **Mục tiêu hiệu năng:** trộn cảnh ở fork ≤ 3 ms/khung trên laptop (khung 480×832, ~40 ms/khung ở 25 fps); fps khi có cảnh không
  thấp hơn quá 10% (SC-004). Vẽ lại lớp ở app ≤ 150 ms, chạy trong thread (`asyncio.to_thread`), không chặn event loop. Đổi sản phẩm nổi
  hiện lên trong ≤ 1 s sau `playback_started` (SC-003): vẽ ~0,1 s + gửi ws + fork áp ở khung kế.
- **Ràng buộc khác:** ảnh và bộ cảnh là dữ liệu của khách, không vào git; ảnh sản phẩm không bao giờ do AI hay chương trình tạo cho khách
  thật (ràng buộc số 7, FR-002); ảnh mẫu cho thương hiệu giả "Mây Sáng" được đánh dấu `placeholder` và lệnh kiểm báo rõ.

## Kiểm tra Constitution (cổng)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt | Lớp ảnh tĩnh + chữ trộn mỗi khung lúc phát, không video/tiếng dựng sẵn. Fork trộn cảnh **trước** watermark và nhãn, và từ chối lớp có điểm ảnh nằm trong vùng nhãn, watermark hay mặt (R5). `scene.json` có `customer_id`, phải khớp `CUSTOMER_ID` |
| II. Đồng ý và bảo mật | Đạt | `assets/scenes/` vào `.gitignore`; `provenance.json` ghi nguồn từng ảnh; không thêm hình người nào |
| III. Trả lời có căn cứ | Đạt | Thẻ lấy nguyên văn tên, giá (`format_price` đã có), khuyến mãi đầu tiên từ `ProductCatalog` đang nạp; không có chữ số nào khác trên thẻ. Ảnh sản phẩm: chỉ ảnh thật đã chỉnh, lệnh kiểm đòi hồ sơ chỉnh sửa với danh sách thao tác cho phép |
| IV. Adapter trước | Đạt | Module mới `ai_live/scene/`; renderer chỉ thêm Protocol tùy chọn; bật bằng `SCENE_ENABLED`. Lõi show chỉ thêm `product_id` vào payload sự kiện `sentence` đã có |
| V. Test trước (GPU: laptop trước) | Đạt | Test bố cục, vẽ, controller, route, fork giả; test fork không GPU; GPU laptop chỉ cho đo SC-004 |
| VI. Ngân sách độ trễ | Đạt | Cảnh không nằm trên đường câu → tiếng. Chỉ tốn thời gian trộn mỗi khung ở fork (đo `scene_ms`, SC-004) |
| VII. Đơn giản trước | Đạt | Một phụ thuộc khai báo lại (đã có trong lock, ADR-051); không kéo thả bố cục, không animation, không model cắt nền |
| VIII. Quan sát được | Đạt | Sự kiện log `scene_rendered`, `scene_highlight`, `scene_rejected`; `scene_ms` trong `stats` của fork → bảng độ trễ; `GET /api/scene` và dòng trạng thái trên trang điều khiển |
| IX. Ngôn ngữ và tài liệu | Đạt | Code/comment tiếng Anh; chữ trên thẻ, thông báo lỗi, tài liệu tiếng Việt |

Kiểm lại sau Phase 1: vẫn Đạt cả 9 điều.

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| LLM → TTS → câu đầu | ≤ 5 s (kịch bản) | Không đổi (cảnh không nằm trên đường này) | Bảng độ trễ như cũ |
| Khoảng lặng giữa câu | p95 ≤ 1,5 s | Không đổi; SC-004 cho phép tăng tối đa 0,1 s | Show 10 phút có / không cảnh (quickstart §7) |
| Tạo hình mỗi khung ở fork | ~40 ms/khung (25 fps) | +trộn cảnh ≤ 3 ms/khung | `scene_ms` trong `stats`, `render_fps` |
| Đổi sản phẩm nổi | ≤ 1 s sau `playback_started` (SC-003) | Mới | Log `scene_highlight` (thời điểm ack, thời điểm gửi lớp) |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/009-live-scene-layout/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md · tasks.md
└── contracts/
    ├── scene-set.md        # scene.json, provenance.json, lệnh check
    ├── fork-protocol.md    # phần thêm vào giao thức 005: scene_layer, hello.scene, error scene_rejected, stats.scene_ms
    ├── api.md              # GET /api/scene, GET /api/scene/still.png, tin `scene` trên /ws/host, host-config
    └── adapters.md         # PlaybackListener, SceneSink, payload `sentence` thêm product_id
```

### Mã nguồn
```
src/ai_live/scene/__init__.py
src/ai_live/scene/models.py        # SceneSet, ProductArt, SceneIssue, FrameGeometry, SceneLayer, ProvenanceRecord
src/ai_live/scene/loader.py        # đọc + kiểm bộ cảnh (FR-003), không bao giờ ném lỗi cho phiên
src/ai_live/scene/layout.py        # chỗ trên bàn, vùng cấm, thẻ (thuần, không Pillow)
src/ai_live/scene/render.py        # vẽ lớp RGBA bằng Pillow, chữ tiếng Việt, ghép ảnh tĩnh
src/ai_live/scene/fonts.py         # tìm font (SCENE_FONT_PATH → font hệ thống)
src/ai_live/scene/controller.py    # SceneController: bus + playback → vẽ lại → fork / ảnh tĩnh
src/ai_live/scene/__main__.py      # `python -m ai_live.scene check|preview`
src/ai_live/core/config.py         # SCENE_ENABLED, SCENE_DIR, SCENE_SUBTITLES, SCENE_FONT_PATH
src/ai_live/core/protocols.py      # PlaybackListener, SceneSink
src/ai_live/core/models.py         # RenderTurnStats.scene_ms
src/ai_live/core/events.py         # EventType.SCENE
src/ai_live/director/script_runner.py   # payload `sentence` thêm product_id
src/ai_live/director/latency.py    # cột scene_ms
src/ai_live/avatar/static_renderer.py · switching_renderer.py · livetalking_renderer.py · factory.py
src/ai_live/app/main.py · context.py · routes.py · static/host.html · host.js · control.(html|js)
scripts/make_demo_scene.py         # vẽ bàn gỗ + ảnh MẪU có ghi "ẢNH MẪU" cho thương hiệu giả, ra assets/scenes/demo (ngoài git)
vendor/livetalking/ailive_ext/scene.py · ingest.py (scene_layer, hello) · avatars/base_avatar.py (móc `# ailive:`)
vendor/livetalking/ailive_ext/tests/test_scene.py
tests/unit/test_scene_layout.py · test_scene_render.py · test_scene_loader.py · test_scene_controller.py
tests/unit/test_playback_listener.py · tests/integration/test_scene_api.py · tests/integration/test_scene_fork.py
```

## Phase 0: Nghiên cứu → [research.md](./research.md)

R1 nơi trộn cảnh · R2 thư viện vẽ (Pillow) · R3 font tiếng Việt · R4 bố cục khung 480×832 · R5 vùng cấm và nơi kiểm · R6 thời điểm đổi
sản phẩm nổi · R7 ảnh tĩnh và về ảnh tĩnh · R8 cắt nền ảnh sản phẩm thật · R9 ảnh mẫu cho demo · R10 phụ đề trong khung · R11 chi phí
trộn mỗi khung · R12 đo và quan sát.

## Phase 1: Thiết kế

- [data-model.md](./data-model.md): `SceneSet`, `ProductArt`, `ProvenanceRecord`, `SceneIssue`, `FrameGeometry`, `Slot`, `CardText`,
  `SceneState`, `SceneLayer`.
- [contracts/](./contracts/): bốn file ở trên.
- [quickstart.md](./quickstart.md): tạo bộ cảnh mẫu, kiểm, xem trước, chạy static, chạy fork, đo SC-004, chụp SC-001, gói duyệt.

## ADR cần ghi

- **ADR-051:** Pillow khai báo trực tiếp để vẽ lớp cảnh và chữ tiếng Việt ở app; font lấy từ `SCENE_FONT_PATH` hoặc font hệ thống, không
  tải font. Sửa phần "Phương án đã loại: Pillow… chưa cần" của ADR-044 (nhãn "AI" vẫn vẽ bằng cv2 ở fork, không đổi).
- **ADR-052:** Cảnh ghép ở fork qua tin `scene_layer` (app vẽ, fork trộn trước watermark và nhãn, fork từ chối lớp chạm vùng cấm);
  ảnh tĩnh ghép ở app; bộ cảnh của khách ngoài git ở `SCENE_DIR`; sản phẩm nổi theo ack `playback_started`.

Cả hai ghi `Đã chốt (tự chốt theo ủy quyền của người dùng 2026-11-13, chờ xác nhận trong gói duyệt)`.

## Rủi ro mới

- **L12** license font: Segoe UI / Arial (font Windows) dùng để vẽ chữ vào luồng thương mại; DejaVu Sans (tự do) trên Linux/RunPod.
- **G16** trộn cảnh làm tụt fps trên GTX 1650 Ti (SC-004).
- **Q20** ảnh sản phẩm sau khi cắt nền bị mất/đổi chi tiết, hoặc ảnh mẫu lọt vào phiên khách thật (SC-007, ràng buộc số 7).
- **Q21** clip nền mới có mặt thấp hơn (face_bottom lớn) làm bàn không còn chỗ: fork từ chối lớp, cảnh biến mất.

## Theo dõi độ phức tạp

Không có vi phạm.
