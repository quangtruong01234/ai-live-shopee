# Kiến trúc: AI Live Shopee

> Cập nhật lần cuối: 2026-11-03. Đây là thiết kế cho giai đoạn Demo. Đã có code của 001 (đường trả lời comment) và 004 (show kịch bản).
> Interface dưới đây là bản phác thảo hợp đồng giữa các khâu. Khi code có thể chỉnh, nhưng phải ghi ADR.

## 1. Pipeline tổng quan

```mermaid
flowchart LR
    subgraph SRC[Comment sources]
        M[MockSource<br/>gõ tay]
        Y[YouTubeChatSource<br/>Live Chat API]
        S[ShopeeSource<br/>làm sau]
    end

    M --> F
    Y --> F
    S --> F
    F[Normalize + Filter<br/>chống trùng, spam, độ dài] --> Q[CommentQueue<br/>ưu tiên + hết hạn]

    Q --> D[ShowDirector<br/>điều phối lượt nói]
    I[ScriptRunner<br/>kịch bản sinh realtime, 004] --> D
    D --> L[ReplyEngine<br/>chuỗi model ADR-035/037, stream theo câu]
    P[(ProductStore<br/>JSON / SQLite)] --> L
    L -- từng câu --> T[TTSEngine<br/>VieNeu / Gemini TTS]
    T -- PCM chunks --> A[AvatarRenderer<br/>static / LiveTalking]
    A --> OV[Overlay nhãn AI]
    OV --> O1[OUTPUT_MODE=meet: trang /host → Chrome → Google Meet]
    OV --> O2[OUTPUT_MODE=obs: trang /obs → Browser Source OBS → RTMP Shopee, 006]

    D -. ngắt lời .-> A
```

**Luồng một comment:**
1. Source nhận comment và chuẩn hóa thành `Comment` (ghi `received_at`).
2. Filter loại spam, comment trùng, quá ngắn hoặc chứa từ cấm, rồi tính điểm ưu tiên và đưa vào queue.
3. `ShowDirector` lấy comment có ưu tiên cao nhất. Nếu avatar đang nói kịch bản rảnh thì dừng ở ranh giới câu gần nhất,
   hoặc chèn câu đệm (ví dụ "Dạ, bạn {author} hỏi về ... ạ") để che độ trễ LLM.
4. `ReplyEngine` truy xuất sản phẩm liên quan và gọi Gemini (ADR-018) ở chế độ streaming. ADR-035/037 thay bằng chuỗi model free ghim sẵn (`REPLY_ENGINE=chain`, spec 008: SEA-LION qua freellmapi → Qwen3.8 gọi thẳng Groq theo ADR-040 → Gemini 3.5 Flash-Lite gọi thẳng Google theo ADR-073, chuyển mục khi lỗi trước câu đầu), đã code (`brain/chain_engine.py`, 2026-11-04; kiểm key + model bằng `GET /models` lúc khởi động, trang điều khiển hiện model đang nói). Số đo độ trễ thật (T055, 2026-11-04, `FakeTTS` + static): câu đầu LLM p95 SEA-LION 1,30 s, gpt-oss-120b 1,72 s, Qwen3.8 1,26 s; khoảng lặng giữa hai câu kịch bản p95 0,016 s, giữa hai phân đoạn p95 0,728 s (lớn nhất 3,578 s khi có giả lập lỗi). Câu chào ≤ 1,64 s khi SEA-LION trả lời; khi SEA-LION hết giờ chờ 3,5 s thì 4,25–4,61 s, 1/5 lần 7,08 s (rủi ro Q18). Vì vậy ADR-040 hạ giờ chờ SEA-LION xuống 2,5 s và bỏ gpt-oss-120b (không đạt SC-001). Chi tiết và số đo lại ở `specs/008-llm-provider-chain/quickstart.md`. Đủ một câu là đẩy ngay sang TTS.
5. `TTSEngine` trả audio PCM16 mono 16 kHz theo chunk (ADR-024, ADR-025, spec 003: `TTS_PROVIDER=vieneu | gemini | fake`;
   máy chạy phiên dùng `vieneu`, Gemini free tier 3 RPM / 10 RPD chỉ để thử);
   `AvatarRenderer` sinh frame nhép miệng realtime.
6. Overlay ghép nhãn "AI" vào frame, sau đó Output phát đi.

**Luồng show kịch bản (feature 004, ADR-026, ADR-032):** nội dung chính của host là kịch bản giới thiệu sản phẩm, sinh realtime.
Đường comment ở trên vẫn chạy, giờ là comment chen vào kịch bản.

```mermaid
flowchart LR
    OPC[Trang điều khiển<br/>Bắt đầu / Tạm dừng / Bỏ qua / Kết thúc / Chọn kế] --> SD[ShowDirector<br/>điều phối phiên duy nhất]
    SD -- tạo khi Bắt đầu --> SR
    subgraph SR[ScriptRunner]
        direction LR
        W[_write<br/>narrate, clean_spoken, guard, chống trùng] -- hàng chữ --> V[_voice<br/>TTS, tối đa 2 câu]
        V -- câu có tiếng --> PL[_play<br/>giữ _floor từng câu]
    end
    SP[SegmentPlanner<br/>xoay vòng sản phẩm × chủ đề] --> W
    PL --> A2[AvatarRenderer]
    PL --> ST[ShowStats<br/>khoảng lặng, thống kê]
    CQ[CommentQueue] --> SD
    SD -. lượt comment giữ _floor cả lượt .-> A2
```

