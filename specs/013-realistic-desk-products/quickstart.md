# Quickstart: kiểm từng user story của 013

- **Feature:** `013-realistic-desk-products` · **Ngày:** 2026-11-22 · **Plan:** [plan.md](./plan.md)
- Ký hiệu: **[không GPU]** chạy với `AVATAR_MODE=static`; **[GPU laptop]** cần fork lip-sync trên GTX 1650 Ti (ADR-023). Không RunPod.
- Mọi lệnh chạy từ gốc repo.

## 0. Chuẩn bị

```bash
uv sync
uv run pytest tests/unit/test_realistic_layout.py tests/unit/test_scene_matting.py   # [không GPU]
```

Bộ cảnh thử: `assets/scenes/demo` (ngoài git). Ghi vào `scene.json`:

```json
"layout": {"mode": "realistic"}
```

Model tách nền (chỉ sau khi ADR-074 được duyệt; người dùng tải tay, không commit):

```powershell
New-Item -ItemType Directory -Force models/matting
# tải isnet-general-use.onnx từ release rembg v0.0.0, kiểm md5 fc16ebd8b0c10d971d3513d564d01e29
Get-FileHash models/matting/isnet-general-use.onnx -Algorithm MD5
```

Rồi đặt `MATTING_MODEL_PATH=models/matting/isnet-general-use.onnx` trong `.env`.

## 1. US1: sản phẩm đứng trên bàn hai bên tay (P1)

1. **[không GPU]** Ảnh tĩnh:
   ```bash
   uv run python -m ai_live.scene preview assets/scenes/demo --out out/us1.png
   uv run python -m ai_live.scene preview assets/scenes/demo --out out/us1_hl.png --highlight <pid món phụ>
   ```
   Kiểm bằng mắt: món đứng hai bên tay, đáy chạm mặt bàn, món sau nhỏ hơn và lùi về sau, có bóng mềm, không thẻ, không che tay/mặt/nhãn AI.
