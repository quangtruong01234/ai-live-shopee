# Kế hoạch triển khai: Nền sau người dẫn giống phòng live của shop

- **Feature ID:** `014-live-host-background` · **Ngày:** 2026-11-24 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/014-live-host-background/spec.md` (Clarified 2026-11-23: bỏ kiểu làm mờ; demo chỉ cần kệ hàng; tên
  shop lấy từ file dữ liệu. Làm rõ lại 2026-11-24: bỏ bật/tắt nền khi đang live)

## Tóm tắt

Thay vùng phòng phía sau host trong khung live bằng nền của shop (demo: **kệ hàng** bày ảnh sản phẩm đã bỏ nền của chính shop), ở mọi khung
của đoạn lặp và theo dáng host từng khung. Mặt nạ người được **chuẩn bị một lần cho mỗi nhân vật** trên laptop (CPU), lưu theo dấu vân từng
khung; lúc live, fork LiveTalking **ghép nền ngay dưới người, sau khi dán miệng** và trước lớp cảnh 009/013, watermark, nhãn AI. App vẽ ảnh
nền một lần (Pillow) rồi gửi qua tin `scene_background`; kiểu nền chỉ chọn trước giờ live (không có công tắc khi live). Thiếu, hỏng hay không khớp thì hiện
phòng gốc kèm cảnh báo. Công cụ đo độ thật (013) đo thêm lọt phòng cũ, lệch sáng và độ mềm viền. Kiểu "bảng shop" / "ảnh shop" (US3, P4) để
sau demo; plan chỉ chừa chỗ.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, `.python-version`, ADR-020); fork chạy trong venv riêng `vendor/livetalking/.venv` (005).
- **Phụ thuộc chính:** app: Pillow, numpy (đã có); fork: numpy, OpenCV (`cv2.grabCut`, `cv2.boxFilter`, `cv2.copyTo`), mediapipe 1.2.3 (đã
  có trong venv fork từ ADR-053). · **Phụ thuộc MỚI cần duyệt:** **không có gói pip mới.** Chỉ có **một file model tuỳ chọn**:
  `selfie_multiclass_256x256.tflite` (MediaPipe Image Segmenter), dùng cho cách tách `mediapipe` khi cách mặc định `plate` không đạt
  SC-001/002. Tải chỉ sau khi **ADR-083** được duyệt và giấy phép được xác minh (research R3, RISKS L16).
- **Lưu trữ:** file trên đĩa: `assets/avatars/<id>/background/` (`manifest.json`, mặt nạ PNG theo dấu vân khung, `preview_frame.png`,
  `review.jpg`; data-model §2) và khối `background` trong `scene.json` (data-model §1). Không DB.
- **Kiểm thử:** pytest, không GPU: ảnh khung tổng hợp (người là hình elip trên phòng có kệ) cho bộ chuẩn bị, bộ ghép và đo lọt; renderer giả
  cài `BackgroundSink`; `TestClient` cho route; test fork chạy bằng python venv fork trên CPU. Phần cần GPU: chỉ kiểm thật trên fork chạy live
  (quickstart US1 bước 4–6, US2 bước 4).
- **Nơi chạy:** chuẩn bị mặt nạ: laptop CPU. Live: GPU laptop lip-sync (ADR-023); RunPod dự phòng, cần duyệt chi phí. `AVATAR_MODE=static`
  không có nền (rơi về `avatar_static`, R14).
- **Adapter liên quan:** `AvatarRenderer` (LiveTalking) thêm Protocol tuỳ chọn `BackgroundSink` (contracts/adapters.md); `ProductStore`
  không đổi trong US1 (US3 thêm `shop_name`).
- **Mục tiêu hiệu năng:** ghép nền ≤ 4 ms/khung trên fork (đo thử 0,18 ms với `cv2.copyTo` + trộn dải viền, research R8); fps giảm ≤ 10%
  (SC-003).
- **Ràng buộc khác:** nền nằm **dưới** người, không bao giờ che nhãn AI (lớp nhãn vẫn ghép sau cùng); kệ hàng không có chữ, giá, logo
  (FR-007, Hiến pháp III, ADR-065); mặt nạ là dữ liệu chuẩn bị, không phải video quay sẵn: miệng vẫn sinh thời gian thực (Điều I).

## Kiểm tra Constitution (cổng)

### Lượt 1 (trước Phase 0)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt | Khung vẫn sinh thời gian thực; nền ghép mỗi khung lúc phát. Nhãn AI ghép sau nền và sau cảnh. Nền thuộc bộ cảnh của một khách (FR-013) |
| II. Đồng ý và bảo mật | Đạt | Không dùng ảnh người mới. Ảnh shop (US3) phải xác nhận quyền như ảnh sản phẩm 012 (FR-009). Mặt nạ suy ra từ ảnh người mẫu đã đồng ý; lưu cạnh avatar, không commit (như `full_imgs`) |
| III. Trả lời có căn cứ | Đạt | Kệ hàng chỉ bày ảnh sản phẩm đã nạp, không chữ/giá/số lượng; không gợi tồn kho (RISKS Q46) |
| IV. Adapter trước | Đạt | Protocol tuỳ chọn `BackgroundSink` cạnh `SceneSink`; lõi pipeline không đổi |
| V. Test trước | Đạt | Test không GPU cho mọi logic; GPU laptop chỉ để kiểm cuối |
| VI. Ngân sách độ trễ | Đạt | Không chạm LLM/TTS; ghép nền ≤ 4 ms/khung trong khung 40 ms |
| VII. Đơn giản trước | Đạt có điều kiện | Không gói mới; model MediaPipe là tuỳ chọn và cần ADR-083 trước khi tải |
| VIII. Quan sát được | Đạt | Log khởi động/rơi về/lỗi, `stats.background_ms` (FR-015) |
| IX. Ngôn ngữ và tài liệu | Đạt | Tài liệu tiếng Việt; mã và comment tiếng Anh; chữ trên trang điều khiển tiếng Việt |

### Lượt 2 (sau Phase 1)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I | Đạt | Thứ tự ghép đã chốt (contracts/fork-protocol §4): paste_back → **nền** → cảnh → watermark → nhãn. Nền không có vùng cấm nhãn vì nằm dưới; nhãn vẫn trên cùng. Mặt nạ tra theo dấu vân khung, không thay khung |
| II | Đạt | Mặt nạ, `review.jpg`, `preview_frame.png` chứa ảnh người mẫu → nằm trong `assets/avatars/`, đã có trong `.gitignore` (dòng 41), không bị commit |
| III | Đạt | `render_backdrop` không vẽ chữ (test); chỉ dùng ảnh có trong dữ liệu sản phẩm đang nạp; đổi bộ sản phẩm (012) thì vẽ lại |
| IV | Đạt | `BackgroundSink` chỉ `LiveTalkingRenderer` cài; `StaticRenderer` không đổi; kiểm bằng `isinstance` |
| V | Đạt | research R16 liệt kê test; fork có test CPU trong `ailive_ext/tests/` |
| VI | Đạt | Bảng dưới; vẽ ảnh nền một lần trong `asyncio.to_thread`, gửi một tin lúc khởi động |
| VII | Đạt có điều kiện | Cách `plate` (không tải gì) là mặc định. `mediapipe` chỉ bật sau ADR-083 + xác minh giấy phép. Không thêm biến môi trường nào trừ `BACKGROUND_SEGMENTER_MODEL` (chỉ dùng cho `mediapipe`) |
| VIII | Đạt | contracts/events.md; lỗi fork gửi một lần, không lặp mỗi khung |
| IX | Đạt | Như lượt 1 |

Không có vi phạm cần biện minh.

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| LLM câu đầu / TTS chunk đầu | 1,5 s / 1,0 s | Không đổi | Log lượt như cũ (SC-004) |
| Lip-sync đến frame đầu | 0,8 s (laptop 0,92–1,16 s, ADR-023) | + thời gian ghép nền một khung: ≤ 4 ms (đo thử 0,18 ms) | `stats.background_ms` |
| Encode + mạng | 0,5 s | Không đổi | — |
| Tốc độ khung live | 25 fps (40 ms/khung) | ≤ 4 ms/khung; fps giảm ≤ 10% | fps trong `stats`, `style: ke_hang` vs `goc` (SC-003) |
| Khởi động fork | ngoài ngân sách lượt | + nạp ~81 mặt nạ PNG, tính dấu vân (~1 ms/khung) ≈ dưới 1 s | log fork lúc nạp avatar |
| Khởi động app | ngoài ngân sách lượt | + vẽ ảnh nền một lần trong luồng phụ | `scene_background_started.plate_ms` |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/014-live-host-background/
├── spec.md
├── plan.md            # file này
├── research.md        # R1–R16
├── data-model.md
├── contracts/
│   ├── fork-protocol.md
│   ├── adapters.md
│   ├── prepare-cli.md
│   ├── api.md
│   └── events.md
├── quickstart.md
└── tasks.md           # /sdd.tasks
```

