# Mô hình dữ liệu (Phase 1): 003-vietnamese-tts

- **Plan:** [plan.md](./plan.md) · Lấy từ "Thực thể chính" của [spec.md](./spec.md). Không có lưu trữ mới ngoài một file JSON trong
  thư mục phiên (đã nằm trong `.gitignore`).

## 1. Nguồn giọng (cấu hình, `Settings`)

| Trường (biến môi trường) | Kiểu | Mặc định | Kiểm tra |
|--------------------------|------|----------|----------|
| `tts_provider` (`TTS_PROVIDER`) | `Literal["fake", "vieneu", "gemini"]` | `fake` | Giá trị khác → lỗi cấu hình lúc mở app. Bỏ `elevenlabs`, `oss` (chưa có adapter, ADR-024) |
| `tts_sample_rate` (`TTS_SAMPLE_RATE`) | `int` | `16000` | > 0. Hợp đồng chung là 16000 (ADR-025) |
| `tts_timeout_s` (`TTS_TIMEOUT_S`) | `float` | `5` | > 0 (đã có từ 001) |
| `tts_quota_cooldown_s` (`TTS_QUOTA_COOLDOWN_S`) | `float` | `60` | ≥ 0. Thời gian từ chối ngay sau lỗi hết hạn mức |
| `vieneu_voice` (`VIENEU_VOICE`) | `str` | `Thục Đoan` (tạm, chốt sau khi nghe) | Không rỗng; tên không có trong danh sách giọng của model → `config_error` lúc warm-up |
| `vieneu_cpu_threads` (`VIENEU_CPU_THREADS`) | `int` | `4` (tạm) | ≥ 1. TODO: đo rồi chốt (research R1) |
| `gemini_tts_model` (`GEMINI_TTS_MODEL`) | `str` | `gemini-3.8-flash-tts` | Không rỗng |
| `gemini_tts_voice` (`GEMINI_TTS_VOICE`) | `str` | `Leda` (tạm, chốt sau khi nghe) | Không rỗng |
| `gemini_api_key` (`GEMINI_API_KEY`) | `SecretStr` | (đã có từ 001) | Bắt buộc khi `TTS_PROVIDER=gemini`; thiếu → lỗi cấu hình lúc mở app. Không log (FR-016) |
| `fake_tts_delay_ms` (`FAKE_TTS_DELAY_MS`) | `int` | `0` | (đã có từ 001) |

- Giá trị "tạm" là mặc định ban đầu để chạy được; giọng chính thức chốt cùng ADR chọn nguồn mặc định sau SC-006.
- Biến bỏ khỏi `.env.example`: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID`, `OSS_TTS_MODEL_PATH`
  (không có adapter; thêm lại cùng adapter nếu sau này dùng).
- Đường dẫn model VieNeu: dùng cache mặc định của thư viện (ngoài repo). TODO: xác nhận thư mục cache sau khi cài (research R1).

## 2. Giọng của AI host

Không thành bảng dữ liệu riêng ở bản này. Một giọng = cặp (`TTS_PROVIDER`, `VIENEU_VOICE` hoặc `GEMINI_TTS_VOICE`) trong `.env` của máy
chạy phiên cho **một** khách (FR-002, Điều I).
- Ràng buộc "một giọng chỉ cho một khách" ở demo được giữ bằng quy trình: mỗi khách một file `.env`, ghi tên giọng đã chọn vào hồ sơ
  khách (ngoài git). TODO: khi có khách thứ hai (mốc Multi-customer), cần sổ đăng ký AI host chặn bằng code (RISKS P4).

## 3. Quy tắc chuyển chữ (`normalize_for_speech`)

Hàm thuần, chạy theo thứ tự dưới đây trên một câu. Đầu ra chỉ có chữ tiếng Việt, khoảng trắng và dấu câu cơ bản (`, . ? !`).
Không bao giờ đổi giá trị số (Điều III).

| # | Quy tắc | Mẫu vào | Mẫu ra |
|---|---------|---------|--------|
| 1 | Bỏ link (`http…`, `www.…`) và emoji/ký tự biểu tượng | `Xem 👉 https://x.vn` | `Xem` |
| 2 | Viết tắt từ `data/rules/tts_abbreviations.json` (khớp nguyên từ, không phân biệt hoa thường) | `SP`, `KM` | `sản phẩm`, `khuyến mãi` |
| 3 | Size chữ: `size` + `S`/`M`/`L`/`XL`/`XXL` | `size M` | `sai em` (TODO: nghe thử) |
| 4 | Khoảng giá/số: `A–B`, `A-B`, `A ~ B` khi hai đầu là số (có hoặc không đơn vị) | `259.000đ–439.000đ` | `từ hai trăm năm mươi chín ngàn đồng đến bốn trăm ba mươi chín ngàn đồng` |
| 5 | Giá tiền: số + `đ` / `đồng` / `VND` / `vnđ` | `259.000đ` | `hai trăm năm mươi chín ngàn đồng` |
| 6 | Số + `k` (ngàn) | `250k` | `hai trăm năm mươi ngàn` |
| 7 | Phần trăm | `15%`, `0,5%` | `mười lăm phần trăm`, `không phẩy năm phần trăm` |
| 8 | Đơn vị đo sau số: `ml`, `l`/`L`, `g`, `kg`, `cm`, `m` | `1,5L`, `500ml`, `2kg` | `một phẩy năm lít`, `năm trăm mi li lít`, `hai ki lô gam` |
| 9 | Dãy số đọc từng chữ số: bắt đầu bằng `0` và dài ≥ 4 chữ số, hoặc ≥ 9 chữ số liền, hoặc từ lẫn chữ và số (mã) | `0909123456`, `GIAM50K` | `không chín không chín một hai ba bốn năm sáu`, `giê i a em năm không ca` (TODO: nghe thử cách đọc chữ cái) |
| 10 | Số còn lại | `1.250.000`, `3,75` | `một triệu hai trăm năm mươi ngàn`, `ba phẩy bảy mươi lăm` |

