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
- **Kết quả cài và chạy thử (T001, T002, 2026-11-07, `vieneu` 3.8.3, `onnxruntime` 1.31.1, `huggingface-hub` 2.4.0):**
  - Cây phụ thuộc không có `torch` hay gói GPU. Ngoài `onnxruntime`, `numpy`, gói còn kéo theo `gradio`, `librosa` (kèm `numba`,
    `scikit-learn`, `scipy`), `pandas`, `huggingface-hub`, `sea-g2p`, `soundfile`, `soxr`, `tokenizers`, `kaldi-native-fbank`
    (ADR-024 chỉ ghi `onnxruntime`, `numpy`).
  - Chữ ký: `Vieneu(mode="v3turbo", backend="onnx", threads=0, onnx_dir=None, precision="fp32", ...)`;
    `infer_stream(text, voice=None, ..., max_chars=256, apply_watermark=True)` sinh ra `numpy.ndarray` **float32, 48 kHz**
    (`tts.sample_rate == 48000`, không chọn được tần số khác) → adapter tự hạ xuống 16 kHz như R5. Có `tts.close()`.
  - Giọng có sẵn: 25 giọng; giọng mặc định của thư viện là `Hải Đăng` (nam, Bắc). Có `Thục Đoan` (nữ, Nam, phong cách kể chuyện).
    Giọng nữ miền Nam: `Thùy Dung` (tin tức), `Thục Đoan`, `Mỹ Duyên`, `Kim Thanh` (đọc truyện). Tên sai → `ValueError`.
  - **Giọng mặc định (T049, 2026-11-09): `Thùy Dung`.** Người dùng nghe q07 giọng `Thục Đoan` thấy "nắng" thành "nứng" (nguy hiểm
    với livestream kem chống nắng). G2P của `sea_g2p` đúng (`nắng` → `nˈaɜŋ`, `nứng` → `nˈyɜŋ`) nên lỗi nằm ở bước sinh tiếng. Nghe
    câu q07 đọc lại nhiều lần (`out/t049/nang_test/`): `Thục Đoan` mặc định, temperature 0,4 / top_k 10, 0,2 / top_k 5; `Mỹ Duyên`,
    `Kim Thanh`, `Thùy Dung` mặc định. Người dùng chọn `Thùy Dung`: nghe rõ nhất. Giữ tham số lấy mẫu mặc định của thư viện
    (temperature 0,8, top_k 25), không thêm biến cấu hình.
  - **Đoạn mẫu `VIENEU_REF_AUDIO` (T049, 2026-11-09):** người dùng chọn lần đọc `D_ThuyDung_lan2` (2,4 s, PCM16 16 kHz) làm chất
    giọng cố định. Cách chính thức của thư viện (`ref_audio=` / `encode_reference()`) cần `speaker_encoder.onnx` chưa có trong cache
    (phải tải, cần ADR) nên không dùng. Thay vào đó giữ vân giọng có sẵn (`speaker_emb` của `Thùy Dung`) và mã hóa đoạn mẫu bằng
    bộ mã hóa MOSS đã có trong cache (`engine._encode_ref_wav`), truyền `voice={"speaker_emb", "codes"}`. Đo offline
    (`HF_HUB_OFFLINE=1`): mã hóa 2,4 s một lần lúc warm-up, ra 30 × 16 mã; đoạn tiếng đầu mỗi câu 0,28–0,54 s (10 câu trả lời mẫu).
    Người dùng nghe `out/t049/ref_lan2/`: ổn, kể cả "nắng".
    - Rủi ro: `_encode_ref_wav` là hàm nội bộ, có thể đổi khi nâng `vieneu` → adapter kiểm có hàm, thiếu thì `config_error` rõ ràng;
      test chạy với model giả. File đoạn mẫu nằm ngoài git (`~/.cache/ai-live/voices/`), phải sao lưu cùng hồ sơ khách.
  - Watermark tiếng: chỉ bật khi cài thêm `resemble-perth` (`vieneu[watermark]`); bản đang cài không có, `apply_watermark` không làm gì.
  - Tự chuẩn hóa chữ bên trong: **có** (`sea_g2p.Normalizer`, gọi trong `infer_stream`, không tắt được). Chữ của mình đã chuẩn hóa
    nên nó gần như không đổi gì; kiểm tra bằng tai ở T034.
  - Số luồng: `threads=0` → mặc định của engine, máy này ra 6 luồng intra-op (máy có 12 luồng logic). `VIENEU_CPU_THREADS` truyền vào
    `threads`.
  - Gọi song song: trên CPU/ONNX thư viện tự nói "one call at a time" (engine có `threading.RLock`). Giữ khóa trong adapter như plan.
  - Dung lượng model: 581 MB (backbone ONNX fp32 454 MB + codec MOSS-Audio-Tokenizer-Nano-ONNX 87 MB + file phụ).
  - Đo nhanh trên laptop (chạy riêng, giọng `Thục Đoan`, 6 luồng): nạp model 5,4 s (đã có cache; lần đầu kèm tải ~40 s); câu 16 ký tự
    → đoạn tiếng đầu 0,36 s, hệ số thời gian thực 0,76; câu 107 ký tự → đoạn đầu 0,41 s, đọc xong 3,96 s cho 5,92 s tiếng (0,67).
