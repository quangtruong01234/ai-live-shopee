# Quickstart: kiểm chứng 008-llm-provider-chain

- **Không bước nào cần GPU.** Mọi bước chạy trên laptop dev với `AVATAR_MODE=static`, `TTS_PROVIDER=fake`.
- Bước đánh dấu **[mạng + hạn mức]** gọi nhà cung cấp thật qua freellmapi hoặc Groq: tốn hạn mức free tier. Hỏi người dùng trước khi chạy
  (dịch vụ miễn phí, nhưng hạn mức dùng chung với tổng duyệt G5 của 004). Bước đánh dấu **[mạng]** chỉ gọi `GET /models` (không tốn hạn
  mức chat). Bước còn lại chạy không cần mạng hay key.
- Chuỗi chỉ dùng cho một ngày demo (spec "Phạm vi dùng"): các bước kiểm sự chính xác (đúng model, đúng nền tảng, đúng cấu hình) quan trọng
  hơn chạy dài.
- Kết quả đo ghi vào mục "Kết quả kiểm chứng" ở cuối file này.
- **ADR-040 (2026-11-05):** chuỗi mặc định còn `sealion` (chờ 2,5 s) → `qwen`. Các bước dưới viết cho chuỗi 3 mục cũ: nơi ghi mục 2
  `gptoss` thì hiểu là `qwen`, và bỏ qua bước chỉ dành cho `gptoss`. Kết quả T055 ngày 2026-11-04 đo với chuỗi cũ.

## 0. Chuẩn bị

```bash
uv sync
uv run pytest                     # mặc định bỏ qua live_llm; chạy cả test chuỗi với nhà cung cấp giả
uv run ruff check . && uv run ruff format --check .
```

Cho các bước **[mạng]** và **[mạng + hạn mức]**:
1. Bật freellmapi (ADR-034, ngoài repo), kiểm dashboard `http://localhost:3001` có key cho SEA-LION (Cloudflare) và gpt-oss-120b (Groq).
2. Trên dashboard freellmapi, tắt các nền tảng chưa benchmark của hai model này (ví dụ gpt-oss-120b trên `cerebras`, `sambanova`,
   `openrouter`, `cloudflare`). Engine vẫn chặn nếu quên (FR-024), nhưng tắt trước thì ít lượt bị chuyển hơn.
3. `.env`: `REPLY_ENGINE=chain`, `FREELLMAPI_KEY=…`, `GROQ_API_KEY=…` (không commit `.env`).
4. Kiểm tên model (TODO ở research R2):
   ```bash
   curl -s http://127.0.0.1:3001/v1/models -H "Authorization: Bearer $FREELLMAPI_KEY" | jq '.data[] | {id, available, execution_status}'
   curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY" | jq '.data[].id'
   ```

## US1: Host nói bằng model đầu chuỗi (P1)

**Không mạng:** `tests/unit/test_chain_engine.py` và contract test `ReplyEngine` chạy `ChainReplyEngine` với nhà cung cấp giả: câu ra theo
từng câu, `TurnRecord` có label, model, provider; `auto`, `fusion`, key trống và mục loopback thiếu `platform` bị từ chối lúc khởi tạo;
`preflight()` trả đúng `problem` cho từng dạng response `/models` giả.

