# Hợp đồng adapter: 001-local-reply-pipeline

> Mọi adapter là `typing.Protocol`, chọn bằng biến môi trường. Kiểu dữ liệu ở [`../data-model.md`](../data-model.md).
> Mỗi adapter có file test riêng chạy được độc lập, không cần GPU, mạng hay API key (Điều IV, V).

```python
from typing import AsyncIterator, Protocol


class CommentSource(Protocol):
    """Nguồn comment. stream() dành cho nguồn kéo về (YouTube ở 006, Shopee về sau); MockSource của 001 không dùng stream()."""
    name: str
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def stream(self) -> AsyncIterator[Comment]: ...


class MockSource:  # lớp cụ thể của 001, thỏa CommentSource
    """Route POST /api/comments gọi push() đồng bộ để trả drop_reason ngay trong response.
    Luồng: push() → CommentFilter → PriorityClassifier → queue.put(). stream() rỗng (kết thúc ngay)."""
    def push(self, author: str, text: str) -> Comment: ...  # gán comment_id, received_at; ghi mốc comment_received


class CommentQueue(Protocol):
    """Hàng đợi ưu tiên in-process. Comment bị loại được báo qua EventBus (comment_dropped), không ném lỗi."""
    async def put(self, comment: Comment, priority: Priority) -> QueuedComment: ...  # status `dropped` nếu bị loại queue_full ngay
    async def get(self) -> QueuedComment: ...     # chờ tới khi có; bỏ comment quá COMMENT_MAX_AGE_S
    def size(self) -> int: ...
    def snapshot(self) -> list[QueuedComment]: ... # theo thứ tự sẽ được lấy, cho trang điều khiển
    def sweep(self) -> list[QueuedComment]: ...    # bỏ ngay mọi comment quá tuổi, trả về danh sách bị bỏ
    async def run_sweeper(self, interval_s: float = 1.0) -> None: ...  # gọi sweep() định kỳ, chạy suốt phiên


class ProductStore(Protocol):
    """Nội dung sản phẩm nạp từ file Word. Bất biến; thay nội dung là đổi cả catalog."""
    @property
    def catalog(self) -> ProductCatalog: ...
    def list_active(self) -> list[Product]: ...
    def get(self, product_id: str) -> Product | None: ...
    def replace(self, data: bytes, source_name: str) -> ProductCatalog: ...  # ném ContentLoadError, giữ catalog cũ


class ReplyEngine(Protocol):
    """Sinh lời thoại. Yield từng câu hoàn chỉnh (đã qua sentence splitter, chưa qua guard)."""
    def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]: ...


class TTSEngine(Protocol):
    """001 chỉ có FakeTTS. PCM16 little-endian mono."""
    sample_rate: int
    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...


class AvatarRenderer(Protocol):
    """001 chỉ có StaticRenderer: đẩy PCM tới trang /host qua WebSocket."""
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def speak(self, utterance_id: str, text: str, audio: AsyncIterator[bytes], sample_rate: int) -> None: ...
    async def interrupt(self) -> None: ...
    @property
    def is_speaking(self) -> bool: ...
    def first_playback_at(self, utterance_id: str) -> float | None: ...  # mốc avatar_first_frame (monotonic) từ ack đầu
```

## Hành vi bắt buộc

