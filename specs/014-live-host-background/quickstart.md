# Quickstart: nền sau host (014)

Kiểm chứng bằng tay từng user story. Ký hiệu: **[không GPU]** chạy trên laptop dev không cần GPU; **[GPU laptop]** cần fork LiveTalking
chạy trên GTX 1650 Ti (ADR-023); **[RunPod]** chỉ dùng khi laptop không chạy được, **hỏi chủ dự án về chi phí trước** (`docs/RUNPOD.md`).

## 0. Chuẩn bị chung [không GPU]

```bash
uv sync
uv run pytest tests -k "background or backdrop"                 # test app, không GPU
vendor/livetalking/.venv/Scripts/python.exe -m pytest vendor/livetalking/ailive_ext/tests -k background   # test fork, không GPU
uv run ruff check . && uv run ruff format --check .
```

- `.env`: `SCENE_ENABLED=true` (cảnh live 009/013 phải bật thì mới có nền).
- `assets/scenes/<scene_id>/scene.json` thêm khối:

```json
"background": { "style": "ke_hang", "softness_px": 1.5, "brightness": 0.95 }
```

## US1 (P1): kệ hàng sau host khi live

1. **Chuẩn bị nền cho nhân vật [không GPU]** (CPU, vài phút):
   ```bash
   uv run python -m ai_live.avatar background-prepare demo_host_02
   ```
   Mong đợi: in số khung (81), cách tách `plate`, đường dẫn `assets/avatars/demo_host_02/background/review.jpg`, mã thoát 0.
2. **Duyệt bằng mắt [không GPU]:** mở `review.jpg` (lưới khung, có khung host nghiêng đầu, viền mặt nạ tô màu). Tìm mảng phòng cũ quanh vai,
   tóc, dải LED trên đầu (SC-001) và chỗ bị khoét mất người (SC-002). Đạt thì:
   ```bash
   uv run python -m ai_live.avatar background-prepare demo_host_02 --mark-reviewed --by "<tên>"
   ```
   Không đạt: chạy lại với `--method mediapipe` **chỉ sau khi ADR-083 được duyệt và model đã tải** (xem research R3).
3. **Xem trước không cần fork [không GPU]:** chạy app (`uv run uvicorn ai_live.app.main:app --port 8000`), mở `/control`, khối "Nền sau host"
   hiện kiểu `kệ hàng`, trạng thái `hợp lệ`, ảnh xem trước. Hoặc mở thẳng `/api/scene/background/preview.png`.
4. **Live thật [GPU laptop]:** `scripts/livetalking/run.ps1` như 005/011, rồi chạy app với `AVATAR_MODE=livetalking`. Mở `/host`:
   - sau host là kệ hàng có ảnh sản phẩm của shop, không chữ, không logo lạ; nhãn "AI-GENERATED CONTENT" vẫn trên cùng; mặt bàn, sản phẩm,
     thẻ của 013 giữ nguyên;
   - miệng vẫn mấp máy theo lời nói (lip-sync sinh thời gian thực, không đổi).
5. **20 khung [GPU laptop]:** chụp 20 khung ngẫu nhiên từ `/host` (công cụ đo của US4, hoặc bộ ghi 005). Đếm khung lọt / khoét (SC-001, SC-002).
6. **OBS [GPU laptop]:** `OUTPUT_MODE=obs`, mở `/obs`: cùng nền như `/host` (FR-014).

## US2 (P2): rơi về an toàn

1. **Thiếu phần chuẩn bị [không GPU + GPU laptop]:** đổi tên tạm thư mục `assets/avatars/demo_host_02/background` (rồi đổi lại). Khởi động:
   `/host` hiện phòng gốc, trang điều khiển báo "Nhân vật chưa có nền…", `GET /api/readiness` có `warn`, log `scene_background_started`
   có `fallback_reason` (SC-006, FR-010, FR-015).
2. **Không khớp:** sửa 1 byte một ảnh trong `full_imgs` của bản sao avatar thử (không sửa bản thật), chạy fork với bản sao: `hello.background`
   = `mismatch`, `frame_not_prepared:<n>`, phòng gốc.
3. **Không có ảnh sản phẩm:** bộ cảnh không có ảnh đã bỏ nền: phòng gốc, lý do `no_product_art` (FR-011).
4. **Tốc độ khung [GPU laptop]:** chạy show 5 phút với `style: "goc"`, khởi động lại, 5 phút với `style: "ke_hang"`; so fps trong `stats` của fork và `background_ms` (SC-003: giảm
   ≤ 10%). So `llm_first_sentence` / khoảng lặng p95 trong log lượt (SC-004).

## US4 (P3): công cụ đo độ thật đo thêm phần nền [không GPU]

```bash
uv run python .claude/skills/live-scene-realism/scripts/realism_report.py --out <thư mục>/report \
    --host-frame <một khung live đã chụp> --background-frames <thư mục 20 khung>
```

`--background-frames` là cờ mới của US4 (script hiện chỉ có `--host-frame`, `--scene`, `--layout`…). Khung chụp từ `/host` đã có nền mới nên không tự biết mặt nạ: chỉ số lọt tính trên khung gốc của fork (`full_imgs`) ghép với mặt nạ khớp
crc32 trong `assets/avatars/<id>/background/`; khung live dùng cho độ nét, độ sáng và màu ánh sáng. Mong đợi: thêm các cột lọt phòng cũ (số điểm ảnh, ảnh đánh dấu), lệch độ sáng / màu ánh sáng người-nền, độ mềm viền; cờ đỏ khi vượt ngưỡng
của research R12. Chạy trên khung nền tắt để thấy cờ "phòng gốc" không bị báo nhầm.

## US3: ảnh shop (đã làm, ADR-100) và bảng shop (chưa làm)

Ảnh shop sau host:

```powershell
uv run python -m ai_live.scene shop-photo assets/scenes/demo "<ảnh>.png" --confirmed-by "<tên>" --ai-generated
```

Bỏ `--ai-generated` nếu là ảnh chụp thật. Ảnh AI phải là cảnh shop chung: không người, không sản phẩm của khách, không logo đọc được.
Đặt `"background": {"style": "anh_shop"}` trong `scene.json`, khởi động lại app, xem `GET /api/scene/background` (`active: true`) và
màn `/obs` hoặc `/host`.

Bảng shop: thêm dòng "Tên shop:" vào file dữ liệu sản phẩm, đặt `style: "bang_shop"` (chưa có bộ vẽ, research R15).

## RunPod (dự phòng)

Chỉ khi laptop không chạy được fork ở fps chấp nhận được **và** chủ dự án đồng ý chi phí. Các bước giống US1 bước 4–6 theo `docs/RUNPOD.md`;
phần chuẩn bị nền (bước 1–2) vẫn làm trên laptop rồi chép thư mục `background/` lên pod. Tắt pod ngay khi xong.
