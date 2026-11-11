# Trung tâm tiến độ (`progress/`)

> Một chỗ duy nhất để biết **đang ở đâu, làm gì tiếp, còn chờ quyết định gì**. Các lệnh `/sdd.*`, `/update-context` và các
> sub-agent `ai-*` đọc thư mục này **trước tiên**, chỉ mở file khác khi thẻ feature hoặc bước đang chạy cần tới (ADR-028).
> Key (`current_milestone`, `status`...) giữ tiếng Anh để lệnh tìm được; giá trị và ghi chú viết tiếng Việt.

## 1. File nào giữ sự thật nào

| File | Giữ cái gì | Ai ghi |
|------|-----------|--------|
| [STATUS.md](STATUS.md) | Ảnh chụp hiện tại: mốc, feature đang làm, bước kế tiếp, việc bị chặn | Mọi lệnh `/sdd.*` (trừ analyze), `/update-context` |
| [FEATURES.md](FEATURES.md) | Sổ đăng ký feature: trạng thái, artifact, tiến độ task, ADR liên quan, phụ thuộc, agent | `/sdd.*`, `/sdd.dispatch`, `/update-context` |
| [OPEN.md](OPEN.md) | Câu hỏi và quyết định đang chờ người dùng (làm rõ, ADR `Đề xuất`, sửa hiến pháp, `TODO:` quan trọng) | Lệnh nào tạo ra hoặc giải quyết câu hỏi thì sửa |
| [LOG.md](LOG.md) | Nhật ký chỉ ghi thêm: ngày, lệnh, file đổi, commit | Mọi lệnh có sửa file |

Thư mục này **không chép lại** nội dung gốc, chỉ tóm tắt và trỏ link. Nguồn gốc vẫn là:

| Sự thật | Nguồn gốc (sửa ở đây trước) | Bản tóm tắt trong `progress/` |
|---------|------------------------------|-------------------------------|
| Trạng thái một feature | dòng "Trạng thái" trong `specs/NNN-slug/spec.md` | FEATURES (bảng + thẻ) |
| Task xong / còn lại | `[x]` / `[~]` / `[ ]` trong `specs/NNN-slug/tasks.md` | FEATURES cột Tasks |
| Câu hỏi chưa rõ của spec | `[NEEDS CLARIFICATION]` trong `spec.md` | OPEN §1 |
| Quyết định | `docs/DECISIONS.md` | OPEN §2 (chỉ ADR chưa chốt), thẻ feature (số ADR) |
| Mốc và checklist dài hạn | `docs/ROADMAP.md` | STATUS `current_milestone` |
| Luật | `.specify/memory/constitution.md` | OPEN §3 (chỉ phần chờ sửa) |

## 2. Khi đổi X thì rà Y

Khi sửa một file ở cột trái, rà các chỗ ở cột phải. Mẹo tìm chỗ phụ thuộc: `grep -rn "ADR-026" docs specs progress .claude`.

| Đổi gì | Rà lại |
|--------|--------|
| Trạng thái trong `spec.md` | FEATURES (bảng + thẻ), STATUS `active_feature` / `next_step`, LOG |
| Tick task trong `tasks.md` | FEATURES cột Tasks; khi xong hết → trạng thái `Done`, ROADMAP mục tương ứng |
| Thêm hoặc bỏ `[NEEDS CLARIFICATION]` | OPEN §1, thẻ feature dòng `open` |
| Thêm ADR / đổi trạng thái ADR | OPEN §2, thẻ feature dòng `adrs`, `CLAUDE.md` nếu là ràng buộc, `docs/ARCHITECTURE.md` nếu đổi interface |
| ADR bị thay thế (`Thay thế bởi ADR-xxx`) | Mọi spec/plan nhắc ADR cũ (grep), PRD, ROADMAP |
| Sửa hiến pháp | Template trong `.specify/templates/`, `.claude/commands/sdd.*`, `CLAUDE.md`, `docs/WORKFLOW.md`, feature `Planned` trở lên trong FEATURES, OPEN §3 |
| Đổi phạm vi trong `docs/PRD.md` | ROADMAP, các spec liên quan, OPEN §4 |
| Đổi mốc trong `docs/ROADMAP.md` | STATUS `current_milestone`, cột Mốc trong FEATURES |
| Đổi interface trong `docs/ARCHITECTURE.md` | `contracts/` của các feature `Planned` trở lên |
| Rủi ro mới cần người dùng quyết | OPEN §4 |

## 3. Giao thức cho lệnh và sub-agent

1. **Đầu lệnh:** đọc `STATUS.md`, rồi thẻ của feature đang xử lý trong `FEATURES.md`. Thẻ cho biết thư mục, artifact đã có, ADR liên
   quan, câu hỏi mở. Chỉ mở thêm file mà thẻ trỏ tới hoặc bước đó bắt buộc đọc.
2. **Xác định feature** (khi input không nêu): `active_feature` trong STATUS, sau đó feature số lớn nhất chưa `Done` trong FEATURES.
3. **Cuối lệnh** (nếu lệnh có sửa file): sửa nguồn gốc trước (`spec.md`, `tasks.md`, `DECISIONS.md`), rồi cập nhật FEATURES, STATUS,
   OPEN theo bảng §2, và thêm **một dòng** vào LOG.
4. **Sub-agent `ai-*` chỉ đọc** thư mục này, không sửa. Phiên chính cập nhật sau khi cả đợt báo cáo.
5. `/sdd.analyze` không sửa file nào, trừ việc ghi kết luận vào dòng `analyze` của thẻ feature và một dòng LOG.

| Lệnh | Đọc | Ghi |
|------|-----|-----|
| `/sdd.specify` | STATUS, FEATURES (cả bảng đề xuất) | FEATURES (dòng + thẻ mới, `Draft`), STATUS, OPEN §1, LOG |
| `/sdd.clarify` | STATUS, thẻ feature, OPEN §1 | FEATURES, STATUS, OPEN §1, LOG |
| `/sdd.plan` | STATUS, thẻ feature, OPEN | FEATURES (artifact, `Planned`, ADR), STATUS, OPEN §2, LOG |
| `/sdd.tasks` | STATUS, thẻ feature | FEATURES (`Tasked`, Tasks 0/N), STATUS, LOG |
| `/sdd.analyze` | STATUS, thẻ feature | Chỉ dòng `analyze` của thẻ + LOG |
| `/sdd.implement`, `/sdd.dispatch` | STATUS, thẻ feature | FEATURES (Tasks, `In progress` / `Done`), STATUS, LOG |
| `/sdd.constitution` | OPEN §3, FEATURES | OPEN §3, LOG; liệt kê feature bị ảnh hưởng từ FEATURES |
| `/update-context` | Cả thư mục | Đối chiếu cả thư mục với nguồn gốc (§1), sửa chỗ lệch, LOG |
