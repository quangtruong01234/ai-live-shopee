# Mô hình dữ liệu: 001-local-reply-pipeline

> Lấy từ mục "Thực thể chính" của spec. Kiểu ghi theo Python 3.12 (ADR-020). Model bất biến dùng `@dataclass(frozen=True)` hoặc pydantic
> `model_config = ConfigDict(frozen=True)`. Thời điểm đo độ trễ dùng `time.monotonic()`; thời điểm hiển thị dùng `datetime` UTC.

## 1. Comment

Giữ đúng các trường của ARCHITECTURE §2; trạng thái và mức ưu tiên nằm ở `QueuedComment` để `Comment` vẫn bất biến.

| Trường | Kiểu | Ràng buộc |
|--------|------|-----------|
| `id` | `str` | uuid4 hex, duy nhất. Khi ghi log, JSON hay API thì tên trường là `comment_id` |
| `source` | `str` | `"mock"` ở feature này |
| `author` | `str` | cắt 30 ký tự; rỗng, chứa link hoặc chứa từ tục tĩu thì thay bằng `"bạn"` (không đọc tên, research R6, RISKS Q5) |
| `text` | `str` | NFC, gộp khoảng trắng, cắt `COMMENT_MAX_CHARS` (300) |
| `received_at` | `float` | `time.monotonic()` khi API nhận; là mốc `comment_received` |
| `platform_ts` | `datetime \| None` | `None` với mock |
| `meta` | `dict[str, Any]` | `received_wall` (datetime UTC để hiển thị), `truncated: bool` |

### Priority (`IntEnum`, số nhỏ là ưu tiên cao)
`HIGH = 0` (giá, khuyến mãi, cách mua, size/biến thể, tồn kho) · `MEDIUM = 1` (thông số, công dụng, so sánh, câu hỏi khác) · `LOW = 2` (chào, khen)

### DropReason (`StrEnum`)
`empty` "không có nội dung" · `link` "chứa link" · `profanity` "từ ngữ không phù hợp" · `duplicate` "trùng" · `stale` "quá cũ" ·
`queue_full` "hàng đợi đầy". Lệnh bỏ qua của người vận hành áp cho lượt nói (`TurnOutcome.skipped`), không phải lý do loại comment.

### QueuedComment

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `comment` | `Comment` | |
| `priority` | `Priority` | |
| `seq` | `int` | tăng dần, để FIFO trong cùng mức |
| `status` | `CommentStatus` | `waiting` \| `answering` \| `answered` \| `skipped` \| `error` \| `dropped`. Trạng thái cuối ghi vào `comments.jsonl` (contracts/events.md §2) |
| `drop_reason` | `DropReason \| None` | có khi `status = dropped` |