**Từ chối cấu hình sai (không mạng):**
1. `.env`: đổi model mục 2 thành `auto`, chạy `uv run uvicorn ai_live.app.main:app --port 8000`.
2. Mong đợi: app không khởi động, thông báo `LLM_CHAIN mục 2 (gptoss): không được dùng model "auto"…`; không in key (US1 #5).
3. Lặp lại với `GROQ_API_KEY=` trống: thông báo nêu `GROQ_API_KEY chưa có giá trị`.
4. Lặp lại với mục `sealion` bỏ `platform`: thông báo nêu mục 1 phải khai platform.

**[mạng] Từ chối khởi động khi kiểm qua mạng thất bại (US1 #6, SC-009):** mỗi lần chỉ đổi một chỗ, chạy app, ghi lại đầu ra.

| Lần | Đổi | Mong đợi (`problem`, mục) |
|-----|-----|---------------------------|
| a | `FREELLMAPI_KEY` thành key sai (vẫn có giá trị) | `auth`, mục 1 và 2 |
| b | `GROQ_API_KEY` thành key sai | `auth`, mục 3 |
| c | model mục 2 thành `gpt-oss-120b-x` | `model_missing`, mục 2 |
| d | trên dashboard freellmapi, tắt key duy nhất phục vụ SEA-LION | `model_unavailable` (`unavailable_reason=no_key`), mục 1 |
| e | tắt freellmapi | `unreachable`, mục 1 và 2 |
| f | cấu hình đúng | app khởi động; log có `llm_preflight ok=true` cho cả 3 mục |

Mỗi lần a–e: app dừng trước khi nhận request, thông báo tiếng Việt nêu số thứ tự và nhãn mục. Chạy kèm bước SC-008 (bước 4 của US3) trên đầu ra
lúc khởi động. Lần f: so `show_first_sentence_s` với một lần chạy trước khi có preflight (preflight chạy trước khi bấm "Bắt đầu show",
nên không cộng vào câu chào).

**[mạng + hạn mức] Show 5 phút với chuỗi một mục:**
1. `LLM_CHAIN` chỉ giữ mục `sealion`. Chạy app, mở `/control` và `/host`, nạp dữ liệu mẫu, bấm "Bắt đầu show".
2. Gửi 3 comment mock hợp lệ trong lúc show chạy.
3. Mong đợi:
   - câu chào mở màn phát trong ≤ 5 s (đọc `show_first_sentence_s` trong bản tổng hợp; US1 #1);
   - host trả lời comment rồi quay lại kịch bản (US1 #2);
   - log có `llm_attempt` + `llm_usage` với `label=sealion`, `provider` bắt đầu bằng `cloudflare/`, cho mọi phân đoạn; có `llm_turn` cho
     từng câu trả lời (US1 #3);
   - guard chặn giá lạ như với Gemini: đọc `guard_blocked` trong log nếu có (US1 #4; test tự động ở `tests/unit/test_guard.py` đã bao).
4. Live test: `uv run pytest -m live_llm tests/live/test_chain_engine.py` (thay test Gemini thật cho bước G1 của 004).

## US2: Tự chuyển model khi lỗi (P1)

**Không mạng:** `tests/unit/test_chain_state.py` (nghỉ, hết nghỉ với đồng hồ giả), `tests/unit/test_chain_engine.py` (mọi dòng của bảng
R3, kể cả `wrong_platform` khi header thiếu / là `cache` / khác nền tảng và không đọc dòng SSE nào; chuyển trước câu đầu, không chuyển sau
câu đầu, hủy không làm nghỉ, hết chuỗi theo R7), `tests/integration/test_show_director.py` (show vào chế độ dự phòng sau
`SCRIPT_FALLBACK_AFTER` lần hết chuỗi; SC-006).

**Bằng tay, dùng giả lập lỗi theo mục** (`APP_ENV=dev`), **[mạng + hạn mức]** với chuỗi thật. `tests/fixtures/fake_openai.py` không có
chế độ server riêng (quyết định ở `/sdd.tasks` 2026-11-03, Điều VII): phần không mạng của US2 do test tự động ở trên lo.

1. Bắt đầu show, đợi phân đoạn thứ 2.
2. Lỗi ngay ở mục 1 (US2 #1, SC-003):
   ```bash
   curl -X POST http://127.0.0.1:8000/api/debug/fault -H "Content-Type: application/json" \
     -d '{"step":"llm","mode":"rate_limited","count":1,"entry":"sealion"}'
   ```
   Mong đợi: phân đoạn kế do `gptoss` nói; log `llm_switch sealion → gptoss reason=rate_limited`, `llm_entry_rest seconds=60`.
3. Trong 60 s nghỉ, các phân đoạn kế không có `llm_attempt label=sealion outcome=failed`, chỉ có `outcome=skipped` (US2 #4, SC-004).
4. Sau 60 s, phân đoạn kế thử `sealion` trước (US2 #6).
5. Lặp lại với `mode` = `overloaded`, `timeout`, `empty`, `wrong_platform` (US2 #2, US2 #8, SC-002: ≥ 5 lần trong một show ≥ 10 phút).
   Với `wrong_platform`: log `llm_attempt reason=wrong_platform` và không có câu nào của `sealion` trong phân đoạn đó.
6. Lỗi giữa phân đoạn (US2 #3): `mode` = `interrupted`. Mong đợi: phân đoạn dừng sau câu đầu, không có câu của `gptoss` trong cùng
   `segment_id` (`script_sentences.jsonl`); phân đoạn kế do `gptoss` nói.
7. Hết chuỗi (US2 #5, SC-006): inject `rate_limited` cho cả ba mục, `count` = 3. Mong đợi: sau 3 phân đoạn lỗi show vào chế độ dự phòng
   (`mode_changed`), lượt hết chuỗi báo lỗi trong ≤ 1 s khi mọi mục đang nghỉ (`llm_chain_exhausted kind=rate_limited`).
8. Hủy (FR-013): inject `timeout` cho mục 1 rồi bấm "Bỏ qua" ngay. Mong đợi: không có `llm_entry_rest` cho mục 1.

**[mạng + hạn mức] Lỗi thật:**
9. Tắt freellmapi giữa show (FR-019): lượt kế có `llm_attempt reason=connection` cho `sealion` rồi `gptoss`, phân đoạn do `qwen` nói; trang
   điều khiển hiện hai mục nghỉ với lý do "lỗi kết nối". Bật lại freellmapi: sau 60 s chuỗi quay lại `sealion`.
10. Nền tảng thật không khớp (US2 #8, tùy chọn): trên dashboard freellmapi, tắt `groq` cho gpt-oss-120b và bật một nền tảng khác (ví dụ
    `cerebras`), inject `rate_limited` cho `sealion`. Mong đợi: lượt của `gptoss` bị từ chối `wrong_platform` (log ghi `routed_via`
    `cerebras/…`), phân đoạn do `qwen` nói. Bật lại `groq`, tắt nền tảng kia sau bước này.

## US3: Trang điều khiển và bản tổng hợp (P2)

Trong lúc chạy US2:
1. Khu "Model LLM" hiện "Đang nói bằng: `sealion` (…)" khi show chạy bằng mục 1 (US3 #1).
2. Sau bước 2 của US2, khu "Model LLM" hiện cảnh báo "Đang dùng model dự phòng" kèm lý do và giờ thử lại trong ≤ 2 s (US3 #2, SC-007). Đo
   bằng `ts` của `llm_switch` trong log so với lúc cảnh báo hiện (DevTools → WebSocket, `ts` của message `llm_chain`).
3. Kết thúc show: `show_summary_<show_id>.json` có `llm_chain` với model, số phân đoạn, câu trả lời, lỗi theo lý do theo mục; số lần chuyển
   theo lý do và số lần hết chuỗi (US3 #3). Không có request hay token.
4. SC-008: tìm key trong toàn bộ log của phiên và đầu ra lúc khởi động của bảng US1 a–f:
   ```bash
   grep -rF "$FREELLMAPI_KEY" data/sessions/ logs/ ; grep -rF "$GROQ_API_KEY" data/sessions/ logs/   # phải không ra dòng nào
   ```
   Log của app chỉ ra stdout (`core/logging.py`), nên mọi lần chạy app trong bảng US1 a–f, US2 và US3 phải chuyển stdout vào `logs/`
   (đã gitignore), ví dụ:
   ```bash
   mkdir -p logs
   uv run uvicorn ai_live.app.main:app --port 8000 > logs/008_quickstart.log 2>&1
   ```

## US4: Kiểm từng model (P3) **[mạng + hạn mức]**

```bash
uv run python -m ai_live.qa_eval run --entry sealion
uv run python -m ai_live.qa_eval run --entry gptoss
uv run python -m ai_live.qa_eval run --entry qwen
uv run python -m ai_live.qa_eval script --entry sealion   # tương tự cho gptoss, qwen
uv run python -m ai_live.qa_eval run                      # cả chuỗi
```

Mong đợi:
- mỗi lần chạy bắt đầu bằng `llm_preflight`; preflight lỗi → mã thoát lỗi cấu hình, không gửi câu hỏi nào;
- khi `--entry`, log chỉ có `llm_attempt` của mục đó; lượt lỗi ghi là lỗi dịch vụ, không tính điểm (US4 #1);
- báo cáo ghi `model_label`, `model`, `provider` cho từng câu hỏi / phân đoạn (US4 #2);
- phần so với lần trước hiện `engine` của hai lần (US4 #3);
- SC-001: mỗi mục định dùng lúc live đạt ≥ 8/10 câu hỏi và 0 vi phạm kịch bản.

## Kết quả kiểm chứng

<!-- Điền sau /sdd.implement: ngày, cấu hình, số đo, đạt / không đạt. -->

| Mục | Ngày | Kết quả | Ghi chú |
|-----|------|---------|---------|
| US1 câu chào ≤ 5 s | 2026-11-04 | Đạt | Show 5 phút chỉ `sealion` (phiên 20261104-162751): `show_first_sentence_s` 0,984 s; 14 phân đoạn, 3 comment do `sealion` trả lời (comment → khung hình đầu 1,23 / 2,30 / 1,36 s); mọi `provider` là `cloudflare/@cf/aisingapore/gemma-sea-lion-v4-27b-it`; `guard_blocked` 0. 10/10 câu chào bình thường ≤ 5 s (lớn nhất 1,64 s). Đo với `FakeTTS` + static, chưa có giọng 003. Live test: 9 passed. |
| SC-009 từ chối khởi động (a–e) | 2026-11-04, d 2026-11-05 | Đạt a–f | Mỗi lần app thoát mã 3 trước khi nhận request, thông báo tiếng Việt nêu số thứ tự và nhãn mục. a: `FREELLMAPI_KEY bị từ chối (401)` mục 1, 2; b: `GROQ_API_KEY` 401 mục 3; c: `không có model "gpt-oss-120b-x"` mục 2; e: **giả lập** bằng `base_url` `127.0.0.1:3999` (không tắt freellmapi thật) → `không kết nối được … dịch vụ gom key đã chạy chưa?` mục 1, 2; f: `llm_preflight ok=true` × 3. Từ chối cấu hình không mạng: `auto`, thiếu `platform`, key Groq trống (kiểm bằng `Settings(_env_file=None)` vì `env_ignore_empty=True` làm biến môi trường trống rơi về `.env`). d (2026-11-05, người dùng tắt key SEA-LION trên dashboard freellmapi, app chạy với `REPLY_ENGINE=chain`): app thoát mã 3, `llm_preflight` mục 1 `sealion` `ok=false problem=model_unavailable detail=unavailable_reason=no_key`, mục 2, 3 `ok=true`; thông báo `LLM_CHAIN mục 1 (sealion): model "gemma-sea-lion-v4-27b" chưa dùng được (unavailable_reason=no_key)`; log `logs/008_quickstart_sc009_d.log` 0 key. |
| SC-002 chuyển mục | 2026-11-04 | Đạt | Show 12,7 phút đủ chuỗi (phiên 20261104-163448): giả lập `rate_limited`, `overloaded`, `timeout`, `empty`, `wrong_platform` ở `sealion`; mỗi lần có `llm_switch` → `gptoss`, `llm_entry_rest seconds=60`, trong lúc nghỉ chỉ có `skipped`, hết nghỉ thử `sealion` trước. `interrupted`: phân đoạn chỉ nói câu đầu, phân đoạn kế do `gptoss` nói. Khoảng lặng ranh giới phân đoạn lớn nhất 3,578 s (< 5 s). Hai lần `gptoss` hết giờ chờ thật (2,016 s) thì `qwen` nói. |
| SC-003 thêm ≤ 1 s | 2026-11-04 | Đạt | 10/10 câu chào với `sealion` lỗi `rate_limited` giả lập ≤ 5 s: `gptoss` 0,69–1,86 s; 1 lần `gptoss` hết giờ thật → `qwen`, 3,047 s. Lỗi giả lập cộng 0,0 s vì không có request mạng; lỗi thật còn cộng thời gian một request bị từ chối (chưa đo). |
| SC-005 đúng nền tảng | 2026-11-04 | Đạt (3 show cộng ≈ 33 phút, không phải một show 30 phút) | 130 lượt `ok`: `sealion` → `cloudflare/…` 67, `gptoss` → `groq/…` 49, `qwen` → `api.groq.com` 10; 0 câu từ nền tảng chưa benchmark; 0 phân đoạn có hai nhãn. 1 lượt không có model / nhà cung cấp: lượt comment bị hủy (`llm_turn outcome=cancelled`), không mục nào trả lời. |
| SC-006 hết chuỗi | 2026-11-04 | Đạt | Giả lập `rate_limited` cả ba mục: 3 lần hết chuỗi liên tiếp rồi `mode_changed` sang dự phòng; lượt hết chuỗi khi mọi mục đang nghỉ báo lỗi sau ≈ 0 ms. Bản tổng hợp: `exhausted` 9, `fallback_spoken` 12. |
| SC-007 cảnh báo ≤ 2 s | 2026-11-04, 2026-11-05 | **Đạt** (người dùng chấp nhận 2026-11-05) | Dòng "nghỉ tới … (lý do)" của mục lỗi hiện 1–2 ms sau mỗi `llm_switch`. Cảnh báo "Đang dùng model dự phòng" (`using_backup=true`) chỉ hiện khi mục dự phòng đã nói: 0,758 / 0,906 / **2,592** / 0,568 / 0,002 / 0,894 / 0,001 / 0,772 s. Lần 2,592 s: `sealion` hết giờ, `gptoss` cũng hết giờ thật (2,0 s) rồi `qwen` nói. Trang vẽ lại mỗi 1 s nên có thể cộng tới 1 s. Người dùng chấp nhận lần 2,592 s (dòng nghỉ đã hiện ngay). Chuỗi ADR-040 chỉ còn một mục dự phòng nên không còn ca hai lần hết giờ. 2026-11-05 (US2 bước 9, lỗi thật): cảnh báo hiện 0,435 s và 0,001 s sau `llm_switch`; người dùng xem bằng trình duyệt thấy "Đang nói bằng: qwen", cảnh báo kèm lý do và giờ thử lại, dòng `sealion` "nghỉ tới 04:36:12 (bị từ chối (key/model))". |
| SC-008 không lộ key | 2026-11-04 | Đạt | Tìm giá trị đầy đủ và 12 ký tự cuối của `FREELLMAPI_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY` trong 85 file ở `logs/` và `data/sessions/`, cùng báo cáo trong `data/eval/runs/`, `data/eval/script_runs/`: 0 kết quả. |
| SC-001 sealion / gptoss / qwen | 2026-11-04, `qwen` 2026-11-05 | `sealion` **Đạt**; `gptoss` **Không đạt** (bỏ khỏi chuỗi, ADR-040); `qwen` **Đạt** | Chi tiết ở bảng US4 bên dưới. Chuỗi live theo ADR-040 (`sealion` → `qwen`) đạt SC-001 cho cả 2 mục. Cả chuỗi (`qa_eval run` không `--entry`): 10/10, cả 10 câu do `sealion` trả lời. |

**US4 theo mục (2026-11-04, `data/eval/demo_questions.json`, `demo.docx`):**

| Mục | Bộ câu hỏi | Kịch bản (21 phân đoạn) | Chấm lại câu đã nói trong show |
|-----|------------|-------------------------|--------------------------------|
| `sealion` | 10/10, mã 0 (`--pace 2`) | 0 vi phạm, mã 0 | Show US1: 0 vi phạm / 13 phân đoạn; show US2: 0 / 11 |
| `gptoss` | `--pace 2`: 5/5 câu chấm được đúng, 5 lỗi dịch vụ (4 timeout, 1 `wrong_platform`), mã 3. `--pace 15`: 6/8 câu chấm được đúng (q05 có ý cấm "chưa có thông tin", q10 thiếu "259.000đ"), 2 timeout, mã 3 | Nhịp 6 s: 2 vi phạm (`bad_pronoun` × 2), 12 lỗi dịch vụ. Nhịp 30 s: 4 vi phạm (`bad_pronoun` × 3 "bạn" / "các bạn", `platform_phrase` × 1 "giỏ hàng"), 4 lỗi dịch vụ | Show US2: 1 vi phạm / 18 phân đoạn (`bad_pronoun` "Bạn chỉ cần dùng 2 lần mỗi ngày…") |
| `qwen` | 9/10 (q10 thiếu "259.000đ"), mã 0 (`--pace 2`) | Nhịp 6 s: 0 vi phạm, 10 lỗi `rate_limited`. Nhịp 30 s: 0 vi phạm, 1 timeout (sữa rửa mặt · Câu hỏi thường gặp, chưa chấm ở cả hai lần). 2026-11-05 nhịp 30 s: **21/21 phân đoạn, 0 vi phạm, 0 lỗi** (`data/eval/script_runs/20261105-041727`, `logs/008_quickstart_adr040_script_qwen_pace30.log`) | Show US2: 1 vi phạm / 8 phân đoạn (`bad_pronoun` "…cho các bạn da thường và da dầu.") |

- Mỗi lần chạy kiểm `GET /models` trước: với `FREELLMAPI_KEY` sai, `qa_eval run --entry sealion` thoát mã 1 (`FREELLMAPI_KEY bị từ chối
  (401)`), không gửi câu hỏi nào. `qa_eval` không bật log INFO nên đầu ra không có dòng `llm_preflight` / `llm_attempt`; nhãn mục đọc
  từ báo cáo (`model_label`, `model`, `provider` từng câu), mọi câu chấm được của lần `--entry X` đều là `X` (US4 #1, #2).
- Phần so với lần trước hiện `engine` của hai lần, ví dụ "So với 20261104-171053 (engine chain:sealion)" (US4 #3).
- `qa_eval script` không có `--pace` (giãn cố định 6 s); với hạn mức free của Groq, nhịp này làm gần nửa số phân đoạn lỗi dịch vụ. Lần
  nhịp 30 s chạy bằng script tạm gọi `run_script_check(pace_s=30)`, không sửa code.

**Độ trễ câu đầu LLM đo được** (lượt `ok` của `llm_attempt`, 3 show + câu chào, `FakeTTS` + static):

| Mục | n | p50 | p95 | Lớn nhất |
|-----|---|-----|-----|----------|
| `sealion` (phân đoạn) | 64 | 0,86 s | 1,30 s | 2,11 s |
| `sealion` (trả lời comment) | 3 | 1,23 s | — | 1,36 s |
| `gptoss` | 49 | 0,98 s | 1,72 s | 1,97 s |
| `qwen` | 10 | 0,73 s | 1,26 s | — |

Khoảng lặng giữa câu (bản tổng hợp show US2, có giả lập lỗi): `script` p95 0,016 s; `segment_boundary` p95 0,728 s, lớn nhất 3,578 s.
Show US1: lớn nhất 1,0 s.

**Cổng Q18 (mục 1 hết giờ chờ ngay câu chào):** 5 câu chào với `sealion` giả lập `timeout` (`logs/008_quickstart_openings_timeout.log`):
`show_first_sentence_s` 4,25 / 4,39 / 4,44 / 4,61 / **7,08** s. Lần 7,08 s: `sealion` 3,5 s + `gptoss` hết giờ thật 2,016 s + `qwen`
1,547 s. 1/5 lần > 5 s, quá ngưỡng 1/10 của cổng; với giọng 003 (≈ +1,0 s chunk đầu theo 004) cả 5 lần có thể vượt 5 s. Người dùng
quyết định hạ `first_sentence_timeout_s` của `sealion` (lúc đó 3,5 s; p95 đo được 1,30 s, lớn nhất 2,11 s): ADR-040 đặt 2,5 s, đo lại bên dưới.

**Đo lại sau ADR-040 (2026-11-05, chuỗi `sealion` 2,5 s → `qwen`):** người dùng chọn hạ giờ chờ và nhờ chọn cách xử lý `gptoss`; ADR-040 bỏ
`gptoss`. 10 câu chào với `sealion` giả lập `timeout` (`logs/008_quickstart_adr040_openings_timeout.log`, phiên `20261105-040341`):
`show_first_sentence_s` 2,906 / 2,953 / 3,313 / 2,907 / 2,906 / 2,953 / 2,906 / 3,015 / 2,906 / 2,922 s; 10/10 `llm_switch` từ `sealion`
sang `qwen`. **0/10 lần > 5 s, cổng Q18 đạt**; lớn nhất 3,31 s, còn ≈ 1,7 s cho chunk TTS đầu của giọng 003. Lúc khởi động
`llm_preflight ok=true` cho 2 mục. Log 0 key.

**US2 bước 9 + US3 (2026-11-05, chuỗi ADR-040, phiên `20261105-043415`, show 8 phút, `logs/008_quickstart_us2_step9.log`):** người dùng
tắt nền tảng Cloudflare trên dashboard freellmapi giữa show thay vì tắt hẳn freellmapi, nên lỗi là 503 (`reason=rejected`) chứ không phải
`connection`. 04:35:12 `llm_attempt sealion outcome=failed status=503` → `llm_entry_rest seconds=60` → `llm_switch sealion → qwen`, phân
đoạn kế do `qwen` nói; trong lúc nghỉ chỉ có `skipped`. 04:36:16 hết nghỉ, Cloudflare còn tắt → lỗi lại, nghỉ thêm 60 s. Người dùng bật
lại; 04:37:27 `sealion outcome=ok` qua `cloudflare/…`, WebSocket `using_backup=false`. Bản tổng hợp `llm_chain`: `sealion` 17 phân đoạn,
lỗi `rejected` 2; `qwen` 9 phân đoạn; `switches` `rejected` 2; `exhausted` 0; không có request hay token (US3 #3). Log 0 dòng lỗi.
SC-008 quét lại 108 file: 0 key. Nhánh lỗi kết nối (`connection`) khi tắt hẳn freellmapi đã có test tự động và bước e của SC-009, chưa
chạy giữa show thật.

**Bỏ qua:** US2 bước 10 (tùy chọn) đổi nền tảng của `gptoss`; ADR-040 bỏ `gptoss` khỏi chuỗi nên không còn mục nào để thử.
