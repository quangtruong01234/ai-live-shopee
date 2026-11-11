# Nghiên cứu (Phase 0): Chuỗi model LLM miễn phí, tự chuyển model khi lỗi

- **Feature:** `008-llm-provider-chain` · **Ngày:** 2026-11-03 · **Plan:** [plan.md](./plan.md)
- Mỗi mục theo dạng **Quyết định / Lý do / Phương án đã cân nhắc**. Chỗ chưa chắc ghi `TODO:` kèm câu hỏi cụ thể.
- Nguồn bên ngoài chính: mã nguồn freellmapi (bản đã cài theo ADR-034, commit `21d287a`, 2026-11-01), các file
  `server/src/routes/proxy.ts`, `server/src/lib/fallback-loop.ts`, `server/src/lib/stream-keepalive.ts`,
  `server/src/lib/error-redaction.ts`, `server/src/services/cache.ts`, `server/src/providers/cloudflare.ts`,
  `server/src/providers/index.ts`, `server/src/app.ts`. Số đo độ trễ lấy từ benchmark ghi ở ADR-035 (2026-11-02, 2026-11-03).
- **Sửa 2026-11-03 sau khi duyệt plan:** freellmapi chỉ dùng cho một ngày demo (spec "Phạm vi dùng"). Bỏ nghỉ theo `Retry-After`, trạng
  thái tắt mục, kiểm dịch vụ gom key mỗi 15 s và thống kê request/token của show. Thêm kiểm lúc khởi động (R9) và kiểm nền tảng (R6).

---

## R1. Cấu trúc bộ sinh lời thoại theo chuỗi

**Quyết định:** Thêm ba module trong `brain/`, không đổi Protocol `ReplyEngine`:

1. `brain/openai_compat.py`: lớp `OpenAICompatClient`.
   - `stream_chat(...)` gửi một request streaming `POST {base_url}/chat/completions` bằng `httpx` (`client.stream(...)`), đọc SSE bằng
     `aiter_lines()`:
     - dòng bắt đầu bằng `:` (ví dụ `: keepalive` của freellmapi) là chú thích, bỏ qua;
     - `data: [DONE]` kết thúc luồng;
     - chữ lấy từ `choices[0].delta.content`; bỏ qua mọi trường suy luận (`reasoning`, `reasoning_content`);
     - đọc `finish_reason`; đọc `usage` ở chunk cuối (Groq có thể đặt ở `x_groq.usage`, xem TODO ở R6);
     - một frame `{"error": ...}` trong luồng là lỗi.
   - Header response (`X-Routed-Via`) đọc ngay khi có status, **trước dòng SSE đầu tiên**, để kiểm nền tảng (R6).
   - `list_models(base_url, key)` gọi `GET {base_url}/models` cho lần kiểm lúc khởi động (R9).
   - Lỗi ném ra là `ProviderFailure(reason, status, message)` (lớp nội bộ của `brain/`, không phải `ReplyEngineError`).
2. `brain/chain_state.py`: lớp thuần `ChainState` (không I/O, đồng hồ tiêm vào được) giữ trạng thái từng mục: `ready` hoặc
   `resting(until, reason)`. Có `next_ready(after)`, `rest(label, reason)`, `snapshot()`. Mục đang nghỉ mà đã quá `until` thì tự coi là
   `ready` khi đọc.
3. `brain/chain_engine.py`: lớp `ChainReplyEngine` thực thi `reply()` và `narrate()`:
   - dùng lại hàm dựng prompt của Gemini (`brain/prompt.py`, `brain/script_prompt.py`), `SentenceSplitter`, và cách đóng luồng trong
     `finally` như `gemini_engine.py`;
   - mỗi lượt đi từ mục cao nhất đang sẵn sàng (FR-015); lấy câu đầu trong giới hạn chờ của mục; lỗi trước câu đầu thì cho mục nghỉ rồi thử
     mục kế (FR-007); sau câu đầu thì không chuyển nữa (FR-008);
   - `preflight()` chạy lần kiểm lúc khởi động (R9);
   - có hai loại observer: `add_turn_observer(cb)` nhận `TurnRecord` khi một lượt kết thúc, `add_state_observer(cb)` nhận ảnh chụp
     chuỗi mỗi khi trạng thái đổi;
   - nhận một hook giả lập lỗi theo mục (R8) và có `aclose()` để đóng `httpx.AsyncClient`, gọi ở bước tắt của lifespan.

   Test dùng `httpx.MockTransport` qua một nhà cung cấp giả `tests/fixtures/fake_openai.py`: không cần Protocol riêng cho HTTP client.

**Điểm phải tránh khi viết code:** không `yield` bên trong khối `asyncio.timeout(...)` của một async generator. Luồng show và luồng comment
gọi `asyncio.wait_for(anext(stream), ...)`, nên mỗi lần `anext` có thể chạy trong một task khác; khối timeout mở qua một `yield` sẽ hủy nhầm
task hoặc ném lỗi. Cách làm: lấy câu đầu trong khối timeout, ra khỏi khối, rồi mới `yield`.