**Chuyển trạng thái:**
```
(nhận) ──lọc trượt──▶ dropped(empty|link|profanity|duplicate)
   │
   └─lọc qua─▶ waiting ──hàng đợi đầy, bị đẩy ra──▶ dropped(queue_full)
                  │ ──quá COMMENT_MAX_AGE_S──▶ dropped(stale)
                  └─director lấy─▶ answering ──▶ answered | skipped | error   (lượt lỗi → error; bị bỏ qua → skipped)
```
Comment ở `dropped` không bao giờ được chuyển cho `ReplyEngine` (FR-002, US2 #4).

## 2. Nội dung sản phẩm

### Variant (Phân loại)
| Trường | Kiểu | Ràng buộc |
|--------|------|-----------|
| `name` | `str` | không rỗng; duy nhất trong sản phẩm (so sánh sau chuẩn hóa) |
| `price` | `int` | VND, > 0 |

### Product
| Trường | Kiểu | Ràng buộc |
|--------|------|-----------|
| `id` | `str` | slug bỏ dấu từ `name`, duy nhất trong catalog |
| `name` | `str` | từ `Heading 1`, không rỗng, duy nhất |
| `is_primary` | `bool` | từ dòng `Loại: chính/phụ` |
| `price` | `int \| None` | VND > 0. **Đúng một trong** `price` hoặc `variants` (không rỗng) |
| `variants` | `tuple[Variant, ...]` | rỗng nếu dùng `price` |
| `description` | `str` | bắt buộc, không rỗng |
| `specs` | `tuple[tuple[str, str], ...]` | tùy chọn; giữ thứ tự trong file |
| `faq` | `tuple[tuple[str, str], ...]` | tùy chọn; (câu hỏi, trả lời) |
| `promotions` | `tuple[str, ...]` | tùy chọn |
| `forbidden_claims` | `tuple[str, ...]` | mục bắt buộc có mặt; `Không có` → tuple rỗng |
| `intro` | `str` | bài giới thiệu, bắt buộc, không rỗng (dùng ở 004; 001 chỉ đưa vào prompt làm ngữ cảnh) |
| `link` | `str \| None` | tùy chọn; **không bao giờ được đọc lên** (để dùng sau, ví dụ ghim link) |

Thuộc tính tính sẵn: `price_range -> tuple[int, int]` (min, max của giá hoặc phân loại).

**Khác ARCHITECTURE §2:** thêm `variants`, `intro`, `link`; `price` thành `int | None`; danh sách đổi thành tuple để bất biến.
Comment "(câu hỏi, câu trả lời) do khách duyệt" ở ARCHITECTURE không còn đúng (khách không duyệt, xem spec Giả định). Đề xuất ADR-014.

### ProductCatalog
| Trường | Kiểu | Ràng buộc |
|--------|------|-----------|
| `version` | `str` | sha256 rút gọn (12 ký tự) của file `.docx` |
| `source_name` | `str` | tên file gốc (không đường dẫn đầy đủ trong log) |
| `loaded_at` | `datetime` | UTC |
| `products` | `tuple[Product, ...]` | đúng 1 `is_primary`; 0–3 sản phẩm phụ |
| `known_amounts` | `frozenset[int]` | mọi số trong file + khoảng giá; dùng cho guard (research R8) |

Bất biến. Thay nội dung = tạo catalog mới rồi đổi tham chiếu (một phép gán). Lượt nói lấy catalog lúc bắt đầu và dùng tới hết lượt.

### ContentLoadError
`list[ContentIssue]`, mỗi `ContentIssue` có `product: str | None`, `section: str | None`, `message: str`. Báo hết lỗi một lần.

## 3. Phiên live

### LiveSession
| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `id` | `str` | `YYYYMMDD-HHMMSS` giờ địa phương, cũng là tên thư mục `data/sessions/<id>/` |
| `state` | `running \| paused` | |
| `catalog_version` | `str` | cập nhật khi thay nội dung |
| `avatar_image` | `str` | đường dẫn ảnh đang dùng |
| `started_at` | `datetime` | |

**Chuyển trạng thái:** `(khởi động, nạp nội dung OK) → running ⇄ paused`. Nạp nội dung lỗi khi khởi động thì app thoát với mã lỗi và danh sách
`ContentIssue`. Thay nội dung lỗi giữa phiên thì giữ catalog cũ, trạng thái không đổi (FR-022).

## 4. Lượt nói

### Utterance
| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `utterance_id` | `str` | uuid4 hex |
| `comment_id` | `str` | |
| `catalog_version` | `str` | nội dung dùng cho lượt này |
| `sentences` | `list[str]` | câu đã **phát** (sau guard) |
| `marks` | `dict[Milestone, float]` | monotonic |
| `outcome` | `TurnOutcome` | |
| `error_step` | `ErrorStep \| None` | `llm` \| `guard` \| `tts` \| `render`. `guard` chỉ dùng khi bản thân guard ném ngoại lệ; guard chặn câu thì lượt vẫn `completed` kèm `guard_reason` |
| `error_message` | `str \| None` | đã che secret |
| `guard_reason` | `str \| None` | khi guard chặn: `forbidden_claim` \| `unknown_amount` |

`Milestone`: `comment_received`, `turn_started`, `llm_first_sentence`, `tts_first_chunk`, `avatar_first_frame` (4 mốc bắt buộc của Điều VIII + 1 mốc phụ).

`TurnOutcome`: `in_progress` → `completed` | `skipped` | `error`. Guard chặn nhưng đã đọc câu từ chối thì vẫn là `completed` với `guard_reason`.

**Ràng buộc:** `completed` phải có đủ 4 mốc bắt buộc (SC-004). `error` có `error_step`. Mốc tăng dần theo thứ tự trên.

### LatencySummary (trong phiên: tính khi xem từ các lượt trong bộ nhớ; khi app tắt: ghi một lần ra `latency_summary.json`, FR-019)
Cho từng bước `received→first_sentence`, `first_sentence→tts_first_chunk`, `tts_first_chunk→first_frame`, `queue_wait`, `floor_wait`,
`total`: `count`, `median`, `p95`. Chỉ tính lượt `completed`; đếm riêng số lượt `error`/`skipped` (US3 #3). p95 bằng
`statistics.quantiles(n=20)[18]` khi `count ≥ 20`, ít hơn thì hiện "chưa đủ mẫu". Có thêm bộ số "chỉ lượt host rảnh" (`queue_wait` và
`floor_wait` đều `< 0,3 s`, research R12).

`floor_wait` (sửa lỗi 2026-11-17): trong show 004, câu trả lời đã có tiếng nhưng phải chờ câu kịch bản đang nói xong mới được phát
(mốc phụ trong bộ nhớ `floor_acquired`: lúc phần phát của lượt trả lời giành được lượt nói). `floor_wait = max(0, floor_acquired −
tts_first_chunk)`, và `tts_first_chunk→first_frame` tính từ mốc muộn hơn trong hai mốc đó, nên khoảng chờ này không còn bị gán vào khâu
dựng hình. Ngoài show `floor_wait` là 0. `total` không đổi. Với `LIVETALKING_LEAD_S > 0` câu kịch bản trả lượt nói sớm tối đa `lead_s`,
nên phần chờ còn lại (≤ `lead_s`) vẫn nằm trong `tts_first_chunk→first_frame`. `floor_acquired` không ghi vào `utterances.jsonl`.

## 5. Bộ câu hỏi mẫu

### EvalQuestion
| Trường | Kiểu | Ràng buộc |
|--------|------|-----------|
| `id` | `str` | `q01`…`q10`, duy nhất |
| `author` | `str` | tên người hỏi giả lập |
| `question` | `str` | |
| `required` | `list[list[str]]` | mỗi ý là danh sách cách nói tương đương; có thể rỗng (câu chỉ kiểm ý cấm) |
| `forbidden` | `list[list[str]]` | như trên |
| `note` | `str \| None` | ghi chú cho người soạn |

File có `content_version` (khớp `ProductCatalog.version`) để cảnh báo khi chấm trên file nội dung khác lúc soạn câu hỏi.

### EvalRun
| Trường | Kiểu |
|--------|------|
| `run_id` | `str` (timestamp) |
| `questions_file`, `content_version`, `llm_model` | `str` |
| `results` | `list[EvalResult]` |
| `score` | `int` (số câu đúng) |
| `previous_run_id` | `str \| None` |
| `diff` | `list[{id, before: bool, after: bool}]` |

### EvalResult
`question_id`, `answer: str` (các câu sau guard ghép lại), `passed: bool`, `missing: list[str]` (ý bắt buộc thiếu, lấy cách nói đầu tiên),
`found_forbidden: list[str]`, `guard_reason: str | None`, `first_sentence_s: float | None`.
