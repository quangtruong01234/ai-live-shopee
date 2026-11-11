# Hợp đồng adapter và module: 008-llm-provider-chain

> Đối chiếu với `docs/ARCHITECTURE.md` §3 và `src/ai_live/core/protocols.py`. **Không đổi Protocol nào.** `ChainReplyEngine` là thêm một
> implementation của `ReplyEngine`; các lớp còn lại là lớp cụ thể trong `brain/` (Điều VII), ghi ở đây để các agent làm song song cùng
> bám một giao diện.

## 1. `ReplyEngine` (Protocol, không đổi)

```python
class ReplyEngine(Protocol):
    def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]: ...
    def narrate(self, request: SegmentRequest, catalog: ProductCatalog) -> AsyncIterator[str]: ...
```

`ChainReplyEngine` giữ đúng hợp đồng 004 (`specs/004-show-director/contracts/adapters.md` §1):
- mỗi giá trị yield là một câu hoàn chỉnh, không rỗng, sau `SentenceSplitter`, trước `clean_spoken` và guard;
- lỗi ném ra luôn là `ReplyEngineError` với `kind` ∈ `api_error`, `rate_limited`, `provider_blocked`, `config_error`; trong một lượt chuỗi chỉ ném
  `rate_limited` hoặc `api_error`, còn `config_error` chỉ ở `from_settings` / `preflight` lúc khởi động (R7);
- không đổi `catalog`; không tự cắt số câu;
- giới hạn tổng của lượt vẫn do `ScriptRunner` (`SCRIPT_LLM_TIMEOUT_S` / `SCRIPT_RETRY_TIMEOUT_S`) và `ShowDirector` (`LLM_TIMEOUT_S`) giữ;
  engine chỉ thêm giới hạn chờ câu đầu theo mục.

**Khác ARCHITECTURE §3:**
- Protocol không đổi.
- Dòng đầu §3 liệt kê biến chọn adapter (`COMMENT_SOURCE`, `TTS_PROVIDER`, `AVATAR_MODE`, `OUTPUT_MODE`) chưa có `REPLY_ENGINE`; thêm vào,
  kèm giá trị `chain | gemini | fake`.
- Docstring `ReplyEngine` thêm: "Implementations: ChainReplyEngine (chuỗi model OpenAI-compatible, ADR-035/037), GeminiReplyEngine,
  FakeReplyEngine." Sửa ARCHITECTURE ở pha Foundational của `/sdd.tasks`.
- §1 (sơ đồ, bước 4) đổi "Gemini API" thành chuỗi model; ghi "chưa code" bỏ đi khi xong feature.

## 2. `ChainReplyEngine` (`brain/chain_engine.py`)

