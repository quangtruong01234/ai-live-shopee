# Kế hoạch triển khai: Khẩu hình miệng host AI giống người thật

- **Feature ID:** `010-natural-mouth-shapes` · **Ngày:** 2026-11-13 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/010-natural-mouth-shapes/spec.md`
- **Ghi chú quy trình:** người dùng giao chạy liên tục specify → … → update-context và cho phép cài tool/repo (2026-11-13), mỗi thứ mới
  có ADR. Plan này viết **sau** khi đã dựng bộ đo và đo vài vòng (research R1–R12), vì hướng kỹ thuật phụ thuộc vào số đo. Những gì cần mắt
  người gom vào gói duyệt cuối (quickstart §7).

## Tóm tắt

Giữ model `wav2lip256` của 005 (model khác như MuseTalk 1.5 chỉ đạt ~0,7 khung/giây trên GPU 4 GB, R4). Chất lượng khẩu hình được nâng
bằng các núm **trong fork**, chọn bằng một biến env `LIVETALKING_MOUTH_METHOD` (cách 005 = `w2l` là dự phòng): ảnh tham chiếu đưa vào model
(`ref`), cách dán vào khung (`paste`, `color`, `sharpen`), độ to mel (`gain_db`) và vị trí cửa sổ tiếng (`shift`, sửa miệng đi trước tiếng
1 khung, R7). Mỗi núm được chấm bằng **bộ đo khách quan** chạy trên laptop (`python -m ailive_ext.mouth_eval`): 24 câu tiếng Việt theo nhóm
âm, MediaPipe đo hình môi (ADR-053), SyncNet đo khớp tiếng (ADR-054), xuất video đặt cạnh nhau và gói xem mù. Cách mặc định chọn theo số
đo (§Quyết định). US3 loại các đoạn clip nói đầu nghiêng lúc `prepare` (góc đầu đo bằng MediaPipe), fork chỉ phát các đoạn còn lại.
App chỉ đổi phần báo cáo (`mouth_method` trong bảng độ trễ, FR-010).

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (app, uv). Fork dùng venv riêng `vendor/livetalking/.venv` (Python 3.12, torch 2.9.1+cu128).
- **Phụ thuộc chính:** như 005 (wav2lip256, OpenCV, numpy, PyAV). **Phụ thuộc MỚI (venv fork, đã có ADR):** `mediapipe` 1.2.3 +
  `face_landmarker.task` (ADR-053), `python_speech_features` 0.6 + `syncnet_v2.model` (ADR-054). App: **không** thêm phụ thuộc.
- **Lưu trữ:** bộ câu `data/eval/mouth_sentences.json` (git); tiếng đọc sẵn `out/mouth/sentences/`, kết quả `out/mouth/runs/` (ngoài
  git); `ailive_pose.json` trong thư mục avatar của clip nói (fork) (ngoài git, cạnh ảnh nhân vật).
- **Kiểm thử:** pytest app (không GPU; fork giả gửi `mouth_method`); pytest fork (`ailive_ext/tests`, không GPU: model giả, ảnh vẽ trong
  test, điểm mốc giả). Bộ đo thật chạy trên GPU laptop, không nằm trong pytest.
- **Nơi chạy:** GPU laptop GTX 1650 Ti 4 GB (ADR-023). Không RunPod.
- **Adapter liên quan:** `AvatarRenderer` (LiveTalking) chỉ thêm trường báo cáo. Không đổi Protocol nào.
- **Mục tiêu hiệu năng:** `render_fps` ≥ 20 trong bộ đo và ≥ 20 trung vị trong show (SC-005); khung đầu chậm thêm ≤ 0,3 s; lặng p95 tăng
  ≤ 0,1 s; VRAM không tăng (cùng model, cùng batch).

## Kiểm tra Constitution (cổng)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt | Mọi núm chạy theo batch lúc phát; `shift` âm chỉ đọc tiếng đã có trong bộ đệm 200 ms của fork. Núm chỉ chạm hộp mặt; cảnh, watermark, nhãn vẽ sau (FR-013). Không tinh chỉnh model (FR-014 không dùng) |
| II. Đồng ý và bảo mật | Đạt | Chỉ dùng clip `demo_host_01` (AI, ADR-036). Video đo, gói A/B, file góc đầu ngoài git |
| III. Trả lời có căn cứ | N/A | Câu mẫu không nêu giá thật hay công dụng; nhóm số dùng số giả để đo |
| IV. Adapter trước | Đạt | Cách tạo miệng chọn bằng env; mặc định `w2l` gọi model y hệt upstream |
| V. Test trước | Đạt | Test fork không GPU cho parse, ref, mel window, paste, pose; bộ đo có test cho các hàm chấm |
| VI. Ngân sách độ trễ | Đạt | Không thêm bước trên đường tiếng; `shift` không thêm độ trễ; đo lại SC-005 bằng show 10 phút |
| VII. Đơn giản trước | Đạt | 2 phụ thuộc chỉ cho bộ đo (ADR-053/054), không vào đường live; không model mới cho live |
| VIII. Quan sát được | Đạt | `mouth_method` trong `hello`, `stats`, `avatar.jsonl`, `/api/latency`; `prepare` báo khung bị loại |
| IX. Ngôn ngữ và tài liệu | Đạt | Code tiếng Anh; báo cáo đo, phiếu A/B, tài liệu tiếng Việt |

Kiểm lại sau Phase 1: vẫn Đạt.

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách | Feature này thay đổi gì | Cách đo |
|------|-----------|-------------------------|---------|
| Tạo hình mỗi khung | ~40 ms/khung (25 fps) | `paste=feather`/`color` thêm ~2–4 ms/khung; `ref`, `shift` gần như 0 | `render_fps` trong bộ đo và `stats` |
| Câu đầu / khung đầu | ≤ 5 s | Không đổi (≤ +0,3 s cho phép) | bảng độ trễ, show 10 phút |
| Lặng giữa câu | p95 ≤ 1,5 s | Không đổi (≤ +0,1 s cho phép) | show 10 phút |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/010-natural-mouth-shapes/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md · tasks.md
└── contracts/
    ├── mouth-method.md   # LIVETALKING_MOUTH_METHOD, hành vi lỗi, mouth_method trong hello/stats
    └── mouth-eval.md     # CLI bộ đo, chỉ số, gói xem mù
```