**Lý do:**
- Điều IV: một adapter cho mọi nhà cung cấp có cùng kiểu giao tiếp OpenAI-compatible (freellmapi, Groq, sau này IteraCompute).
- Điều VII: `httpx` đã có trong `uv.lock` (dev), không thêm SDK nào; ADR-035 đã ghi dùng `httpx` khi làm adapter.
- Tách `ChainState` thuần cho phép test nghỉ và quay lại ngay bằng đồng hồ giả, không cần mạng (FR-023, Điều V).

**Phương án đã cân nhắc:**
- SDK `openai` cho Python: thêm một dependency lớn chỉ để parse SSE; khó đọc được header `X-Routed-Via` và frame lỗi riêng của freellmapi.
  Loại.
- Đưa toàn bộ việc chuyển model cho freellmapi (một model id gom nhiều nền tảng): freellmapi tự chuyển trong 45 s và có thể dùng model
  chưa benchmark (R6). ADR-034 và ADR-035 cấm để dịch vụ tự chọn. Loại.
- Một lớp `FallbackReplyEngine` bọc nhiều `ReplyEngine` (Gemini + OpenAI-compatible): cần chuẩn hóa lỗi của từng SDK, và Gemini đã đi
  được qua freellmapi. Để sau nếu có nhà cung cấp không OpenAI-compatible (ngoài phạm vi spec).

---

## R2. Cấu hình chuỗi

**Quyết định:**
- `REPLY_ENGINE` thành `Literal["gemini", "chain", "fake"]`, mặc định `chain` (spec "Giả định"). `.env.example` đặt cùng giá trị vì
  `tests/unit/test_config.py` kiểm mặc định trùng nhau.
- `LLM_CHAIN` là một mảng JSON viết trên một dòng. pydantic-settings parse trường kiểu phức tạp bằng JSON, nên khai
  `llm_chain: list[ChainEntryConfig]` trong `core/config.py`.
- Mỗi mục có:

  | Trường | Kiểu | Bắt buộc | Ghi chú |
  |--------|------|----------|---------|
  | `label` | str | có | nhãn ngắn hiển thị, duy nhất trong chuỗi |
  | `base_url` | str | có | ví dụ `http://127.0.0.1:3001/v1` |
  | `model` | str | có | tên ghim cứng; cấm `auto`, `auto:*` và `fusion` |
  | `key_env` | str | có | tên biến key, phải là một trường secret của `Settings` |
  | `first_sentence_timeout_s` | float > 0 | có | giới hạn chờ câu đầu của mục (R4) |
  | `platform` | str | có khi `base_url` là loopback | nền tảng mong đợi trong `X-Routed-Via` (R6), ví dụ `cloudflare`, `groq` |
  | `params` | dict | không | trộn vào body request (ví dụ `reasoning_effort`); không được đặt `model`, `messages`, `stream`, `stream_options` |

- `key_env` chỉ được là tên một trường `SecretStr` của `Settings`: `GEMINI_API_KEY` (đã có), `FREELLMAPI_KEY`, `GROQ_API_KEY` (mới).
  pydantic-settings không đưa giá trị trong `.env` vào `os.environ`, nên engine không đọc `os.environ[key_env]` mà đọc trường tương ứng
  của `Settings`.
- `base_url` loopback là host `127.0.0.1`, `localhost` hoặc `::1`: đó là dịch vụ gom key (ADR-034). Mục loopback **phải** khai
  `platform` (FR-004, FR-024). Mục gọi thẳng nhà cung cấp có thể bỏ `platform`; khi đó không kiểm nền tảng và nhà cung cấp trong log là
  host của `base_url`.
- `ChainReplyEngine.from_settings()` kiểm và ném `ReplyEngineError("config_error", ...)` (app từ chối khởi động như khi thiếu
  `GEMINI_API_KEY` hôm nay; FR-004). Từ chối khi:
  - chuỗi rỗng; `model` rỗng, là `auto`, `fusion` hoặc bắt đầu bằng `auto:`; `base_url` rỗng;
  - `key_env` không phải trường secret đã biết, hoặc trường đó chưa có giá trị;
  - mục loopback không có `platform`;
  - trùng `label`;
  - `params` đặt khóa bị cấm;
  - tổng `first_sentence_timeout_s` > min(`LLM_TIMEOUT_S`, `SCRIPT_LLM_TIMEOUT_S`) (hiện là min(8, 10) = 8 s; FR-009).

  Thông báo nêu số thứ tự và nhãn mục, tên biến; không in giá trị key. Sau bước này là lần kiểm qua mạng (R9).
- `LLM_CHAIN_COOLDOWN_S` = `60`: thời gian nghỉ cố định của mọi lỗi (R5).
- Mọi request tới mục có `platform` gửi thêm header `X-FreeLLM-Cache: off`. Bộ nhớ đệm câu trả lời của freellmapi tắt sẵn
  (`services/cache.ts`), nhưng nếu ai đó bật thì một lượt trúng cache sẽ phát lại câu cũ, trái Điều I. Header này tắt cache cho riêng
  request đó (`services/cache.ts`, dòng 120–134: nhận `off|no|0|false|bypass|skip`).