1. "Bắt đầu show" → `ShowDirector` tạo `ScriptRunner`. `SegmentPlanner` (logic thuần) chọn phân đoạn kế: `opening`, rồi xoay vòng
   sản phẩm × chủ đề có dữ liệu, cuối cùng `closing`. Người vận hành có thể chọn tay phân đoạn kế (`origin = operator`).
2. `_write` gọi `ReplyEngine.narrate(SegmentRequest)` (ADR-030) cho **một phân đoạn đi trước**: có chữ của N+1 thì chờ N+1 bắt đầu phát
   mới sinh N+2. Mỗi câu qua `clean_spoken()` → `OutputGuard` (ADR-031) → chống lặp nguyên văn rồi vào hàng chữ.
3. `_voice` tạo tiếng theo thứ tự, giữ tối đa `SENTENCE_QUEUE_MAX` câu đã có tiếng. Câu TTS lỗi chỉ bỏ câu đó.
4. `_play` giữ `_floor` cho từng câu, gọi `renderer.speak()`, rồi ghi khoảng lặng (§4). Trước câu đầu của một phân đoạn, kiểm
   `catalog_version`; lệch thì bỏ phân đoạn và sinh lại theo nội dung mới.
5. Comment chen vào: vòng `run()` của 001 bắt đầu lượt trả lời ngay (LLM chạy song song với phần còn lại của câu kịch bản đang nói), tầng
   phát của lượt chờ `_floor`. Sau mỗi câu, `_play` hỏi `InterleaveGate.pending()`; có lượt hoặc comment đang chờ thì nhả `_floor` và
   `wait_clear()`. Tiếng kịch bản đã tạo được giữ qua lượt trả lời. Lời trả lời vào `SpokenHistory` (`source = reply`), không tính xoay vòng.
6. Tạm dừng: nói hết câu đang nói, bỏ tiếng đã tạo mà chưa phát (Điều I), giữ chữ. `SCRIPT_FALLBACK_AFTER` lần `narrate()` lỗi liên tiếp
   → chế độ dự phòng: đọc lần lượt phần giới thiệu và mô tả có sẵn trong file sản phẩm (vẫn qua làm sạch, guard, TTS và renderer
   realtime), trước mỗi phân đoạn dự phòng thử `narrate()` lại, được thì về `normal`. Kết thúc → `closing` (1–2 câu chào) → `ended`; comment lúc
   `closing`/`ended` bị `dropped` với lý do `show_ended`.
7. Mỗi câu kịch bản là một `Utterance` riêng (`utterance_id`, `segment_id`, `show_id`), log mốc `segment_requested` →
   `llm_first_sentence` → `tts_first_chunk` → `avatar_first_frame` vào `script_sentences.jsonl`; tổng hợp show vào
   `show_summary_<show_id>.json`.

**Cảnh live quanh host (feature 009, ADR-051, ADR-052):** bàn, ảnh thật sản phẩm, thẻ tên/giá lấy từ file sản phẩm, làm nổi
món đang nói, phụ đề trong khung (tùy chọn). Bật bằng `SCENE_ENABLED`; bộ cảnh ở `SCENE_DIR` (ngoài git, một khách).

```mermaid
flowchart LR
    SS[(Bộ cảnh SCENE_DIR<br/>bàn, ảnh sản phẩm, scene.json)] --> SC
    PS[(ProductStore<br/>tên, giá)] --> SC
    R[Renderer<br/>PlaybackListener: câu đang được nghe] --> SC
    SC[SceneController<br/>layout + render Pillow, luồng phụ] -- scene_layer base/subtitle --> FK[Fork: kiểm vùng mặt/nhãn/watermark,<br/>trộn mỗi khung dưới watermark và nhãn AI]
    SC -- ảnh tĩnh có cảnh --> HP[Trang /host<br/>AVATAR_MODE=static hoặc dự phòng]
```

1. `SceneController` nạp bộ cảnh và catalog, tính bố cục (món chính ở giữa, món phụ hai bên theo thứ tự file, món đang nói to hơn),
   vẽ hai lớp RGBA trong suốt ở vùng mặt, nhãn "AI" và watermark. Mọi lỗi cảnh chỉ thành `issues`/`last_error`, không dừng show.
2. Món được làm nổi theo câu **đang được nghe** (ack phát của renderer qua `PlaybackListener`), không theo câu vừa sinh chữ.
3. Fork báo khung thật và đường cằm trong `hello.scene`; app vẽ lại theo đó và gửi lớp mới mỗi khi đổi. Fork cũ không có `scene` thì
   chỉ ảnh tĩnh có cảnh. Hợp đồng: `specs/009-live-scene-layout/contracts/`.
4. Thay file sản phẩm → vẽ lại; món bị bỏ khỏi file biến khỏi bàn. Bộ cảnh của khách khác (`customer_id` lệch) không bao giờ được vẽ.

**Đổi ảnh và bộ sản phẩm giữa live (feature 012, ADR-071, ADR-072):** người vận hành thay ảnh từng món, đổi cả bộ, hoàn tác hay gỡ ảnh
từ trang điều khiển mà không tắt show. Không đổi Protocol adapter nào; mọi thứ nằm trong `scene/`, `app/` và trang điều khiển.

