# Tasks: [TÊN TÍNH NĂNG]

- **Feature ID:** `[NNN-slug]` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), research.md, data-model.md, contracts/

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[GPU]**: cần RunPod; không làm trên laptop, gom vào đợt GPU (xem cuối file)
- **[US#]**: thuộc user story nào (US1, US2...). Phase Setup, Foundational và Polish không gắn nhãn này.
- Mỗi task ghi **đường dẫn file cụ thể**. Một task chỉ đủ nhỏ để xong và kiểm chứng trong một lần làm.

<!--
TASK GENERATION RULES (for /sdd.tasks; delete this block in the real file; write task descriptions in Vietnamese)
- Group by user story so each story can be built, tested and demoed independently.
- Test-first: within each story, test tasks come before implementation tasks and must FAIL first.
- Order within a story: models → services/adapters → endpoints/integration.
- No vague tasks like "finish X". No two [P] tasks edit the same file.
-->

## Phase 1: Setup

- [ ] T001 [...]
- [ ] T002 [P] [...]

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

- [ ] T003 [...]

**Checkpoint:** nền tảng sẵn sàng, các story bắt đầu được.

---

## Phase 3: User Story 1: [tiêu đề] (P1) 🎯 MVP

**Mục tiêu:** [story mang lại gì]
**Kiểm thử độc lập:** [lấy từ spec]

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [ ] T010 [P] [US1] Test [kịch bản chấp nhận 1] trong `tests/unit/test_[...].py`
- [ ] T011 [P] [US1] Test [kịch bản chấp nhận 2] trong `tests/integration/test_[...].py`

### Implement US1

- [ ] T012 [P] [US1] [...] trong `src/ai_live/[...]/[...].py`
- [ ] T013 [US1] [...] (phụ thuộc T012)

**Checkpoint:** US1 chạy và test độc lập được. Dừng lại, báo người dùng, demo.

---

## Phase 4: User Story 2: [tiêu đề] (P2)

[cấu trúc giống Phase 3]

---

## Phase N: Hoàn thiện và việc chung

- [ ] TXXX [P] Cập nhật `docs/ARCHITECTURE.md` nếu interface thay đổi
- [ ] TXXX Chạy `quickstart.md` từ đầu đến cuối
- [ ] TXXX `uv run pytest` và `uv run ruff check .` đều sạch
- [ ] TXXX Chạy `/update-context`

## Phụ thuộc và thứ tự

- Setup → Foundational → các user story (theo ưu tiên, hoặc song song nếu độc lập) → Hoàn thiện
- [Phụ thuộc riêng giữa các task, nếu có]

## Chạy song song

- [Nhóm task [P] làm cùng lúc được]

## Đợt GPU (RunPod)

- [Danh sách task [GPU], gom để bật pod một lần] (xem `docs/RUNPOD.md`)

## Chiến lược MVP

1. Setup + Foundational → 2. US1 → **dừng, kiểm chứng, demo** → 3. thêm US2, US3... từng bước một
