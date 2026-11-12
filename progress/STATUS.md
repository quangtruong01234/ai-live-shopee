# Trạng thái hiện tại

> Ảnh chụp ngắn, đọc đầu tiên. Mỗi dòng là `key: giá trị`. Sửa theo giao thức ở [README.md](README.md) §3.

- `last_updated`: 2026-11-13
- `branch`: main (không tách branch theo feature, ADR-027)
- `last_commit`: commit "005 US4 T073–T082" ngay sau 2c7bbf3 (fork `ailive` local: 2455b3c)
- `current_milestone`: M1a: Logic chạy local — [docs/ROADMAP.md](../docs/ROADMAP.md) mục "M1a"
- `active_feature`: [004-show-director](FEATURES.md#004-show-director) — feature chính tiếp theo (ADR-026); [008-llm-provider-chain](FEATURES.md#008-llm-provider-chain) Done 2026-11-05, mở khóa T075–T079 của 004
- `next_step`: `autonomous_plan` xong phần máy tự làm được (2026-11-12). Còn chờ người dùng: gói duyệt (xem [OPEN.md](OPEN.md) §4:
  `LIVETALKING_LEAD_S` 2,5, batch 16 hay 8, bộ clip nhỏ hơn / RunPod, clip nói đầu nghiêng, danh sách claim ADR-050), 004 T079
  (SC-009 người chấm, tổng duyệt lại ngày riêng, cắm sạc), 005 T068 (3 người xem), T080 (Meet). SEA-LION hết hạn mức ngày (freellmapi báo reset 07:00 2026-11-13). Khi hạn mức
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
  - [005-lipsync-livetalking](FEATURES.md#005-lipsync-livetalking): `In progress` (2026-11-07), 80/83; US1, US2 xong; US3 xong phần máy (T068 cần người xem); US4 đo xong 2026-11-12 (T075 phần cuối chờ người dùng); còn T080 Meet
- `paused_features`: [001-local-reply-pipeline](FEATURES.md#001-local-reply-pipeline) (101/116 task, tạm dừng theo ADR-026)
- `blockers`: TODO R2 (nơi đẩy nhánh `ailive` của fork) chưa quyết
- `pending_decisions`: xem [OPEN.md](OPEN.md) (0 câu làm rõ, 2 ADR `Đề xuất`, các `TODO:` chính)