| Adapter | Hợp đồng |
|---------|----------|
| `CommentQueue.put` | Đầy (`COMMENT_QUEUE_MAX`) thì đẩy ra comment ưu tiên thấp nhất, đến sớm nhất; nếu comment mới còn thấp hơn hết thì loại chính nó. Báo `comment_dropped(queue_full)`. |
| `CommentQueue.get` | Thứ tự (priority, seq). Comment quá tuổi bị bỏ (`stale`) và lấy tiếp. Có thêm vòng quét mỗi 1 s để trang điều khiển thấy comment hết hạn kịp thời. |
| `CommentIntake.submit` | (không phải adapter, `comments/intake.py`) `MockSource.push` → `CommentFilter.check` → `PriorityClassifier.classify` → `CommentQueue.put`. Bị lọc thì phát `comment_dropped`, không vào hàng đợi; qua lọc thì phát `comment_accepted` rồi `put`. Route `POST /api/comments` và lệnh `ai_live.comments` cùng dùng. |
| `ProductStore.replace` | Kiểm hết lỗi rồi mới đổi; lỗi thì ném `ContentLoadError(issues)` và **không** đổi catalog. Thành công phát `content_replaced`. |
| `ReplyEngine.reply` | Câu đầu tiên yield là mốc `llm_first_sentence`. Lỗi nhà cung cấp ném `ReplyEngineError(kind, message)` với `kind` thuộc `api_error`, `rate_limited`, `provider_blocked`, `config_error`. Timeout do `ShowDirector` áp: `LLM_TIMEOUT_S` tính cho **mỗi lần chờ câu kế tiếp** (không tính lúc chờ hàng đợi phát), hết giờ ghi `error_step=llm`. Không chứa lịch sử hội thoại. Huỷ task thì đóng stream HTTP. |
| `TTSEngine.synthesize` | Chunk đầu là mốc `tts_first_chunk`. Lỗi ném ngoại lệ; director bắt và ghi `error_step=tts`. |
| `AvatarRenderer.speak` | Trả về khi trang `/host` báo `sentence_played`, hoặc khi bị `interrupt()`. Không có trang `/host` kết nối thì ném `RendererUnavailable`. Ack đầu tiên `playback_started` là mốc `avatar_first_frame`; không có ack sau `RENDERER_ACK_TIMEOUT_S` thì ném `TimeoutError` (tính cho **mỗi** ack). `TTS_TIMEOUT_S` do `ShowDirector` áp cho **mỗi lần chờ chunk kế tiếp** của một câu (chờ chunk đầu và chờ giữa hai chunk liền nhau; không tính lúc chờ hàng đợi phát), nên câu dài không bị cắt mà engine treo vẫn bị phát hiện nhanh (ADR-049). |
| `AvatarRenderer.interrupt` | Gửi `stop` cho trang `/host`, trả về ngay; idempotent. |

## Thành phần không phải adapter (lõi, không cần Protocol)

- `OutputGuard.check(sentence: str, catalog: ProductCatalog) -> GuardResult` (`ok` hoặc `blocked` kèm `reason`). Hàm thuần, xem research R8.
- `SentenceSplitter.feed(delta: str) -> list[str]` và `flush() -> list[str]`. Hàm thuần, xem research R7.
- `EventBus`: `publish(event)` và `subscribe() -> AsyncIterator[Event]`. Mỗi subscriber có hàng đợi riêng giới hạn 1000; đầy thì bỏ sự kiện cũ nhất
  cho subscriber đó (trang điều khiển chậm không được làm chậm pipeline).
- `ShowDirector`: vòng lấy comment → lượt nói. Không có `narrate` (để 004).

## Khác biệt so với `docs/ARCHITECTURE.md` §3

| Chỗ | ARCHITECTURE §3 | 001 | Lý do |
|-----|-----------------|-----|-------|
| `AvatarRenderer.speak` | `(utterance_id, audio, sample_rate)` | thêm `text` | trang `/host` hiện phụ đề câu đang nói; LiveTalking cách (a) cũng cần text. ADR-016 |
| `CommentQueue.put` | `priority: int` | `priority: Priority` | `IntEnum` nên vẫn tương thích `int` |
| `CommentQueue.get` | trả `Comment` | trả `QueuedComment` | director cần `priority` và `seq` để ghi log |
| `CommentQueue.snapshot` | không có | thêm | FR hiển thị hàng đợi (US2). ADR-016 |
| `MockSource.push` | không có (chỉ `stream()`) | thêm, đồng bộ | API trả `drop_reason` ngay trong response (US2); nguồn kéo về vẫn dùng `stream()` |
| `ProductStore.search` | có | **chưa làm** | ≤ 4 sản phẩm, đưa hết vào prompt (ADR-005) |
| `ProductStore.replace`, `catalog` | không có | thêm | thay nội dung giữa phiên (FR-022). ADR-014 |
| `ReplyEngine.reply` | `products: list[Product]` | `catalog: ProductCatalog` | prompt cần `version` để khớp cache và log |
| `ReplyEngine.narrate` | có | **chưa làm** | thuộc 004-show-director |
| `OutputSink` | có | **không dùng** | static renderer phát thẳng ra trình duyệt; sink làm ở 005 |

ARCHITECTURE §3 được sửa theo bảng này ở pha Foundational (trước khi viết adapter). §2 (mô hình `Product`) sửa ở pha Hoàn thiện cùng `src/README.md`.
