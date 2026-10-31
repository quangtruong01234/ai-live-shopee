# Hợp đồng adapter: 003-vietnamese-tts

> Kiểu dữ liệu ở [`../data-model.md`](../data-model.md). Mọi test mặc định chạy không cần mạng, key hay model (Điều V).

## 1. Protocol `TTSEngine` (sửa so với 001)

```python
from typing import AsyncIterator, Protocol


class TTSEngine(Protocol):
    """Vietnamese TTS. Output: PCM16 little-endian, mono, exactly `sample_rate` Hz (16000, ADR-025)."""
    sample_rate: int
    async def warm_up(self) -> None: ...                    # MỚI: nạp model trước phiên; nguồn không cần thì không làm gì
    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...


class TTSEngineError(RuntimeError):                         # MỚI, ở core/protocols.py, giống ReplyEngineError
    """`kind`: quota_exhausted | rate_limited | api_error | config_error | model_error. `message` tiếng Việt."""
    def __init__(self, kind: str, message: str) -> None: ...
    kind: str
```

| Thành phần | Hợp đồng |
|-----------|----------|
| `warm_up()` | Gọi một lần lúc mở app (lifespan) và trước câu đầu của CLI. Không chặn event loop. Lỗi ném `TTSEngineError(config_error)`; app ghi log `tts_warm_up_failed` và vẫn mở (lượt đầu sẽ báo lỗi ở bước tts). |
| `synthesize(text)` | Async generator. Chunk đầu là mốc `tts_first_chunk` (ShowDirector ghi, như 001). Mỗi chunk có số byte chẵn (trọn mẫu int16). Lỗi ném `TTSEngineError` (hoặc ngoại lệ khác; ShowDirector đọc `kind` nếu có). |
| Hủy | Khi ShowDirector bỏ qua lượt hoặc hết giờ, nó gọi `aclose()` trên generator. Adapter PHẢI dừng việc tạo tiếng còn lại (FR-014): `vieneu` bật cờ dừng cho luồng, `gemini` đóng stream HTTP. |
| Tuần tự | Mỗi adapter chỉ tạo một câu tại một thời điểm (khóa `asyncio.Lock` bên trong). ShowDirector vốn gọi tuần tự nên không chờ thêm. |

## 2. Các lớp cụ thể

```python
class FakeTTS:            # đã có (001). Thêm `async def warm_up(self) -> None: return None`.
    ...


class VieneuTTS:          # MỚI, ai_live/tts/vieneu_tts.py. Import `vieneu` và `numpy` bên trong (chỉ khi TTS_PROVIDER=vieneu).
    def __init__(self, *, voice: str, cpu_threads: int, sample_rate: int = 16000) -> None: ...
    async def warm_up(self) -> None: ...                     # asyncio.to_thread: nạp Vieneu(backend="onnx"), kiểm tên giọng, đọc thử "Dạ."
    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...
    # Luồng phụ chạy infer_stream(text, voice=...) → float32 48 kHz → int16 → 16 kHz → loop.call_soon_threadsafe(queue.put_nowait, ...)


class GeminiTTS:          # MỚI, ai_live/tts/gemini_tts.py. Dùng google-genai đã có (ADR-018).
    def __init__(self, *, client: "genai.Client", model: str, voice: str, sample_rate: int = 16000) -> None: ...
    async def warm_up(self) -> None: ...                     # không gọi API (không tốn hạn mức)
    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...
    # client.aio.interactions.create(model=..., input=text, response_format={"type": "audio", "mime_type": "audio/l16",
    #   "sample_rate": sample_rate}, generation_config={"speech_config": [{"voice": voice}]}, stream=True)
    # → sự kiện step.delta có delta.type == "audio" → base64.b64decode(delta.data)
    # Chỉ gửi `text` (đã chuẩn hóa) và câu chỉ dẫn giọng cố định; không gửi session_id, utterance_id, tên khách hay metadata khác.
    # APIError code 429 → TTSEngineError("quota_exhausted", "Hết hạn mức giọng nói (Gemini TTS, gói miễn phí)..."); khác → "api_error".


class SpeechTTS:          # MỚI, ai_live/tts/speech.py. Lớp bọc do create_tts() luôn trả về; thỏa TTSEngine.
    def __init__(self, engine: TTSEngine, *, provider: str, normalize: Callable[[str], str],
                 quota_cooldown_s: float, clock: Callable[[], float] = time.monotonic) -> None: ...
    sample_rate: int                                         # = engine.sample_rate
    usage: TTSUsage                                          # data-model §4
    async def warm_up(self) -> None: ...                     # chuyển tiếp
    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...
    # 1. Đang nghỉ (cooling_down) → ném ngay TTSEngineError(quota_exhausted, ... "thử lại sau N giây").
    # 2. spoken = normalize(text); spoken rỗng → kết thúc không có chunk (câu chỉ có emoji/link).
    # 3. usage.requests += 1; usage.chars += len(spoken); chuyển tiếp các chunk của engine.synthesize(spoken).
    # 4. Bắt TTSEngineError(quota_exhausted) → vào cooling_down, usage.quota_errors += 1, ném lại.
    # aclose() của lớp bọc đóng generator bên trong.
```

**Câu rỗng sau chuẩn hóa:** ShowDirector 001 đã xử lý stream không có chunk (`first is None`), vẫn đánh dấu `tts_first_chunk` và đẩy
câu cho trình phát. Plan không đổi hành vi đó.

## 3. Chuẩn hóa

```python
# ai_live/tts/normalize.py
def load_abbreviations(path: Path) -> dict[str, str]: ...   # data/rules/tts_abbreviations.json; sai định dạng → ValueError
def normalize_for_speech(text: str, abbreviations: Mapping[str, str]) -> str: ...  # hàm thuần, quy tắc ở data-model §3
```

## 4. Factory

```python
def create_tts(settings: Settings) -> SpeechTTS: ...
# fake   → SpeechTTS(FakeTTS(...))
# vieneu → SpeechTTS(VieneuTTS(voice=settings.vieneu_voice, cpu_threads=settings.vieneu_cpu_threads, ...))
# gemini → SpeechTTS(GeminiTTS(client=genai.Client(api_key=...), model=settings.gemini_tts_model, voice=settings.gemini_tts_voice))
# Thiếu `vieneu` chưa cài, hoặc thiếu GEMINI_API_KEY → TTSConfigError với thông báo tiếng Việt chỉ cách sửa.
```

## 5. So với `docs/ARCHITECTURE.md` §3

| Điểm | ARCHITECTURE §3 hiện tại | Feature này | Xử lý |
|------|--------------------------|-------------|-------|
| `sample_rate` | `TODO: thống nhất 16 kHz mono PCM16 theo yêu cầu của lip-sync?` | Chốt 16 kHz mono PCM16 | ADR-025 đề xuất; sửa §3 khi ADR được chốt |
| Implementations | "OSS model (TODO: chọn), ElevenLabs, FakeTTS" | `VieneuTTS`, `GeminiTTS`, `FakeTTS` (+ lớp bọc `SpeechTTS`) | ADR-024 đề xuất; sửa §3 khi chốt |
| `warm_up()` | Không có | Thêm vào Protocol | Ghi trong ADR-024; sửa §3 |
| `TTSEngineError` | Không có | Thêm, giống `ReplyEngineError` | Sửa §3 |
| ElevenLabs | Có trong danh sách | Bỏ khỏi cấu hình (không có adapter) | ADR-024 ghi lý do; `docs/VENDORS.md` vẫn giữ làm ứng viên |
