# Danh mục feature (specs)

> Mỗi feature có một thư mục `specs/NNN-slug/`, được tạo bởi `/sdd.specify`. Quy trình ở `docs/WORKFLOW.md`.
> Các lệnh `/sdd.*` cập nhật cột Trạng thái của bảng dưới đây.

| ID | Tên | Mốc | Trạng thái |
|----|-----|-----|------------|
| [001-local-reply-pipeline](001-local-reply-pipeline/spec.md) | Pipeline trả lời comment chạy local | M1a | Tasked (tạm dừng, ADR-026) |
| [003-vietnamese-tts](003-vietnamese-tts/spec.md) | Giọng tiếng Việt thật cho AI host | M1a | Planned |
| [004-show-director](004-show-director/spec.md) | AI host tự nói kịch bản giới thiệu sản phẩm, sinh realtime | M1a | Draft |
| [005-lipsync-livetalking](005-lipsync-livetalking/spec.md) | AI host nhép miệng realtime trên laptop | M1b | Clarified |

## Gợi ý chia feature cho M1 (chưa tạo, chỉ là đề xuất)

Mỗi dòng là một lần `/sdd.specify`. Thứ tự đi theo ROADMAP; người dùng có thể gộp, tách hoặc đổi.

| Đề xuất ID | Nội dung | Mốc | Cần GPU |
|-----------|----------|-----|---------|
| 001-local-reply-pipeline | Người vận hành gõ comment mock, hệ thống chọn theo ưu tiên, trả lời dựa trên dữ liệu sản phẩm, đọc bằng TTS giả hoặc thật, hiển thị avatar tĩnh; có log độ trễ | M1a | Không |
| ~~002-product-qa-eval~~ | Đã gộp vào `001` (User Story 5), chốt khi clarify 2026-10-30 | M1a | Không |
| 003-vietnamese-tts | Giọng tiếng Việt thật qua adapter (ElevenLabs hoặc OSS), streaming, chuẩn hóa số/giá | M1a | Không |
| 004-show-director | **Ưu tiên tiếp theo (ADR-026).** Host nói kịch bản giới thiệu sản phẩm liên tục, sinh realtime từ dữ liệu sản phẩm | M1a | Không |
| 005-lipsync-livetalking | Avatar nhép miệng realtime qua fork LiveTalking, có nhãn AI, xem qua WebRTC | M1b | GPU laptop, chấp nhận chậm (ADR-023) |
| 006-youtube-live | Đẩy RTMP lên YouTube Unlisted (phần đọc comment tạm hoãn, ADR-026) | M1c | Có (phần RTMP + avatar) |
| 007-demo-readiness | Chạy liên tục 30 phút, watchdog cơ bản, runbook, video dự phòng | M1d | Có |

Đã chốt (2026-10-30): gộp `002` vào `001`. Feature tiếp theo vẫn giữ số theo bảng (003, 004...).
Đã chốt (2026-10-31, ADR-026): tạm không làm phần đọc chat để trả lời người xem; `004` thành feature chính tiếp theo.
