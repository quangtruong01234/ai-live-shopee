# Nghiên cứu (Phase 0): 003-vietnamese-tts

- **Ngày:** 2026-10-31 · **Plan:** [plan.md](./plan.md) · **Spec:** [spec.md](./spec.md)
- Thông tin bên ngoài tra ngày 2026-10-31, có ghi nguồn. Chỗ chưa xác minh được ghi `TODO:`; không đoán.

## R1. Nguồn giọng (a) chạy trên laptop: VieNeu-TTS v3 Turbo, chạy bằng CPU (ONNX)

- **Quyết định:** Adapter `vieneu` dùng gói pip `vieneu` (VieNeu-TTS v3 Turbo) với backend ONNX trên **CPU**, không dùng GPU.
  Gọi `Vieneu(backend="onnx")` một lần lúc mở app (nạp model), mỗi câu gọi `infer_stream(text, voice=...)` để nhận từng đoạn tiếng.
- **Lý do:**
  - License Apache-2.0; các giọng có sẵn (preset) được phép dùng thương mại theo trang model. Hợp FR-002 (giọng có sẵn, không clone).
  - Có giọng nữ miền Nam có sẵn: Kim Thanh, Mỹ Duyên, Thục Đoan, Thùy Dung (FR-007, giả định giọng nữ miền Nam).
  - Đường ONNX trên CPU không cần torch, nên không giành 4 GB VRAM với nhân vật nhép miệng ở feature 005 (ADR-023). Spec FR-003 (a)
    ghi "dùng chung card đồ họa 4 GB"; chạy CPU tránh được việc tranh VRAM, đổi lại là tranh CPU (xem rủi ro mới trong plan).
  - Có hàm stream theo đoạn, hợp FR-004 (câu đầu phát sớm). Tác giả công bố tốc độ khoảng 2 lần thời gian thực trên CPU.
  - Miễn phí, chạy không cần mạng sau khi tải model (ADR-019).
- **Phương án đã cân nhắc:**
  - VieNeu chạy GPU (torch + CUDA): nhanh hơn nhưng tranh VRAM với lip-sync trên card 4 GB; thêm torch nặng. Để sau nếu CPU quá chậm.
  - VietTTS và các model TTS tiếng Việt mã nguồn mở khác: chưa thấy giọng nữ miền Nam có sẵn kèm license thương mại rõ như VieNeu;
    không đào sâu (Điều VII, chỉ cần một nguồn chạy laptop).
- **Nguồn:** https://github.com/pnnbao97/VieNeu-TTS · https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo · https://pypi.org/project/vieneu/
- **TODO:**
  - Tốc độ thật trên CPU laptop này (12 luồng logic): thời gian đến đoạn tiếng đầu và hệ số thời gian thực, khi chạy riêng và khi
    chạy cùng lip-sync. Đo ở SC-006.
  - Dung lượng model tải về là bao nhiêu? Tải vào thư mục nào (mặc định là cache Hugging Face trong thư mục người dùng, ngoài repo)?
  - Số luồng CPU cho ONNX: để mặc định hay giới hạn (để chừa CPU cho app và lip-sync)? Đặt bằng `VIENEU_CPU_THREADS`, đo rồi chốt.
  - Đối tượng `Vieneu` có gọi song song từ nhiều luồng được không? Plan giả định **không**: adapter chỉ cho một câu tổng hợp tại một
    thời điểm (khóa), đúng với ShowDirector vốn tạo tiếng tuần tự từng câu.
  - VieNeu có tự chuẩn hóa văn bản bên trong không? Nếu có, kiểm tra nó không đổi chữ mình đã chuẩn hóa (ví dụ "ngàn").
  - Có cho chọn tần số lấy mẫu đầu ra không? Nếu không thì adapter tự hạ từ 48 kHz xuống 16 kHz (R5).

## R2. Nguồn giọng (b) dịch vụ ngoài miễn phí: Gemini TTS, free tier

- **Quyết định:** Adapter `gemini` gọi model Gemini TTS (mặc định `gemini-3.8-flash-tts`, thử thêm `gemini-3.8-flash-lite-tts`) qua SDK
  `google-genai` đã cài (ADR-018), chế độ async streaming: `client.aio.interactions.create(..., stream=True)`, đọc các sự kiện
  `step.delta` có `delta.type == "audio"`, giải base64 `delta.data`. Yêu cầu đầu ra `response_format={"type": "audio",
  "mime_type": "audio/l16", "sample_rate": 16000}`, giọng chọn qua `generation_config={"speech_config": [{"voice": "<tên>"}]}`.
  Dùng lại `GEMINI_API_KEY`. Chỉ gửi chữ đã chuẩn hóa của câu cần đọc (FR-003 b).