```python
FaultHook = Callable[[str], str | None]  # label -> entry fault mode or None (dev only, research R8)

@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int | None

@dataclass(frozen=True)
class Attempt:
    label: str
    outcome: Literal["ok", "failed", "skipped", "cancelled"]
    reason: AttemptReason | None
    routed_via: str | None              # full X-Routed-Via value, also on wrong_platform
    elapsed_s: float
    injected: bool = False

@dataclass(frozen=True)
class TurnRecord:
    turn_key: str                       # comment.id or segment_id
    kind: Literal["reply", "segment"]
    label: str | None
    model: str | None
    provider: str | None
    attempts: list[Attempt]
    outcome: Literal["ok", "interrupted", "exhausted", "cancelled"]
    usage: Usage | None

class ChainReplyEngine:
    def __init__(
        self,
        entries: list[ResolvedEntry],          # ChainEntryConfig + the SecretStr key, resolved by from_settings
        *,
        cooldown_s: float,
        max_tokens: int,                       # LLM_MAX_TOKENS for reply()
        script_max_tokens: int,                # SCRIPT_MAX_TOKENS for narrate()
        transport: httpx.AsyncBaseTransport | None = None,   # httpx.MockTransport in tests
        clock: Callable[[], datetime] = ...,   # injectable for ChainState
        fault_hook: FaultHook | None = None,
    ) -> None: ...

    @classmethod
    def from_settings(cls, settings: Settings, *, only: str | None = None,
                      fault_hook: FaultHook | None = None) -> ChainReplyEngine: ...
    # Raises ReplyEngineError("config_error") on any rule of data-model §1. `only=LABEL` builds a one-entry chain with cooldown 0
    # (qa_eval --entry, research R10); an unknown label is a config_error.

    async def preflight(self) -> list[PreflightResult]: ...
    # One GET {base_url}/models per distinct (base_url, key_env) (research R9). Logs llm_preflight; raises
    # ReplyEngineError("config_error") naming the failing entries when any result has ok=False. Called once by the
    # app lifespan and by qa_eval, never during a show.

    def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]: ...
    def narrate(self, request: SegmentRequest, catalog: ProductCatalog) -> AsyncIterator[str]: ...

    def add_turn_observer(self, cb: Callable[[TurnRecord], None]) -> None: ...
    def add_state_observer(self, cb: Callable[[ChainSnapshot], None]) -> None: ...
    def snapshot(self) -> ChainSnapshot: ...
    @property
    def entries(self) -> list[ChainEntryConfig]: ...
    async def aclose(self) -> None: ...                           # closes the shared httpx.AsyncClient
```

Hành vi của một lượt (cả `reply` và `narrate`):
1. Dựng `messages` như Gemini: `system` = `build_system_prompt(catalog)` / `build_script_system_prompt(catalog)`, `user` =
   `build_user_message(comment)` / `build_segment_message(request, catalog)`.
2. Đi qua các mục theo thứ tự; mục `resting` (chưa hết `retry_at`) thì ghi `Attempt(skipped)` và bỏ qua, không gọi mạng.
3. Với mục được thử: gọi `fault_hook(label)` nếu có; có lỗi giả thì tạo lỗi đó. Không thì mở stream qua `OpenAICompatClient`; client kiểm
   nền tảng (`X-Routed-Via`) ngay sau header, trước chữ đầu (research R6).
4. Lấy câu đầu trong `first_sentence_timeout_s` của mục (đọc chữ, đưa vào `SentenceSplitter`, tới khi có câu hoặc hết luồng). Khối timeout
   đóng trước khi `yield` (research R1).
5. Lỗi trước câu đầu: phân loại theo R3; mọi lý do trừ `blocked` cho mục nghỉ `cooldown_s`; log `llm_attempt` + `llm_switch`, thử mục kế.
6. Có câu đầu: `yield` các câu của mục đó tới hết luồng; `flush()` splitter cuối luồng. Lỗi lúc này: mục nghỉ (`interrupted`), ném
   `ReplyEngineError("api_error")`.
7. Không còn mục: log `llm_chain_exhausted`, ném `ReplyEngineError` theo R7.
8. `finally`: đóng response httpx; gửi `TurnRecord` cho turn observer (cả khi hủy, `outcome="cancelled"`); log `llm_usage` nếu có.

`CancelledError` / `GeneratorExit` (bỏ qua, tạm dừng, kết thúc, giới hạn tổng bên ngoài): đóng response, không đổi `ChainState`, ném lại.

## 3. `OpenAICompatClient` (`brain/openai_compat.py`)

