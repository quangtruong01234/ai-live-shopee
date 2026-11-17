# Mô hình dữ liệu: 004-show-director

> Dùng lại từ 001, không đổi: `Product`, `Variant`, `ProductCatalog`, `Comment`, `QueuedComment`, `LiveSession`, `LatencySummary`.
> Kiểu dùng `dataclass(frozen=True)` hoặc model pydantic như 001. Enum là `StrEnum` trong `core/models.py`.

## 1. Enum mới

| Enum | Giá trị | Ghi chú |
|------|---------|---------|
| `ShowState` | `idle`, `running`, `paused`, `closing`, `ended` | Tên hiển thị (FR-019): chưa chạy / đang chạy / tạm dừng / đang chào kết / đã kết thúc |
| `ShowMode` | `normal`, `fallback` | FR-021 |
| `Topic` | `opening`, `intro`, `highlights`, `specs`, `price`, `promotion`, `faq`, `call_to_action`, `closing` | Có `label` tiếng Việt và điều kiện dữ liệu (research R5) |
| `SegmentOrigin` | `rotation`, `operator`, `fallback` | `operator` = người vận hành chọn (FR-018) |
| `SegmentStatus` | `preparing`, `ready`, `speaking`, `done`, `skipped`, `failed`, `blocked`, `discarded` | `discarded` = bỏ vì đổi nội dung, đổi hướng hoặc kết thúc |
| `SentenceStatus` | `spoken`, `blocked`, `dropped`, `tts_error`, `render_error`, `interrupted` | `dropped` kèm `drop_reason`: `duplicate`, `empty_after_clean`, `sentence_count_exceeded` (vượt `max_sentences`), `paused_discard` (chỉ ghi khi tiếng bị bỏ; chữ vẫn được nói sau), `segment_discarded` (câu đã qua guard nhưng chưa phát của phân đoạn bị bỏ vì `catalog_version` lệch). Khi app tắt, câu chưa phát ghi `interrupted` |
| `GapKind` | `script`, `segment_boundary`, `comment`, `paused`, `fault`, `error` | research R12 |

Thêm vào enum có sẵn:
- `Milestone.SEGMENT_REQUESTED = "segment_requested"`.
  - `REQUIRED_MILESTONES` của 001 giữ nguyên cho lời trả lời comment.
  - Thêm `REQUIRED_SCRIPT_MILESTONES = (SEGMENT_REQUESTED, LLM_FIRST_SENTENCE, TTS_FIRST_CHUNK, AVATAR_FIRST_FRAME)` (Điều VIII).
- `GuardReason`: `LINK = "link"`, `UNKNOWN_PERCENT = "unknown_percent"`, `PLATFORM_PHRASE = "platform_phrase"` (research R9),
  `UNSUPPORTED_CLAIM = "unsupported_claim"` (ADR-050, thêm 2026-11-12).
- `DropReason.SHOW_ENDED = "show_ended"`, nhãn "phiên đã kết thúc" (FR-030).

## 2. `Utterance` (sửa của 001)

| Trường | Kiểu | Thay đổi |
|--------|------|----------|
| `utterance_id` | `str` (uuid4 hex) | như cũ |
| `comment_id` | `str \| None` | **đổi:** `None` với câu kịch bản |
| `segment_id` | `str \| None` | **mới:** có giá trị với câu kịch bản |
| `show_id` | `str \| None` | **mới:** có giá trị khi utterance nằm trong show, kể cả lời trả lời comment chen vào |
| `catalog_version` | `str` | như cũ |
| `sentences`, `marks`, `outcome`, `error_step`, `error_message`, `guard_reason` | | như cũ; `marks` của câu kịch bản dùng `REQUIRED_SCRIPT_MILESTONES` |

Kiểm tra: đúng một trong hai trường `comment_id` và `segment_id` khác `None`. `POST /api/debug/speak` của 001 tạo utterance với
`comment_id = "debug"` như hiện tại.

## 3. `ShowSession`

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `show_id` | `str` (uuid4 hex) | tạo khi "Bắt đầu show" từ `idle` hoặc `ended` |
| `session_id` | `str` | phiên app của 001; file ghi vào thư mục phiên này |
| `state` | `ShowState` | |
| `mode` | `ShowMode` | |
| `started_at`, `ended_at` | `datetime \| None` | |
| `start_requested_at` | `float` (monotonic) | để tính SC-001 |
| `catalog_version` | `str` | phiên bản nội dung lúc bắt đầu; phân đoạn ghi phiên bản riêng |
| `consecutive_llm_failures` | `int` | reset về 0 khi `narrate()` thành công (R10) |
| `current_segment`, `next_segment` | `Segment \| None` | FR-019 |
| `recent_blocked` | `deque[ScriptSentence]` (≤ 20) | FR-019 |
| `recent_errors` | `deque[dict]` (≤ 20) | FR-019 |

**Chuyển trạng thái**

