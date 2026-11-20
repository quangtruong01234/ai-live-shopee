# Hợp đồng: phần thêm vào giao thức app ↔ fork (009)

> Mở rộng [005 contracts/fork-protocol.md](../../005-lipsync-livetalking/contracts/fork-protocol.md). Mọi tin vẫn là JSON trên
> `/ailive/ws`. Fork cũ bỏ qua tin lạ (không trả lỗi), nên app nhận biết hỗ trợ cảnh qua `hello.scene` (§3): `hello` không có `scene`
> thì app log `scene_unsupported` một lần, không gửi `scene_layer`, và vẫn giữ ảnh tĩnh có cảnh để dự phòng.

## 1. app → fork: `scene_layer`

```json
{"type": "scene_layer", "name": "base", "x": 0, "y": 590, "png_b64": "iVBORw0KGgo..."}
{"type": "scene_layer", "name": "subtitle", "x": 24, "y": 336, "png_b64": null}
```

- `name` ∈ `base | subtitle`. Mỗi tên giữ đúng một lớp; tin mới thay lớp cũ cùng tên. `png_b64: null` xóa lớp.
- Thứ tự trộn cố định: `base` rồi `subtitle`.
- PNG RGBA 8 bit; `x, y` là góc trên trái trong khung `(w, h)` của fork. Ảnh phải nằm trọn trong khung.
- Kích thước PNG sau base64 ≤ 4 MB (app cắt sát vùng có hình nên thường < 300 KB).

## 2. Kiểm tra của fork (FR-019)

Fork từ chối lớp và **giữ lớp cũ** nếu:
1. Không giải mã được, không đủ 4 kênh, hoặc vượt khung → `error {kind: "scene_rejected", layer, message}`.
2. Có điểm ảnh alpha > 0 trong vùng cấm:
   - mặt: `y < face_bottom + 8`, cả chiều ngang;
   - hộp nhãn "AI" do `ailive_ext/label.py` tính theo env của fork, nới 4 px (ví dụ dưới là nhãn "AI" cũ; nhãn mặc định đổi
     thành "AI-GENERATED CONTENT" bởi ADR-065, hộp rộng hơn);
   - hộp watermark "LiveTalking" `(0, 0, 90, 30)`.

`error` dạng này không có `utterance_id` và **không** làm hỏng lượt nói nào (app không gọi `_fail_waiters`).

## 3. fork → app: `hello.scene`

`hello` có thêm:

```json
"scene": {
  "frame_size": [480, 832],
  "face_bottom": 304,
  "keep_out": [
    {"name": "ai_label", "box": [402, 8, 472, 68]},
    {"name": "watermark", "box": [0, 0, 90, 30]}
  ]
}
```

- `face_bottom` = max y2 trong `coords` của mọi clip đã nạp (`avatar.ailive_clips`).
- App so với ước lượng của mình; khác thì vẽ lại lớp theo số của fork. Mỗi lần nhận `hello` (khởi động, nối lại, fork khởi động lại),
  app gửi lại các lớp hiện có.

## 4. fork → app: `stats.scene_ms`

`stats` có thêm `scene_ms` (số thực, ms trung bình mỗi khung để trộn cảnh trong lượt; `0.0` khi không có lớp). App đưa vào
`RenderTurnStats.scene_ms` và cột `scene_ms` của `/api/latency` (FR-022).

## 5. Nơi trộn trong fork

`avatars/base_avatar.py` `process_frames`: sau `ailive_fade.apply(...)`, trước `cv2.putText(... "LiveTalking" ...)` và
`ailive_label.apply(...)`, có dòng móc `# ailive: scene` (`ailive_ext/scene.py`). Trộn trên khung BGR uint8:
`roi = (roi·inv_a + premult) // 255`.

- Trộn trên **bản sao** khung: khung idle là mảng gốc của clip (upstream không sao chép), mà trộn alpha không lũy đẳng.
- Mỗi lớp được chuẩn bị một lần khi nhận. Lớp có ≤ 10% điểm bán trong suốt thì chép điểm đục và chỉ trộn từng điểm bán trong suốt;
  còn lại trộn cả vùng. Đo trên CPU laptop: lớp `base` thật 480×382 khoảng 3,5 ms/khung.
- Lỗi khi trộn: log một lần, bỏ lớp đó (khung vẫn ra, FR-021).
- `face_bottom` lấy từ `avatar.ailive_clips` (mọi clip) hoặc, với avatar upstream không có clip, từ `coord_list_cycle`. Không đo được
  thì `hello` không có `scene`.

## 6. Kiểm thử

- `ailive_ext/tests/test_scene.py` (venv fork, không GPU): nhận lớp hợp lệ, trộn đúng màu và alpha; từ chối lớp chạm vùng mặt/nhãn/
  watermark; `null` xóa lớp; lớp vượt khung; đo `take_mean_ms`.
- App `tests/integration/test_scene_fork.py`: fork giả nhận `scene_layer`, gửi `hello.scene`; app gửi lại lớp khi nối lại;
  `scene_rejected` không hỏng lượt nói.
