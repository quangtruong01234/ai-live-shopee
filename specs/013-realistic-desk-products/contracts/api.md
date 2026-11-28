# Hợp đồng: API, log và CLI tách nền (013)

> Bổ sung cho [012 contracts/api.md](../../012-product-image-upload/contracts/api.md). Endpoint không nhắc tới ở đây giữ nguyên. Không
> endpoint mới; chỉ thêm trường (khóa cũ giữ nguyên nghĩa) và một tham số.

## 1. `POST /api/scene/uploads?product_id={pid}&target=live|staging` (đổi)

Sau bước kiểm và chuẩn hóa của 012, request **chờ bỏ nền xong** rồi mới trả lời (research R9). Vẫn **không** áp lên live.

201, thêm vào phản hồi 012:

```json
{
  "product_id": "coca-thung-24", "version_id": "3f9a0c1b2d4e", "reused": false,
  "width": 1280, "height": 960, "has_alpha": false,
  "bg_removal": {"method": "flat", "result": "removed", "reason": null, "ms": 182.4, "model": null},
  "cutout": {"version_id": "a81c55d09e2f", "width": 1104, "height": 902,
             "thumb_url": "/api/scene/images/coca-thung-24/versions/a81c55d09e2f.png"},
  "recommended_version": "a81c55d09e2f",
  "warnings": [], "warning_messages": {}, "thumb_url": "/api/scene/images/coca-thung-24/versions/3f9a0c1b2d4e.png"
}
```

- `bg_removal.result`: `removed` (có `cutout`), `failed` (`cutout: null`, `reason` tiếng Việt cho trang), `kept` (ảnh đã trong suốt,
  `method: already_transparent`, `cutout: null`).
- `recommended_version`: bản trang nên chọn sẵn: bản bỏ nền khi `removed`, ngược lại ảnh tải lên. Không bao giờ là bản bị `assess_cut` đánh
  trượt (FR-014).
- `warnings`:
  - `has_background` (012) chỉ còn khi `result = failed` (ảnh tải lên vẫn còn nền và không có bản bỏ nền);
  - `too_wide` (012) tính cho `recommended_version`.
- Bỏ nền lỗi **không** làm request lỗi: ảnh tải lên vẫn được lưu, trả 201 với `failed`.
- Thời gian (SC-006): ≤ 5 s nền trơn, ≤ 20 s nền phức tạp. Trang hiện "Đang bỏ nền…" và khóa nút áp tới khi có phản hồi.
- `reused: true` → trả lại `bg_removal`/`cutout` đã lưu (data-model §9 nói khi nào chạy lại).

## 2. `GET /api/scene/images` (đổi)

Mỗi mục trong `versions` thêm `bg_removal`, `cutout_version`, `derived_from` (null nếu không có). Mục sản phẩm thêm `issues` mới
`art_has_background` khi cách bày `realistic` và ảnh đang dùng còn nền.

## 3. `GET /api/scene/preview.png` (đổi)

Thêm tham số `debug=1`: vẽ vạch mép bàn, vùng tay và vùng cấm 009 lên ảnh xem trước (research R2). Chỉ ảnh trả về; không đổi live, không gửi
fork. Thiếu hoặc `debug=0` → như 012.

## 4. Trang điều khiển (khung ảnh sản phẩm 012)

- Sau khi tải: hai ảnh cạnh nhau trên **nền ô cờ** (ảnh tải lên | bản bỏ nền), ghi cách bỏ nền và thời gian; bản `recommended_version` được
  chọn sẵn; người vận hành bấm chọn bản kia được (US2 #5). `failed` → chỉ một ảnh, kèm lý do.
- Nút "Xem trước" và "Áp dụng" của 012 dùng `version_id` đang chọn. Ô xác nhận quyền dùng như 012.
- Không có nút đổi cách bày hay chế độ thẻ (chọn trong `scene.json`).

## 5. Log JSONL (logger cảnh)

```json
{"event": "scene_bg_removed", "product_id": "coca-thung-24", "version_id": "3f9a0c1b2d4e", "cutout_version": "a81c55d09e2f",
 "method": "flat", "result": "removed", "reason": null, "ms": 182.4, "model": null, "width": 1280, "height": 960,
 "fg_ratio": 0.61, "border_fg_ratio": 0.0, "uncertain_ratio": 0.02}
```

`scene_rendered` (009) thêm `layout_mode`, `cards`, `stations` (`{product_id: station}`).

## 6. CLI tiến trình con tách nền (nội bộ)

```bash
python -m ai_live.scene.matting --model <file.onnx> --in <input.png> --out <mask.png> [--threads 2]
```

- Đọc ảnh RGB, chạy model, ghi **mặt nạ** 8 bit (L, cùng cỡ ảnh vào) ra `--out`. Không ghi gì khác. Không đọc `.env`, không mạng.
- Tự hạ ưu tiên lúc khởi động (POSIX `os.nice(10)`; Windows do tiến trình cha đặt `BELOW_NORMAL_PRIORITY_CLASS`).
- Mã thoát: 0 thành công; 2 tham số sai; 3 không mở được model; 4 không đọc được ảnh; 5 lỗi chạy model. Lỗi in một dòng ra stderr.
- Tiền/hậu xử lý theo tên file model: `isnet-*` (research R6, ISNet), `birefnet-*`/`BiRefNet-*` (BiRefNet). Tên khác → mã 3.
- Tiến trình cha: `asyncio.create_subprocess_exec(sys.executable, "-m", "ai_live.scene.matting", …)`, `Semaphore(1)`, hết giờ 60 s thì giết
  tiến trình. Ghép mặt nạ vào alpha, chạy `assess_cut`, cắt theo hộp alpha trong tiến trình cha.

## 7. Biến môi trường mới (`core/config.py`, `.env.example`)

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `MATTING_MODEL_PATH` | rỗng | File ONNX model tách nền. Rỗng/không có file → chỉ bỏ nền phẳng; readiness cảnh báo `matting_model_missing` |
| `MATTING_DURING_SHOW` | `true` | `false`: khi show đang chạy, không chạy model (ảnh nền phức tạp → `failed` "đang live…"); nền phẳng vẫn chạy |

## 8. So với `docs/ARCHITECTURE.md` §3

Không thêm hay đổi Protocol adapter nào. `AvatarRenderer.set_scene_layer` không đổi. Bố cục, vẽ cảnh và tách nền là mã nội bộ của `scene/`.