**Đọc số (miền Nam, FR-007):**
- Nhóm ba chữ số theo `ngàn`, `triệu`, `tỷ`. Nhóm giữa có hàng trăm bằng 0 đọc `không trăm` (`1.050.000` → `một triệu không trăm năm mươi ngàn`).
  Nhóm toàn 0 thì bỏ.
- Hàng chục bằng 0 và hàng đơn vị khác 0: `lẻ` (`105` → `một trăm lẻ năm`).
- `mười`, `hai mươi`…; đơn vị 1 sau hàng chục ≥ 2 đọc `mốt`; đơn vị 5 sau hàng chục ≥ 1 đọc `lăm`; đơn vị 4 đọc `bốn` (rõ hơn `tư`).
- Dấu chấm là ngăn cách ngàn **chỉ khi** sau mỗi dấu chấm có đúng 3 chữ số (`1.250.000`). Dấu phẩy giữa hai chữ số là thập phân,
  đọc `phẩy`, phần sau dấu phẩy đọc như số (`3,75` → `ba phẩy bảy mươi lăm`; bắt đầu bằng 0 thì đọc từng chữ số: `0,05` → `không phẩy không năm`).
  Dạng `1.5` (không đúng 3 chữ số sau chấm) đọc `một chấm năm`, không đoán là thập phân.
- Số rất lớn (> 999 tỷ): đọc từng chữ số.

**`data/rules/tts_abbreviations.json`** (mới, có trong git, không chứa dữ liệu khách):
```json
{"SP": "sản phẩm", "KM": "khuyến mãi", "SL": "số lượng", "VND": "đồng"}
```
Kiểm tra lúc nạp: khóa không rỗng, không trùng khi bỏ hoa thường, giá trị là chữ (không có số).

## 4. Hạn mức và số ký tự đã dùng (`TTSUsage`)

| Trường | Kiểu | Ý nghĩa |
|--------|------|---------|
| `provider` | `str` | `fake` / `vieneu` / `gemini` |
| `requests` | `int` | Số câu đã gửi tới nguồn giọng (kể cả câu lỗi) |
| `chars` | `int` | Tổng số ký tự **sau chuẩn hóa** đã gửi (đây là thứ tính hạn mức) |
| `quota_errors` | `int` | Số lần nhận lỗi hết hạn mức |
| `rejected_in_cooldown` | `int` | Số câu bị từ chối ngay vì đang nghỉ, không gọi nguồn giọng |

Ghi ra `data/sessions/<session_id>/tts_usage.json` một lần khi đóng app, cùng lúc với `latency_summary.json` (FR-015).

**Trạng thái nghỉ khi hết hạn mức (lớp bọc `SpeechTTS`):**

```
ready --(nguồn giọng ném TTSEngineError kind=quota_exhausted)--> cooling_down(until = now + TTS_QUOTA_COOLDOWN_S)
cooling_down --(synthesize() khi now < until)--> ném ngay TTSEngineError(quota_exhausted), không gọi nguồn giọng
cooling_down --(synthesize() khi now ≥ until)--> ready (thử thật đúng một lần)
```