1. Ảnh tải lên được chuẩn hóa thành PNG RGBA và lưu ở `SCENE_DIR/uploads/<product_id>/<version_id>.png`; sổ `uploads/images.json`
   (`ProductImageStore`, `scene/uploads.py`) ghi mỗi món đang dùng gì (`active`: một phiên bản, `"kit"` = ảnh 009, `null` = đã gỡ),
   lịch sử để "Về ảnh trước" và thời điểm tải / áp / xác nhận quyền dùng. Sổ ghi qua file tạm + `os.replace`, không xóa phiên bản nào.
   `load_scene_set` đọc sổ: ảnh tải lên đã xác nhận không cần `provenance.json`; thiếu xác nhận hay hỏng thì không vẽ và báo `issues`.
   Hợp đồng: `specs/012-product-image-upload/contracts/`.
2. "Áp dụng" chỉ chạy khi tích ô xác nhận quyền dùng (`rights_confirmed` phải là `true`). Sau khi ghi sổ, `SceneController.reload()`
   chờ đúng lần vẽ đọc sổ mới rồi trả `scene_version`; app phát sự kiện `scene` `image_changed` và log `scene_image_changed` với
   `to_frame_ms`. `preview()` vẽ khung tĩnh với ảnh hay bộ chưa áp, không đụng live.
3. "Chuẩn bị bộ mới" (`app/staging.py`) đọc file nội dung mới vào bộ nhớ (tối đa một bộ), gán ảnh từng món, xem trước, rồi
   "Áp dụng bộ mới" đổi catalog và sổ ảnh trong `SceneController.hold()`, nên không khung nào trộn bộ cũ với bộ mới. Lỗi thì trả cả hai về
   như cũ (`snapshot`/`restore`).
4. "AI vừa nói" (`app/spoken.py`, `SpokenLog`): vòng đệm 100 câu kịch bản gần nhất (câu `sentence` có `segment_id`), kèm món và chủ đề;
   trang lấy lại qua `GET /api/state` (`spoken`) khi tải lại. Bấm một món để xem đủ dữ liệu của món đó, ở bộ live hay bộ chuẩn bị.

**Sản phẩm đứng trên bàn như đồ thật (feature 013, ADR-074, ADR-079):** `scene.json` chọn cách bày bằng `layout.mode`: `rows` (009,
mặc định khi thiếu khóa), `realistic` hay `showcase`. Không đổi Protocol adapter nào; lớp `base`/`punch`, cách gửi lớp cho fork và luồng đổi món nổi giữ nguyên.

1. `compute_realistic_layout` (`scene/layout.py`) trả cùng kiểu `SceneLayout` như `compute_layout`. Món chính đứng trước bên phải tay
   host (trạm `P`; cả bố cục lật sang trái khi ở đó món chính được vẽ to rõ hơn), món phụ ở các trạm `S1`, `S2`… hai bên, món sau nhỏ hơn và lùi về sau; đáy món chạm vạch mép bàn `desk_top`, có bóng
   đổ mềm hai lớp cắt trong `shadow_box`. Vùng tay lấy từ `character.json` `scene.hands_zone`; thiếu thì dùng vùng giữa mặc định và báo
   `hands_zone_missing`. Không món nào chạm mặt, tay, nhãn "AI", watermark hay dải phụ đề; món không đủ chỗ bị bỏ và báo trong `issues`.
2. Làm nổi: món đang nói to lên tối đa `highlight_scale` (mặc định 1,08) từ giữa đáy, có ánh sáng ấm mềm phía sau (`glow_box`, cắt khỏi
   vùng tay khi vẽ); món khác tối đi (0,85). Món đứng sau (kể cả món nổi) không lấn món đứng trước nó cả chiều cao lẫn diện tích (FR-004).
3. Thẻ `layout.cards`: `none` (mặc định), `one` (chỉ thẻ món đang nói, trên các món cùng bên, dưới dải phụ đề; hết chỗ thì xuống đáy bên
   đó), `all` (thẻ dưới đáy từng món). Thẻ không đủ chỗ thì ẩn và báo `card_no_room`. `scene_rendered` log `layout_mode`, `cards`, trạm
   từng món và `card_texts` (chữ trên mỗi thẻ) để đối chiếu với file nội dung (SC-007). Với `rows`, thẻ luôn có, `layout.cards` bị bỏ
   qua kèm cảnh báo `cards_ignored`.
4. Bỏ nền ảnh tải lên (`scene/matting.py`): nền trơn (trắng hay một màu) bỏ bằng loang màu từ viền trên luồng phụ; nền phức tạp chạy
   model ONNX (IS-Net hay BiRefNet) trong **tiến trình con ưu tiên thấp, 2 luồng, giết sau 60 giây**, để vòng sự kiện và VieNeu không bị
   giật. Chỉ kênh alpha đổi, R, G, B giữ nguyên. Mỗi bản cắt qua `assess_cut`; bản không chắc thành `failed` kèm lý do tiếng Việt, không
   bao giờ được chọn sẵn. Bản bỏ nền là một phiên bản mới trong kho 012 (`derived_from`, `bg_removal`), nên áp dụng, về ảnh trước, bộ
   chuẩn bị và xác nhận quyền dùng chạy như cũ. Biến môi trường: `MATTING_MODEL_PATH` (trống = chỉ bỏ nền trơn), `MATTING_DURING_SHOW`
   (`false` = không chạy model khi show đang live). Hợp đồng: `specs/013-realistic-desk-products/contracts/`.