### Mã nguồn
```
vendor/livetalking/ailive_ext/background.py            # load masks by frame fingerprint, apply(), stats (fork, ai-media)
vendor/livetalking/ailive_ext/background_prep.py       # one-time mask prep: plate/mediapipe, temporal, guided filter, desk ramp, leak
vendor/livetalking/ailive_ext/ingest.py                # hello.background, scene_background message, background_ms
vendor/livetalking/avatars/base_avatar.py              # one hook line before ailive_scene.apply (# ailive: 014)
vendor/livetalking/ailive_ext/tests/test_background.py
vendor/livetalking/ailive_ext/tests/test_background_prep.py
vendor/livetalking/ailive_ext/tests/bg_synth.py        # synthetic frames for fork tests (no images committed)
src/ai_live/core/protocols.py                          # BackgroundSink, ForkBackgroundStatus
src/ai_live/scene/models.py                            # BackgroundConfig on SceneSet
src/ai_live/scene/loader.py                            # "background" block, clamps, unknown-key warnings
src/ai_live/scene/backdrop.py                          # render_backdrop (ke_hang), no text
src/ai_live/scene/background.py                        # BackgroundController: status, preview
src/ai_live/avatar/livetalking_renderer.py             # BackgroundSink implementation
src/ai_live/avatar/switching_renderer.py               # forwards BackgroundSink to the active renderer
src/ai_live/avatar/__main__.py                         # background-prepare subcommand
src/ai_live/app/context.py, routes.py                  # wiring, /api/scene/background*
src/ai_live/app/static/control.html, control.js, style.css  # "Nền sau host" status row + preview
src/ai_live/ops/readiness.py                           # check_background
src/ai_live/ops/watchdog.py                            # background_failed/rejected banner (existing scene-error path)
.claude/skills/live-scene-realism/scripts/realism_report.py, REFERENCE.md   # US4 background metrics
tests/unit/test_scene_backdrop.py, test_scene_background_loader.py, test_background_controller.py
tests/unit/test_realism_background.py
tests/integration/test_background_routes.py, test_watchdog_show.py
```

