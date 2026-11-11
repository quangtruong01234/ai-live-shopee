# Quickstart: 004-show-director

> **Mọi bước dưới chạy trên laptop dev, `AVATAR_MODE=static`, `TTS_PROVIDER=fake` mặc định. Không bước nào bắt buộc cần GPU hay RunPod.**
> Các lệnh chỉ chạy được sau khi `/sdd.implement` xong. Feature này không thêm dependency mới (plan.md).
> Bước đánh dấu **[Đo lại]** phải đo lại khi có giọng của 003 hoặc nhân vật của 005. Lip-sync chạy trên GPU laptop trước (ADR-023);
> RunPod chỉ là dự phòng, phải hỏi chi phí trước khi bật pod.

## 0. Chuẩn bị

Giống quickstart 001 §0, thêm:

```bash
# .env: thêm các biến SCRIPT_* (mặc định trong .env.example, plan.md "Biến môi trường") và PLATFORM_PHRASES_PATH
uv run pytest                                    # không cần mạng, key hay GPU
uv run uvicorn ai_live.app.main:app --port 8000
```

Mở `http://127.0.0.1:8000/host` (bấm **Bắt đầu** để mở khóa âm thanh) và `http://127.0.0.1:8000/` (trang điều khiển, khu **Show**).

> Với `REPLY_ENGINE=fake`, câu kịch bản có dạng "Câu n về <chủ đề> của <sản phẩm>.", đủ để kiểm luồng, nhịp và nút bấm.
> Kiểm nội dung (xưng hô, giá, độ tự nhiên) phải dùng LLM thật: engine chuỗi model free qua freellmapi của feature `008-llm-provider-chain`
> (ADR-035; giá trị `REPLY_ENGINE` chốt ở spec 008), không gọi Gemini trực tiếp. Hạn mức tính theo từng nhà cung cấp trong chuỗi (research R14).

### Lịch chạy các bước cần LLM thật (research R14, "Lịch test LLM thật chia giai đoạn")

Mọi bước khác trong file này chạy với `REPLY_ENGINE=fake`, không tốn hạn mức. Các bước cần LLM thật (engine 008) chạy theo giai đoạn, mỗi giai đoạn
một ngày nếu RPD thấp:

| Giai đoạn | Bước trong file này |
|-----------|---------------------|
| G1. Thử nhanh (sau US1) | US1 bước 4; test `live_llm` của `narrate()` với engine 008 (tên test chốt ở spec 008) |
| G2. Hồi quy guard | "Hồi quy" (bộ 10 câu của 001) + US4 lần 1 |
| G3. SC-008 | US4 bước 4: 3 lần, lần nào bị 429 thì chạy lại ngày khác |
| G4. SC-001 | US1 bước 7 |
| G5. Tổng duyệt | US3 + US6 bước 5 + SC-009, ngày riêng |
| Ngày demo | chỉ chạy phiên demo |

Trước mỗi giai đoạn, xem hạn mức còn lại của từng nhà cung cấp trong chuỗi. Không dùng nhiều tài khoản free để né giới hạn (research R14).

## US1: Bấm "Bắt đầu show", host tự nói liên tục (P1)

1. Trang điều khiển → **Bắt đầu show**.
2. **Kỳ vọng:** trong ≤ 5 s host nói câu chào mở màn (xưng "em", gọi "anh chị"). Phụ đề và tiếng đi cùng nhau, nhãn **AI** luôn hiện.
3. Để chạy 5 phút không chạm vào gì. Khu Show hiện phân đoạn đang nói và phân đoạn kế tiếp. Hai phân đoạn liền nhau không trùng cả
   sản phẩm lẫn chủ đề; có phân đoạn của cả sản phẩm chính và sản phẩm phụ.