5. Cách bày trưng bày `showcase` (ADR-079, `compute_showcase_layout`): món chính cao khoảng 0,28 H (gần cỡ thật, ADR-082) ở giữa ngay trước host, tối đa 3 món phụ
   phía sau (phải, trái, phải xa hơn), không món nào che món nào, cách nhau ≥ 8 px kể cả lúc làm nổi (ADR-081: thiếu chỗ thì món chính
   nhỏ lại tới 0,22 H rồi món phụ nhỏ lại); cụm được che tay và ngực nhưng ảnh, bóng, ánh sáng, bục và sticker không chạm
   mặt, nhãn "AI", watermark. `layout.riser` vẽ bục tròn trắng dưới món chính; `layout.sticker` vẽ sticker tròn chỉ có `price_text` của món
   chính (không bao giờ có khuyến mãi). `compute_scene_layout` thêm cảnh báo `art_low_resolution` ở mọi cách bày khi ảnh nguồn < 1,5 ×
   chiều cao vẽ lúc nổi; phản hồi tải ảnh 012 có `low_resolution`. Ảnh sản phẩm giữ tối đa `ART_MAX_SIDE` = 960 px (`scene/limits.py`).

**Hai chế độ chạy:**

| Chế độ | Máy | AvatarRenderer | Output | Dùng khi |
|--------|-----|----------------|--------|----------|
| `static` | Laptop dev (GTX 1650 Ti 4GB) | Ảnh tĩnh + phát audio (có thể nhấp nháy hoặc đổi khung khi đang nói) | Trang web local | Phát triển logic, test |
| `livetalking` | Laptop GTX 1650 Ti 4GB (tạm, chấp nhận chậm, ADR-023); RunPod RTX 3090/4090 là dự phòng | Fork LiveTalking (Wav2Lip; MuseTalk nhiều khả năng không đủ 4 GB) | WebRTC / RTMP | Test lip-sync, demo |

**Khẩu hình (010, ADR-055, ADR-056):** fork chọn cách tạo miệng bằng `LIVETALKING_MOUTH_METHOD` (mặc định `w2l` = cách 005; các núm
`ref`, `paste`, `color`, `sharpen`, `gain_db`, `shift` ở `specs/010-natural-mouth-shapes/contracts/mouth-method.md`), giá trị sai thì
về `w2l`. `prepare` đo góc đầu từng khung clip nói (MediaPipe) và ghi `ailive_pose.json`; fork chỉ phát các đoạn mặt thẳng. Chất lượng
khẩu hình đo bằng `python -m ailive_ext.mouth_eval` (MediaPipe + SyncNet, chỉ để đo, không vào đường live).

## 2. Mô hình dữ liệu chính

```python
@dataclass(frozen=True)
class Comment:
    id: str
    source: str                 # "mock" | "youtube" | "shopee"
    author: str
    text: str
    received_at: float          # time.monotonic() lúc hệ thống nhận, dùng để đo độ trễ
    platform_ts: datetime | None
    meta: dict[str, Any]

# Nội dung sản phẩm (src/ai_live/products/models.py, specs/001-local-reply-pipeline/data-model.md §2). Bất biến.
@dataclass(frozen=True)
class Variant:                  # một phân loại, ví dụ dung tích hay màu
    name: str                   # duy nhất trong sản phẩm (so sánh sau chuẩn hóa)
    price: int                  # VND > 0

@dataclass(frozen=True)
class Product:
    id: str                     # slug bỏ dấu từ name, duy nhất trong catalog
    name: str                   # từ Heading 1 của file Word (ADR-014)
    is_primary: bool            # sản phẩm chính của phiên live
    description: str
    intro: str                  # bài giới thiệu, nguồn chính của show kịch bản (004)
    price: int | None = None    # VND; đúng một trong price hoặc variants
    variants: tuple[Variant, ...] = ()
    specs: tuple[tuple[str, str], ...] = ()      # giữ thứ tự trong file
    faq: tuple[tuple[str, str], ...] = ()        # (câu hỏi, câu trả lời) do người soạn file viết
    promotions: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()       # các khẳng định không được nói (ví dụ công dụng y tế)
    link: str | None = None     # không bao giờ được đọc lên
    # price_range -> (min, max) của giá hoặc các phân loại

@dataclass(frozen=True)
class ProductCatalog:           # thay nội dung = tạo catalog mới rồi đổi tham chiếu; lượt nói giữ catalog lúc bắt đầu
    version: str                # sha256 rút gọn 12 ký tự của file .docx
    source_name: str            # tên file gốc, không có đường dẫn
    loaded_at: datetime         # UTC
    products: tuple[Product, ...]   # đúng 1 is_primary, 0–3 sản phẩm phụ
    known_amounts: frozenset[int]   # mọi số trong file + khoảng giá, cho guard chặn giá bịa
```

File Word sai mẫu báo `ContentLoadError` mang toàn bộ `ContentIssue` (`code`, `message`, `product`, `section`) một lần.

**Mô hình của show kịch bản (004)** nằm trong `src/ai_live/core/models.py`; bảng đầy đủ ở `specs/004-show-director/data-model.md`.

