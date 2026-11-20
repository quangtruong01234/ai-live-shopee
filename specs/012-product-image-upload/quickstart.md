# Quickstart: 012 Tải và thay ảnh sản phẩm trên trang điều khiển

> Chạy trên laptop dev. Bước 0–6 **không cần GPU** (`AVATAR_MODE=static`). Bước 7–8 cần fork nhép miệng chạy trên GPU laptop (ADR-023);
> không dùng RunPod. Ảnh thử đặt ngoài git (`out/012-test-images/`); bộ cảnh và `uploads/` là dữ liệu khách, ngoài git.

## 0. Chuẩn bị

`.env`: `SCENE_ENABLED=true`, `SCENE_DIR=assets/scenes/demo`, `AVATAR_MODE=static`, file nội dung demo như 009.

```bash
uv run python scripts/make_demo_scene.py        # nếu chưa có bộ cảnh mẫu (009)
uv run uvicorn ai_live.app.main:app --port 8000
```

Mở trang điều khiển (`/`) và `/host` cạnh nhau. Muốn làm lại từ đầu: tắt app, xóa `assets/scenes/demo/uploads/` (contracts/scene-set.md §6).

## 1. US1: thay ảnh một sản phẩm (không GPU)

1. Trang điều khiển, khối "Ảnh sản phẩm": mỗi món có ảnh nhỏ và trạng thái "ảnh bộ cảnh" (`GET /api/scene/images`, `state: "kit"`).
2. Chọn món phụ, chọn một ảnh PNG nền trong suốt → hiện ảnh nhỏ của phiên bản mới, chưa đổi live.
3. Bấm "Xem trước": khung hình tĩnh hiện cạnh ảnh live, món đó dùng ảnh mới (`/api/scene/preview.png`).
4. Bấm "Áp dụng" khi chưa tích ô xác nhận → nút bị khóa; gọi thẳng API không có `rights_confirmed` → 422 `rights_not_confirmed` (SC-003).
5. Tích ô xác nhận, "Áp dụng" → `/host` đổi ảnh; thân trả về có `to_frame_ms` (ghi lại); log `scene_image_changed`.
6. Thử ảnh JPEG có nền → cảnh báo "ảnh còn nền" nhưng vẫn áp được (FR-004).
7. Tắt rồi bật lại app → món vẫn dùng ảnh mới (FR-012). `uv run python -m ai_live.scene check assets/scenes/demo` có dòng
   `Ảnh tải lên: 1 đang dùng…`, không báo thiếu `provenance.json` cho món đó.
8. Hai tab trang điều khiển: áp ảnh ở tab 1 → tab 2 tự cập nhật (sự kiện `scene` `image_changed`).
9. SC-002: bấm giờ từ lúc chọn món tới lúc ảnh đổi trên `/host`, ảnh có sẵn trên máy: ≤ 30 s.

## 2. SC-004: file sai (không GPU)

Tạo bộ file thử (script nhỏ trong scratchpad hoặc tay): file hỏng (cắt đôi PNG), file `.txt` đổi tên `.png`, GIF/WebP động, PNG trong suốt
hoàn toàn, ảnh > 10 MB, ảnh 4100×300. Tải từng file:

- Mỗi file bị từ chối với câu tiếng Việt đúng mã (contracts/api.md §6); log `scene_image_rejected`.
- Ảnh trên `/host` không đổi; `uploads/` không có file mới.

Test tự động cùng bộ này nằm ở `tests/` (tạo file bằng Pillow trong test, không commit ảnh).

## 3. US3: về ảnh trước, gỡ ảnh (không GPU)

1. Áp ảnh A rồi ảnh B cho cùng món; "Về ảnh trước" → A trên live; lần nữa → ảnh bộ cảnh; lần nữa → nút khóa (409 `nothing_to_revert`).
2. "Gỡ ảnh" → hỏi lại → món chỉ còn thẻ tên/giá; "Về ảnh trước" → ảnh cũ quay lại.
3. Món đã gỡ: `check` báo `warning missing_image`.

## 4. US2: đổi bộ sản phẩm (không GPU)