2. **[không GPU]** `"brightness": 0.9` rồi `1.1`: món tối/sáng đều, màu bao bì không đổi (so với ảnh gốc; FR-006).
3. **[không GPU]** Đổi số món 1 → 5 trong file nội dung, chụp lại từng lần (US1 #4, #5).
4. **[không GPU]** Bỏ `"mode"` khỏi `scene.json` → ảnh giống hệt 009 (US1 #6; test hồi quy so điểm ảnh).
5. **[GPU laptop]** Chạy show với `demo_host_02`, `OUTPUT_MODE=meet`, mở `/host`, chụp 3 lúc (phân đoạn chung, nói món chính, nói món phụ).
   SC-001: người dùng chấm ≥ 4/5 "như đồ thật" trên ảnh chụp.

## 2. Đo vạch mép bàn và vùng tay (FR-008, FR-010)

1. **[không GPU]**
   ```bash
   uv run python -m ai_live.scene preview assets/scenes/demo --out out/debug.png --debug-zones
   # đúng khung live: vẽ lên khung đầu của avatar fork
   uv run python -m ai_live.scene preview assets/scenes/demo --out out/live.png --host-frame vendor/livetalking/data/avatars/<avatar>/full_imgs/00000000.png
   ```
   hoặc mở `http://localhost:8000/api/scene/preview.png?debug=1`.
2. Vạch xanh lá phải trùng mép bàn trong ảnh nhân vật (sai ≤ 1% chiều cao, khoảng 8 px ở khung 832). Khung tím phải ôm cả hai tay ở mọi clip
   nói (xem vài khung của clip `talk`). Sửa `scene.desk_top`, `scene.hands_zone` trong `character.json` rồi chạy lại.
3. Kiểm trước demo (`uv run python -m ai_live.ops readiness` hoặc trang điều khiển) không còn `hands_zone_missing`.

## 3. US2: tải ảnh có nền, hệ thống bỏ nền (P2)

1. **[không GPU]** Mở trang điều khiển, khung ảnh sản phẩm, tải một ảnh nền trắng (vd thùng Coca). Trong ≤ 5 s thấy hai ảnh cạnh nhau trên
   nền ô cờ, bản bỏ nền được chọn sẵn, mép sạch. Áp dụng → ảnh lên khung ≤ 2 s.
2. Tải ảnh PNG đã trong suốt → không có bản thứ hai, ghi "ảnh đã trong suốt" (US2 #2).
3. Tải ảnh sản phẩm có phần trắng trong lòng (hộp trắng in chữ) → phần trắng trong lòng còn nguyên (US2 #4).
4. Tải ảnh nền phức tạp:
   - chưa có model → `failed` "chưa cài model tách nền", ảnh gốc vẫn dùng được;
   - có model → trong ≤ 20 s có bản bỏ nền hoặc `failed` với lý do.
5. **SC-003 [không GPU]:** bộ ≥ 20 ảnh (10 nền trơn, 10 nền phức tạp, thêm vài ảnh khó: sản phẩm trắng trên nền trắng, chai trong suốt).
   Ghi từng ảnh: kết quả, `ms`, chấm đạt/không. Đạt: ≥ 9/10 nền trơn, ≥ 7/10 nền phức tạp, 100% ảnh xấu bị báo không chắc. Ghi bảng và ngưỡng
   cuối vào `research.md` R8. Ảnh thử nằm ngoài git.
6. **SC-004:** sau mỗi lần áp, "Về ảnh trước" (012) đưa về ảnh trước ≤ 2 s; ảnh gốc vẫn trong danh sách phiên bản.

## 4. US3: thẻ (P3)

1. **[không GPU]** `"cards": "none"` (mặc định) → không thẻ, kể cả khi món đang nổi.
2. `"cards": "one"` → chụp `--highlight` món chính, món phụ, không món nổi: thẻ chỉ của món đang nổi, ở trên các món cùng bên, không che món.
   TODO: người dùng duyệt vị trí thẻ (research R4).
3. `"cards": "all"` → mỗi món một thẻ dưới đáy; món không đủ chỗ có cảnh báo `card_no_room`.
4. `"mode": "rows", "cards": "none"` → vẫn có thẻ + cảnh báo `cards_ignored`.

## 4b. Cách bày trưng bày `showcase` (FR-025–FR-028, ADR-079)

1. **[không GPU]** `scene.json`: `"layout": {"mode": "showcase", "max_slots": 4, "riser": true, "sticker": true}`, rồi
   `uv run python -m ai_live.scene preview assets/scenes/demo --out out/013/showcase.png --host-frame assets/avatars/demo_host_02/face.png`.
   Món chính to giữa khung trên bục trắng, sticker giá đúng file dữ liệu ở góc trên, món phụ đứng phía sau hai bên, không món nào che
   món nào (ADR-081); mặt, nhãn "AI" sạch.
2. Thêm `--highlight <mã món phụ>`: món đó to lên nhưng không chạm món nào (ADR-081; trước đó: không bị che quá 40%).
3. Ảnh sản phẩm nhỏ (ví dụ 300 px) → `check` và phản hồi tải ảnh có cảnh báo `art_low_resolution` / `low_resolution`, ảnh vẫn áp được.
4. Lưu ý: `preview` đoán vùng mặt theo khung chuẩn, nên phụ đề có thể đè miệng trên ảnh của nhân vật khác khung; lúc live fork báo vùng
   mặt thật.

## 5. Hiệu năng (SC-005, SC-006) [GPU laptop]

1. Show 10 phút cách bày `rows`, rồi 10 phút `realistic`, cùng cấu hình. So `scene_ms` trung vị và FPS (lệch ≤ 10%), lặng p95.
2. Show 10 phút `realistic`, trong lúc chạy tải 3 ảnh nền phức tạp (có model). Lặng p95 không tăng quá 0,1 s so với bước 1. Không đạt → đặt
   `MATTING_DURING_SHOW=false`, ghi vào RISKS Q40 và research R7.
3. Ghi thời gian nạp model, RAM đỉnh của tiến trình con (Task Manager) vào research R7.