- **Lý do:**
  - Có free tier (không tính tiền ở gói miễn phí), hỗ trợ tiếng Việt, có stream tiếng.
  - **Không thêm dependency** và không thêm tài khoản/khóa mới: SDK và key đã có từ feature 001.
  - Có nhiều giọng nữ có sẵn: Leda, Aoede, Autonoe, Achernar, Pulcherrima, Vindemiatrix (FR-002).
- **Điều kiện cần báo người dùng (ADR-019, ADR-018):**
  - Ở free tier, Google dùng dữ liệu gửi lên để cải thiện sản phẩm. Chữ gửi đi là câu host sắp đọc, có thể chứa tên người xem mà LLM
    nhắc lại. Comment đó vốn đã gửi lên Gemini ở bước LLM (RISKS S7), nên TTS không làm lộ thêm loại dữ liệu mới.
  - Gói trả phí (chỉ để tham khảo, **không dùng** khi chưa có đồng ý của người dùng): $0.50 / 1M token chữ vào, $9.00 / 1M token tiếng ra
    (bản lite $6.00).
- **Phương án đã cân nhắc:**
  - Azure Speech gói F0: 0,5 triệu ký tự giọng neural mỗi tháng miễn phí, có giọng Việt. Bị loại vì cần tài khoản Azure mới và SDK mới
    (dependency mới), trong khi Gemini dùng lại được SDK và key.
  - ElevenLabs gói free: 10 nghìn ký tự mỗi tháng, quá ít cho phiên 30 phút (SC-005).
  - FPT.AI: 100 nghìn ký tự mỗi tháng nhưng trả về đường dẫn file sau khi xử lý xong (không stream, docs/VENDORS.md), nên câu đầu đến chậm.
- **Nguồn:** https://ai.google.dev/gemini-api/docs/speech-generation · https://ai.google.dev/gemini-api/docs/pricing ·
  https://ai.google.dev/gemini-api/docs/rate-limits · https://azure.microsoft.com/en-us/pricing/details/speech/
- **TODO:**
  - **Giới hạn free tier của model TTS (RPM, RPD)** chỉ xem được trong AI Studio. Mỗi câu là một request; phiên 30 phút có thể cần khoảng
    100–200 request. Nếu RPD thấp hơn mức này, Gemini TTS chỉ dùng để so sánh (SC-006) và thử ngắn, không chạy hết phiên 30 phút
    (rủi ro mới Q12). Người dùng mở AI Studio xem giúp.
  - Gemini có trả đúng 16 kHz như yêu cầu không, hay luôn trả 24 kHz? Xác minh bằng test `live_tts`. Nếu luôn 24 kHz thì adapter hạ
    tần số như R5.
  - Giọng Gemini đọc tiếng Việt theo giọng miền nào? Có chỉnh được bằng câu chỉ dẫn phong cách (`annotations` kiểu `speech_metadata`)
    không? Nghe thử ở SC-006. Câu chỉ dẫn phong cách chỉ chứa yêu cầu giọng đọc, không chứa thông tin phiên hay người xem.
  - Thời gian đến đoạn tiếng đầu tiên từ Việt Nam: đo ở SC-006.

## R3. Chuẩn hóa chữ trước khi đọc: tự viết, không thêm thư viện

- **Quyết định:** Module `ai_live/tts/normalize.py`, hàm thuần `normalize_for_speech(text: str) -> str`, áp dụng các quy tắc theo thứ tự
  cố định (xem data-model §3). Danh sách viết tắt nằm ở `data/rules/tts_abbreviations.json` để thêm dần không sửa code.
  Chuẩn hóa chạy cho mọi nguồn giọng (kể cả giả) qua lớp bọc ở R4.
- **Lý do:**
  - Cần cách đọc miền Nam ("ngàn", "lẻ"), cách đọc giá và khoảng giá riêng của live bán hàng; thư viện chuẩn hóa có sẵn thường theo miền
    Bắc ("nghìn", "linh") và khó chỉnh.
  - Hai nguồn giọng phải nghe giống nhau về cách đọc số để so sánh công bằng (SC-006).
  - FR-010: kiểm thử riêng được, không cần nguồn giọng. Hàm thuần nên test nhanh, không cần mạng.
  - Phạm vi nhỏ (số, giá, %, 6 đơn vị, vài viết tắt), viết tay vừa đủ (Điều VII).