1. Tạo file nội dung có 3 món mới (sửa bản sao file demo). "Chuẩn bị bộ mới" → tải file → danh sách món mới, ảnh `missing`; live không đổi.
2. Gán ảnh cho 2 món (tải + tích xác nhận); "Xem trước" bộ chuẩn bị.
3. "Áp dụng bộ mới" → hỏi lại vì còn 1 món thiếu ảnh (409 `missing_images` có tên món) → đồng ý → thẻ và ảnh của cả bộ đổi trong một lần;
   ghi `to_frame_ms`. Chụp `/host` ngay sau: không có khung nào ghép thẻ mới với ảnh cũ (SC-006).
4. Tắt/bật app → ảnh 2 món vẫn còn. Chuẩn bị lại file cũ → các món cũ tự có ảnh (`reused_upload` / `reused_kit`).
5. Chuẩn bị bộ mới rồi "Hủy" → live không đổi, ảnh đã tải vẫn còn trong sổ.
6. Trong khi có bộ chuẩn bị, `PUT /api/content` từ khối cũ → bộ chuẩn bị báo `live_changed: true`.
7. SC-005: bấm giờ từ lúc chọn file tới lúc áp xong 3 món: ≤ 3 phút.

## 5. US4: "AI vừa nói" và xem dữ liệu sản phẩm (không GPU)

1. Bắt đầu show kịch bản. Khối "AI vừa nói" thêm câu theo thời gian thực, mỗi câu có giờ, món, chủ đề (`topic`).
2. Tải lại trang giữa show → danh sách cũ hiện lại từ `GET /api/state` (`spoken`).
3. Bấm một món → xem đủ mô tả, giá, phân loại, thông số, FAQ, khuyến mãi; không có đường link. So từng mục với file demo (SC-007).
4. Trong bộ chuẩn bị, bấm một món mới → xem dữ liệu của file chuẩn bị (`source: "staging"`).
5. SC-007: hết show 10 phút, so `sentence` có `segment_id` trong nhật ký phiên với danh sách trên trang (50 câu gần nhất): đủ, đúng thứ tự;
   không câu nào có `guard_blocked`.

## 6. Kiểm trước demo (không GPU)

`uv run python -m ai_live.ops readiness`: sửa tay `images.json` bỏ `rights_confirmed_at` của một món → mục cảnh báo **LỖI**
`missing_confirmation`; làm hỏng JSON → **LỖI** `bad_uploads`. Trả lại như cũ → OK.

## 7. SC-001: đo trong chế độ nhép miệng (cần GPU laptop)

`.env`: `AVATAR_MODE=livetalking`. Bật fork trước bằng `powershell scripts/livetalking/run.ps1`, rồi chạy app.

1. Show 10 phút không đổi ảnh: lấy khoảng lặng giữa câu p95 từ `/api/latency`.
2. Show 10 phút cùng cấu hình, 10 lần "Áp dụng" (đổi qua lại 2–3 ảnh, có cả "Về ảnh trước"):
   - `to_frame_ms` của cả 10 lần ≤ 2000 (log `scene_image_changed`); quay màn hình `/host` để thấy ảnh mới trong 2 s;
   - show không dừng; lặng p95 tăng ≤ 0,1 s so với bước 1.
3. Nếu vượt: xem `scene_loaded` (thời gian nạp) và cân nhắc nhớ ảnh đã giải mã (research R5, rủi ro Q39), đo lại.

## 8. SC-006: ảnh chụp khung hình (cần GPU laptop)

Trong show bước 7, chụp ≥ 20 khung `/host` quanh các lần đổi, với ảnh rất cao (300×1600), rất rộng (1600×300), ảnh còn nền. Kiểm bằng mắt và
script so vùng như 009 quickstart §8: nhãn "AI-GENERATED CONTENT", watermark, mặt host không bị che; không khung nào ghép ảnh món này với thẻ
món khác.

## 9. Gói duyệt cho người dùng (cần mắt người)

- Ảnh chụp trang điều khiển: khối "Ảnh sản phẩm", bộ chuẩn bị, "AI vừa nói", xem dữ liệu sản phẩm: dễ dùng giữa live không.
- Câu ô xác nhận quyền dùng ảnh (FR-006) và ADR-071, ADR-072.
- Số đo SC-001 (bước 7) và ảnh SC-006 (bước 8).
- Nói "commit" để mình commit.