| Mô hình | Vai trò | Giá trị chính |
|---------|---------|---------------|
| `ShowSession` | Một show, từ "Bắt đầu" tới `ended`; `show_id` mới mỗi lần bắt đầu | `state`: `idle` → `running` ⇄ `paused` → `closing` → `ended`; `mode`: `normal` / `fallback` |
| `Segment` | Một phân đoạn: một sản phẩm × một chủ đề, 3–6 câu (`opening` 2–3, `closing` 1–2) | `topic`: `opening`, `intro`, `highlights`, `specs`, `price`, `promotion`, `faq`, `call_to_action`, `closing`; `origin`: `rotation` / `operator` / `fallback`; `status`: `preparing` → `ready` → `speaking` → `done` (hoặc `skipped`, `failed`, `blocked`, `discarded`) |
| `SegmentRequest` | Đầu vào của `narrate()` | `topic`, `product_id`, `min_sentences`–`max_sentences`, `previous_sentence`, `recent_lines` |
| `ScriptSentence` | Một câu kịch bản; câu được nói có `Utterance` cùng `utterance_id` | `raw_text` (chữ LLM), `text` (sau `clean_spoken()`), `status`: `spoken`, `blocked`, `dropped`, `tts_error`, `render_error`, `interrupted` |
| `SpokenHistory` | Lịch sử đã nói trong một show, cho nối mạch và chống lặp | `source`: `script`, `fallback`, `reply` |
| `SentenceGap` | Khoảng lặng giữa hai câu kịch bản đã nói (§4) | `seconds`, `kind` |

## 3. Interface các adapter

Mọi adapter là `typing.Protocol` và được chọn bằng biến môi trường (`COMMENT_SOURCE`, `REPLY_ENGINE` (`chain | gemini | fake`), `TTS_PROVIDER`, `AVATAR_MODE`, `OUTPUT_MODE`).
Mã nguồn: `src/ai_live/core/protocols.py`. Bản dưới đây đã cập nhật theo feature 001 (`specs/001-local-reply-pipeline/contracts/adapters.md`)
và phần renderer theo feature 005 (`specs/005-lipsync-livetalking/contracts/adapters.md`).

```python
class CommentSource(Protocol):
    """Nguồn comment. Implementations: MockSource, YouTubeChatSource, ShopeeSource (sau)."""
    name: str
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def stream(self) -> AsyncIterator[Comment]: ...   # nguồn kéo về; MockSource dùng push() đồng bộ thay cho stream()

class CommentQueue(Protocol):
    """Hàng đợi ưu tiên. Demo: in-process (asyncio). Nhiều khách: Redis."""
    async def put(self, comment: Comment, priority: Priority) -> None: ...   # Priority là IntEnum, vẫn tương thích int
    async def get(self) -> QueuedComment: ...    # kèm priority, seq; bỏ qua comment đã quá COMMENT_MAX_AGE_S
    def size(self) -> int: ...
    def snapshot(self) -> list[QueuedComment]: ...   # theo thứ tự sẽ lấy, cho trang điều khiển

class ProductStore(Protocol):
    """Dữ liệu sản phẩm nạp từ file Word theo mẫu (ADR-014). Chưa dùng vector DB."""
    @property
    def catalog(self) -> ProductCatalog: ...
    def list_active(self) -> list[Product]: ...
    def get(self, product_id: str) -> Product | None: ...
    def replace(self, data: bytes, source_name: str) -> ProductCatalog: ...   # kiểm xong mới đổi; lỗi thì giữ catalog cũ
    # search(query, limit): chưa làm ở 001 (≤ 4 sản phẩm, đưa hết vào prompt, ADR-005)

class ReplyEngine(Protocol):
    """LLM sinh lời thoại. Yield từng câu hoàn chỉnh để TTS bắt đầu sớm."""
    def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]: ...
    def narrate(self, request: SegmentRequest, catalog: ProductCatalog) -> AsyncIterator[str]: ...
    # narrate(): câu kịch bản của 004 (ADR-030). Lỗi ném ReplyEngineError; engine không tự cắt số câu, ScriptRunner cắt.
    # Câu ra từ reply() và narrate() đều qua clean_spoken() (brain/sanitize.py) rồi OutputGuard. Guard kiểm theo thứ tự
    # forbidden_claim → unknown_amount → unknown_percent → link → platform_phrase → unsupported_claim
    # (ADR-017, mở rộng ở ADR-031 và ADR-050).

class TTSEngineError(RuntimeError):
    """Lỗi ở bước tts (spec 003). kind: quota_exhausted | rate_limited | api_error | config_error | model_error;
    message tiếng Việt, hiện nguyên văn cho người vận hành."""

class TTSEngine(Protocol):
    """TTS tiếng Việt (ADR-024). Implementations: VieneuTTS (chạy CPU trên máy), GeminiTTS (gói miễn phí), FakeTTS (test).
    create_tts() luôn bọc engine trong SpeechTTS: chuẩn hóa chữ trước khi đọc, đếm ký tự, nghỉ sau lỗi hết hạn mức."""
    sample_rate: int            # PCM16 little-endian, mono, đúng 16000 Hz (ADR-025); adapter tự hạ tần số nguồn
    async def warm_up(self) -> None: ...   # nạp model trước phiên; lỗi ném TTSEngineError("config_error"), app vẫn chạy
    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...   # lỗi ném TTSEngineError

class AvatarRenderer(Protocol):
    """Biến audio thành hình nhép miệng realtime. Implementations: StaticRenderer (ảnh + tiếng), LiveTalkingRenderer
    (fork LiveTalking, Wav2Lip), SwitchingRenderer (lớp bọc chọn renderer theo lượt, ADR-046)."""
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def speak(self, utterance_id: str, text: str, audio: AsyncIterator[bytes], sample_rate: int) -> None: ...
    async def interrupt(self) -> None: ...
    @property
    def is_speaking(self) -> bool: ...
    def first_playback_at(self, utterance_id: str) -> float | None: ...   # lúc câu đầu bắt đầu phát (avatar_first_frame)
    # Không có trang /host kết nối thì speak() ném RendererUnavailable (ADR-016).
    # Lỗi bước tạo hình ném RendererError(kind): lipsync_unavailable | vram_oom | inference_failed | bad_audio |
    # renderer_restarted | timeout (FR-021).

# Protocol tùy chọn (005, ADR-046): lõi kiểm bằng isinstance, renderer không có (StaticRenderer) vẫn chạy như cũ.
class RenderOutcomeSink(Protocol):     # renderer muốn biết lượt kết thúc ra sao (SwitchingRenderer đếm lỗi để chuyển về static)
    def record_render_outcome(self, utterance_id: str, ok: bool, *, error_kind: str | None = None) -> None: ...
class RenderStatsSource(Protocol):     # renderer tự đo fps của lượt (render_fps, infer_fps, clips_used; FR-020)
    def render_stats(self, utterance_id: str) -> RenderTurnStats | None: ...
class RenderSettleSource(Protocol):    # speak() có thể trả về trước khi câu cuối phát xong (LIVETALKING_LEAD_S)
    def turn_settled(self, utterance_id: str) -> asyncio.Future[None] | None: ...   # lõi chờ future rồi mới lấy số đo

class HostLink(Protocol):
    """Kênh /host mà renderer nhép miệng cần: sessionid WebRTC của fork, trang đã sẵn sàng chưa, gửi tin JSON tới trang
    (src/ai_live/avatar/static_renderer.py)."""
    @property
    def lipsync_session(self) -> str | None: ...
    @property
    def host_ready(self) -> bool: ...
    async def send_to_host(self, message: dict[str, Any]) -> bool: ...
    def on_session_change(self, callback: Callable[[str | None], None]) -> None: ...

class OutputSink(Protocol):
    """Đích phát. Implementations: WebRTCSink, VirtualCamSink, RtmpSink. Chưa làm: ở 001 static renderer phát thẳng ra
    trình duyệt; ở 005 fork LiveTalking tự phát WebRTC tới /host và tự vẽ nhãn AI (ADR-043, ADR-044); ở 006 OBS lấy
    hình và tiếng từ trang /obs (Browser Source). Để dành cho RTMP / virtual cam trực tiếp từ app."""
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def write_video(self, frame: "np.ndarray", pts: float) -> None: ...
    async def write_audio(self, pcm: bytes, pts: float) -> None: ...
```