- **Phương án đã cân nhắc:**
  - Gói `vinorm` hoặc chuẩn hóa sẵn có bên trong VieNeu: dependency hoặc hành vi không kiểm soát được, đọc theo miền Bắc, không áp dụng
    được cho Gemini.
  - Nhờ LLM viết sẵn chữ đọc trong câu trả lời: phá guard chặn giá bịa (guard đối chiếu số), tăng token và độ trễ.
- **Ngoài phạm vi bản này (thêm khi gặp):** ngày tháng ("12/12"), giờ ("20h"), "1tr2", số La Mã, phân số.

## R4. Lớp bọc chung: chuẩn hóa, đếm ký tự, nghỉ khi hết hạn mức

- **Quyết định:** `create_tts()` luôn trả `SpeechTTS(engine, normalizer, quota_cooldown_s)`, một lớp bọc cũng thỏa `TTSEngine`.
  Nó chuẩn hóa chữ, gọi adapter thật, đếm số câu và số ký tự đã gửi (`usage`), và sau lỗi `quota_exhausted` thì từ chối ngay
  (không gọi nguồn giọng) trong `TTS_QUOTA_COOLDOWN_S` giây.
- **Lý do:**
  - ShowDirector, route `/api/debug/speak` và CLI `python -m ai_live.tts say` đều đi qua `create_tts`, nên cả ba được chuẩn hóa mà
    **không sửa lõi pipeline** (FR-011, Điều IV). ShowDirector vẫn đưa câu gốc cho phụ đề (FR-009): nó gửi `sentence` gốc cho cả
    `synthesize()` và trình phát; chỉ lớp bọc đổi chữ trước khi đọc.
  - Đếm ký tự và chặn thử lại liên tục là việc chung cho mọi nguồn có hạn mức (FR-013, FR-015), không lặp ở từng adapter.
  - Nghỉ theo thời gian thay vì khóa tới hết phiên: lỗi 429 có thể do giới hạn theo phút (hồi lại sau vài chục giây) hoặc theo ngày.
    Sau thời gian nghỉ, lượt kế tiếp thử lại đúng một lần; lỗi tiếp thì nghỉ tiếp. Không có vòng thử lại trong một lượt.
- **Phương án đã cân nhắc:** Chuẩn hóa trong ShowDirector (sửa lõi, CLI và route debug phải tự gọi lại); chuẩn hóa trong từng adapter
  (lặp code, dễ lệch giữa hai nguồn).

## R5. Định dạng tiếng ra: PCM16 mono 16 kHz cố định

- **Quyết định:** Mọi adapter trả PCM16 little-endian, mono, đúng `TTS_SAMPLE_RATE` (mặc định và khuyến nghị 16000). Chốt 16 kHz làm
  hợp đồng chung, giải TODO ở `docs/ARCHITECTURE.md` §3 (ADR-025 đề xuất).
  - VieNeu trả float32 48 kHz: adapter cắt biên về [-1, 1], đổi sang int16 và hạ tần số 48 → 16 kHz (tỉ lệ 3:1) bằng lọc thông thấp
    đơn giản rồi lấy 1 mẫu trong 3, dùng `numpy` (đi kèm `vieneu` qua `onnxruntime`). Không dùng `audioop` (đã bị bỏ khỏi Python 3.13).
  - Gemini: xin thẳng 16 kHz (R2).
- **Lý do:** Wav2Lip và MuseTalk đều tính đặc trưng tiếng ở 16 kHz, LiveTalking nhận PCM 16 kHz, và trang host ảnh tĩnh của 001 đã chạy
  16 kHz (FR-005: dùng được trực tiếp cho cả hai). 16 kHz đủ rõ cho giọng nói.
- **Phương án đã cân nhắc:**
  - Giữ 48 kHz rồi để renderer tự hạ: mỗi renderer phải tự làm, dễ lệch.
  - Gói `soxr` để hạ tần số chất lượng cao: thêm dependency; chỉ cân nhắc nếu nghe thấy tiếng rè khi so sánh (SC-002).
- **TODO:** Nghe thử xem lọc đơn giản có gây rè không (SC-002). Nếu có, đề xuất ADR thêm `soxr`.

## R6. Hủy giữa chừng khi bỏ qua lượt (FR-014) và không chặn event loop

- **Quyết định:**
  - `vieneu`: vòng tạo tiếng (generator đồng bộ, nặng CPU) chạy trong một luồng riêng qua `asyncio.to_thread`. Luồng đẩy từng đoạn vào
    `asyncio.Queue` bằng `loop.call_soon_threadsafe`; generator async của adapter đọc hàng đợi đó. Khi ShowDirector hủy lượt, nó gọi
    `aclose()` trên stream (đã có sẵn trong `_enqueue`); khối `finally` của adapter bật cờ `threading.Event` để luồng dừng sau đoạn đang
    làm và bỏ phần còn lại. Nạp model cũng chạy trong luồng riêng.
  - `gemini`: `aclose()` đóng stream HTTP của SDK; phần tiếng chưa nhận bị bỏ.