4. (LLM thật) Nghe các phân đoạn "giá": giá từng phân loại đúng như file. Sản phẩm không có giá thì không có phân đoạn "giá" (US1 #4).
5. Bấm **Bắt đầu show** lần nữa khi đang chạy → không mở phiên thứ hai (`already_running: true`).
6. Khi chưa có show: đóng tab host rồi bấm **Bắt đầu show** → lỗi "Màn hình host chưa sẵn sàng". Khi show đang chạy mà host ngắt: câu bị
   bỏ với lỗi `render`, show vẫn `running`, bấm **Bắt đầu show** trả `already_running: true` (ADR-033).
7. **SC-001 [Đo lại]:** lặp 10 lần **Bắt đầu show** → **Kết thúc**. Đọc `segment_requested` → `avatar_first_frame` của câu đầu trong log:
   ≥ 9/10 lần ≤ 5 s.

## US2: Tạm dừng, tiếp tục, bỏ qua, kết thúc (P2), quy trình kiểm SC-007

1. Đang giữa phân đoạn, bấm **Tạm dừng** → host nói hết câu đang nói rồi im. Nhân vật và nhãn AI vẫn hiện. Lặp ≥ 10 lần; sau
   `control_applied` (pause) không có `sentence_start` mới.
2. Bấm **Tiếp tục** → câu kế tiếp của phân đoạn đang dở phát trong ≤ 3 s (câu đã tạo tiếng trước lúc dừng được tạo tiếng lại, research R7).
   Lặp ≥ 10 lần.
3. Bấm **Bỏ qua** khi đang nói → tiếng và phụ đề dừng trong ≤ 1 s, phân đoạn ghi `skipped`, host sang phân đoạn kế. Lặp ≥ 10 lần;
   mọi `control_applied` (skip) có `latency_ms` ≤ 1000.
4. Bấm **Kết thúc** → host nói lời chào kết (≤ 2 câu) rồi dừng, trạng thái "đã kết thúc". Có file `show_summary_<show_id>.json`.
5. Bắt đầu lại, bấm **Kết thúc**, rồi bấm **Bỏ qua** trong lúc chào kết → dừng ngay.

## US3: Phiên 30 phút (P2), tổng duyệt SC-002 đến SC-006, SC-009, SC-010

> Cần LLM thật (engine 008). Trước khi chạy, xem hạn mức thật của từng nhà cung cấp trong chuỗi (research R14 `TODO:`). Một phiên 30 phút tốn khoảng
> 60–120 lần gọi LLM; không chạy chung ngày với nhiều lần bộ tự kiểm tra nếu RPD thấp.

1. **Bắt đầu show**, để chạy 30 phút. Trong lúc chạy, giả lập lỗi ở các thời điểm khác nhau (SC-006):
   ```bash
   curl -X POST http://127.0.0.1:8000/api/debug/fault -H "Content-Type: application/json" \
        -d '{"step": "llm", "mode": "error", "count": 1}'     # ≥ 3 lần; thử cả "mode": "timeout"
   curl -X POST http://127.0.0.1:8000/api/debug/fault -H "Content-Type: application/json" \
        -d '{"step": "tts", "mode": "error", "count": 1}'     # ≥ 3 lần
   ```
   **Kỳ vọng:** lỗi `llm` làm mất một phân đoạn, lỗi `tts` làm mất một câu. Phiên không dừng, trang điều khiển hiện lỗi.
2. Chế độ dự phòng: gửi `{"step": "llm", "mode": "error", "count": 3}` → sau 3 phân đoạn lỗi, dải "Đang ở chế độ dự phòng" hiện, host đọc
   nguyên văn câu của bài giới thiệu và mô tả. Khi hết lỗi, phân đoạn kế tiếp tự quay về chế độ bình thường.
3. **Bấm Kết thúc.** Mở `data/sessions/<id>/show_summary_<show_id>.json`:
   - **SC-002 [Đo lại]:** `gaps.counted.p95_s` ≤ 1,5 và `gaps.counted.max_s` ≤ 5 (`counted` chỉ gồm `script`, `segment_boundary`,
     `error`; data-model §9).
   - **SC-003:** mọi câu `status = spoken` trong `script_sentences.jsonl` cho qua lại `OutputGuard` đều đạt (0 câu vi phạm).
     Kiểm bằng `uv run python -m ai_live.qa_eval script --session data/sessions/<id>` (tasks T055, T058, T059): lệnh chấm lại mọi
     câu `spoken` bằng `script_grader`, không gọi LLM, mã thoát 2 khi có vi phạm. Vẫn cần file nội dung (`--content` hoặc
     `PRODUCT_DATA_PATH`) để guard so giá và khuyến mãi.
   - **SC-004:** `segments.primary_share` ≥ 0,5; mọi cửa sổ trong `secondary_coverage` có `missing_products` rỗng.
   - **SC-005:** `duplicates.spoken_rate` ≤ 0,05 (không tính câu dự phòng) và `duplicates.identical_segments` = 0.
   - **SC-006:** `gaps.by_kind.fault.max_s` ≤ 8; `errors.jsonl` có đủ các lỗi đã giả lập, kèm bước lỗi.
4. **SC-009:** chọn ngẫu nhiên 10 `segment_id` trong `segments.jsonl` (bỏ `opening`, `closing`, `fallback`). Người vận hành nghe lại
   theo log hoặc đọc chữ trong `script_sentences.jsonl` và chấm "tự nhiên / không". Đạt khi ≥ 8/10.
   `TODO:` không có bản ghi tiếng (Điều I), nên chấm "nghe" chỉ làm được lúc phiên đang chạy. Cần chọn 10 phân đoạn ngay khi nghe hay
   chấm theo chữ sau phiên?
5. **SC-010:** chụp ≥ 10 ảnh màn hình host ở thời điểm ngẫu nhiên, kể cả lúc tạm dừng và lúc dự phòng → 100% có nhãn AI.

## US4: Bộ tự kiểm tra kịch bản (P2), quy trình kiểm SC-008

```bash
REPLY_ENGINE=fake uv run python -m ai_live.qa_eval script --content data/products/demo.docx   # kiểm luồng, không tốn hạn mức
uv run python -m ai_live.qa_eval script --content data/products/demo.docx                     # LLM thật (engine 008), khoảng 30 lần gọi
```
Tham số thêm: `--per-combo N` (số phân đoạn mỗi tổ hợp, mặc định 1), `--runs-dir DIR` (mặc định `data/eval/script_runs`).

1. **Kỳ vọng:** báo cáo có một phân đoạn cho mỗi tổ hợp sản phẩm × chủ đề có dữ liệu, cùng `opening` và `closing`. Lưu ở
   `data/eval/script_runs/<timestamp>.json`, kèm bản tóm tắt tiếng Việt `<timestamp>.md`.
2. Mã thoát:
   - `0`: không có vi phạm, mọi phân đoạn đều được chấm.
   - `1`: lỗi cấu hình hoặc nội dung (file nội dung hỏng, guard thiếu cụm từ, `--per-combo` < 1...).
   - `2`: có ít nhất một vi phạm; báo cáo liệt kê câu và lý do.
   - `3`: không có vi phạm nhưng có phân đoạn chưa chấm được vì lỗi dịch vụ (429, hết thời gian chờ). Lần chạy này **không tính**
     cho SC-008, chạy lại sau.
3. Chạy lần hai → báo cáo có phần so sánh số vi phạm theo loại với lần trước.
4. **SC-008:** 3 lần liên tiếp với LLM thật (engine 008) đều mã thoát 0. Nếu RPD thấp, chạy 3 lần ở 3 ngày khác nhau, không chạy cùng ngày tổng duyệt
   (research R14).
5. Lần đầu: người dùng xem danh sách "sai xưng hô" và `data/rules/platform_phrases.txt` trong báo cáo, rồi xác nhận (research R9, R15 `TODO:`).

## US5: Chọn phân đoạn kế tiếp (P3)

1. Đang chạy, ở bộ chọn "phân đoạn kế tiếp" chọn một sản phẩm phụ → danh sách chủ đề chỉ có các chủ đề có dữ liệu cho sản phẩm đó.
2. Chọn chủ đề "khuyến mãi" → phân đoạn đang nói được nói hết; phân đoạn ngay sau đó là sản phẩm phụ + khuyến mãi (khu Show hiện
   `origin: operator`). Sau đó xoay vòng tiếp như cũ.
3. Gọi API với tổ hợp không có dữ liệu → `422 topic_unavailable`:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/show/next -H "Content-Type: application/json" \
        -d '{"product_id": "<id sản phẩm không có khuyến mãi>", "topic": "promotion"}'
   ```

## US6: Comment mock chen vào kịch bản (P3), quy trình kiểm SC-011

1. Đang giữa phân đoạn, gửi comment "Lan: giá bao nhiêu?" từ ô comment mock → host nói hết câu đang nói, trả lời "bạn Lan" như 001,
   rồi nói câu kế của phân đoạn bị ngắt.
2. Gửi "có link không http://x.y" → bị loại kèm lý do, kịch bản không bị ngắt.
3. Gửi comment lúc show đang tạm dừng → comment được trả lời theo luật tạm dừng của 001 (không trả lời đến khi Tiếp tục).
4. Gửi comment trong lúc chào kết → comment ghi `dropped`, lý do "phiên đã kết thúc".
5. **SC-011 [Đo lại]:** gửi ≥ 10 comment hợp lệ ở các thời điểm khác nhau (giữa phân đoạn, giữa hai phân đoạn) với LLM thật (engine 008). Mở
   `GET /api/latency`: 100% `completed`, p95 `total` < 5 s. `script_sentences.jsonl` không có câu `interrupted` do comment.
   Nếu p95 ≥ 5 s: ghi vào "Kết quả kiểm chứng" và hỏi người dùng có cho cắt câu kịch bản ở dấu phẩy không (plan.md, độ trễ (c); sẽ sửa
   US6 #1).

## Hồi quy khi đổi prompt kịch bản, guard hoặc model (Điều III)

Mỗi lần sửa `brain/script_prompt.py`, `brain/guard.py`, `brain/sanitize.py`, `narrate()` của engine đang dùng (Gemini hoặc engine 008) hoặc đổi `LLM_MODEL`:

```bash
uv run python -m ai_live.qa_eval script --content data/products/demo.docx
```
Số vi phạm không được tăng so với lần gần nhất. Sửa `guard.py` hoặc `sanitize.py` thì chạy thêm bộ 10 câu hỏi của 001
(quickstart 001 "Hồi quy"), vì guard và bộ làm sạch dùng chung cho đường comment (research R9).

## Kết quả kiểm chứng

> Điền khi chạy thật ở `/sdd.implement`. Chưa có số đo nào; không điền số ước tính vào đây.

| Ngày | Mục | Kết quả | Ghi chú |
|------|-----|---------|---------|
| | SC-001 (Start → câu đầu, 10 lần) | | giọng, máy |
| | SC-002 (khoảng lặng p95 / max, 30 phút) | | giọng, máy, số câu |
| | SC-003 / SC-005 / SC-004 (phiên 30 phút) | | |
| | SC-006 (≥ 3 lỗi llm, ≥ 3 lỗi tts) | | khoảng lặng `fault` lớn nhất |
| 2026-11-02 | SC-007 (bỏ qua / tạm dừng / tiếp tục, ≥ 10 lần mỗi lệnh) | Đạt: 10/10 mỗi lệnh; `latency_ms` lớn nhất 0,0 (pause, resume, skip) | fake engine + `FakeTTS`, script giả lập host; 0,0 là dưới độ phân giải đồng hồ Windows (~15,6 ms). Chi tiết ở "US2 bước 1–5" |
| | SC-008 (bộ tự kiểm tra, 3 lần) | | số lần gọi, ngày chạy |
| | SC-009 (10 phân đoạn) | | người chấm |
| | SC-010 (ảnh chụp nhãn AI) | | |
| | SC-011 (≥ 10 comment chen) | | p95 `total` |

### US1 bước 1–6, `REPLY_ENGINE=fake` (T039, 2026-11-01)

Chạy trên laptop dev, `TTS_PROVIDER=fake`, `AVATAR_MODE=static`, `data/products/demo.docx` (1 sản phẩm chính, 2 phụ). Không có trình duyệt:
một script giả lập màn hình host qua `/ws/host` (gửi `ready`, ack `playback_started` khi nhận audio, `sentence_played` sau đúng độ dài audio).
Phiên `data/sessions/20261101-211620`, chạy 300 s. Số đo dưới là của engine và TTS giả, **không** dùng cho SC-001 hay SC-002.

| Bước | Kết quả | Ghi chú |
|------|---------|---------|
| Trước khi bấm, chưa có host | `409 host_unavailable`, "Màn hình host chưa sẵn sàng. Mở /host và bấm Bắt đầu." | đúng contracts/api.md §2 |
| `GET /api/show` trước lần bắt đầu đầu tiên | `200 null` | contract chưa ghi trường hợp `null` |
| 1–2. Bắt đầu show | `200 already_running: false`; câu đầu "Câu 1 Chào mở màn.", `segment_requested` → `avatar_first_frame` 0,016 s | phần nhìn (phụ đề, nhãn AI) chưa kiểm, cần trình duyệt |
| 3. Chạy 5 phút | 30 phân đoạn, 91 câu, cả 30 `done`; 0 cặp liền nhau trùng cả sản phẩm lẫn chủ đề; chính 15, mỗi phụ 7, mở màn 1; `primary_share` 0,517; gap p95 = max = 0,016 s; 0 câu bị chặn; chế độ `normal` | |
| 4. (gemini) | xem mục G1 dưới | chạy 2026-11-02 |
| 5. Bấm lần nữa khi đang chạy | `200 already_running: true`, cùng `show_id` | |
| 6. Ngắt host rồi bấm | khi show đang chạy: `200 already_running: true` (không phải `409`); `errors.jsonl` có 1 dòng `render` / `host_unavailable` | người dùng duyệt giữ cách này 2026-11-01 (ADR-033); bước 6 đã sửa theo |

### G1, Gemini thật (T038 + US1 bước 4, 2026-11-02)

> Lịch sử, giữ nguyên. Từ 2026-11-03 (ADR-035) G1 chạy lại bằng engine 008 (T075); kết quả ghi thành mục mới bên dưới.

Laptop dev, `LLM_MODEL=gemini-3.8-flash`, `LLM_THINKING_LEVEL=low` (mặc định), free tier, `data/products/demo.docx`. Tổng 5 request,
không gặp 429.

| Mục | Kết quả | Ghi chú |
|-----|---------|---------|
| `pytest -m live_llm tests/live/test_gemini_narrate.py` | 2 passed trong 117,24 s | `opening` và `price` (sản phẩm chính): mọi câu qua `clean_spoken` và guard, giá chỉ lấy từ file |
| Bước 4, `narrate --topic price`, kem chống nắng (chính) | 5 câu, 259.000đ (50 ml) và 439.000đ (100 ml) đúng file; khuyến mãi "mua chai 100 ml tặng túi đựng mỹ phẩm" đúng file | câu đầu ở 53,30 s |
| Bước 4, sữa rửa mặt | 5 câu, 159.000đ, 120 ml đúng file; không nhắc khuyến mãi (file không có) | câu đầu ở 58,39 s. Câu "xài được rất lâu" không có trong file (không phải giá, khuyến mãi hay công dụng y khoa; guard không chặn) |
| Bước 4, nước cân bằng | 5 câu, 189.000đ, 150 ml, "mua kèm kem chống nắng giảm 20.000đ" đúng file | câu đầu ở 6,77 s |
| Bước 4, sản phẩm không có giá | không kiểm được | mọi sản phẩm trong `demo.docx` có giá (mục Giá bắt buộc); xem TODO R4 |

- Độ trễ: 2/3 lần `narrate` đợi Gemini trên 50 s mới có câu đầu, rồi cả 5 câu về gần như cùng lúc (trong 0,6 s). Engine không retry
  khi gặp 429, nên thời gian chờ nằm ở phía API. CLI `narrate` không áp `SCRIPT_LLM_TIMEOUT_S`; trong show, các lần này sẽ hết hạn ở
  10 s và chuyển sang câu dự phòng. TODO: chậm do free tier xếp hàng hay do model/thinking? Cần đo lại ở G3 (SC-001, 10 lần) trước
  khi kết luận về mục tiêu câu đầu ≤ 5 s.

### US2 bước 1–5, `REPLY_ENGINE=fake` (T046, 2026-11-02)

Laptop dev, `TTS_PROVIDER=fake`, `AVATAR_MODE=static`, nội dung theo `PRODUCT_DATA_PATH` của `.env`, server thật (uvicorn) ở cổng 8010. Không có trình duyệt:
script giả lập màn hình host qua `/ws/host` như T039 (ack `playback_started` khi có audio, `sentence_played` sau đúng độ dài audio, `stop`
thì bỏ câu đang phát). Mỗi lệnh bấm lúc host đang nói được 0,2 s. Phiên `data/sessions/20261102-170927`. Thời gian đo từ `t_mono` của
`control_command` tới `avatar_first_frame` trong log server, không đo phía client (phía client HTTP trả về sau khi câu mới đã gửi).

| Bước | Kết quả | Ghi chú |
|------|---------|---------|
| 1. Tạm dừng × 10 | 10/10: body `{"state": "paused", "show_state": "paused"}`; 0 `sentence_start` mới trong 2 s dừng | câu đang nói phát hết. Phần nhìn (nhân vật, nhãn AI khi dừng) chưa kiểm, cần trình duyệt |
| 2. Tiếp tục × 10 | 10/10 ≤ 3 s: tới câu kế 0,766–1,532 s | thời gian này là phần còn lại của câu đang phát lúc dừng (câu `FakeTTS` dài ~3,25 s, dừng 2 s). 7/10 lần tiếp tục cùng phân đoạn, 3/10 sang phân đoạn kế. `TODO:` chưa xác minh 3 lần này là do dừng ở câu cuối của phân đoạn |
| 3. Bỏ qua × 10 | 10/10: `stop` tới host trước khi HTTP trả về; câu đầu phân đoạn kế 0,000–0,016 s; cả 10 phân đoạn `skipped` trong `segments.jsonl`; body có `skipped_segment_id` | `control_applied` (skip) `latency_ms` = 0,0 cả 11 lần (10 lần này + bước 5) |
| 4. Kết thúc | body `{"state": "closing"}` → `ended` sau 4,12 s; chào kết 1 câu; bấm lại trả `ended` cùng `show_id`; 0 câu mới trong 3 s sau `ended`; có `show_summary_9b4bc0b1….json` (`ended_by: operator`) | `control_command` `show_end` ghi 3 lần (bước 4 hai lần, bước 5 một lần) |
| 5. Bắt đầu lại → Kết thúc → Bỏ qua lúc chào kết | `start` cho `show_id` mới; skip lúc `closing` → `stop` tới host ngay, lần đọc trạng thái đầu tiên đã là `ended`; phân đoạn chào kết `skipped`; có `show_summary_45f2f534….json` | |

- Khu Show trên trang điều khiển (nút **Kết thúc**, nhãn trạng thái tiếng Việt) chưa kiểm bằng trình duyệt.
