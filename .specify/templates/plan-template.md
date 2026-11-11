# Kế hoạch triển khai: [TÊN TÍNH NĂNG]

- **Feature ID:** `[NNN-slug]` · **Ngày:** [YYYY-MM-DD] · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/[NNN-slug]/spec.md`

<!--
The plan answers HOW (guidance in English; write the plan itself in Vietnamese).
Every technical choice must trace back to an FR/SC in the spec.
Resolve unknowns in Phase 0 (research.md); never guess.
Delete sections that do not apply.
-->

## Tóm tắt

[Yêu cầu chính của spec và hướng kỹ thuật, trong 3–5 câu]

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, `.python-version`, ADR-020)
- **Phụ thuộc chính:** [gói đang dùng] · **Phụ thuộc MỚI cần duyệt:** [tên gói, lý do] hoặc "không có"
- **Lưu trữ:** [JSON / SQLite / không có]
- **Kiểm thử:** [pytest; mock nào; test nào cần API thật hoặc GPU]
- **Nơi chạy:** [laptop `AVATAR_MODE=static` / GPU laptop lip-sync (ADR-023) / RunPod dự phòng, cần duyệt chi phí]
- **Adapter liên quan:** [CommentSource / CommentQueue / ProductStore / ReplyEngine / TTSEngine / AvatarRenderer / OutputSink]
- **Mục tiêu hiệu năng:** [ví dụ: câu đầu từ LLM ≤ 1.5 s]
- **Ràng buộc khác:** [...]

## Kiểm tra Constitution (cổng)

*Phải ĐẠT trước Phase 0, và kiểm tra lại sau Phase 1.* Vi phạm thì ghi vào "Theo dõi độ phức tạp" hoặc sửa thiết kế.

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt / Vi phạm / N/A | |
| II. Đồng ý và bảo mật | | |
| III. Trả lời có căn cứ | | |
| IV. Adapter trước | | |
| V. Test trước (GPU: laptop trước, RunPod dự phòng) | | |
| VI. Ngân sách độ trễ (kịch bản: câu đầu ≤ 5 s, lặng p95 ≤ 1,5 s; comment < 5 s p95) | | |
| VII. Đơn giản trước (không hạ tầng hay abstraction thừa, dependency mới có ADR) | | |
| VIII. Quan sát được (mốc `utterance_id`; câu kịch bản có `segment_id`, `segment_requested`) | | |
| IX. Ngôn ngữ và tài liệu | | |

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| [...] | | | |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/[NNN-slug]/
├── spec.md          # /sdd.specify (+ /sdd.clarify)
├── plan.md          # file này
├── research.md      # Phase 0
├── data-model.md    # Phase 1
├── contracts/       # Phase 1: Protocol, API HTTP, schema sự kiện
├── quickstart.md    # Phase 1: cách chạy và kiểm chứng bằng tay
└── tasks.md         # /sdd.tasks
```

### Mã nguồn (đường dẫn thật, xóa dòng không dùng)
```
src/ai_live/[module]/[file].py
tests/[unit|integration]/test_[...].py
```

## Phase 0: Nghiên cứu → `research.md`

Với mỗi ẩn số (NEEDS CLARIFICATION còn lại, lựa chọn thư viện, best practice), ghi theo dạng:
- **Quyết định:** [...] · **Lý do:** [...] · **Phương án đã cân nhắc:** [...]

## Phase 1: Thiết kế → `data-model.md`, `contracts/`, `quickstart.md`

- **data-model.md:** thực thể, trường, ràng buộc kiểm tra và chuyển trạng thái, lấy từ "Thực thể chính" của spec.
- **contracts/:** Protocol của adapter, endpoint HTTP/WebSocket, schema sự kiện. Phải khớp `docs/ARCHITECTURE.md` §3;
  nếu khác thì nêu rõ và đề xuất ADR.
- **quickstart.md:** các bước chạy và kiểm chứng từng user story bằng tay, ghi rõ bước nào cần GPU (laptop trước, RunPod dự phòng).

## ADR cần ghi

- [ADR đề xuất: tiêu đề + quyết định một dòng] (ghi vào `docs/DECISIONS.md` với trạng thái `Đề xuất`)

## Rủi ro mới

- [Rủi ro → thêm vào `docs/RISKS.md`]

## Theo dõi độ phức tạp

*Chỉ điền khi Kiểm tra Constitution có vi phạm cần biện minh.*

| Vi phạm | Vì sao cần | Phương án đơn giản hơn bị loại vì |
|---------|-----------|-----------------------------------|
| | | |