- **Lý do:** Điều VI cấm chặn event loop; ShowDirector 001 đã gọi `aclose()` khi bỏ qua hoặc lỗi.
- **Phương án đã cân nhắc:** Chạy VieNeu trong process riêng (cô lập CPU tốt hơn nhưng thêm IPC và độ phức tạp; để sau nếu đo thấy giật).

## R7. Nạp model trước phiên (warm-up)

- **Quyết định:** Thêm `async def warm_up(self) -> None` vào Protocol `TTSEngine`. App gọi một lần lúc khởi động (lifespan), CLI gọi
  trước câu đầu. `vieneu` nạp model và đọc thử một câu ngắn; `gemini` và `fake` không làm gì (không tốn hạn mức). Nạp lỗi thì app vẫn
  chạy, lỗi được ghi log và báo ở lượt đầu tiên.
- **Lý do:** Nếu để nạp ở câu đầu của lượt đầu, lượt đó chắc chắn vượt `TTS_TIMEOUT_S` và làm sai số đo SC-003.
- **Phương án đã cân nhắc:** Nạp trong `__init__` (chặn lúc tạo, `create_tts` đồng bộ); dò `hasattr(..., "warm_up")` (ngầm, khó đọc).

## R8. Lỗi của bước tạo tiếng

- **Quyết định:** Thêm `TTSEngineError(kind, message)` ở `core/protocols.py`, giống `ReplyEngineError`. `kind` là một trong:
  `quota_exhausted`, `rate_limited`, `api_error`, `config_error`, `model_error`. Thông báo tiếng Việt. ShowDirector đã đọc
  `exc.kind` và hiện "Lỗi ở bước tts: …" trên trang điều khiển, nên không phải sửa lõi.
  - Gemini: HTTP 429 → `quota_exhausted` với thông báo "Hết hạn mức giọng nói (Gemini TTS, gói miễn phí). Thử lại sau N giây."
    (FR-013). Không thử lại trong lượt. Lỗi khác → `api_error`.
  - VieNeu: không nạp được model → `config_error`; lỗi khi tạo tiếng → `model_error`.
- **Lý do:** Giữ một kiểu lỗi cho mỗi bước như 001; `kind` vào `errors.jsonl` để thống kê.
- **TODO:** Gemini có phân biệt 429 do giới hạn theo phút và theo ngày trong nội dung lỗi không? Nếu có, thông báo nói rõ hơn.

## R9. Thời gian chờ của bước tạo tiếng

- **Quyết định:** Giữ nguyên `TTS_TIMEOUT_S=5` và cách ShowDirector áp thời gian chờ cho cả câu. Không sửa lõi ở feature này.
- **Lý do:** Nếu VieNeu đạt khoảng 2 lần thời gian thực như công bố, một câu dài 5 giây tiếng cần khoảng 2,5 giây để tạo, còn trong
  giới hạn. Chưa có số đo trên laptop nên chưa đủ lý do sửa lõi.
- **TODO:** Sau khi đo SC-006 khi chạy cùng lip-sync: nếu câu dài hay bị quá thời gian thì tăng `TTS_TIMEOUT_S` bằng cấu hình (ADR-023
  chấp nhận chậm), hoặc đề xuất tách thời gian chờ câu đầu và cả câu (sửa lõi, cần sửa spec 001 trước).

## R10. Kiểm thử

- **Quyết định:**
  - Test mặc định (không mạng, không model): bảng ≥ 40 câu chuẩn hóa (SC-001) ở `tests/unit/test_tts_normalize.py`; lớp bọc (chuẩn hóa,
    đếm ký tự, nghỉ khi hết hạn mức) bằng một engine giả; adapter `vieneu` với đối tượng `Vieneu` giả (đổi float32 48 kHz sang PCM16
    16 kHz, hủy giữa chừng dừng luồng); adapter `gemini` với client giả trả sự kiện `step.delta` (giải base64, 429 →
    `quota_exhausted`, chỉ gửi đúng chữ cần đọc); factory chọn đúng adapter.
  - Marker mới `live_tts`: gọi nguồn giọng thật (Gemini cần key, tính vào hạn mức; VieNeu cần model đã tải). Không chạy mặc định:
    `addopts = '-m "not live_llm and not live_tts"'`.
  - Nghe thử (SC-002, SC-006) là bước tay trong quickstart.
- **Lý do:** Điều V: test mặc định không cần GPU, mạng hay key.