- Chuỗi mặc định trong `Settings` và `.env.example` có 3 mục theo ADR-035; Gemini (mục 4) để thành dòng ví dụ đã comment trong
  `.env.example` cho tới khi qua benchmark US4:

  ```
  LLM_CHAIN=[{"label":"sealion","base_url":"http://127.0.0.1:3001/v1","model":"gemma-sea-lion-v4-27b","key_env":"FREELLMAPI_KEY","platform":"cloudflare","first_sentence_timeout_s":3.5},{"label":"gptoss","base_url":"http://127.0.0.1:3001/v1","model":"gpt-oss-120b","key_env":"FREELLMAPI_KEY","platform":"groq","first_sentence_timeout_s":2.0,"params":{"reasoning_effort":"low"}},{"label":"qwen","base_url":"https://api.groq.com/openai/v1","model":"qwen/qwen3.8-27b","key_env":"GROQ_API_KEY","first_sentence_timeout_s":2.0,"params":{"reasoning_effort":"none"}}]
  ```
  Đổi bởi ADR-040 (2026-11-05): bỏ `gptoss`, SEA-LION chờ 2,5 s; giá trị hiện hành ở contracts/config.md §2.

  Tổng giới hạn chờ câu đầu: 3,5 + 2,0 + 2,0 = 7,5 s ≤ 8 s. `cloudflare` và `groq` là id nền tảng của freellmapi
  (`providers/cloudflare.ts:109`, `providers/index.ts:69`); benchmark ADR-035 chạy SEA-LION trên Cloudflare và gpt-oss-120b trên Groq.

**TODO:**
- `TODO:` Tên model chính xác trên freellmapi và Groq (`gemma-sea-lion-v4-27b`, `gpt-oss-120b`, `qwen/qwen3.8-27b`) có đúng như trên
  không? Lần kiểm lúc khởi động (R9) sẽ báo sai ngay; vẫn chạy `GET /v1/models` của freellmapi và
  `GET https://api.groq.com/openai/v1/models` một lần trước khi chốt `.env.example`. Đã trả lời ở T055 (2026-11-04): cả ba tên có trên
  dịch vụ, `llm_preflight ok=true`.
- `TODO:` `GEMINI_API_KEY` được phép làm `key_env` để sau này gọi thẳng endpoint OpenAI-compatible của Gemini; chưa kiểm endpoint đó
  stream SSE có giống OpenAI không. Mục 4 mặc định đi qua freellmapi như ADR-035, nên chưa cần kiểm ở feature này.
- `TODO:` python-dotenv (pydantic-settings dùng khi đọc `.env`) có đọc đúng một giá trị JSON không đặt trong nháy không, nhất là dấu `"`
  và `:`? `tests/unit/test_config.py` sẽ bắt lỗi này; nếu sai thì bọc giá trị trong nháy đơn ở `.env.example`.

**Lý do:** Đổi chuỗi chỉ bằng cấu hình, không sửa code (FR-020, spec "Giả định"). Một biến JSON giữ thứ tự mục rõ ràng hơn nhiều biến
`LLM_CHAIN_1_*`. Kiểm tổng thời gian chờ lúc khởi động bảo đảm FR-009 không phụ thuộc người vận hành tự cộng. Bắt buộc `platform` cho mục
loopback vì đó là chỗ duy nhất một tên model có thể bị phục vụ bởi nền tảng khác (R6).

**Phương án đã cân nhắc:**
- Nhiều biến `LLM_CHAIN_<N>_MODEL`, `..._URL`: dài, dễ hở số thứ tự. Loại.
- File YAML riêng cho chuỗi: thêm một nguồn cấu hình ngoài `.env`, trái ADR-015. Loại.
- Đọc key bằng `os.environ[key_env]`: không thấy giá trị trong `.env` (pydantic-settings không export). Loại.
- Cho phép tên biến key tùy ý: cần đọc `.env` lần hai; danh sách trường cố định đủ cho ADR-035 (thêm nhà cung cấp mới thì thêm trường
  và ADR). Loại.
- Ghim nền tảng bằng tên model riêng của nền tảng (ví dụ `@cf/aisingapore/gemma-sea-lion-v4-27b-it`): freellmapi định tuyến theo id
  trong catalog của nó, không theo id của nền tảng; chưa kiểm được cách này có chặn gom nhóm không. Kiểm header sau khi có response chắc
  chắn hơn. Loại.

---

## R3. Phân loại lỗi

**Quyết định:** Mỗi lần thử một mục kết thúc bằng một trong các kết quả sau. Bảng dựa trên cách freellmapi trả lỗi
(`routes/proxy.ts`, `lib/fallback-loop.ts`) và mã HTTP chuẩn của API OpenAI-compatible. Lý do chỉ để ghi log và hiển thị; mọi lỗi trước câu
đầu (trừ `blocked`) xử lý như nhau: chuyển mục kế và nghỉ `LLM_CHAIN_COOLDOWN_S`.

