# Hợp đồng: giao thức fork cho nền sau host (014)

Bổ sung cho `specs/005-lipsync-livetalking/contracts/fork-protocol.md` và `specs/009-live-scene-layout/contracts/fork-protocol.md`.
Không đổi tin nào đã có; chỉ thêm. Fork không có phần này (bản cũ) vẫn chạy với app mới: app thấy `hello` không có `background` nên rơi về
phòng gốc (`fork_unsupported`).

## 1. Khởi động fork

- Fork đọc phần chuẩn bị nền từ `<ailive_character>/background/` (`--ailive_character` mà `scripts/livetalking/run.ps1` đã truyền, thư mục
  app `assets/avatars/<id>`). Không thêm cờ dòng lệnh hay biến môi trường mới.
- Lúc nạp avatar (sau khi có `frame_list_cycle` và thư viện clip), `ailive_ext.background.load(avatar, character_dir)`:
  - tính dấu vân từng khung (data-model §2), tra mặt nạ, tách sẵn `bg_mask` / `edge_idx` / `edge_alpha` (research R8);
  - đặt `status` = `valid | missing | mismatch` và `reason`. Lỗi không làm fork dừng.

## 2. `hello` (fork → app) thêm khối `background`

```json
{
  "type": "hello",
  "...": "các trường cũ giữ nguyên",
  "background": {
    "status": "valid",
    "reason": null,
    "frames": 81,
    "width": 480,
    "height": 832,
    "method": "plate",
    "reviewed": false
  }
}
```

- `status`: `"valid" | "missing" | "mismatch"`; `reason`: `null` hoặc mã ở data-model §2 (`not_prepared`, `frame_not_prepared:<n>`,
  `size_mismatch`, `character_mismatch`, `mask_unreadable:<file>`).
- Khối luôn có ở fork đã có 014 (kể cả `missing`). Không có khối = fork cũ.

## 3. `scene_background` (app → fork)

```json
{ "type": "scene_background", "png_b64": "<base64 PNG>" }
```

| Trường | Bắt buộc | Ràng buộc |
|---|---|---|
| `png_b64` | có | PNG RGB hoặc RGBA (kênh alpha bị bỏ), **cỡ đúng bằng khung** (`width`×`height` của `hello.background`), ≤ 4 MB sau giải mã base64 (`MAX_PNG_B64` của 009). Có ảnh thì thay ảnh nền đang giữ; `null` thì xoá ảnh nền (phòng gốc) |

- Không có luật vùng mặt / nhãn / watermark như lớp cảnh 009: ảnh nền nằm **dưới** người (chỉ hiện ở chỗ mặt nạ là nền).
- Áp từ khung kế tiếp.
- App gửi tin này **sau mỗi `hello`** (fork khởi động lại thì gửi lại) và khi ảnh nền phải vẽ lại (áp bộ sản phẩm mới 012). Không có công
  tắc bật/tắt khi live (spec, làm rõ 2026-11-24): muốn tắt nền thì đặt `style: "goc"` rồi khởi động lại.
- Nền chỉ hiện khi có ảnh nền **và** `status = "valid"` **và** fork chưa gặp lỗi ghép.
- **Ảnh nền một màu = phông khoá màu** (ADR-102, 2026-11-28): ảnh nền phẳng một màu (chênh từng kênh ≤ 2, như phông xanh `/obs`) là để
  OBS Chroma Key cắt sau. Khi đó fork **không pha mép mềm với màu phông**: điểm có alpha ≥ 200 giữ người **với màu thật của chính nó**,
  thêm 1 px viền ngoài lấy trung bình các điểm được giữ quanh nó trong ô 3×3; còn lại là phông.
  Lý do: mép pha xanh bị Chroma Key cắt giữa chừng rồi khử xanh thành viền xám đen quanh má, cằm, tóc và lẹm cổ áo. Ảnh nền thật (Meet)
  vẫn pha mép mềm như cũ.
  Sửa 2026-11-28 (bản đầu: ngưỡng 128 và tô cả dải mép bằng trung bình người đặc ô 9×9): dải mép mềm bên phải host rộng 5–9 px, tô đè cả
  dải thành một mảng màu trung bình nên má, tai, cổ bị nhoè và còn vệt xám xanh. Ngưỡng 200 chỉ giữ điểm gần như toàn người (lẫn phòng cũ
  ≤ 22%) nên giữ được chi tiết thật mà không lộ màu phòng; trừ màu phòng theo alpha (`(C − (1−a)·B)/a`) đã thử và bị loại vì alpha ước
  lượng lệch làm tai/cổ áo ửng đỏ, viền tím.
