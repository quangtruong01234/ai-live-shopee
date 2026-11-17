# Contract: bộ đo khẩu hình `python -m ailive_ext.mouth_eval`

- **Feature:** 010 (US2, FR-006 đến FR-009) · Chạy từ `vendor/livetalking` bằng venv fork, GPU laptop (ADR-023). Chỉ đo, không chạy live.

## 1. Đầu vào

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `--set` | `data/eval/mouth_sentences.json` | bộ câu mẫu (FR-007) |
| `--sentences` | `out/mouth/sentences` | WAV 16 kHz mono mỗi câu, tạo bằng `uv run python scripts/mouth/synth_sentences.py` |
| `--methods` | `w2l` | danh sách `nhãn` (preset) hoặc `nhãn@chuỗi cấu hình`, cách nhau dấu phẩy |
| `--avatar` | `demo_host_01__talk_01` | clip nói dùng để dán |
| `--idle-avatar` | `demo_host_01__idle_01` | clip im lặng để lấy ngưỡng môi khép |
| `--only` | (tất cả) | danh sách id câu |
| `--clips` | tắt | ghi video từng đoạn, video đặt cạnh nhau |
| `--ab NHÃN` / `--baseline NHÃN` | — / `w2l` | tạo gói xem mù so `NHÃN` với baseline |
| `--no-sync` | tắt | bỏ SyncNet |
| `--out` | `out/mouth/runs/<ngày-giờ>` | thư mục kết quả |

Model và file cần có (ngoài git): `models/wav2lip.pth`, `models/face_landmarker.task` (ADR-053), `models/syncnet_v2.model` (ADR-054).

## 2. Cách dựng (giống live)

- Mel 80 bước/s, cửa sổ 16 bước mỗi khung, đệm 200 ms im lặng trước câu như bộ đệm live; vị trí cửa sổ = `mouth.mel_window_start`.
- Mọi cách dùng chung con trỏ clip (chạy tiếp qua các câu, phản chiếu ở hai đầu), batch 8, cùng hàm dán `mouth.paste` với live.

## 3. Chỉ số (`summaries[]`)

| Trường | Ý nghĩa | Tiêu chí |
|---|---|---|
| `lse_c`, `lse_d` | độ tin cậy / khoảng cách SyncNet trung bình | FR-006a, SC-001 (LSE-C không thấp hơn) |
| `closure_recall` | môi khép đếm được / mong đợi ở nhóm `bilabial` | FR-006b, SC-002 ≥ 0,8 |
| `open_ratio` | độ mở trung vị nhóm `a` / nhóm `i`+`u` | FR-006c, SC-003 ≥ 1,5 |
| `spread_ratio` | rộng/cao nhóm `i` / nhóm `u`+`o` | FR-006c, SC-003 ≥ 1,2 |
| `corr_open_loud` | tương quan độ mở – độ to từng khung | FR-006d |
| `sharp_ratio` | độ nét miệng / cùng vùng trên khung clip gốc | FR-006e |
| `silence_closed` | tỷ lệ khung im lặng có môi khép | trường hợp biên |
| `detected` | tỷ lệ khung tìm thấy mặt | phải ≥ 0,95 thì số mới tin được |
| `render_fps` | khung / (thời gian suy luận + dán) | FR-006f, SC-005 ≥ 20 |
| `spec` | chuỗi cấu hình đầy đủ của cách | FR-009 |
| `pass` | `{sc001, sc002, sc003}` so với baseline | báo cáo |

`sentences[]` thêm `sync_offset` (khung; dương = tiếng đi trước hình) và các trung vị từng câu.

## 4. Gói xem mù (`ab/`)

- Mỗi đoạn ~20 s (4 đoạn: `nguyen_am_1`, `nguyen_am_2`, `moi`, `tu_nhien`) ra một cặp `<đoạn>_X.mp4`, `<đoạn>_Y.mp4`; bản nào là X
  được xáo theo seed.
- `ab/PHIEU.md` (phiếu cho người xem, không lộ đáp án), `ab_key.json` ở thư mục lần đo (đáp án, chỉ mở sau khi chấm).
