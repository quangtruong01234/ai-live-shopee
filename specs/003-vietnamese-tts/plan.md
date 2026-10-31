# Kế hoạch triển khai: Giọng tiếng Việt thật cho AI host

- **Feature ID:** `003-vietnamese-tts` · **Ngày:** 2026-10-31 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/003-vietnamese-tts/spec.md`

## Tóm tắt

Thay âm "bíp" của `FakeTTS` bằng giọng nữ tiếng Việt thật, giọng có sẵn (không clone), qua hai adapter `TTSEngine` mới chọn bằng
`TTS_PROVIDER`: **`vieneu`** (VieNeu-TTS v3 Turbo chạy CPU/ONNX trên laptop, không tranh VRAM với lip-sync) và **`gemini`** (Gemini TTS
free tier, dùng lại SDK `google-genai` và key đã có). Cả hai stream tiếng PCM16 mono 16 kHz theo từng câu. Một lớp bọc `SpeechTTS` do
`create_tts()` trả về chuẩn hóa chữ trước khi đọc (số, giá, khoảng giá, %, đơn vị, viết tắt, theo cách nói miền Nam), đếm ký tự đã dùng
và tạm ngừng gọi sau lỗi hết hạn mức, nên **lõi pipeline của 001 không phải sửa** và phụ đề vẫn giữ chữ gốc. Sau khi so sánh hai nguồn
(SC-006), nguồn mặc định được chốt bằng ADR.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, `.python-version`)
- **Phụ thuộc chính:** FastAPI, pydantic-settings, google-genai 2.34.0 (ADR-018, đã cài) · **Phụ thuộc MỚI cần duyệt:**
  - `vieneu` (Apache-2.0), cài bản CPU/ONNX, kéo theo `onnxruntime` và `numpy`. Lý do: nguồn giọng (a) chạy trên laptop (FR-003). ADR-024.
  - Tải model VieNeu-TTS v3 Turbo từ Hugging Face vào cache ngoài repo. Dung lượng: TODO (research R1). Cần người dùng duyệt.
  - Gemini TTS: **không** thêm dependency.
- **Lưu trữ:** không có mới; thêm file `tts_usage.json` trong thư mục phiên (đã gitignore) và `data/rules/tts_abbreviations.json` (trong git).
- **Kiểm thử:** pytest. Test mặc định dùng engine giả, `Vieneu` giả, client Gemini giả; không mạng, không key, không model.
  Marker mới `live_tts` cho test gọi nguồn giọng thật (không chạy mặc định). Nghe thử là bước tay trong quickstart.
- **Nơi chạy:** laptop, `AVATAR_MODE=static`; không cần RunPod. VieNeu chạy CPU; Gemini cần mạng.
- **Adapter liên quan:** `TTSEngine` (thêm `VieneuTTS`, `GeminiTTS`, lớp bọc `SpeechTTS`; Protocol thêm `warm_up()`).
- **Mục tiêu hiệu năng:** câu đầu → chunk tiếng đầu ≤ 1,0 s p95 khi chạy riêng (SC-003); khi chạy cùng lip-sync chỉ ghi số (ADR-023).
- **Ràng buộc khác:** ưu tiên miễn phí (ADR-019); Gemini free tier dùng dữ liệu gửi lên để cải thiện sản phẩm (ADR-018, RISKS S7);
  chỉ gửi chữ cần đọc (FR-003 b); khóa không vào log (FR-016).

## Kiểm tra Constitution (cổng)

**Lần 1 (trước Phase 0):** Đạt, không có vi phạm. **Lần 2 (sau Phase 1):** Đạt, bảng dưới là kết quả sau thiết kế.

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt | Tiếng tạo lúc trả lời, từng câu. File `.wav` của CLI chỉ để thử trên laptop. Không cache tiếng. Một giọng = cấu hình `.env` của một khách (data-model §2); chặn bằng code để tới mốc Multi-customer (RISKS P4). Nhãn AI không đổi. |
| II. Đồng ý và bảo mật | Đạt | Giọng có sẵn, không clone giọng ai. `GEMINI_API_KEY` chỉ từ `.env`, che trong log. Model tải về cache ngoài repo; `.wav` đã gitignore. Gemini chỉ nhận chữ cần đọc. |
| III. Trả lời có căn cứ | Đạt | Chuẩn hóa không đổi giá trị số; bảng ≥ 40 câu kiểm từng giá trị (SC-001). Guard 001 vẫn chạy trên chữ gốc trước khi chuẩn hóa. Không đổi prompt nên không cần chạy lại bộ câu hỏi. |
| IV. Adapter trước | Đạt | Mỗi nguồn giọng là một adapter, chọn bằng `TTS_PROVIDER`; lõi pipeline không sửa. Chạy riêng được qua CLI `say` / `normalize` và `/api/debug/speak`. |
| V. Test trước | Đạt | Chuẩn hóa, lớp bọc, hai adapter đều có test viết trước với đối tượng giả. Ca gọi thật có marker `live_tts`. Không có việc GPU. |
| VI. Ngân sách độ trễ | Đạt | Ngân sách 1,0 s giữ nguyên (bảng dưới). Việc nặng CPU của VieNeu chạy trong luồng riêng; nạp model lúc mở app (warm-up), không ở lượt đầu. |
| VII. Đơn giản trước | Đạt (cần duyệt) | Một dependency mới (`vieneu`) có ADR-024 chờ duyệt. Hai adapter thật nên lớp bọc chung là hợp lệ. Không process riêng, không hàng đợi ngoài. Chuẩn hóa tự viết thay vì thêm thư viện. |
| VIII. Quan sát được | Đạt | Mốc `tts_first_chunk` như 001; log `tts_ready`, `tts_quota_exhausted`, `tts_usage`; `kind` lỗi vào `errors.jsonl`; thời gian chờ và nghỉ khi hết hạn mức giữ phiên chạy. |
| IX. Ngôn ngữ và tài liệu | Đạt | Code và comment tiếng Anh; thông báo lỗi và chữ đọc tiếng Việt. File đang có comment tiếng Việt (`tts/factory.py`, `tts/fake_tts.py`, `tts/__main__.py`) được dịch khi sửa (ADR-022). Chỗ chưa chắc ghi `TODO:`. |

Ghi chú ngoài cổng: Điều V còn ghi việc GPU "chạy theo đợt trên RunPod", lệch với ADR-023. Không ảnh hưởng 003 (không có việc GPU),
nhưng cần sửa Hiến pháp trước `/sdd.plan 005`.

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| TTS đến chunk tiếng đầu | 1,0 s | Thay FakeTTS (gần 0 s) bằng tiếng thật. Thêm chuẩn hóa (hàm thuần, dưới 1 ms) và hạ tần số 48 → 16 kHz cho VieNeu. Chưa có số đo của nguồn nào trên laptop. | `first_sentence_to_tts_first_chunk` trong `GET /api/latency`, ≥ 20 lượt mỗi nguồn (SC-003, SC-006) |
| Lip-sync đến frame đầu | 0,8 s | Không đổi ở 003. Khi chạy cùng 005, VieNeu tranh CPU với lip-sync. | `tts_first_chunk_to_first_frame`, chỉ ghi số (ADR-023) |
| Tổng | ≤ 5,0 s | Lần đầu đo được tổng với giọng thật (vẫn còn ảnh tĩnh). | `GET /api/latency` |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/003-vietnamese-tts/
├── spec.md
├── plan.md            # file này
├── research.md        # R1–R10
├── data-model.md      # cấu hình, quy tắc chuyển chữ, TTSUsage
├── contracts/
│   ├── adapters.md    # TTSEngine (+warm_up), TTSEngineError, VieneuTTS, GeminiTTS, SpeechTTS, so với ARCHITECTURE §3
│   └── events.md      # log, kind lỗi, tts_usage.json, biến môi trường, CLI
├── quickstart.md
└── tasks.md           # /sdd.tasks
```