### Mã nguồn
```
vendor/livetalking/ailive_ext/mouth.py                 # MouthMethod, parse, reference_faces, mel_window_start, apply_gain, paste
vendor/livetalking/ailive_ext/mouth_eval/{__main__,render,score,syncnet,report}.py   # bộ đo (US2)
vendor/livetalking/ailive_ext/pose.py                  # US3: góc đầu từng khung, đoạn dùng được, ailive_pose.json
vendor/livetalking/ailive_ext/prepare.py, clips.py     # US3: ghi file lúc prepare, cắt clip nói theo đoạn dùng được lúc nạp
vendor/livetalking/avatars/{base_avatar,wav2lip_avatar}.py, avatars/audio_features/mel.py   # móc `# ailive:` (010)
vendor/livetalking/ailive_ext/ingest.py                # mouth_method trong hello và stats
vendor/livetalking/ailive_ext/tests/test_{mouth,mouth_eval,wav2lip_mouth,pose,clips}.py
scripts/mouth/synth_sentences.py                       # đọc bộ câu bằng VieNeu (app venv)
data/eval/mouth_sentences.json
src/ai_live/avatar/livetalking_renderer.py, core/models.py, director/{latency,render_report,session_log}.py,
  app/static/control.js                                # FR-010: cột "Miệng"
src/ai_live/avatar/__main__.py                         # US3: in góc đầu từng clip nói sau `prepare`
tests/unit/test_livetalking_renderer.py, tests/unit/test_session_log_avatar.py, tests/unit/test_avatar_cli.py,
  tests/integration/test_avatar_api.py
```

## Phase 0: Nghiên cứu → `research.md`

Đã xong R1–R12: thước đo, "ph", độ nét so với clip gốc, MuseTalk bị loại vì tốc độ, ảnh tham chiếu cố định bị loại, các núm hậu kỳ (r1),
cửa sổ tiếng lệch (r2), dự phòng, torchaudio, ảnh tham chiếu môi khép (r3), góc đầu trong clip nói (R11), lần đo lặp lại và gói A/B (r4).

## Quyết định

- **Cách mặc định:** giữ `w2l` (ADR-055). Không cách hậu kỳ nào đạt SC-001. Ứng viên `shift=-1` (hết lệch hình–tiếng theo SyncNet) chờ
  người dùng xem gói A/B r4; đổi thì sửa `.env.example` và `docs/ARCHITECTURE.md`.
- **Ngưỡng góc đầu (US3):** lệch so với trung vị idle quá roll 35° / pitch 20° / yaw 30°, đoạn dùng được tối thiểu 2 s, cảnh báo khi còn
  < 4 s (ADR-056, research R11).
- **`ref=closed:W`:** chỉ trong bộ đo, không đưa vào live (R10).

## ADR đã ghi

- **ADR-055:** cách tạo miệng của fork chọn bằng `LIVETALKING_MOUTH_METHOD` (các khóa ở contracts/mouth-method.md), mặc định theo số đo
  010; giữ wav2lip256, loại MuseTalk 1.5 trên laptop vì ~0,7 khung/giây.
- **ADR-056:** US3: loại khung clip nói có góc đầu lệch quá ngưỡng lúc `prepare`, fork chỉ phát các đoạn dùng được.

## Rủi ro mới (đã vào `docs/RISKS.md`: L13, Q22–Q24)

- `mediapipe` kéo `opencv-python-headless` vào venv fork cùng OpenCV có sẵn (ADR-053) → `docs/RISKS.md`.
- Số SyncNet/MediaPipe chỉ so được giữa các cách trên cùng nhân vật; đổi nhân vật phải đo lại baseline → `docs/RISKS.md`.
- Clip nói còn quá ngắn sau khi loại đoạn nghiêng → lặp lộ; `prepare` cảnh báo, việc làm lại clip là việc riêng.
