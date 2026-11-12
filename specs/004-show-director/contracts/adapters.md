# Hợp đồng adapter và module: 004-show-director

> Đối chiếu với `docs/ARCHITECTURE.md` §3 và `src/ai_live/core/protocols.py`. Chỉ có **một** thay đổi Protocol: `ReplyEngine.narrate()`
> (ADR-030). Các module khác là lớp cụ thể (Điều VII), ghi ở đây để các agent làm song song cùng bám một giao diện.

## 1. `ReplyEngine` (Protocol, sửa)

```python
class ReplyEngine(Protocol):
    """Generates host lines. Both methods yield complete sentences (after the sentence splitter, before sanitize/guard)."""

    def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]: ...
    def narrate(self, request: SegmentRequest, catalog: ProductCatalog) -> AsyncIterator[str]: ...
```

- `narrate()` ném `ReplyEngineError(kind, message)` với cùng các `kind` như `reply()`: `api_error`, `rate_limited`, `provider_blocked`,
  `config_error`. Timeout **không** do engine xử lý: `ScriptRunner` bọc cả phân đoạn bằng `SCRIPT_LLM_TIMEOUT_S` (bằng
  `SCRIPT_RETRY_TIMEOUT_S` khi thử lại trong chế độ dự phòng).
- Engine không tự cắt số câu. Runner bỏ các câu vượt `max_sentences` (ghi `sentence_count_exceeded`) và đóng stream.
- `GeminiReplyEngine.narrate()`: `system_instruction = build_script_system_prompt(catalog)` (giữ nguyên trong một `catalog_version`, cache
  được). `contents = build_segment_message(request, catalog)`. `max_output_tokens = SCRIPT_MAX_TOKENS`. `thinking_level` như `reply()`.
  Log `llm_usage` có thêm `segment_id`.
- `FakeReplyEngine.narrate()`: có kịch bản theo `(product_id, topic)` hoặc mặc định. Mặc định sinh
  `"Câu {n} về {topic} của {product_name}."` với `n` tăng theo mỗi lần gọi, nên không trùng nguyên văn. Có các tham số `delay_s`,
  `first_sentence_delay_s` và `fail_next(kind, count)` để test.
- Contract test (`tests/contract/test_reply_engine_contract.py`) thêm cho cả hai engine:
  - mỗi giá trị yield là một câu không rỗng;
  - lỗi được ném ra là `ReplyEngineError`;
  - `narrate()` không đổi `catalog`.

**Khác ARCHITECTURE §3:** dòng ghi chú `# narrate(segment_hint, catalog): chưa làm ở 001, thuộc 004-show-director` được thay bằng chữ ký
trên. Tham số là `SegmentRequest` (data-model §5), không phải `segment_hint` chung chung. Sửa ARCHITECTURE §3 ở pha Foundational.

## 2. `brain/script_prompt.py`

```python
SCRIPT_RULES: str  # Vietnamese, research R4
def build_script_system_prompt(catalog: ProductCatalog) -> str: ...
def build_segment_message(request: SegmentRequest, catalog: ProductCatalog) -> str: ...
def topic_brief(topic: Topic) -> str: ...  # one-line Vietnamese description of what the segment covers
```
- `build_script_system_prompt` dùng lại `render_catalog()` của `brain/prompt.py`, không sao chép.
- `build_segment_message` không chứa `GEMINI_API_KEY`, đường dẫn file hay `session_id` (FR-027). Chữ comment trong `recent_lines` được bọc
  như cách chống injection của 001.

## 3. `brain/sanitize.py`

```python
def clean_spoken(text: str) -> str: ...
```
- Hàm thuần, idempotent: `clean_spoken(clean_spoken(x)) == clean_spoken(x)`.
- Bỏ: đầu dòng `-`, `*`, `•`, `–`, `1.`, `1)`; `#` tiêu đề; cặp `**…**`, `__…__`, `` `…` ``; ký tự Unicode thuộc nhóm `So` và các khối emoji;
  dấu biến thể `U+FE0F`; ký tự nối `U+200D`.