```
idle ──start──▶ running ──pause──▶ paused ──resume──▶ running
                   │                  │
                   └──────end─────────┴──▶ closing ──(chào kết xong | skip)──▶ ended ──start──▶ running (show_id mới)
```
- `start` khi đang `running`, `paused` hoặc `closing`: không đổi gì, trả về show hiện tại (`already_running: true`). Kiểm này đứng
  trước kiểm host: host ngắt khi show đang chạy thì `start` vẫn trả `already_running: true` (người dùng duyệt 2026-11-01, ADR-033).
- `start` khi chưa nạp nội dung hoặc host chưa `ready`: từ chối, giữ trạng thái (trường hợp biên).
- `end` khi `paused`: chào kết vẫn được nói, tức kết thúc có hiệu lực luôn, không cần bấm "Tiếp tục".
- `end` khi `idle` hoặc `ended`: không làm gì (idempotent).
- Host ngắt kết nối khi đang `running`: tầng phát nhận lỗi render, câu bị bỏ, show vẫn ở `running`, trang điều khiển báo
  `host_connection` như 001. Host nối lại thì nói tiếp.

## 4. `Segment`

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `segment_id` | `str` (uuid4 hex) | FR-022 |
| `show_id` | `str` | |
| `index` | `int` | số thứ tự trong show, từ 0 |
| `product_id` | `str \| None` | `None` với `opening`/`closing` |
| `topic` | `Topic` | |
| `origin` | `SegmentOrigin` | |
| `mode` | `ShowMode` | chế độ lúc sinh |
| `catalog_version` | `str` | kiểm trước khi phát câu đầu (R7) |
| `status` | `SegmentStatus` | |
| `requested_at`, `ready_at`, `started_at`, `finished_at` | `datetime \| None` | |
| `sentences` | `list[ScriptSentence]` | |
| `error_step`, `error_kind`, `error_message` | `str \| None` | `error_step` ∈ `llm`, `tts`, `render` |

**Chuyển trạng thái**

```
preparing ──LLM xong, có ≥ 1 câu qua guard──▶ ready ──câu đầu bắt đầu phát──▶ speaking ──hết câu──▶ done
    │                                           │                              ├─skip──▶ skipped
    ├─LLM lỗi / quá giờ──▶ failed               ├─catalog_version lệch / sản    └─end──▶ discarded (câu đang nói được nói hết)
    ├─mọi câu bị chặn / bỏ──▶ blocked           │  phẩm bị bỏ / override / end──▶ discarded
    └─override / end / đổi nội dung──▶ discarded
```
- Phân đoạn ở `speaking` mà các câu còn lại đều bị chặn hoặc lỗi TTS: vẫn kết thúc là `done`, vì đã có câu được nói.
- `ready` được đặt ngay khi có câu đầu qua guard. Tầng tiếng bắt đầu từ lúc đó, không chờ LLM sinh xong cả phân đoạn (FR-007).
  Phân đoạn mà mọi câu đều bị chặn thì chuyển `ready → blocked` khi LLM kết thúc.

## 5. `SegmentRequest` (gửi vào `narrate()`)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `segment_id` | `str` | để log `llm_usage` gắn đúng phân đoạn |
| `topic` | `Topic` | |
| `product_id` | `str \| None` | `None` với `opening`/`closing` |
| `min_sentences`, `max_sentences` | `int` | `closing`: `1`–`2` (FR-017); `opening`: `2`–`3` |
| `previous_sentence` | `str \| None` | câu cuối đã nói, để nối mạch |
| `recent_lines` | `tuple[str, ...]` | ≤ `SCRIPT_HISTORY_SENTENCES` câu gần nhất về cùng sản phẩm, gồm lời trả lời comment (R4, FR-030) |

Kiểm tra: `product_id` có trong catalog (trừ `opening`/`closing`); `topic` có dữ liệu cho sản phẩm đó (R5);
`1 ≤ min ≤ max`.

## 6. `ScriptSentence`

Một câu kịch bản. Câu được nói thì có `Utterance` tương ứng (cùng `utterance_id`). Câu bị chặn hoặc bỏ trước TTS chỉ có bản ghi này.

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `utterance_id` | `str` | |
| `segment_id` | `str` | |
| `seq` | `int` | thứ tự trong phân đoạn, kể cả câu bị chặn |
| `raw_text` | `str` | chữ LLM trả về (để soát lỗi prompt) |
| `text` | `str` | chữ đọc và phụ đề, sau `clean_spoken()` |
| `word_form` | `str` | dạng so khớp chống lặp (R11) |
| `status` | `SentenceStatus` | |
| `guard_reason`, `guard_detail` | `GuardReason \| None`, `str \| None` | khi `blocked` |
| `drop_reason` | `str \| None` | khi `dropped` |
| `marks` | `dict[Milestone, datetime]` | 4 mốc của `REQUIRED_SCRIPT_MILESTONES` khi `spoken` |
| `played_at` | `datetime \| None` | khi `renderer.speak()` trả về |

## 7. `SpokenHistory`