**Ghi chú tích hợp LiveTalking:** LiveTalking có sẵn TTS, WebRTC và RTMP bên trong. Hai cách tích hợp có thể dùng:
- (a) Viết TTS adapter của mình thành plugin TTS bên trong fork LiveTalking, rồi gửi *text* qua HTTP.
- (b) Mình tự làm TTS, sau đó đẩy *PCM audio* vào LiveTalking để nó chỉ làm lip-sync và output.

Đã chốt (b) (ADR-042, ADR-043): app đẩy PCM qua WebSocket `/ailive/ws` của fork, fork chỉ làm lip-sync và phát WebRTC tới `/host`.
Với `livetalking`, nhãn AI vẽ trong khung hình của fork (ADR-044).
- Fork chạy **process riêng, venv riêng, ngoài git** (`vendor/livetalking/`, ADR-042), khởi động bằng `scripts/livetalking/run.ps1`;
  app chỉ nói chuyện với fork qua HTTP/WebSocket (`/ailive/health`, `/ailive/ws`), không import code fork.
- `SwitchingRenderer` giữ cả `StaticRenderer` lẫn `LiveTalkingRenderer`: chọn theo `AVATAR_MODE`, tự về `static` sau nhiều lỗi liên
  tiếp và chỉ bật lại khi người vận hành bấm (FR-022).
- Giao thức app ↔ fork: `specs/005-lipsync-livetalking/contracts/fork-protocol.md`.

## 4. Ngân sách độ trễ (mục tiêu < 5 giây)

> Hiến pháp 1.2.0 Điều VI (ADR-029): bảng dưới áp dụng cho câu trả lời comment. Show kịch bản (feature 004) đo riêng: từ lúc bấm
> "Bắt đầu" đến câu đầu phát ra ≤ 5 giây; khoảng lặng giữa hai câu p95 ≤ 1,5 giây, không lần nào > 5 giây. Câu kịch bản dùng mốc
> `segment_requested` thay cho `comment_received`.

Đo từ `comment_received` (hệ thống nhận comment) đến `avatar_first_frame` (frame đầu tiên miệng bắt đầu nói ra khỏi output).
Các con số dưới đây là **mục tiêu thiết kế**, chưa đo thực tế.

| Bước | Ngân sách (p95) | Ghi chú |
|------|-----------------|---------|
| Ingest + normalize + filter | 0.2 s | Không tính độ trễ polling của YouTube (xem dưới) |
| Queue → ShowDirector nhận lượt | 0.3 s | Gồm thời gian chờ ngắt câu kịch bản rảnh, hoặc chèn câu đệm |
| LLM đến câu đầu tiên (streaming) | 1.5 s | Prompt ngắn, phần đầu prompt cố định để tận dụng cache; `thinking_level=low`. TODO: benchmark model Gemini nào (spec 001, R5) |
| TTS đến chunk audio đầu tiên | 1.0 s | Phụ thuộc nhà cung cấp; cần TTS hỗ trợ streaming |
| Lip-sync đến frame đầu tiên | 0.8 s | Wav2Lip thường nhanh hơn MuseTalk. Laptop 1650 Ti đo 0,92–1,16 s (005 T046, chấp nhận theo ADR-023). TODO: benchmark trên 3090/4090 |
| Encode + mạng (WebRTC) | 0.5 s | RTMP/Shopee có thêm độ trễ phía nền tảng, không tính ở đây |
| **Dự phòng** | 0.7 s | |
| **Tổng** | **≤ 5.0 s** | |