- Giữ: dấu tiếng Việt, số và dấu chấm hoặc phẩy trong số (`1.250.000`), `%`, dấu câu thường.
- Gọi trước guard ở cả hai đường (kịch bản và comment). Với đường comment, chữ đã làm sạch là chữ đọc (ADR-031).

## 4. `OutputGuard` (lớp cụ thể, sửa)

```python
class OutputGuard:
    def __init__(self, platform_phrases: Sequence[str] = (), claim_phrases: Sequence[str] = ()) -> None: ...
    # platform_phrases from PLATFORM_PHRASES_PATH; claim_phrases from CLAIM_PHRASES_PATH (ADR-050)
    def check(self, sentence: str, catalog: ProductCatalog) -> GuardResult: ...
```
Tham số `platform_phrases` không bắt buộc (mặc định rỗng = bỏ kiểm `platform_phrase`) để test cũ gọi `OutputGuard()` vẫn chạy. Mọi chỗ
tạo guard trong code chạy thật (`app/main.py` → `ShowDirector`, `brain/__main__.py`, `qa_eval/runner.py`) **phải** truyền cụm từ đã nạp từ
`PLATFORM_PHRASES_PATH` (analyze A4, người dùng duyệt 2026-11-01). Từ ADR-050, chỗ chạy thật tạo guard bằng
`load_guard(platform_phrases_path, claim_phrases_path)`; `claim_phrases` rỗng thì bỏ kiểm `unsupported_claim`.

Thứ tự kiểm (dừng ở lỗi đầu tiên): `forbidden_claim` → `unknown_amount` → `unknown_percent` → `link` → `platform_phrase` →
`unsupported_claim` (ADR-050).
- `unknown_percent`: số ngay trước `%` hoặc trước "phần trăm" (cho phép khoảng trắng) không có trong tập số của catalog.
  `detail = "<số>%"`.
- `link`: `core.text.contains_link(sentence)`. `detail` = phần khớp, đã cắt còn 40 ký tự.
- `platform_phrase`: so trên `word_form`. Cụm có trong `word_form` của chữ toàn bộ catalog (gồm promotions, faq, description) thì được
  phép. `detail` = cụm khớp.
- `unsupported_claim` (ADR-050): như `platform_phrase` nhưng với danh sách `claim_phrases.txt` (an toàn, kích ứng, lời khen của khách,
  tồn kho, hối thúc). `detail` = cụm khớp dài nhất.
- Nạp `platform_phrases.txt` và `claim_phrases.txt`: mỗi dòng một cụm; dòng trống và dòng bắt đầu bằng `#` bị bỏ. File thiếu thì app không khởi động (lỗi
  cấu hình rõ ràng), như `profanity.txt` của 001.

## 5. `director/segment_planner.py` (thuần, không asyncio)

```python
class SegmentPlanner:
    def __init__(self, catalog: ProductCatalog, primary_share: float) -> None: ...
    def available_topics(self, product_id: str) -> tuple[Topic, ...]: ...          # FR-004, research R5 order
    def availability(self) -> dict[str, tuple[Topic, ...]]: ...                    # for the control page
    def next_slot(self) -> PlannedSlot: ...                                         # consumes rotation
    def peek_slot(self) -> PlannedSlot: ...                                         # does not consume
    def choose(self, product_id: str | None, topic: Topic | None) -> PlannedSlot: ...  # FR-018; raises TopicUnavailable
    def take_override(self) -> PlannedSlot | None: ...
    def replace_catalog(self, catalog: ProductCatalog) -> None: ...                # keeps cursors of surviving products
```
- `PlannedSlot(product_id: str | None, topic: Topic, origin: SegmentOrigin)`.
- `opening` và `closing` không do `next_slot()` trả về. Runner tự tạo hai slot này.
- Bất biến (unit test): trong mọi chuỗi 1000 lần `next_slot()`, hai slot liền nhau không trùng cả `(product_id, topic)`, trừ khi catalog
  chỉ có đúng một tổ hợp. Tỷ lệ sản phẩm chính ≥ `primary_share`. Mỗi sản phẩm phụ xuất hiện trong mỗi chu kỳ.