### Mã nguồn
```
src/ai_live/core/protocols.py        # sửa: TTSEngine.warm_up(), thêm TTSEngineError
src/ai_live/core/config.py           # sửa: tts_provider Literal, biến VIENEU_*, GEMINI_TTS_*, TTS_QUOTA_COOLDOWN_S
src/ai_live/tts/normalize.py         # mới: normalize_for_speech, load_abbreviations
src/ai_live/tts/speech.py            # mới: SpeechTTS, TTSUsage
src/ai_live/tts/vieneu_tts.py        # mới
src/ai_live/tts/gemini_tts.py        # mới
src/ai_live/tts/fake_tts.py          # sửa: warm_up() không làm gì
src/ai_live/tts/factory.py           # sửa: ba nhà cung cấp, luôn bọc SpeechTTS
src/ai_live/tts/__main__.py          # sửa: gọi warm_up, in chữ đã chuẩn hóa, lệnh con normalize
src/ai_live/app/main.py              # sửa: warm_up trong lifespan, ghi tts_usage lúc đóng
src/ai_live/director/session_log.py  # sửa: ghi tts_usage.json
data/rules/tts_abbreviations.json    # mới
.env.example                         # sửa: khối TTS (contracts/events.md §4)
pyproject.toml                       # sửa: marker live_tts; dependency vieneu (sau khi duyệt)
tests/unit/test_tts_normalize.py     # mới: ≥ 40 câu (SC-001)
tests/unit/test_tts_speech.py        # mới: lớp bọc (chuẩn hóa, đếm ký tự, nghỉ khi hết hạn mức)
tests/unit/test_vieneu_tts.py        # mới: Vieneu giả (đổi định dạng, hủy giữa chừng)
tests/unit/test_gemini_tts.py        # mới: client giả (base64, 429, chỉ gửi chữ)
tests/unit/test_tts_factory.py       # mới
tests/unit/test_config.py            # sửa theo biến mới
tests/integration/test_tts_live.py   # mới, marker live_tts
docs/ARCHITECTURE.md, docs/VENDORS.md # sửa khi ADR-024, ADR-025 được chốt
```