**Đo show kịch bản (004, research R12):** dùng đúng các ack của trang host đã có (ADR-016), không ước từ thời lượng audio (sai khi
trình duyệt đệm hoặc tab bị nền).

- **Khoảng lặng** giữa hai câu kịch bản đã nói: `gap = avatar_first_frame(câu N+1) − played_at(câu N)`. `played_at` là lúc
  `renderer.speak()` trả về, tức khi trang host đã ack câu N phát xong. `ScriptRunner._play` ghi mỗi gap vào `ShowStats` và log
  `sentence_gap` kèm nhãn:

  | Nhãn | Khi nào | Tính vào SC-002 (p95 ≤ 1,5 s, không lần nào > 5 s) |
  |------|---------|-----------------------------------------------------|
  | `script` | Hai câu liền nhau trong cùng phân đoạn | Có |
  | `segment_boundary` | Câu cuối phân đoạn N và câu đầu N+1 | Có |
  | `error` | Có lỗi thật xen giữa (người xem vẫn nghe thấy im lặng) | Có |
  | `fault` | Có lỗi giả lập xen giữa | Không; kiểm riêng ≤ 8 s cho SC-006 |
  | `comment` | Có lượt trả lời comment xen giữa | Không; SC-011 đo riêng |
  | `paused` | Người vận hành tạm dừng xen giữa | Không |

  `ShowStats` tính trung vị, p95 (cần ≥ 20 mẫu, dùng chung `director/latency.step_stats` với 001) và giá trị lớn nhất theo từng nhãn,
  ghi vào `show_summary_<show_id>.json`. Câu đầu tiên của show không có gap.
- **Bắt đầu → câu đầu** (SC-001): `avatar_first_frame` của câu đầu phân đoạn `opening` trừ lúc server nhận `POST /api/show/start`,
  ghi là `show_first_sentence_s`.
- Câu kịch bản không vào `LatencyTracker` của comment, nên bảng độ trễ comment ở trên giữ nguyên ý nghĩa.

- YouTube Live Chat API trả `pollingIntervalMillis` và comment chỉ tới theo chu kỳ polling. TODO: tiêu chí < 5 giây có tính phần này không?
- Mẹo che độ trễ: câu đệm cố định ("Dạ, câu hỏi hay quá ạ...") có thể được TTS sẵn (chỉ cache audio). Lip-sync vẫn sinh realtime.
  TODO: xác nhận việc cache audio câu đệm không vi phạm quy định "không phát nội dung quay sẵn".

## 5. Ưu tiên comment (bản đầu)

| Ưu tiên | Loại | Ví dụ |
|---------|------|-------|
| Cao | Hỏi giá, khuyến mãi, cách mua, size/biến thể, tồn kho | "Giá bao nhiêu vậy shop?" |
| Trung bình | Hỏi thông số, công dụng, so sánh | "Dùng cho da dầu được không?" |
| Thấp | Chào hỏi, khen | "Chào shop": lời chào ngắn được trả lời bằng câu mẫu trong `data/rules/greetings.json`, không gọi LLM (ADR-077) |
| Bỏ | Spam, link, tục tĩu, comment trùng, quá `COMMENT_MAX_AGE_S`; người gửi quá `COMMENT_AUTHOR_MAX` comment trong `COMMENT_AUTHOR_WINDOW_S` (tạm bỏ qua `COMMENT_AUTHOR_MUTE_S`); lời chào lặp lại của người đã được chào; comment cũ hơn của người đã có comment khác đang chờ (ADR-077) | |

Phân loại ban đầu dùng luật từ khóa (rẻ và nhanh). TODO: có cần LLM phân loại không? Nếu có thì sẽ tốn thêm độ trễ.

## 6. Guardrails cho LLM

- System prompt chỉ cho phép dùng thông tin trong `ProductStore`. Thiếu dữ liệu thì trả lời lịch sự là sẽ để shop phản hồi.
- Câu trả lời ngắn (1–3 câu, nói được trong khoảng 10–15 giây), đúng phong cách xưng hô đã chốt.
- Không nói `forbidden_claims` và không hứa hẹn ngoài dữ liệu.
- Bộ 10 câu hỏi mẫu là regression test cho prompt (`tests/`).

## 7. Độ bền và quan sát

- Mỗi khâu có timeout. Khi TTS hoặc LLM lỗi thì bỏ lượt đó và quay lại kịch bản rảnh; không để avatar đứng im lâu.
- Log có cấu trúc kèm `utterance_id` và các mốc thời gian. Có endpoint `/health` cho từng khâu.
- Watchdog (giai đoạn 2): khởi động lại renderer hoặc output khi mất frame quá N giây.

**Sẵn sàng demo (007, ADR-057):** gói `src/ai_live/ops/` nằm ngoài đường live, không gọi LLM.