- **Vấn đề khi nạp (từng chặn T002, đã gỡ):** với cache mặc định, `onnxruntime` 1.31 từ chối nạp: *"External data path escapes model directory"*.
  `huggingface-hub` 2.x lưu file trong `blobs/<2 ký tự>/<hash>` và để symlink trong `snapshots/`. ONNX lần theo symlink tới thư mục
  `blobs/..` thật, nên file trọng số đi kèm (`*.data`) nằm ở thư mục khác và bị chặn. Truyền `onnx_dir` chỉ sửa được phần backbone,
  vì `V3TurboVieNeuTTS` không chuyển `codec_dir` xuống engine. Đặt `HF_HUB_DISABLE_SYMLINKS=1` cùng `HF_HUB_CACHE` trỏ tới một thư mục
  cache riêng (đường dẫn ngắn, Windows giới hạn 260 ký tự) thì nạp và đọc được (số đo ở trên). Đã thử trên
  `C:\Users\<user>\.cache\hf_nosym`, ngoài repo.
  **Cách chốt (người dùng duyệt 2026-11-07):** biến `VIENEU_MODEL_CACHE` (mặc định `~/.cache/ai-live/hf`, data-model §1). Adapter đặt
  `HF_HUB_CACHE` và `HF_HUB_DISABLE_SYMLINKS=1` trong `os.environ` ngay trước lần import `vieneu` đầu tiên; app không import
  `huggingface_hub` ở chỗ khác (đã kiểm), còn nếu đã import thì báo `config_error`. Đã bỏ: tự đặt biến trong cửa sổ lệnh (dễ quên),
  hạ `onnxruntime` (mất lớp kiểm tra an toàn, cần ADR). Bản tải lần đầu ở cache mặc định đã xóa; model hiện ở
  `~/.cache/ai-live/hf`, đo lại sau khi chuyển: nạp 6,1 s, đoạn tiếng đầu 0,32–0,33 s.
- **TODO:**
  - Tốc độ khi chạy cùng lip-sync. Đo ở SC-006 (T050).
- **`VIENEU_CPU_THREADS` (T049, 2026-11-09): giữ 4.** Đo 2 / 4 / 6 luồng ở mục "Kết quả SC-003 / SC-006" cuối file: 6 luồng
  chỉ nhanh hơn 4 luồng ~0,015 s (p95), 2 luồng chậm hơn ~0,11 s. Giữ 4 để chừa CPU cho app và lip-sync (RISKS G7); đo lại khi chạy
  cùng 005 (T050).

## R2. Nguồn giọng (b) dịch vụ ngoài miễn phí: Gemini TTS, free tier

- **Quyết định:** Adapter `gemini` gọi model Gemini TTS (mặc định `gemini-3.8-flash-tts`, thử thêm `gemini-3.8-flash-lite-tts`) qua SDK
  `google-genai` đã cài (ADR-018), chế độ async streaming: `client.aio.interactions.create(..., stream=True)`, đọc các sự kiện
  `step.delta` có `delta.type == "audio"`, giải base64 `delta.data`. Yêu cầu đầu ra `response_format={"type": "audio"}` (API trả
  PCM `audio/l16` 24 kHz), adapter tự hạ 24 → 16 kHz như R5. Câu gửi đi theo dạng có cấu trúc của docs:
  `input=[{"type": "user_input", "content": [{"type": "text", "text": "<câu>"}]}]`. Giọng chọn qua
  `generation_config={"speech_config": [{"voice": "<tên>"}]}`. Dùng lại `GEMINI_API_KEY`. Chỉ gửi chữ đã chuẩn hóa của câu cần đọc
  (FR-003 b).