```python
class ProviderFailure(Exception):
    reason: AttemptReason
    status: int | None
    message: str            # already redacted (research R12); Retry-After is not read (research R3)

@dataclass
class StreamMeta:
    routed_via: str | None  # X-Routed-Via header
    model: str | None       # response "model"
    finish_reason: str | None
    usage: Usage | None

class OpenAICompatClient:
    def __init__(self, client: httpx.AsyncClient, secrets: Sequence[str]) -> None: ...
    def stream_chat(self, entry: ResolvedEntry, messages: list[dict[str, str]], max_tokens: int,
                    meta: StreamMeta) -> AsyncIterator[str]: ...
    # Yields text deltas. Raises ProviderFailure for HTTP errors, SSE error frames and transport errors; the caller decides
    # whether that is before or after the first sentence. When entry.platform is set, checks the platform part of
    # X-Routed-Via right after the status line and raises ProviderFailure(WRONG_PLATFORM) before reading any SSE line.
    # Request body: {"model", "messages", "stream": true, "stream_options": {"include_usage": true}, "max_tokens", **entry.params}
    async def list_models(self, base_url: str, key: SecretStr) -> ModelListing: ...
    # GET {base_url}/models with a 5 s timeout. Returns {id: ModelRow(available: bool | None, unavailable_reason, execution_status)};
    # raises ProviderFailure(CONNECTION) or ProviderFailure(REJECTED, status) so preflight can name the problem.
```

- Header: `Authorization: Bearer <key>`; mục có `platform` gửi thêm `X-FreeLLM-Cache: off` (research R2). Không log header, không log body
  request.
- `httpx.Timeout(connect=2.0, read=None, write=5.0, pool=2.0)`: giới hạn câu đầu do engine giữ; đọc giữa luồng do giới hạn tổng bên ngoài.
  `TODO:` đo thời gian bắt tay TLS tới `api.groq.com` từ laptop; nếu > 1 s thì xem lại `connect`.
- Phân loại HTTP theo `research.md` R3; đọc `error.code` (freellmapi) hoặc `error.type` trong body JSON.

## 4. `ChainState` (`brain/chain_state.py`, thuần)

```python
class AttemptReason(StrEnum):
    RATE_LIMITED = "rate_limited"; OVERLOADED = "overloaded"; EMPTY = "empty"; CONNECTION = "connection"
    TIMEOUT = "timeout"; REJECTED = "rejected"; WRONG_PLATFORM = "wrong_platform"; BLOCKED = "blocked"
    INTERRUPTED = "interrupted"

RESTING_REASONS: frozenset[AttemptReason]   # all except BLOCKED

class ChainState:
    def __init__(self, labels: Sequence[str], clock: Callable[[], datetime]) -> None: ...
    def status(self, label: str) -> EntryState: ...           # resting past retry_at reads as ready
    def is_ready(self, label: str) -> bool: ...
    def rest(self, label: str, seconds: float, reason: AttemptReason) -> datetime: ...   # returns retry_at = now + seconds
    def snapshot(self) -> list[EntryState]: ...
```

## 5. `FaultInjector` (`director/faults.py`, mở rộng)

```python
FAULT_STEPS = ("llm", "tts", "render")             # unchanged
FAULT_MODES = ("error", "timeout")                 # unchanged, step-wide
ENTRY_FAULT_MODES = ("rate_limited", "overloaded", "timeout", "empty", "wrong_platform", "interrupted")

class FaultInjector:
    def inject(self, step: str, mode: str, count: int = 1, entry: str | None = None) -> None: ...
    # entry given: step must be "llm" and mode in ENTRY_FAULT_MODES; queued per label.
    def take_entry(self, label: str) -> str | None: ...   # pops one pending mode for that label
    def pending_entry(self, label: str) -> int: ...
```

`brain/` chỉ nhận một `Callable[[str], str | None]` (là `faults.take_entry`), không import `director/`.

## 6. Bộ kiểm (`qa_eval`)

- `run --entry LABEL`, `script --entry LABEL` (research R10). `--entry` chỉ hợp lệ khi `REPLY_ENGINE=chain`, không thì báo lỗi cấu hình.
- Runner gọi `preflight()` trước câu hỏi đầu; lỗi → mã thoát lỗi cấu hình.
- Runner đăng ký turn observer để lấy `label`, `model`, `provider` của từng câu hỏi hoặc phân đoạn (data-model §8).
