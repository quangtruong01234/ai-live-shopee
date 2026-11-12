# Trạng thái hiện tại

> Ảnh chụp ngắn, đọc đầu tiên. Mỗi dòng là `key: giá trị`. Sửa theo giao thức ở [README.md](README.md) §3.

- `last_updated`: 2026-11-12
- `branch`: main (không tách branch theo feature, ADR-027)
- `last_commit`: afd1477 — 005 T062: fix skip tail audio and pause playing an unheard sentence (fork `ailive` local: cd4ef4d stop drops all speech)
- `current_milestone`: M1a: Logic chạy local — [docs/ROADMAP.md](../docs/ROADMAP.md) mục "M1a"
- `active_feature`: [004-show-director](FEATURES.md#004-show-director) — feature chính tiếp theo (ADR-026); [008-llm-provider-chain](FEATURES.md#008-llm-provider-chain) Done 2026-11-05, mở khóa T075–T079 của 004
- `next_step`: đang làm `autonomous_plan` mục 4: 004 T075–T080. Mục 2 (T062, T063) và mục 3 (003 T050, 003 Done) xong 2026-11-12.
- `autonomous_plan` (người dùng duyệt 2026-11-12, làm liên tục, tự kiểm bằng Chrome DevTools MCP + bộ ghi luồng; đánh dấu
  `[x]` khi xong từng mục; hết hạn mức thì mục đang dở ghi rõ đã tới đâu):
  - [x] 0. Commit repo chính lên `main`; commit trong máy nhánh `ailive` của fork (không push)
  - [x] 1. Bộ tự kiểm: bộ ghi luồng ra mp4 trong fork (cờ env, ngoài git), script phân tích miệng/tiếng/giật/fps/nhãn, test, thử MCP
  - [x] 2. 005 T062–T063
  - [x] 3. 003 T050
  - [ ] 4. 004 T075–T080 (LLM thật, hạn mức free; T077 có thể kéo nhiều ngày)
  - [ ] 5. 005 US3 T064–T067 (T068 cần 3 người thật → để người dùng)
  - [ ] 6. 005 US4 T069–T075, T083
  - [ ] 7. 005 T076–T079, T081, `/update-context`, commit; gói duyệt 2–3 phút cho người dùng (T080 Meet cần người thật)
- `parallel_features`:
  - [005-lipsync-livetalking](FEATURES.md#005-lipsync-livetalking): `In progress` (2026-11-07), 63/83; US1, US2 xong (T062–T063 đạt 2026-11-12; US2 #1 giữ clip nói chuyển sang US3); tiếp US3 T064–T067
- `paused_features`: [001-local-reply-pipeline](FEATURES.md#001-local-reply-pipeline) (101/116 task, tạm dừng theo ADR-026)
- `blockers`: TODO R2 (nơi đẩy nhánh `ailive` của fork) chưa quyết
- `pending_decisions`: xem [OPEN.md](OPEN.md) (0 câu làm rõ, 2 ADR `Đề xuất`, các `TODO:` chính)
