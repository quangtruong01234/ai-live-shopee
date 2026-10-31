# Đặc tả tính năng: [TÊN TÍNH NĂNG]

- **Feature ID:** `[NNN-slug]` · **Branch:** `[NNN-slug]` · **Ngày tạo:** [YYYY-MM-DD]
- **Trạng thái:** Draft <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** [M1a / M1b / ...]
- **Mô tả gốc:** "[mô tả người dùng đưa vào /sdd.specify]"

<!--
SPEC WRITING RULES (guidance in English; write the spec itself in Vietnamese)
- The spec describes WHAT and WHY, not HOW. Do not name frameworks, libraries, classes or file structure.
- Target reader: the project owner, not a developer.
- Mark anything unclear with [NEEDS CLARIFICATION: specific question]; never guess. At most 3 markers; for the rest
  use a sensible default and record it under "Giả định".
- Delete sections that do not apply; do not leave "N/A".
-->

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

<!--
Each user story is an INDEPENDENTLY TESTABLE slice: building that story alone yields a demoable result.
Order by priority P1 (most important, the MVP), P2, P3...
-->

### User Story 1: [Tiêu đề ngắn] (Ưu tiên: P1)

[Mô tả hành trình bằng ngôn ngữ thường: ai làm gì, để được gì]

**Vì sao ưu tiên này:** [giá trị mang lại, lý do đứng trước]

**Kiểm thử độc lập:** [cách kiểm chứng riêng story này và kết quả thấy được]

**Kịch bản chấp nhận:**
1. **Given** [trạng thái ban đầu], **When** [hành động], **Then** [kết quả mong đợi]
2. **Given** ..., **When** ..., **Then** ...

---

### User Story 2: [Tiêu đề ngắn] (Ưu tiên: P2)

[...]

### Trường hợp biên

- Điều gì xảy ra khi [điều kiện biên, ví dụ: không có comment, comment dồn dập, API lỗi, mất mạng]?
- Hệ thống xử lý thế nào khi [tình huống lỗi]?

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

- **FR-001**: Hệ thống PHẢI [năng lực cụ thể, kiểm thử được]
- **FR-002**: Người vận hành PHẢI có thể [...]
- **FR-003**: Hệ thống PHẢI [...] [NEEDS CLARIFICATION: ví dụ câu hỏi]

### Ràng buộc từ Hiến pháp

<!-- Tick the relevant articles and state the concrete requirement for this feature. Delete irrelevant lines. -->
- [ ] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): [...]
- [ ] Điều II (đồng ý / bảo mật): [...]
- [ ] Điều III (trả lời có căn cứ): [...]
- [ ] Điều VI (độ trễ): [feature này chiếm bao nhiêu trong ngân sách < 5 giây]

### Thực thể chính *(nếu feature có dữ liệu)*

- **[Thực thể]**: [là gì, thuộc tính chính ở mức khái niệm, quan hệ]

## Tiêu chí thành công *(bắt buộc)*

<!-- Measurable and technology-agnostic. Good: "trả lời đúng ≥ 8/10 câu hỏi mẫu". Bad: "API trả về 200". -->
- **SC-001**: [chỉ số đo được]
- **SC-002**: [...]

## Giả định

- [Mặc định đã chọn khi mô tả không nói rõ, kèm lý do ngắn]

## Ngoài phạm vi

- [Những gì feature này cố ý KHÔNG làm]

## Làm rõ

<!-- /sdd.clarify writes here. One subsection per session. -->
### Phiên [YYYY-MM-DD]
- Q: [câu hỏi] → A: [câu trả lời]

## Checklist chất lượng spec

- [ ] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [ ] Mọi FR đều kiểm thử được và không mơ hồ
- [ ] Mọi SC đều đo được và không phụ thuộc công nghệ
- [ ] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [ ] Trường hợp biên đã liệt kê
- [ ] Phạm vi và ngoài phạm vi rõ ràng
- [ ] Ràng buộc Hiến pháp liên quan đã được nêu
- [ ] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại)