Fork là repo git riêng (`vendor/livetalking`, commit cuối 477d4e4): sửa fork commit trong repo fork, như 005/009/011.

## Phase 0: Nghiên cứu → `research.md`

Đã xong: R1 nơi ghép (fork) · R2 mặt nạ chuẩn bị sẵn · R3 cách tách (`plate` mặc định, `mediapipe` tuỳ chọn, ADR-083) · R4 làm mượt theo
thời gian · R5 guided filter · R6 dốc mặt bàn · R7 dấu vân khung · R8 chi phí ghép · R9 giao thức app↔fork · R10 vẽ kệ hàng · R11 khớp ánh
sáng · R12 đo lọt · R13 xem trước không cần fork · R14 chế độ tĩnh · R15 US3 · R16 test.

## Phase 1: Thiết kế → `data-model.md`, `contracts/`, `quickstart.md`

Đã xong. Khác với `docs/ARCHITECTURE.md` §3: thêm Protocol tuỳ chọn `BackgroundSink` và tin fork `scene_background` / `hello.background`
(contracts/fork-protocol §6); cập nhật ARCHITECTURE ở `/update-context` sau implement. Ghi trong ADR-084.

## Phụ thuộc chờ duyệt

| Mục | Loại | Cần cho | Trạng thái |
|---|---|---|---|
| `selfie_multiclass_256x256.tflite` (MediaPipe; `TODO:` ghi cỡ và sha256 khi tải) | tải model | cách tách `mediapipe` (chỉ khi `plate` không đạt SC-001/002) | chờ ADR-083 + xác minh giấy phép (L16) |
| Gói pip mới | — | — | không có |

## ADR cần ghi

- **ADR-083 (Đề xuất):** Tách người cho nền sau host: mặt nạ chuẩn bị một lần mỗi nhân vật; cách mặc định `plate` (ảnh nền trung vị + hiệu +
  GrabCut, không tải gì); MediaPipe multiclass là cách dự phòng, chỉ tải sau khi xác minh giấy phép.
- **ADR-084 (Đề xuất):** Ghép nền trong fork, ngay dưới người, sau khi dán miệng; tin `scene_background` + khối `hello.background`; khối
  `background` trong `scene.json`; kiểu nền chọn trước giờ live, không bật/tắt khi live; thiếu/hỏng thì phòng gốc.

## Rủi ro mới

- **L16** giấy phép model MediaPipe multiclass chưa xác minh (nguồn chính thức vs bản đăng lại ghi khác nhau).
- **G17** ghép nền làm tụt fps trên laptop.
- **Q43** mặt nạ lọt phòng cũ / khoét mất tóc, vai khi host nghiêng đầu.
- **Q44** bóng mờ / nhấp nháy viền khi crossfade giữa clip.
- **Q45** mặt nạ cũ sau khi làm lại đoạn lặp (giảm nhờ dấu vân → `mismatch` → phòng gốc).
- **Q46** kệ hàng đầy sản phẩm gợi hiểu sai về tồn kho.

## Theo dõi độ phức tạp

Không có vi phạm.