- **Đã đo ở T044 (2026-11-09):** xin `"mime_type": "audio/l16", "sample_rate": 16000` bị trả HTTP 400 "Request contains an invalid
  argument" (thử cả `input` dạng chuỗi lẫn dạng có cấu trúc). Bỏ hai trường đó thì API trả `audio/l16` 24 kHz. Chưa thử `input` dạng
  chuỗi với `{"type": "audio"}` (mỗi lần thử tốn một request), nên giữ dạng có cấu trúc như docs.
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
- **Giới hạn free tier của `gemini-3.8-flash-tts`:** 3 RPM, 10K TPM, 10 RPD (gói miễn phí, project `AIStreamming`, người dùng xem AI Studio 2026-11-10, T048; dùng cao nhất 28 ngày: 2 RPM, 58 TPM, 7 RPD). Mỗi câu là một request; phiên 30 phút cần khoảng
  100–200 request (T051 dùng 84 request cho 60 comment; show liên tục của 004 ước 250–450 câu). 10 RPD chỉ đủ khoảng 3–5 phút
  phát, 3 RPM chậm hơn nhịp câu của host. Kết luận: Gemini TTS free tier chỉ dùng để thử `say` và so sánh ngắn, **không** thay được
  VieNeu cho cả phiên; nếu VieNeu hỏng giữa phiên thì Gemini chỉ cầm cự vài câu rồi lớp bọc báo "Hết hạn mức giọng nói" (RISKS Q12).
- **TODO:**
  - Giọng Gemini đọc tiếng Việt theo giọng miền nào? Có chỉnh được bằng câu chỉ dẫn phong cách (`annotations` kiểu `speech_metadata`)
    không? Nghe thử ở SC-006. Câu chỉ dẫn phong cách chỉ chứa yêu cầu giọng đọc, không chứa thông tin phiên hay người xem.
  - Thời gian đến đoạn tiếng đầu tiên từ Việt Nam: đo ở SC-006. Một lần đo ở T044 (2026-11-09, `gemini-3.8-flash-tts`, giọng Leda,
    câu 39 ký tự): đoạn đầu 4,0 s, xong cả câu 6,5 s cho 2,9 s tiếng. Đoạn đầu 4 s chậm hơn nhiều so với VieNeu (0,26 s) và có thể
    làm lặng giữa câu vượt 1,5 s (Điều VI) nếu câu sau chỉ bắt đầu gọi khi câu trước phát xong; cần đo thêm ở SC-006.

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
  hợp đồng chung, giải TODO ở `docs/ARCHITECTURE.md` §3 (ADR-025).
  - VieNeu trả float32 48 kHz: adapter cắt biên về [-1, 1], đổi sang int16 và hạ tần số 48 → 16 kHz (tỉ lệ 3:1) bằng lọc thông thấp
    đơn giản rồi lấy 1 mẫu trong 3, dùng `numpy` (đi kèm `vieneu` qua `onnxruntime`). Không dùng `audioop` (đã bị bỏ khỏi Python 3.13).
  - Gemini trả PCM16 24 kHz (API không nhận yêu cầu 16 kHz, đo ở T044): adapter hạ 24 → 16 kHz (tỉ lệ 2:3) bằng cùng bộ lọc, chèn 0
    để tăng gấp đôi rồi lọc và lấy 1 mẫu trong 3. Bộ lọc dùng chung nằm ở `ai_live/tts/resample.py`.
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

- **Quyết định (đổi bởi ADR-049, 2026-11-09):** Giữ `TTS_TIMEOUT_S=5` nhưng áp cho **mỗi lần chờ chunk** (chunk đầu và giữa hai
  chunk liền nhau), không áp cho cả câu. Sửa ở `ShowDirector` (001) và `ScriptRunner` (004); spec 001 đã sửa trước.
