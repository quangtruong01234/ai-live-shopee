# Mô hình dữ liệu: Khẩu hình miệng host AI giống người thật

- **Feature ID:** `010-natural-mouth-shapes` · **Ngày:** 2026-11-13 · **Plan:** [plan.md](./plan.md)
- Không có DB. Mọi thứ là cấu hình env, file JSON và file kết quả đo ngoài git.

## 1. Cách tạo miệng (`MouthMethod`, fork `ailive_ext/mouth.py`)

Đọc **một lần** khi fork khởi động từ `LIVETALKING_MOUTH_METHOD` (cú pháp: [contracts/mouth-method.md](./contracts/mouth-method.md)).

| Trường | Kiểu | Mặc định (`w2l`) | Ý nghĩa |
|---|---|---|---|
| `name` | str | `w2l` | tên preset hoặc chuỗi cấu hình gốc; ghi vào `stats.mouth_method` (FR-010) |
| `ref_offset` | int | 0 | `ref=offset:N`: ảnh tham chiếu là khung cách N bước trong clip (theo con trỏ phản chiếu) |
| `ref_closed` | int ≥ 0 | 0 | `ref=closed:W`: ảnh tham chiếu là khung môi khép nhất trong ±W khung; cần độ mở từng khung của clip |
| `feather` | bool | false | `paste=feather`: dán mềm nửa dưới mặt thay cho dán cả hộp |
| `color` | bool | false | chỉnh màu vùng miệng theo clip gốc |
| `sharpen` | float ≥ 0 | 0 | làm nét vùng dán (unsharp mask) |
| `gain_db` | float | 0 | dời mel đưa vào model (độ to) |
| `mel_shift` | int | 0 | `shift=N`: dời cửa sổ tiếng N khung (âm = sớm hơn), research R7 |

- **Ràng buộc:** khóa lạ, giá trị sai kiểu, `closed:0` → `MouthMethodError`; khi khởi động thì log lỗi và dùng `w2l` (FR-005).
- `is_upstream` đúng khi mọi trường bằng mặc định: fork gọi model **y hệt** upstream (không truyền ảnh tham chiếu riêng).
- Không có trạng thái chuyển: đổi cách tạo miệng = sửa `.env` rồi khởi động lại fork.

## 2. Bộ câu mẫu (`data/eval/mouth_sentences.json`, trong git)

| Trường | Ý nghĩa |
|---|---|
| `version` | số phiên bản bộ câu; đổi câu thì tăng, kết quả đo khác phiên bản không so trực tiếp |
| `sentences[].id` | `a1`…`n6`, `p1`… (duy nhất) |
| `sentences[].group` | `vowel_a`, `vowel_i`, `vowel_u`, `vowel_o`, `bilabial`, `natural`, `number` |
| `sentences[].text` | câu tiếng Việt; không nêu công dụng sản phẩm; giá trong nhóm `number` là số giả để đo, không phải giá thật |

- Tiếng đọc sẵn: `out/mouth/sentences/<id>.wav` (16 kHz mono, VieNeu, ngoài git) do `scripts/mouth/synth_sentences.py` tạo. Chỉ là
  đầu vào đo, **không phát ra live**.

## 3. Lần đo (`out/mouth/runs/<tên>/`, ngoài git)

- `report.json`: `meta` (thời điểm, nhân vật, số câu, bộ câu, model, GPU, `peak_gpu_mb`, `closed_gap`, `batch`), `summaries[]` (một dòng
  mỗi cách: các chỉ số FR-006, `render_fps`, `spec`, `pass`), `sentences[]` (một dòng mỗi cách × câu). Schema:
  [contracts/mouth-eval.md](./contracts/mouth-eval.md).
- `report.md`: bảng tóm tắt tiếng Việt, đánh dấu cách tốt hơn baseline ở từng chỉ số.
- Với `--clips`: `clips/<cách>/<đoạn>.mp4`, `side_by_side/<đoạn>.mp4`, và với `--ab`: `ab/` (cặp X/Y xáo thứ tự, `PHIEU.md`) và `ab_key.json`.

## 4. Đoạn clip nói dùng được (US3, `ailive_pose.json` trong thư mục avatar của clip)

Viết lúc chuẩn bị nhân vật (`prepare`, sau `genavatar`), chỉ cho clip `talk`. Ngoài git (thư mục `data/` của fork).

| Trường | Ý nghĩa |
|---|---|
| `version` | 1 |
| `limits` | ngưỡng đã dùng: `roll_deg`, `pitch_deg`, `yaw_deg` (độ lệch so với `reference`), mặc định 35 / 20 / 30 |
| `reference` | tư thế trung vị của **mọi khung clip idle** (`pitch`, `yaw`, `roll`, độ). Lấy idle làm gốc để bù lệch cố định của bộ đo và tư thế nghỉ của host (demo_host_01 nghiêng sẵn khoảng 16°) |
| `frames` | số khung của clip |
| `excluded` | danh sách `{start, end, reason}` (khung `start`..`end` **bao gồm**); `reason` = `roll`/`pitch`/`yaw` (trục đầu tiên vượt ngưỡng), `no_face`, hoặc `short` (đoạn dùng được ngắn hơn `min_usable`) |
| `usable` | các khoảng còn dùng được `{start, end}` (bao gồm hai đầu) |
| `pose` | góc từng khung `[pitch, yaw, roll]` (độ; `null` khi không thấy mặt), để xem lại hoặc chỉnh ngưỡng mà không đo lại |

- **Góc:** từ ma trận biến đổi khuôn mặt của MediaPipe (ADR-053): pitch = atan2(R21, R22), yaw = asin(−R20), roll = atan2(R10, R00). Độ lệch
  so với `reference` tính vòng quanh ±180°.
- **Ràng buộc:** khoảng dùng được ngắn hơn `min_usable` (50 khung, 2 s) bị bỏ (`short`); tổng khung dùng được < min(100, số khung clip)
  → `warning: talk_too_short` trong kết quả `prepare`, không tự tạo lại clip (US3 kịch bản 3).
- **Không đo được** (thiếu `face_landmarker.task`, MediaPipe lỗi): không viết file, kết quả `prepare` ghi `pose: {"skipped": "<lý do>"}`,
  `prepare` vẫn `ready`, clip nói phát nguyên đoạn.
- **Fork đọc lúc khởi động:** không có file, JSON hỏng (log lỗi), hoặc `frames` khác số khung clip đã nạp → cả clip dùng được (nhân vật
  chuẩn bị trước 010 vẫn chạy như cũ). Nhiều khoảng → nhiều clip nói `talk_01~1`, `talk_01~2`, ... (fork-protocol §4 của 005). Mọi clip
  nói đều rỗng → phát nguyên clip.
- **Kết quả `prepare` (JSON, mỗi clip nói):** `pose: {usable_frames, excluded, warning}`; CLI app `python -m ai_live.avatar prepare` in
  "góc đầu: dùng N khung, loại M đoạn" và từng đoạn bị loại. Cờ chỉnh ngưỡng của fork: `--max-roll`, `--max-pitch`, `--max-yaw`.