## 6. `director/script_runner.py`

```python
class ScriptRunner:
    def __init__(self, *, show: ShowSession, planner: SegmentPlanner, engine: ReplyEngine, guard: OutputGuard,
                 tts: TTSEngine, renderer: AvatarRenderer, store: ProductStore, floor: asyncio.Lock,
                 interleave: InterleaveGate, faults: FaultInjector, stats: ShowStats, log: SessionLog,
                 bus: EventBus, settings: Settings, clock: Callable[[], float] = time.monotonic) -> None: ...
    async def run(self) -> None: ...            # opening, then rotation until close() or cancellation
    def pause(self) -> None: ...                # takes effect after the current sentence; drops voiced audio
    def resume(self) -> None: ...
    async def skip(self) -> str | None: ...     # interrupt + discard rest of segment; returns segment_id
    async def close(self) -> None: ...          # closing segment (≤ 2 sentences) then return
    def on_catalog_replaced(self, catalog: ProductCatalog) -> None: ...
    def snapshot(self) -> dict: ...             # current/next segment, mode, recent blocked/errors (FR-019)
```
- `InterleaveGate`: một đối tượng nhỏ do `ShowDirector` cung cấp, có `pending() -> bool` (đang có lượt comment hoặc hàng đợi còn comment)
  và `wait_clear() -> Awaitable[None]` (R8). Không phải Protocol, vì chỉ có một hiện thực.
- `FaultInjector`: tách `_take_fault`/`_faulty_stream` của `ShowDirector` thành lớp nhỏ để runner dùng chung (FR-024). Lỗi ở bước
  `llm` áp dụng cho lần gọi LLM kế tiếp, dù đó là `reply()` hay `narrate()`.
- Runner **không** gọi `renderer.interrupt()` khi pause, chỉ khi `skip`.
- Mọi task con bị hủy sạch khi `run()` bị hủy (app tắt). Bảng tổng hợp được ghi trong `finally`.

## 7. `ShowDirector` (sửa)

Thêm (không đổi chữ ký các method của 001):
```python
async def start_show(self) -> tuple[ShowSession, bool]: ...   # (show, already_running); raises HostUnavailable, NoContent
async def end_show(self) -> ShowSession | None: ...
def choose_next(self, product_id: str | None, topic: Topic | None) -> PlannedSlot: ...  # raises ShowNotRunning, TopicUnavailable
def show_snapshot(self) -> dict | None: ...
```
- `pause()`, `resume()`, `skip()` của 001 áp dụng cho cả show (research R7, R13). `skip()` ưu tiên lượt comment đang nói, nếu không thì
  phân đoạn kịch bản.
- `run()` của 001: khi show ở `closing` hoặc `ended`, comment lấy ra khỏi hàng đợi bị ghi `dropped` với lý do `show_ended` (FR-030).
- `_floor: asyncio.Lock`: tầng phát của lượt comment giữ khóa này trong cả lượt; tầng phát kịch bản giữ nó cho từng câu.
- Sau mỗi lượt trả lời trong show, câu đã nói được thêm vào `SpokenHistory` với `source = "reply"` (FR-030).

## 8. `director/show_stats.py`

```python
class ShowStats:
    def record_segment(self, segment: Segment) -> None: ...
    def record_sentence(self, sentence: ScriptSentence, source: Literal["script", "fallback"]) -> None: ...
    def record_gap(self, gap: SentenceGap) -> None: ...
    def record_reply_latency(self, seconds: float) -> None: ...
    def summary(self) -> ShowSummary: ...
```
Thuần, không I/O; `SessionLog` ghi kết quả. Cách tính p95 dùng lại hàm của `director/latency.py`, không viết lại.

## 9. Không đổi

`CommentSource`, `CommentQueue`, `ProductStore`, `TTSEngine`, `AvatarRenderer`, `OutputSink`, giao thức WebSocket host. Renderer nhận
mỗi câu kịch bản như một utterance một câu (`seq = 0`).