```mermaid
flowchart LR
    HT[Tab /host] -- host_status mỗi giây<br/>framesDecoded, AudioContext, video --> WS[/ws/host/]
    WS --> WD[ops/watchdog<br/>canh show]
    SD[ShowDirector + renderer<br/>câu, khoảng lặng, fork] --> WD
    WD -- alert open/update/close --> CT[/ws/control → banner trang điều khiển/]
    WD -- skip_current một lần ở 15 s --> SD
    WD --> AL[(alerts.jsonl)]
    SD --> GP[(gaps.jsonl, script_sentences.jsonl,<br/>show_summary, avatar.jsonl)]
    GP --> RH[ops/rehearsal<br/>lệnh report]
    AL --> RH
    RD[ops/readiness<br/>GET /api/readiness + lệnh readiness] --> RJ[(readiness.jsonl)]
    BV[ops/backup_video<br/>lệnh backup-video] -- show verbatim + record start/stop --> SD
```

- `readiness`: kiểm cấu hình, fork (`/ailive/health` có `record_enabled`), nhân vật, host, nội dung, cảnh, nhãn "AI", video dự phòng,
  trạng thái chuỗi model (chỉ đọc snapshot), nguồn điện (`ctypes`) và ổ đĩa. Chạy được cả khi app chưa bật (phần không cần app).
- `watchdog`: chạy theo nhịp `WATCHDOG_TICK_S` khi show ở `running`/`paused`/`closing`; bảy loại cảnh báo `silence`, `frozen`,
  `audio_missing`, `fork_lost`, `host_closed`, `fallback_mode`, `static_mode`; `fork_lost` và `host_closed` luôn ở mức `operator`,
  `silence` lên `operator` nếu vẫn im sau khi đã tự bỏ câu. Việc tự làm duy nhất: bỏ câu kẹt một lần.
- `rehearsal`: đọc log phiên của một show, chấm tiêu chí 3 (khoảng lặng) và 4 (30 phút sạch), ghi `rehearsal_<show_id>.md/.json`.
- `backup_video`: show nội dung `verbatim` (`POST /api/show/start {"content": "verbatim"}`, đọc nguyên văn giới thiệu + mô tả, không gọi
  engine) qua đường realtime, ghi bằng recorder của fork, chấm bằng `ailive_ext.analyze`, chép vào `BACKUP_VIDEO_DIR` kèm phiếu. App
  không có route nào phát file video.

**Đầu ra OBS (006, ADR-058):** `OUTPUT_MODE=meet | obs` (mặc định `meet`; giá trị cũ `webrtc` chạy như `meet` và log cảnh báo). Không có
sink Python: đầu ra OBS là trang `/obs`, cùng `host.html` với `<body class="host obs">`, tự phát không cần bấm, không có lớp phủ, chữ
trạng thái hay phụ đề, chỉ có hình (nhép miệng hoặc ảnh tĩnh, cảnh 009) và nhãn "AI". OBS thêm trang này làm Browser Source 720×1248,
"Control audio via OBS" (runbook §8).

- Vai trên `/ws/host?role=obs|host` (thiếu hoặc lạ là `host`): `obs` > `host`. Cùng vai thì trang mới thắng, trang cũ nhận mã đóng 4000;
  `obs` lấy quyền của `host` đang phát thì `host` nhận 4001 `obs_active`, `host` mở sau khi `obs` đang phát cũng nhận 4001. Trang nhận
  4000/4001 nhả hết (tắt tiếng, dừng video, đóng peer WebRTC) và không tự nối lại. `/obs` mất server vì lý do khác thì thử lại mỗi giây
  và tự tải lại khi nối được. Thứ tự ưu tiên giống nhau ở cả hai chế độ.
- Chế độ chỉ đổi phần kiểm: `readiness` mục host đòi kết nối vai `obs`; `watchdog` coi kết nối `host` là đầu ra mất, thêm luật nguồn còn
  nối mà không gửi nhịp quá `WATCHDOG_HOST_STALE_S` (mặc định 10 s, chỉ ở `obs` vì Chrome điều tiết timer tab nền), lời nhắn theo OBS.
  `/api/state` và snapshot có `output_mode`, `host_role`; trang điều khiển hiện "Đầu ra: OBS (đã nối)" hoặc "Meet — trang host".
- `OutputSink` (§3) vẫn chưa làm; RTMP hay virtual cam trực tiếp từ app để sau. Hợp đồng: `specs/006-obs-output/contracts/api.md`.
- Log phiên thêm `session.json` (cấu hình lúc mở phiên), `gaps.jsonl`, `alerts.jsonl`, `readiness.jsonl`. Hợp đồng:
  `specs/007-demo-readiness/contracts/`.

## 8. Triển khai cho buổi demo

```mermaid
flowchart LR
    subgraph POD[RunPod RTX 3090/4090]
        APP[App FastAPI<br/>pipeline] --> LT[LiveTalking fork]
    end
    OP[Laptop người vận hành<br/>Chrome] -- trang điều khiển + comment mock --> APP
    LT -- WebRTC --> OP
    OP -- share tab có âm thanh --> MEET[Google Meet<br/>khách xem]
    LT -. RTMP tùy chọn .-> YT[YouTube Unlisted]
    YT -. Live Chat API .-> APP
```

TODO: RunPod có thể không mở được cổng UDP cho WebRTC. Cần thử ngay ở mốc đầu tiên; nếu không được thì dùng TURN qua TCP/TLS
hoặc chuyển sang RTMP/HLS. Xem `RUNPOD.md` và `RISKS.md`.