| Trường hợp | Lý do (`reason`) | Xử lý |
|------------|------------------|-------|
| HTTP 429 | `rate_limited` | chuyển; nghỉ cố định (không đọc `Retry-After`) |
| HTTP 500 / 502 / 503 / 504 (trừ các mã ở dòng `rejected`); frame lỗi SSE trước câu đầu | `overloaded` | chuyển; nghỉ |
| HTTP 502 `empty_completion`, hoặc luồng kết thúc không có chữ | `empty` | chuyển; nghỉ |
| `httpx.ConnectError`, `ReadError`, `RemoteProtocolError` | `connection` | chuyển; nghỉ |
| Hết `first_sentence_timeout_s` mà chưa có câu đầu | `timeout` | chuyển; nghỉ |
| HTTP 400 / 401 / 403 / 404 (`model_not_found`) / 422 / 4xx khác; 502 `provider_authentication_failed`; 502 `provider_error`; 503 `no_providers_configured` | `rejected` | chuyển; nghỉ (lỗi cấu hình lộ ra giữa show) |
| `X-Routed-Via` thiếu, là `cache`, hoặc nền tảng khác `platform` của mục | `wrong_platform` | đóng response trước khi đọc chữ; chuyển; nghỉ (FR-024) |
| `finish_reason = content_filter` và không có chữ | `blocked` | chuyển, không nghỉ |
| Lỗi sau câu đầu (frame lỗi, ngắt kết nối) | `interrupted` | ném `ReplyEngineError("api_error")`; không chuyển; mục nghỉ để lượt kế dùng mục kế (US2 #3) |
| `CancelledError` / `GeneratorExit` | (hủy) | dừng ngay; không nghỉ, không chuyển (FR-013) |

- Câu bị guard chặn không bao giờ tới engine như một lỗi: guard chạy ở `ShowDirector` / `ScriptRunner` sau khi engine đã `yield` câu, nên
  không tính là lỗi nhà cung cấp (FR-014).
- Lỗi cấu hình (`rejected`) thường đã bị lần kiểm lúc khởi động bắt (R9). Nếu lộ ra giữa show (key bị thu hồi, model bị tắt trên dashboard
  freellmapi) thì mục chỉ nghỉ rồi được thử lại; mỗi lần thử lại bị từ chối ngay nên tốn rất ít. Chuỗi chỉ chạy một ngày demo nên chấp
  nhận cách này thay cho trạng thái tắt mục.
- `blocked` không nghỉ vì đó là lỗi theo nội dung của lượt, không phải nhà cung cấp hỏng; lượt kế vẫn thử mục đó trước.

**Lý do:** FR-007 (mọi lỗi trước câu đầu thì chuyển), FR-010 (nghỉ cố định), FR-008 (không trộn câu hai model), FR-013 (hủy không phạt mục).
freellmapi ánh xạ lỗi upstream thành các mã trên: model không biết hoặc đã tắt → 404 `model_not_found`; không có key bật → 503
`no_providers_configured`; key thống nhất sai → 401; mọi key upstream lỗi xác thực → 502 `provider_authentication_failed`; lỗi 4xx không
thử lại được của upstream → 502 `provider_error`; mọi lần thử đều bị giới hạn → 429; luồng rỗng → 502 `empty_completion`; lỗi giữa luồng →
frame SSE `stream_error` rồi `[DONE]`.

**Phương án đã cân nhắc:**
- Thử lại cùng mục một lần trước khi chuyển: tốn thêm thời gian chờ, làm vượt SC-003 (+1 s). Mục kế đã là bản thử lại. Loại.
- Tắt hẳn mục khi gặp lỗi cấu hình (bản plan đầu): thêm một trạng thái và một loại lỗi khi hết chuỗi chỉ để phục vụ phiên chạy dài; lần
  kiểm lúc khởi động đã bắt phần lớn lỗi cấu hình. Loại (làm rõ 2026-11-03).
- Nghỉ theo `Retry-After` / `retryAtMs` (bản plan đầu): chỉ có lợi khi chạy nhiều giờ liền. Loại (làm rõ 2026-11-03).

---

## R4. Giới hạn chờ câu đầu từng mục

**Quyết định:**
- SEA-LION: 3,5 s (benchmark ADR-035: câu đầu p95 2,81 s với kịch bản, 2,40 s với trả lời). Đổi bởi ADR-040: 2,5 s sau số đo T055
  (p95 1,30 s, lớn nhất 2,11 s; câu chào khi hết giờ 1/5 lần 7,08 s).
- gpt-oss-120b và Qwen3.8 (Groq): 2,0 s mỗi mục (p95 1,04–1,40 s).
- Giới hạn tổng bên ngoài không đổi: `ScriptRunner` dùng `SCRIPT_LLM_TIMEOUT_S` (10 s) hoặc `SCRIPT_RETRY_TIMEOUT_S` (4 s) ở chế độ dự
  phòng; đường comment dùng `LLM_TIMEOUT_S` (8 s). Hết giờ bên ngoài là một lần hủy (`CancelledError` vào generator), nên mục đang thử không
  bị nghỉ (R3).
- freellmapi tự chuyển key và nền tảng trong tối đa 45 s (`fallback-loop.ts`); giới hạn chờ của mục cắt trước, và freellmapi không phạt key
  khi client tự ngắt (`proxy.ts`).

**Ước tính câu đầu của câu chào mở màn (SC-001, SC-003):**
- Mục 1 lỗi ngay (kể cả `wrong_platform`, biết ngay khi có header): ≈ 0,3 s + 1,04 s (p95 mục 2) ≈ 1,4 s tới câu đầu, còn dư nhiều trong 5 s.
- Mục 1 hết giờ chờ: 3,5 s + ≈ 1,4 s + TTS chunk đầu ≈ 4,9–5,9 s, **có thể vượt 5 s**. Ghi thành rủi ro Q18 và vào bảng độ trễ của plan.
- Chế độ dự phòng (4 s tổng): mục 1 hết giờ ở 3,5 s thì mục 2 chỉ còn 0,5 s, thường bị cắt; lượt đó thành một lần LLM lỗi của 004 như
  hiện nay. Chấp nhận: chế độ dự phòng vốn là lúc chuỗi đang hỏng.

**Lý do:** FR-009 bắt tổng thời gian chờ nằm trong giới hạn của một phân đoạn. Giới hạn đặt quanh p95 × 1,25–1,5 để ít cắt nhầm lượt
chậm bình thường mà vẫn để chỗ cho các mục sau.

**Phương án đã cân nhắc:**
- Một giới hạn chung cho mọi mục: SEA-LION chậm hơn hẳn hai mục Groq, giới hạn chung hoặc cắt nhầm SEA-LION hoặc để mục Groq chờ quá lâu.
  Loại.
- Hạ SEA-LION xuống 2,5 s để câu chào luôn ≤ 5 s: cắt nhầm khoảng 5–10% lượt bình thường của model tốt nhất. Chờ số đo thật ở quickstart
  rồi chỉnh qua cấu hình. `TODO:` sau tổng duyệt G5, nếu câu chào > 5 s quá 1/10 lần thì hỏi người dùng có hạ giới hạn của mục 1 không.

---

## R5. Trạng thái nghỉ

**Quyết định:**
- Một `ChainState` cho cả phiên chạy app, dùng chung cho đường kịch bản và đường comment (spec "Giả định", trường hợp biên "gọi cùng lúc").
- Mỗi mục chỉ có hai trạng thái: `ready` và `resting(until, reason)`. Không có trạng thái tắt.
- Mọi lỗi ở R3 (trừ `blocked` và hủy) làm mục nghỉ đúng `LLM_CHAIN_COOLDOWN_S` tính từ lúc lỗi. Lỗi mới trong lúc đang nghỉ không xảy ra
  (mục nghỉ không được gọi), nên không cần gộp `until`.
- Hết nghỉ thì mục tự sẵn sàng; không có tác vụ nền nào đánh thức (đọc lại `until` mỗi lượt).
- asyncio chạy một luồng, các thao tác trên `ChainState` không có `await` ở giữa, nên không cần khóa.
- Hai lượt chạy song song cùng làm một mục lỗi (kịch bản và comment): lần `rest` sau ghi đè lần trước; khác nhau dưới 1 s, chấp nhận.

**Lý do:** FR-010, FR-015, SC-004. Không có trạng thái "đang thử lại" riêng: lượt kế sau khi hết nghỉ là lần thử lại (quay lại ngay,
làm rõ 2026-11-03).

**Phương án đã cân nhắc:**
- Nghỉ tăng dần (60 s, 120 s, 240 s...): thêm trạng thái, spec không đòi. Loại (Điều VII).
- Nghỉ theo `Retry-After`, tắt mục tới hết phiên: bỏ ở làm rõ 2026-11-03 (R3).
- Mỗi đường một trạng thái: đường comment sẽ gọi lại một mục mà đường kịch bản vừa thấy hỏng, trái trường hợp biên. Loại.

---

## R6. Định danh model, kiểm nền tảng và log

**Quyết định:**
- **Nền tảng thật** của một lượt qua freellmapi: header `X-Routed-Via`, dạng `<platform>/<modelId>`. Kiểm trong mã nguồn freellmapi:
  - với request streaming, header được đặt một lần lúc gửi header SSE cho lần thử nội bộ được chọn (`routes/proxy.ts` quanh dòng
    1585–1592). Các lần tự chuyển nội bộ trước đó được giữ lại ở phía freellmapi, nên header đến **trước chữ đầu tiên** và nêu đúng lần thử
    đang phục vụ;
  - `modelId` là id riêng của nền tảng (ví dụ `@cf/aisingapore/gemma-sea-lion-v4-27b-it` trên Cloudflare), nên chỉ so **phần nền tảng**
    (trước dấu `/` đầu tiên) với `platform` của mục; giá trị đầy đủ ghi vào log;
  - lượt trúng cache có `X-Routed-Via: cache` (dòng 2292, 2304); phát lại theo `Idempotency-Key` có `idempotency` (dòng 2340, engine không
    gửi header này). Cả hai không phải tên nền tảng nên bị từ chối.
- **Kiểm nền tảng (FR-024):** với mục có `platform`, ngay khi có status 200 và header, engine tách phần nền tảng của `X-Routed-Via`:
  - bằng `platform` (không phân biệt hoa thường) → đọc luồng như thường;
  - khác, là `cache` / `idempotency`, hoặc không có header → đóng response (không đọc dòng SSE nào), lần thử thành `wrong_platform`, mục
    nghỉ, lượt chuyển sang mục kế. Thông báo ghi nền tảng mong đợi và giá trị header thật.
- Mục không có `platform` (gọi thẳng nhà cung cấp): nhà cung cấp trong log là host của `base_url` (ví dụ `api.groq.com`), không kiểm.
- Model: trường `model` của response, nếu không có thì `model` của mục.
- Gửi `stream_options: {"include_usage": true}` để có `usage` (prompt, completion, cached tokens) ở chunk cuối; chỉ ghi vào log từng lượt.
- Sự kiện log mới (JSON, qua `log_event`, có `segment_id` + `topic` cho kịch bản hoặc `comment_id` cho comment như `llm_usage` hiện có):
  - `llm_preflight`: kết quả lần kiểm lúc khởi động theo từng mục (R9);
  - `llm_attempt`: label, model, provider, kết quả, thời gian tới câu đầu hoặc tới lỗi;
  - `llm_switch`: from_label, to_label, reason;
  - `llm_entry_rest`: label, reason, retry_at, seconds;
  - `llm_chain_exhausted`: lý do từng mục;
  - `llm_usage`: như Gemini, thêm label, provider.
- `ShowDirector` đăng ký turn observer và ghi thêm `llm_turn` có `utterance_id` (FR-005) bằng bảng `comment_id → utterance_id` của nó; đường
  kịch bản đã có `segment_id` trong log.

**TODO:**
- `TODO:` Groq có trả `usage` ở chunk cuối khi gửi `stream_options.include_usage` không, hay chỉ ở `x_groq.usage`? Đọc cả hai; kiểm bằng
  test `live_llm` lần đầu.
- `TODO:` freellmapi có chuyển `usage` của upstream xuống client trong chế độ stream không? Nếu không có thì log không có token (FR-005 cho
  phép "nếu nhà cung cấp trả về").

**Lý do:** FR-005, FR-024, SC-005. freellmapi bật gom nhóm (unify) thì một tên model ứng với cả nhóm: gpt-oss-120b có trên `groq`,
`cerebras`, `sambanova`, `openrouter` và `cloudflare` trong catalog của freellmapi (`db/migrations/20260101_000000_legacy_baseline.ts`). Chỉ header `X-Routed-Via` cho biết
nền tảng thật đã trả lời. Kiểm trước chữ đầu nên người xem không nghe câu nào từ nền tảng chưa benchmark (rủi ro Q16).

**Phương án đã cân nhắc:**
- Chỉ ghi tên model của cấu hình: không phát hiện được freellmapi đã đưa lượt sang nền tảng chưa benchmark. Loại.
- Chỉ ghi log nền tảng thật, không chặn (bản plan đầu): người xem vẫn nghe model chưa chấm. Loại (làm rõ 2026-11-03).
- Tắt nền tảng chưa benchmark trên dashboard freellmapi thay cho kiểm trong engine: vẫn nên làm (quickstart bước chuẩn bị), nhưng là thao
  tác tay dễ quên; kiểm trong engine bảo đảm SC-005 kể cả khi quên.

---

## R7. Hết chuỗi

**Quyết định:** Khi không còn mục nào để thử (đã thử hết trong lượt, hoặc mọi mục đang nghỉ), engine ném ngay `ReplyEngineError` với:
- `kind = "rate_limited"` nếu mọi lý do (của lần thử trong lượt hoặc của lần nghỉ đang chạy) đều là `rate_limited`;
- còn lại `kind = "api_error"`.

`config_error` chỉ dùng cho lỗi cấu hình lúc khởi động (R2, R9), không dùng khi hết chuỗi.

Thông báo tiếng Việt liệt kê lý do từng mục, ví dụ "Hết chuỗi model: sealion đang nghỉ (rate_limited, thử lại 10:42:05); gptoss lỗi
wrong_platform; qwen lỗi timeout". Log `llm_chain_exhausted`.

**Lý do:** FR-012, SC-006: dùng đúng các `kind` mà `ScriptRunner` và `ShowDirector` đang xử lý, nên 004 đếm lỗi liên tiếp và vào chế độ dự
phòng như cũ. Không thêm `kind` mới, không đổi Protocol. Khi mọi mục đang nghỉ, lượt ném lỗi mà không gọi mạng (< 1 s, SC-006).

**Phương án đã cân nhắc:** Thêm `kind = "chain_exhausted"`: phải sửa nơi đọc `kind` ở 004 và bộ đếm lỗi; không có lợi gì cho người xem. Loại.

---

## R8. Giả lập lỗi theo mục (FR-016)

**Quyết định:**
- Mở rộng `director/faults.py`: `FaultInjector.inject(step="llm", mode, count, entry=label)` và `take_entry(label) -> mode | None`.
- Các mode theo mục: `rate_limited`, `overloaded`, `timeout`, `empty`, `wrong_platform`, `interrupted`. `interrupted` cắt luồng thật sau
  câu đầu (đo US2 #3). Mode chung `error`, `timeout` không có `entry` giữ nguyên như 004.
- Lỗi kết nối không có mode giả: test tự động dùng nhà cung cấp giả (FR-023), và quickstart kiểm bằng cách tắt freellmapi thật giữa show.
- `FaultIn` thêm `entry: str | None`; mode theo mục bắt buộc có `entry`; `entry` không có trong chuỗi → 422.
- `app/main.py` truyền hàm `faults.take_entry` vào `ChainReplyEngine` chỉ khi `APP_ENV=dev`; `brain/` không import `director/`.
- Engine gọi hook ngay trước khi gửi request tới mục; nếu có lỗi giả thì tạo đúng lỗi đó (không gọi mạng), đi qua đúng đường phân loại
  của R3. Lỗi giả cho một mục đang nghỉ nằm chờ tới khi mục đó được thử.

**Lý do:** Đo US2 và SC-002, SC-006 không cần chờ nhà cung cấp lỗi thật; lỗi giả đi qua cùng code chuyển mục như lỗi thật. Ngoài dev,
endpoint giả lập lỗi đã bị tắt từ 004.

**Phương án đã cân nhắc:**
- Giả lập ở tầng HTTP bằng một proxy lỗi: thêm tiến trình, khó điều khiển từ trang điều khiển. Loại.
- Dùng mode chung `error` của 004: không chọn được mục, không phân biệt loại lỗi. Loại.

---

## R9. Kiểm lúc khởi động, trang điều khiển và bản tổng hợp

**Quyết định — kiểm lúc khởi động (FR-011, SC-009):**
- Lifespan của app gọi `await engine.preflight()` sau `from_settings()` và trước khi nhận request. Lỗi ném `ReplyEngineError("config_error")`
  như lỗi cấu hình hôm nay, nên uvicorn dừng và app không khởi động.
- Mỗi cặp (`base_url`, `key_env`) khác nhau gọi một lần `GET {base_url}/models` có key, giới hạn 5 s (hằng số trong code). Chuỗi mặc định
  có 2 cặp: freellmapi và Groq. Request này không sinh lời thoại, không tốn hạn mức chat.
- Một mục đạt khi: status 200, có một phần tử `data[].id` bằng `model` của mục, và nếu phần tử đó có trường `available` thì phải là `true`.
- Thông báo lỗi (tiếng Việt, nêu số thứ tự và nhãn mục, không in key):
  - lỗi kết nối: dịch vụ chưa chạy ở `base_url`;
  - 401 / 403: key `key_env` bị từ chối;
  - model không có trong danh sách: tên model sai;
  - `available: false`: model có nhưng chưa dùng được, kèm `unavailable_reason` (`no_key` hoặc `disabled`);
  - status khác: mã status.
- Dữ liệu freellmapi (`routes/proxy.ts` dòng 318–340, 495–520): `GET /v1/models` cần key thống nhất (`requireInferenceAuth`, key sai → 401),
  trả cả catalog, mỗi dòng có `available` (đã bật và có key bật phục vụ được), `unavailable_reason` và `execution_status`
  (`ready` / `needsKey` / `exhausted`).
- `execution_status: exhausted` (hết hạn mức lúc khởi động) không chặn khởi động: đó không phải lỗi cấu hình, lượt đầu sẽ chuyển mục. Ghi
  vào `llm_preflight` để người vận hành thấy trước.
- **Giới hạn đã biết:** lần kiểm không xác nhận được nền tảng mong đợi còn key (catalog không có danh sách nền tảng từng model), cũng không
  kiểm key của từng nhà cung cấp lưu trong freellmapi ngoài việc freellmapi báo key đó đang bật. Hai lỗi này lộ ra ở lượt đầu dưới dạng
  `wrong_platform` hoặc `rejected` và chuỗi chuyển mục.
- Không có lần kiểm nào khác giữa show (bỏ kiểm mỗi 15 s của bản plan đầu).
- `qa_eval` cũng chạy `preflight()` cho chuỗi nó dựng (R10); lỗi trả mã thoát lỗi cấu hình.

**Quyết định — trang điều khiển và bản tổng hợp:**
- Thêm `EventType.LLM_CHAIN = "llm_chain"`, phát qua EventBus mỗi khi state observer báo trạng thái đổi (chuyển, nghỉ, lượt dùng mục mới).
  `build_state` thêm khóa `llm_chain` với ảnh chụp: `entries[]` (label, model, platform, position, status, reason, retry_at),
  `last_entry`, `using_backup`.
- JS trang điều khiển coi mục có `retry_at` đã qua là sẵn sàng, nên không cần server phát thêm sự kiện lúc hết nghỉ.
- Dịch vụ gom key tắt giữa show: lượt kế lỗi `connection`, các mục loopback lần lượt nghỉ và hiện trên khu "Model LLM" như mọi lỗi khác
  (FR-019).
- `ShowStats` thêm phần `llm_chain` trong bản tổng hợp, theo từng label: model, số phân đoạn, số câu trả lời; cùng số lần chuyển theo lý do
  và số lần hết chuỗi. Không có request hay token. Dữ liệu đến từ turn observer trong lúc show chạy. Số đếm là số lượt engine đã trả (có
  thể lệch nhẹ với số lượt đã nói khi người vận hành bỏ qua phân đoạn).

**Lý do:** FR-011, FR-017 (≤ 2 s: sự kiện đẩy ngay qua WebSocket sẵn có), FR-018, FR-019, SC-007, SC-009. Không có nút điều khiển chuỗi
(FR-020). Kiểm một lần lúc khởi động bắt lỗi cấu hình trước khi có người xem; chuỗi chỉ chạy một ngày nên không cần kiểm định kỳ.

**Phương án đã cân nhắc:**
- Kiểm bằng một request chat ngắn cho mỗi mục: xác nhận được cả nền tảng, nhưng tốn hạn mức và vài giây lúc khởi động, và có thể bị gom
  nhóm sang nền tảng khác ngay ở lần kiểm. Loại.
- `GET /v1/models/:id` từng mục: freellmapi có (404 `model_not_found`), nhưng Groq thì chưa kiểm; một lần `GET /models` cho mỗi cặp đủ
  dùng cho cả hai. Loại.
- Cảnh báo rồi vẫn khởi động khi kiểm thất bại: người dùng chọn không khởi động (làm rõ 2026-11-03). Loại.
- Trang điều khiển tự hỏi `/api/state` định kỳ: chậm hơn và tốn request; WebSocket đã có. Loại.

---

## R10. Bộ kiểm từng model (US4)

**Quyết định:**
- `python -m ai_live.qa_eval run --entry LABEL` và `script --entry LABEL`: dựng chuỗi chỉ gồm mục đó, `LLM_CHAIN_COOLDOWN_S=0`, để cơ chế
  thử lại khi 429 của bộ kiểm (`--max-retries`, `--pace`) tự lo; không chuyển sang mục khác (FR-021). Kiểm nền tảng vẫn bật.
- Không có `--entry`: chạy cả chuỗi như lúc live.
- Mỗi kết quả ghi model, label và nền tảng đã trả lời (lấy từ turn observer); phần so với lần trước in model của cả hai lần (FR-022).
- Nhãn engine trong báo cáo: `chain` hoặc `chain:<label>` (thay `settings.llm_model` hiện dùng cho Gemini).
- `--entry` với label không có trong chuỗi → mã thoát lỗi cấu hình như hiện nay. Lỗi dịch vụ giữ quy ước mã thoát của bộ tự kiểm tra 004.

**Lý do:** ADR-035 bắt mỗi model qua bộ câu hỏi (≥ 8/10) và bộ tự kiểm tra (0 vi phạm) trước khi dùng lúc live; ghim một mục giúp chấm đúng
model đó.

**Phương án đã cân nhắc:** Cho bộ kiểm nhận thẳng `--base-url --model`: trùng với cấu hình chuỗi, dễ kiểm một model khác với model lúc live.
Loại.

---

## R11. Test với nhà cung cấp thật

**Quyết định:** `tests/live/test_chain_engine.py` dùng lại marker `live_llm` (đã khai ở `pyproject.toml`, không chạy mặc định); sửa mô tả
marker thành "gọi LLM thật (Gemini hoặc chuỗi model)". Test chạy `preflight()`, rồi gọi một `reply` và một `narrate` ngắn cho từng mục của
chuỗi đang khai, kiểm có câu, có model/provider trong `TurnRecord` và nền tảng khớp. Các file test Gemini thật giữ nguyên. Bước G1 của 004
chạy bằng test này (FR-023).

**Lý do:** Điều V: test thật tách khỏi bộ mặc định; tốn hạn mức nên chỉ chạy khi người dùng đồng ý.

**Phương án đã cân nhắc:** Marker mới `live_chain`: thêm một cờ phải nhớ mà không có lợi. Loại.

---

## R12. Che key trong log (SC-008, Điều II)

**Quyết định:**
- Thêm mẫu vào `security/redact.py`: key Groq `gsk_…`, key thống nhất của freellmapi `freellmapi-…`, key dạng OpenAI `sk-…` (danh sách tham
  khảo theo `server/src/lib/error-redaction.ts` của freellmapi).
- Ngoài mẫu, engine che chính giá trị key đang dùng (các trường secret của chuỗi) trong mọi thông báo lỗi trước khi ghi log, phát sự kiện
  hay đưa vào `ReplyEngineError`, vì nhà cung cấp có thể trả lại key trong body lỗi. Áp dụng cả cho thông báo lỗi lúc khởi động.
- Không bao giờ log header `Authorization` hay body request.

**Lý do:** Điều II, FR-004, FR-011, US1 #6, SC-008. Mẫu bắt key lạ; che theo giá trị bắt cả key không theo mẫu.

**Phương án đã cân nhắc:** Chỉ dựa vào mẫu: key IteraCompute hay nhà cung cấp mới có thể có dạng khác. Loại.

---

## R13. Dependency

**Quyết định:** Không thêm package mới. `httpx` chuyển từ nhóm dev sang dependency chạy (ADR-035 đã ghi "dùng httpx"; bản đã có trong
`uv.lock`, không đổi version). Việc chuyển này vẫn liệt kê để người dùng xác nhận trước khi `/sdd.implement` sửa `pyproject.toml`.

**Lý do:** Điều VII; CLAUDE.md cấm thêm dependency khi chưa có ADR.

**Phương án đã cân nhắc:** `aiohttp`: thêm package mới trong khi `httpx` đã có và có `MockTransport` cho test. Loại.