Trong bộ nhớ, sống trong một show (spec Giả định: phiên mới bắt đầu lại từ đầu).
- `lines: list[SpokenLine]`. Mỗi `SpokenLine` có `text`, `word_form`, `product_id | None`, `source` ∈ `script`, `fallback`, `reply`,
  và `comment_text` (khi `reply`).
- `seen_word_forms: set[str]`, chỉ gồm câu `script` và `reply`, dùng cho lớp 2 chống lặp (R11). Câu dự phòng không vào tập này, vì chúng
  được phép đọc lại (SC-005 loại trừ).
- `recent_for(product_id, n) -> tuple[str, ...]`, dùng cho `SegmentRequest.recent_lines`.

## 8. `SentenceGap`

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `from_utterance_id`, `to_utterance_id` | `str` | |
| `seconds` | `float` | `avatar_first_frame(to) − played_at(from)` |
| `kind` | `GapKind` | |

Chỉ ghi khi cả hai câu đều là câu kịch bản đã nói (kể cả câu dự phòng). Câu đầu tiên của show không có gap. Thời gian tới câu đầu là
`show_first_sentence_s` (SC-001).

## 9. `ShowSummary` → `show_summary_<show_id>.json` (FR-023)

```json
{
  "show_id": "…", "session_id": "…", "started_at": "…", "ended_at": "…", "ended_by": "operator|shutdown",
  "show_first_sentence_s": 2.1,
  "segments": {"total": 64, "by_product": {"p1": 31, "p2": 15, "p3": 15}, "by_topic": {"intro": 9, "…": 0},
               "by_status": {"done": 60, "skipped": 1, "failed": 3}, "primary_share": 0.51},
  "secondary_coverage": [{"window_start_s": 0, "window_end_s": 600, "missing_products": []}],
  "sentences": {"spoken": 340, "blocked": 4, "dropped": 2, "tts_error": 3, "render_error": 0, "interrupted": 0, "fallback_spoken": 0, "verbatim_spoken": 0},
  "gaps": {"counted": {"n": 330, "median_s": 0.21, "p95_s": 0.38, "max_s": 1.9},
           "by_kind": {"script": {"n": 270, "median_s": 0.2, "p95_s": 0.3, "max_s": 0.9}, "fault": {"n": 3, "max_s": 6.2}}},
  "duplicates": {"before_filter_rate": 0.03, "spoken_rate": 0.0, "identical_segments": 0},
  "mode_changes": [{"at": "…", "mode": "fallback"}, {"at": "…", "mode": "normal"}],
  "comments": {"answered": 10, "reply_latency": {"n": 10, "p95_s": 3.8}}
}
```
- `gaps.counted` gồm các loại `script`, `segment_boundary`, `error` (SC-002). Loại `fault` kiểm riêng `max_s ≤ 8` (SC-006).
- `sentences.spoken` gồm cả câu dự phòng; `fallback_spoken` là phần câu dự phòng trong số đó (người dùng duyệt 2026-11-01).
  `verbatim_spoken` (sửa lỗi 2026-11-17): phần câu đọc nguyên văn của show `content: "verbatim"` (007 R6, video dự phòng);
  các câu này không tính vào `fallback_spoken`, vì show không gặp sự cố nào.
- `by_product`, `primary_share` và `secondary_coverage` chỉ tính phân đoạn đã phát (`done`, `skipped`); `total`, `by_topic`,
  `by_status` tính mọi phân đoạn (sửa lỗi 2026-11-17: trước đó `by_product` đếm cả phân đoạn `failed`/`blocked`).
- `secondary_coverage`: chia show thành các cửa sổ 10 phút (cửa sổ cuối có thể ngắn hơn, xem `window_end_s`), mỗi cửa sổ liệt kê sản phẩm phụ không có phân đoạn nào (SC-004).
- `p95` là `null` khi chưa đủ 20 mẫu (như `LatencySummary` của 001).
- `duplicates.spoken_rate` (SC-005) tính trên câu `script` đã nói; `identical_segments` đếm cặp phân đoạn có cùng danh sách `word_form`.

## 10. `ScriptEvalRun` → `data/eval/script_runs/<timestamp>.json` (FR-026)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `run_id`, `started_at`, `finished_at` | | |
| `engine`, `model`, `content_source`, `catalog_version` | `str` | |
| `segments` | `list[ScriptEvalSegment]` | mỗi phần tử: `product_id`, `topic`, `sentences: [{raw_text, violations: [{kind, detail}]}]`, `sentence_count_warning: bool`, `error` |
| `totals` | `dict[str, int]` | theo loại vi phạm: `unknown_amount`, `unknown_percent`, `forbidden_claim`, `link`, `platform_phrase`, `unsupported_claim`, `bad_pronoun`, `formatting` |
| `violation_count` | `int` | tổng |
| `previous` | `{run_id, violation_count, totals} \| null` | lần chạy trước cùng `content_source` |
| `delta` | `dict[str, int] \| null` | `totals − previous.totals` |

Lỗi gọi dịch vụ (429, timeout) **không** tính là vi phạm. Tổ hợp đó ghi `error` và không có câu. Lần chạy có lỗi thì không dùng để
tính SC-008.