- **Quyết định cũ:** Giữ nguyên `TTS_TIMEOUT_S=5` và cách ShowDirector áp thời gian chờ cho cả câu. Không sửa lõi ở feature này.
- **Lý do:** Nếu VieNeu đạt khoảng 2 lần thời gian thực như công bố, một câu dài 5 giây tiếng cần khoảng 2,5 giây để tạo, còn trong
  giới hạn. Chưa có số đo trên laptop nên chưa đủ lý do sửa lõi.
- **Số đo T026 (2026-11-09):** VieNeu trên laptop cần khoảng 0,63 s cho mỗi giây tiếng. Câu 9,6 s tiếng bị cắt ở 6,6 s với giới hạn
  5 s cho cả câu, lượt lỗi `tts/timeout`. Vì vậy quyết định cũ sai với câu dài; đã chọn tách thời gian chờ (ADR-049).

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

## Kết quả SC-003 / SC-006 (T049, chạy riêng, không có lip-sync)

Cách đo (2026-11-09, laptop dev): app thật (`AVATAR_MODE=static`, trang host giả lập phát theo thời gian thật), engine trả lời giả
đọc lại đúng 10 câu trả lời thật của lần chấm `data/eval/runs/20261104-171739` (Qwen3.8, 14 câu nói), 20 lượt mỗi lần đo (10 câu
× 2), số lấy từ `GET /api/latency`, `chars` từ sự kiện `tts_usage` lúc đóng app.

| Nguồn | Luồng CPU | Lượt (lỗi) | p95 câu đầu → chunk đầu (SC-003 ≤ 1,0 s) | Trung vị | p95 nhận comment → phát | `chars` / request | Điểm nghe (SC-002) |
|-------|-----------|------------|------------------------------------------|----------|--------------------------|-------------------|--------------------|
| VieNeu, Thục Đoan | 2 | 20 (0) | 0,529 s | 0,367 s | 0,593 s | 2116 / 28 | — |
| VieNeu, Thục Đoan | 4 | 20 (0) | 0,419 s | 0,297 s | 0,482 s | 2116 / 28 | q07 đọc "nắng" thành "nứng" → đổi giọng |
| VieNeu, Thục Đoan | 6 | 20 (0) | 0,405 s | 0,281 s | 0,454 s | 2116 / 28 | — |
| VieNeu, **Thùy Dung** | 4 | 20 (0) | 0,405 s | 0,281 s | 0,467 s | 2116 / 28 | người dùng muốn cố định vân giọng → thêm đoạn mẫu |
| VieNeu, **Thùy Dung + đoạn mẫu `lan2`** | 4 | 20 (0) | 0,516 s | 0,360 s | 0,578 s | 2116 / 28 | ổn, kể cả "nắng" (người dùng nghe `out/t049/ref_lan2/`) |
| Gemini | — | không đo 20 lượt (người dùng chốt nguồn mặc định 2026-11-09) | 3,5–4,1 s (đo đơn lẻ T044, T045) | — | — | — | nghe rõ (T045) |

- VieNeu đạt SC-003 ở cả ba mức luồng; 20/20 lượt xong, không lỗi bước `tts`.
- Đoạn mẫu làm đoạn tiếng đầu chậm thêm khoảng 0,1 s (p95 0,405 → 0,516 s), vẫn dưới 1,0 s. Warm-up lần đầu (nạp model + mã hóa
  đoạn mẫu) khoảng 12 s.
- Gemini: các lần đo đơn lẻ ở T044, T045 cho đoạn đầu 3,5–4,1 s, tức không đạt SC-003 dù chưa đo đủ 20 lượt.
- **Chốt (2026-11-09, người dùng):** nguồn mặc định `vieneu` (giọng `Thùy Dung` + đoạn mẫu `VIENEU_REF_AUDIO`, 4 luồng), `gemini`
  dự phòng, đổi tay bằng `TTS_PROVIDER` (spec không tự chuyển nguồn). Không đo Gemini đủ 20 lượt để giữ hạn mức free tier: số đo
  đơn lẻ đã gấp 3–4 lần ngưỡng SC-003 nên không đổi được kết luận. Giá trị mặc định trong code vẫn là `fake` (test và máy chưa có
  model chạy được ngay, quickstart §0); máy chạy phiên đặt `TTS_PROVIDER=vieneu` trong `.env`.
- Khi có lip-sync (T050): TODO, cần fork LiveTalking của 005 chạy được.