## Phase 0: Nghiên cứu → [`research.md`](./research.md)

- R1 VieNeu CPU/ONNX là nguồn (a) · R2 Gemini TTS free tier là nguồn (b) · R3 chuẩn hóa tự viết · R4 lớp bọc chung · R5 PCM16 16 kHz
  · R6 hủy giữa chừng, luồng riêng · R7 `warm_up()` · R8 `TTSEngineError` · R9 giữ `TTS_TIMEOUT_S` · R10 kiểm thử.

## Phase 1: Thiết kế

- [data-model.md](./data-model.md): biến cấu hình, giọng của AI host, bảng quy tắc chuyển chữ, `TTSUsage` và trạng thái nghỉ.
- [contracts/adapters.md](./contracts/adapters.md): Protocol và các lớp; bảng khác biệt so với ARCHITECTURE §3 (4 điểm, đều qua ADR-024/025).
- [contracts/events.md](./contracts/events.md): log, `kind` lỗi, file phiên, `.env.example`, CLI.
- [quickstart.md](./quickstart.md): mọi bước chạy trên laptop; bước cần mạng, key, model hay 005 được đánh dấu.

## ADR cần ghi

- **ADR-024 (Đề xuất):** hai nguồn giọng miễn phí VieNeu-TTS (CPU/ONNX, local) và Gemini TTS (free tier), thêm dependency `vieneu`,
  bỏ `elevenlabs`/`oss` khỏi cấu hình, thêm `warm_up()` vào `TTSEngine`. Nguồn mặc định chốt sau SC-006 (ghi thêm vào ADR này).
- **ADR-025 (Đề xuất):** hợp đồng tiếng PCM16 mono 16 kHz cho mọi TTS; chuẩn hóa chữ tự viết theo cách đọc miền Nam, áp dụng trong lớp
  bọc trước mọi nguồn giọng.

## Rủi ro mới

- **L8** VieNeu: license code/model Apache-2.0, giọng có sẵn cho dùng thương mại theo trang model; cần đọc lại điều khoản từng giọng.
- **L9** Gemini TTS: điều khoản dùng tiếng tạo ra cho mục đích thương mại và ở free tier.
- **G7** VieNeu tranh CPU với app và lip-sync trên laptop: tiếng chậm hoặc giật khi chạy cùng 005.
- **Q12** Giới hạn free tier của Gemini TTS (RPM/RPD) thấp hơn số câu của phiên 30 phút.
- **Q13** Giọng có sẵn không ra giọng miền Nam (Gemini) hoặc chất lượng giọng có sẵn của VieNeu không đạt SC-002.

## Theo dõi độ phức tạp

Không có vi phạm cần biện minh.