- **Mép mềm hẹp với ảnh nền thật** (2026-11-28, người dùng: "vệt phân giải quanh host", "bên trái host"): khi pha mép với ảnh nền
  thật, fork dùng alpha đã kéo hẹp `a' = clip((a − 120) · 255 / 110, 0, 255)` thay cho alpha gốc. Điểm alpha ≤ 120 là nền, ≥ 230 là
  người, ở giữa pha. Lý do: mặt nạ có dải mềm rộng ở hàm/tai phải (lẫn màu phòng cũ), pha nguyên dải thì má/hàm loang; kéo hẹp vẫn
  khử răng cưa mà mép gọn. Phông khoá màu (mục trên) không đổi.
- **`/obs` có thể dùng ảnh nền thật thay phông xanh** (2026-11-28): đặt ảnh shop (đã cắt khớp vùng host trong khung OBS) làm ảnh nền
  của cảnh `obs_layers` và tắt Chroma Key của nguồn "AI host" trong OBS. Fork ghép mép mềm như Meet, OBS không phải cắt nền nên hết
  viền răng cưa phóng 2,25 lần. Đổi lại phần nền trong vùng host chỉ nét bằng khung fork (480×832 phóng lên).

Lỗi (fork → app), cùng dạng `error` đã có:

```json
{ "type": "error", "kind": "background_rejected", "message": "size 480x800 != frame 480x832" }
{ "type": "error", "kind": "background_failed", "message": "ValueError: ..." }
```

- `background_rejected`: ảnh nền sai cỡ, không giải mã được, quá lớn, hoặc `status ≠ valid` khi nhận ảnh nền (message ghi lý do). Fork giữ
  trạng thái trước đó.
- `background_failed`: ghép lỗi lúc phát. Fork tự về phòng gốc (`failed = true` cho tới khi nhận ảnh nền mới), khung vẫn được đẩy ra (live không dừng), gửi lỗi **một lần**.

## 4. Thứ tự ghép trong `process_frames`

```python
if ailive_clip is not None: combine_frame = ailive_fade.apply(ailive_clip.clip_id, combine_frame)
combine_frame = ailive_background.apply(self, combine_frame, idx, ailive_clip)  # ailive: 014 background, under the host
combine_frame = ailive_scene.apply(self, combine_frame)  # ailive: scene, under the watermark and label
combine_frame = ailive_watermark.apply(combine_frame)
combine_frame = ailive_label.apply(combine_frame)
```

- Áp cho cả khung đứng yên (`frame_list_cycle[idx]` / `ailive_clip.frames[idx]`) lẫn khung đang nói (`paste_back_frame`), sau khi dán
  miệng (research R1).
- `apply` không làm gì (trả nguyên khung) khi nền không hiện, nên chi phí khi tắt ≈ 0.
- Khung đang crossfade giữa hai clip (`ailive_fade`): dùng mặt nạ của khung đích; bóng mờ của khung cũ có thể lộ ở viền trong vài khung
  (RISKS Q44). `character.json` demo không có clip nên không gặp.

## 5. `stats` thêm `background_ms`

```json
{ "type": "stats", "...": "...", "scene_ms": 0.4, "background_ms": 0.2 }
```

Thời gian ghép nền trung bình mỗi khung (ms) từ lần `stats` trước; chỉ có khi fork có 014. `0.0` khi không khung nào được ghép.
Mục tiêu ≤ 4 ms (plan, SC-003).

## 6. Khác với `docs/ARCHITECTURE.md` §3

- Thêm Protocol tuỳ chọn `BackgroundSink` (contracts/adapters.md) cạnh `SceneSink`: chỉ `LiveTalkingRenderer` cài; `StaticRenderer` không
  có nên chế độ tĩnh không đổi. Lõi pipeline không đổi. Ghi vào ARCHITECTURE §3 và sơ đồ cảnh (dòng `SceneController -- scene_layer`)
  khi `/update-context` sau implement.
