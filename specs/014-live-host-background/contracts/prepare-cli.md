# Hợp đồng: công cụ chuẩn bị nền cho nhân vật (014)

Chạy **một lần cho mỗi nhân vật**, trước giờ live, trên laptop dev (miễn phí, không cần GPU). Hai lớp, giống `prepare` của 005:

## 1. Lệnh của app (người vận hành gõ)

```bash
uv run python -m ai_live.avatar background-prepare <character_id> [--method plate|mediapipe] [--json]
uv run python -m ai_live.avatar background-prepare <character_id> --mark-reviewed --by "<tên người duyệt>"
```

- Tìm thư mục avatar fork của nhân vật (`data/avatars/<character_id>__*` có `full_imgs`, như `character.py` đang làm) và gọi lệnh fork bên
  dưới bằng python của venv fork (`vendor/livetalking/.venv`).
- `--method` mặc định `plate`. `mediapipe` chỉ chạy khi có file model ở đường dẫn cấu hình `BACKGROUND_SEGMENTER_MODEL` (biến môi trường,
  không hardcode); không có thì báo lỗi tiếng Việt chỉ cách tải (sau khi ADR-083 được duyệt).
- `--mark-reviewed`: đặt `reviewed=true`, `reviewed_by`, `reviewed_at` trong manifest sau khi người duyệt xem `review.jpg`.
- `--room-area "x,y x,y x,y ..."` (thêm 2026-11-25, ADR-094, lặp lại được): đa giác pixel khung quanh một khe phòng cũ còn sót mà cách
  tách tự động giữ lại (ví dụ khe giữa cánh tay và thân dưới nách). Không truyền `--room-area` thì **dùng lại** các vùng đã ghi trong
  manifest cũ (in "Dùng lại N vùng phòng khoanh lần trước"); `--no-room-areas` bỏ hết vùng.
- In tiếng Việt: số khung, cách tách, số khung có cờ lọt (R12), đường dẫn `review.jpg`. Mã thoát: 0 xong, 1 lỗi dữ liệu, 2 lỗi chương trình.

## 2. Lệnh của fork (app gọi)

```bash
vendor/livetalking/.venv/Scripts/python.exe -m ailive_ext.background_prep \
    --ailive_character <assets/avatars/<id>> --avatars <data/avatars/<id>__a> [<data/avatars/<id>__b> ...] \
    --method plate|mediapipe [--model <file.tflite>] [--room-area "x,y x,y x,y ..." ...] --json
```

- `--room-area` (ADR-094): sau bước lấp lỗ, trong mỗi đa giác (bỏ phần từ `desk_top_px` trở xuống) chia điểm ảnh của mọi khung làm hai
  lớp sáng/tối bằng Otsu trên độ sáng Lab; lớp có màu trung bình xa màu người ở vành 4 px quanh đa giác hơn là phòng và được trả về 0
  trên từng khung. Đa giác sai cú pháp, ngoài khung, nằm hẳn dưới mặt bàn hoặc không giáp người → JSON `ok: false`, mã thoát 1.

- Đọc đúng các khung fork sẽ phát: `full_imgs` của từng thư mục avatar (đọc bằng cùng hàm nạp của fork để bytes khung giống lúc live) và
  khung clip nếu `character.json` có clip.
- Các bước: mặt nạ thô (R3) → làm mượt theo thời gian (R4) → guided filter (R5) → giữ mảng lớn nhất, lấp lỗ → dốc mặt bàn (R6) → đo ánh
  sáng (R11) và lọt (R12) → ghi thư mục `background/` (data-model §2) qua thư mục tạm rồi đổi tên.
- Stdout đúng một dòng JSON:

```json
{ "ok": true, "frames": 81, "method": "plate", "flagged_frames": [40], "max_blob_px": 210,
  "review": "assets/avatars/demo_host_02/background/review.jpg", "errors": [] }
```

- Chạy trong **tiến trình riêng, ưu tiên thấp** nếu app đang live (giống bộ bỏ nền 013), để VieNeu và lip-sync không bị giật. Khuyến nghị
  chạy khi không live.
- Thời gian mong đợi: vài phút cho 81 khung (giả định của spec). Đo thật (T032, 2026-11-24, laptop dev, CPU, `plate`): **122–126 s** cho
  `demo_host_02` = 2 thư mục khung × 81 khung = 162 khung (khung w2l và ultralight khác byte nên không dùng chung mặt nạ), tức ~60 s cho
  mỗi vòng 81 khung.
- `flagged_frames` là **số ô trong `review.jpg`** (mỗi ô có in số), không phải chỉ số khung trong một thư mục: chỉ số khung lặp lại giữa
  các thư mục avatar.
