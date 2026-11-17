# Quickstart: 009 Bố cục cảnh live

> Chạy trên laptop dev. Các bước 1–5 không cần GPU; bước 6–7 cần fork LiveTalking chạy trên GPU laptop (ADR-023).

## 1. Tạo bộ cảnh mẫu (ngoài git)

```bash
uv run python scripts/make_demo_scene.py            # ra assets/scenes/demo/ (bàn gỗ vẽ + ảnh "ẢNH MẪU" cho sản phẩm demo)
```

Với khách thật: cắt nền ảnh khách gửi bằng tay (Paint của Windows 11 → "Xóa nền", hoặc GIMP), lưu PNG nền trong suốt vào
`products/<product_id>.png`, ảnh gốc vào `originals/`, ghi `provenance.json` (contracts/scene-set.md §3). Không dùng dịch vụ cắt nền
trên mạng (ảnh của khách).

## 2. Kiểm bộ cảnh (FR-003)

```bash
uv run python -m ai_live.scene check assets/scenes/demo
```

Mong đợi với bộ mẫu: chỉ có `warning placeholder` cho từng sản phẩm, mã thoát 0. Thử làm hỏng một ảnh (đổi tên `.png` thành `.jpg`)
→ có `error`, mã thoát 1.

## 3. Xem trước không cần chạy app

```bash
uv run python -m ai_live.scene preview assets/scenes/demo --out preview.png --debug-zones
uv run python -m ai_live.scene preview assets/scenes/demo --out preview_hl.png --highlight <product_id> --subtitle "Câu thử có dấu tiếng Việt"
```

Kiểm bằng mắt: mặt không bị che (nét đứt vùng cấm), sản phẩm đứng trên mặt bàn, thẻ đọc được, món nổi to hơn.

## 4. Chế độ ảnh tĩnh trên trang host

`.env`: `SCENE_ENABLED=true`, `SCENE_DIR=assets/scenes/demo`, `AVATAR_MODE=static`. Chạy app, mở `/host`:
- Thấy host đứng sau bàn, 3 sản phẩm + thẻ, nhãn "AI" ở góc (US1 #1).
- Bắt đầu show từ trang điều khiển: sản phẩm nổi đổi theo phân đoạn (US2), `GET /api/scene` báo `highlight`.
- Tinh chỉnh bố cục bằng Chrome DevTools MCP: chụp `/host` ở 480×832 và 1280×720 (cửa sổ Meet), sửa hằng số bố cục, chụp lại.

## 5. Thay file dữ liệu giữa phiên (FR-013)

`PUT /api/content` với file có giá khác → trong 2 s thẻ đổi; chụp màn hình so với file.

## 6. Chế độ nhép miệng (fork)

`.env`: `AVATAR_MODE=livetalking`. Bật fork trước bằng `powershell scripts/livetalking/run.ps1` (app không tự bật fork), rồi chạy app. Kiểm:
- `hello` có `scene.face_bottom`; `GET /api/scene` báo `geometry.source = "fork"`.
- Mở `/host`: cảnh nằm trong luồng WebRTC; watermark "LiveTalking" và nhãn "AI" nằm trên cùng.
- Tắt fork giữa show → app tự về ảnh tĩnh: cảnh và món nổi vẫn còn, nhãn "AI" vẫn hiện (US1 #6).

## 7. Đo SC-004

Hai show 10 phút cùng cấu hình (`SCENE_ENABLED=false` rồi `true`), lấy `render_fps`, `scene_ms`, khoảng lặng p95 từ `/api/latency`.
Đạt khi fps giảm ≤ 10% và khoảng lặng p95 tăng ≤ 0,1 s. Ghi kết quả vào FEATURES card và ADR-052.

## 8. SC-001

Chụp ≥ 20 ảnh `/host` ở thời điểm ngẫu nhiên (chờ, nói, ảnh tĩnh, lúc đổi sản phẩm nổi); script kiểm vùng nhãn/watermark/mặt không có
điểm ảnh của cảnh (so với khung tắt cảnh) + mắt người.

## 9. Gói duyệt cho người dùng (cần mắt người)

- Ảnh chụp bố cục (chờ, đang nói, món nổi, ảnh tĩnh): có giống live bán hàng không, chỉnh gì.
- Ảnh thật của khách + cắt nền + `provenance.json` (FR-002, SC-007): đặt ảnh gốc cạnh ảnh đã chỉnh để người dùng xác nhận.
- SC-006: 3 người xem so hai đoạn 1 phút có/không cảnh (gộp với 005 T068 nếu được).
- License font (RISKS L12), xác nhận ADR-051 và ADR-052.
- Nói "commit" để mình commit repo chính và nhánh `ailive` của fork.
