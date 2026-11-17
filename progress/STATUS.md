# Trạng thái hiện tại

> Ảnh chụp ngắn, đọc đầu tiên. Mỗi dòng là `key: giá trị`. Sửa theo giao thức ở [README.md](README.md) §3.

- `last_updated`: 2026-11-18
- `branch`: main (không tách branch theo feature, ADR-027)
- `last_commit`: c955600 "ROADMAP M1a: tick items already built and tested in 001" (fork `ailive` local: 477d4e4, còn thay đổi chưa commit, kiểm 2026-11-17); 006, 007, 009, 010 chưa commit
- `current_milestone`: M1a: Logic chạy local — [docs/ROADMAP.md](../docs/ROADMAP.md) mục "M1a"
- `active_feature`: [006-obs-output](FEATURES.md#006-obs-output) — In progress 2026-11-13 (30/35): phần máy không GPU xong, chờ gói duyệt ([006 quickstart](../specs/006-obs-output/quickstart.md) §5) và 4 task `[GPU]`;
  001 (107/116): việc không cần LLM xong 2026-11-13;
  [007-demo-readiness](FEATURES.md#007-demo-readiness) — In progress 2026-11-13 (58/59): phần máy xong (kể cả GPU laptop T054–T056, `REPLY_ENGINE=fake`, không gọi LLM free), chờ người dùng T058;
  [010-natural-mouth-shapes](FEATURES.md#010-natural-mouth-shapes) — In progress 2026-11-13 (30/32: T026 chốt giữ ngưỡng 2026-11-16), phần máy xong, chờ gói duyệt;
  [009-live-scene-layout](FEATURES.md#009-live-scene-layout) Done 2026-11-13 (38/38), chờ gói duyệt;
  [004-show-director](FEATURES.md#004-show-director) — feature chính (ADR-026); [008-llm-provider-chain](FEATURES.md#008-llm-provider-chain) Done 2026-11-05, mở khóa T075–T079 của 004
- `next_step`: **006 chờ người dùng** ([006 quickstart](../specs/006-obs-output/quickstart.md) §5 "Gói duyệt"): cho phép chạy OBS
  portable (T029), thêm nguồn `/obs` trong OBS thật theo RUNBOOK §8 và bấm giờ (SC-001), nghe/xem một bản ghi OBS, xác nhận ADR-058.
  Sau đó các task `[GPU]` T018, T019, T030, T031 trên laptop (fork nhép miệng).
  **007 chờ người dùng** ([007 quickstart](../specs/007-demo-readiness/quickstart.md) "Kết quả kiểm chứng" §5, §6):
  xem video dự phòng `out/backup_video/backup_20261113-1634_demo_customer_01.mp4` và thử phát qua Meet (T058), xác nhận ADR-057,
  xóa `AILIVE_RECORD_DIR=out/selfcheck` khỏi `.env` trước demo; tổng duyệt 30 phút với LLM thật ở T-1 ngày. Không gọi LLM nào trong 007.
  **010 chờ người dùng** (gói duyệt [010 quickstart](../specs/010-natural-mouth-shapes/quickstart.md) §7): chấm A/B
  `out/mouth/runs/r4/ab/PHIEU.md` (≥ 3 người) → nếu `shift=-1` thắng thì ADR mới, đổi mặc định, show 10 phút (T018, T019); giữ hay siết
  ngưỡng góc đầu (T026). Hướng tiếp đã chọn 2026-11-17: thử Ultralight với video huấn luyện tạo bằng InfiniteTalk trên Kaggle (ADR-060). Nhân vật mới `demo_host_02` ngồi bàn trong shop: ảnh tạo bằng `scripts/avatar_clips/make_host_scene.ipynb` (FLUX.1-schnell; lần 2 sửa da "nhựa", chọn mặt mới seed 606; ADR-061 sửa ảnh seed 606 cho giống ảnh chụp thật bằng Qwen-Image-Edit-2511 qua `edit_host_photo.ipynb`, chờ người dùng chọn ảnh); sau đó chạy thử InfiniteTalk 13 giây bằng `make_infinitetalk_video.ipynb`, rồi huấn luyện Ultralight bằng `train_ultralight.ipynb` (đã viết 2026-11-18, chưa chạy, cần video `train_v1` 3–5 phút).
  mặc định giữ `w2l` (ADR-055); `shift=-1` hết lệch hình–tiếng 1 khung. Trong lúc chờ, tự làm tiếp các việc không cần LLM API: đã có bản nháp [RUNBOOK.md](../docs/RUNBOOK.md) (M1d, câu hỏi
  ở OPEN §4).
  Kiểm luồng 2026-11-17 (không sửa code): test, show ảnh tĩnh và show nhép miệng 2 phút đều đạt; so sánh với sản phẩm cùng loại ở
  [VENDORS.md](../docs/VENDORS.md); 6 lỗi nhỏ tìm được đã sửa cùng ngày (đường tắt sửa lỗi, xem [LOG](LOG.md)); các đề xuất còn chờ người dùng
  (đóng băng cấu hình demo, thứ tự ưu tiên M2, RISKS P9) ở [OPEN.md](OPEN.md) §4.
  Trước đó, 009 xong phần máy (2026-11-13): người dùng xem gói duyệt 009 (ảnh bố cục, ảnh thật của khách + SC-007, SC-006,
  ADR-051/052), nói "commit" để commit. Việc cũ: `autonomous_plan` xong phần máy tự làm được (2026-11-12). Còn chờ người dùng: gói duyệt (xem [OPEN.md](OPEN.md) §4:
  `LIVETALKING_LEAD_S` 2,5, batch 16 hay 8, bộ clip nhỏ hơn / RunPod, clip nói đầu nghiêng, danh sách claim ADR-050), 004 T079
  (SC-009 người chấm, tổng duyệt lại ngày riêng, cắm sạc), 005 T068 (3 người xem), T080 (Meet). SEA-LION hết hạn mức ngày; 07:25 2026-11-13 gọi thử vẫn `rate_limited`, freellmapi báo reset tiếp theo 07:00 2026-11-14
  (`retryAtMs` 1794614400001). Khi hạn mức
  reset: chạy lại hồi quy Điều III cho ADR-050 (`qa_eval run` bộ 10 câu hỏi + `qa_eval script` 3 lần bằng SEA-LION), ghi vào ADR-050.
- `autonomous_plan` (người dùng duyệt 2026-11-12, làm liên tục, tự kiểm bằng Chrome DevTools MCP + bộ ghi luồng; đánh dấu
  `[x]` khi xong từng mục; hết hạn mức thì mục đang dở ghi rõ đã tới đâu):
  - [x] 0. Commit repo chính lên `main`; commit trong máy nhánh `ailive` của fork (không push)
  - [x] 1. Bộ tự kiểm: bộ ghi luồng ra mp4 trong fork (cờ env, ngoài git), script phân tích miệng/tiếng/giật/fps/nhãn, test, thử MCP
  - [x] 2. 005 T062–T063
  - [x] 3. 003 T050
  - [x] 4. 004 T075–T080 (LLM thật, hạn mức free; T077 có thể kéo nhiều ngày). T079 chạy một phần (chờ người dùng: SC-009, ngày riêng);
    thêm ADR-050 (guard `unsupported_claim`) và sửa SC-011 (giữ câu kịch bản khi có comment chờ)
  - [x] 5. 005 US3 T064–T067 (T068 cần 3 người thật → để người dùng). T067 đạt 2026-11-12: SC-007 0 chỗ giật; sửa giữ clip nói
    qua các câu kịch bản, đổi sau một vòng, `LIVETALKING_HOLD_S=2.5` (spec phiên 2026-11-12, chờ duyệt trong gói review)
  - [x] 6. 005 US4 T069–T075, T083 (2026-11-12; T075 phần bộ clip nhỏ hơn / RunPod chờ người dùng)
  - [x] 7. 005 T076–T079, T081, `/update-context`, commit; gói duyệt cho người dùng (T080 Meet cần người thật)
- `parallel_features`:
  - [005-lipsync-livetalking](FEATURES.md#005-lipsync-livetalking): `In progress` (2026-11-07), 81/83; US1, US2 xong; US3 xong phần máy (T068 cần người xem); US4 xong (T075 người dùng chốt 2026-11-16: `LEAD_S` 2,5, batch 16, không RunPod); còn T080 Meet
- `paused_features`: [001-local-reply-pipeline](FEATURES.md#001-local-reply-pipeline) (101/116 task, tạm dừng theo ADR-026)
- `blockers`: TODO R2 (nơi đẩy nhánh `ailive` của fork) chưa quyết
- `pending_decisions`: xem [OPEN.md](OPEN.md) (0 câu làm rõ, 2 ADR `Đề xuất`, các `TODO:` chính)
