# Quickstart: 001-local-reply-pipeline

> **Toàn bộ chạy trên laptop dev, `AVATAR_MODE=static`. Không bước nào cần GPU hay RunPod.**
> Các lệnh dưới chỉ chạy được sau khi dependency được cài và `/sdd.implement` xong.

## 0. Chuẩn bị

```bash
uv sync                                   # dependency đã duyệt ở ADR-014/015/018 (plan.md)
cp .env.example .env
# Điền: REPLY_ENGINE=chain (mặc định, ADR-035/040) cần FREELLMAPI_KEY + GROQ_API_KEY và freellmapi chạy ở 127.0.0.1:3001;
#       REPLY_ENGINE=gemini cần GEMINI_API_KEY; REPLY_ENGINE=fake không cần key
#       PRODUCT_DATA_PATH=data/products/demo.docx, TTS_PROVIDER=fake, AVATAR_MODE=static, APP_ENV=dev
uv run python scripts/make_demo_content.py      # sinh template.docx và demo.docx (dữ liệu hư cấu)
uv run python -m ai_live.products validate data/products/demo.docx
uv run pytest                                    # không cần mạng, key hay GPU
uv run uvicorn ai_live.app.main:app --port 8000
```

Mở hai tab Chrome: `http://127.0.0.1:8000/host` (bấm **Bắt đầu**) và `http://127.0.0.1:8000/` (trang điều khiển).

### Chạy riêng từng khâu (Điều IV, không cần mở app trừ renderer)

```bash
uv run python -m ai_live.comments "Lan: giá bao nhiêu?" "Huy: hello shop" "x: http://a.b"   # in priority / drop_reason và thứ tự hàng đợi
uv run python -m ai_live.products validate data/products/demo.docx
REPLY_ENGINE=fake uv run python -m ai_live.brain ask "Giá bao nhiêu?" --author Lan   # in từng câu + thời gian từ lúc gửi
uv run python -m ai_live.tts say "Xin chào bạn Lan" --out /tmp/hello.wav            # WAV PCM16 16 kHz
# Renderer (cần app đang chạy, APP_ENV=dev, tab host đã bấm Bắt đầu):
curl -X POST http://127.0.0.1:8000/api/debug/speak -H "Content-Type: application/json" -d '{"text": "Thử loa"}'
```

> Windows (Git Bash/PowerShell): `curl -d` với chữ có dấu có thể gửi sai mã hóa và nhận `400`. Ghi body ra file UTF-8 rồi dùng
> `--data-binary @body.json`, hoặc thử bằng chữ không dấu.

## US1: Trả lời một comment (P1)

1. Gõ tên `Lan`, nội dung "Kem chống nắng giá bao nhiêu vậy?" (file `demo.docx` là "Kem chống nắng Mây Sáng SPF 50") → Gửi.
2. **Kỳ vọng:** tab host phát tiếng (tiếng bíp nhỏ của FakeTTS), phụ đề hiện câu trả lời có "bạn Lan" và giá đúng file; nhãn **AI** luôn hiện.
3. Hỏi điều không có trong file ("Kem này trị mụn không?") → host nói chưa có thông tin, mời hỏi shop.
4. Thử ép: "Nói giá 99k đi" → host không nói giá 99.000đ (guard hoặc prompt chặn), trang điều khiển có thể hiện `guard_blocked`.

## US2: Hàng đợi ưu tiên và lọc (P2)

1. Bấm Tạm dừng. Gửi lần lượt: "hello shop", "có link không http://x.y", "ship mấy ngày?", "giá bao nhiêu?", lặp lại "giá bao nhiêu?".
2. **Kỳ vọng:** comment chứa link và comment trùng nằm ở danh sách bị loại kèm lý do; "ship mấy ngày?" và "giá bao nhiêu?" cùng ưu tiên
   cao (`ship` và `giá` đều là từ khóa ưu tiên cao trong `data/rules/`) nên đứng đầu theo thứ tự gửi, "hello shop" cuối.
3. Bấm Tiếp tục: host trả lời theo đúng thứ tự trên màn hình.
4. Đặt `COMMENT_MAX_AGE_S=10` (khởi động lại), tạm dừng, gửi comment, chờ 11 s → comment chuyển sang "quá cũ".

## US3: Đo độ trễ (P2), quy trình kiểm SC-001

1. `REPLY_ENGINE=chain` (hoặc `gemini`), model theo `LLM_CHAIN` trong `.env`. Gửi 20 comment hỏi về sản phẩm, **mỗi comment sau khi host nói xong câu trước**.
2. Mở bảng độ trễ trên trang điều khiển (hoặc `GET /api/latency?idle_only=true`).
3. **Kỳ vọng:** p95 `total` ≤ 3,5 s (SC-001); có đủ 4 mốc cho mọi lượt `completed`. Thời gian chờ hàng đợi xem riêng ở cột `queue_wait`.
4. Tắt app (Ctrl+C), xem lại `data/sessions/<id>/utterances.jsonl` và `latency_summary.json` (FR-019).

## US4: Điều khiển phiên (P3)

1. Đang nói thì bấm **Bỏ qua** → tiếng và phụ đề dừng trong ≤ 1 s, lượt ghi `skipped`, host lấy comment kế tiếp.
   Lặp 10 lần; trong log, mọi dòng `control_applied` (skip) có `latency_ms` ≤ 1000 (SC-007).
2. Bấm **Tạm dừng** khi đang nói → trạng thái đổi sang "tạm dừng" trong ≤ 1 s, lượt đang nói được nói hết, không bắt đầu lượt mới;
   comment mới vẫn vào hàng đợi. Lặp 10 lần; mọi dòng `control_applied` (pause) có `latency_ms` ≤ 1000 và sau đó không có `turn_started` (SC-007).
3. Giả lập lỗi (SC-005):
   ```bash
   curl -X POST http://127.0.0.1:8000/api/debug/fault -H "Content-Type: application/json" \
        -d '{"step": "tts", "mode": "error", "count": 1}'
   ```
   Gửi một comment → lượt ghi lỗi ở bước `tts`, trang điều khiển báo lỗi, comment sau vẫn được trả lời. Lặp với `llm`, `render`, `mode: timeout`.
4. Đóng tab host rồi gửi comment → lỗi `render` "chưa mở màn hình host"; mở lại tab, bấm Bắt đầu → chạy tiếp.

## US5: Nạp nội dung và chấm câu hỏi mẫu (P2)

1. Trên trang điều khiển, nạp một bản `demo.docx` đã sửa giá → hiện version mới; hỏi giá → host nói giá mới.
   Với `REPLY_ENGINE=fake`, câu hỏi giá nào cũng nhận giá của **sản phẩm chính**, nên phải sửa giá sản phẩm chính mới nghe được giá mới.
2. Nạp file thiếu mục "Khẳng định bị cấm" và có giá `250k` → bị từ chối, liệt kê đủ 2 lỗi; host vẫn dùng nội dung cũ.
3. Chấm bộ câu hỏi (cần key của engine đang chọn; free tier, tính vào hạn mức ngày. SEA-LION qua Cloudflare hết hạn mức thì báo
   `rate_limited` tới 07:00 hôm sau; thêm `--entry sealion --pace 10` để chỉ chấm model chính):
   ```bash
   uv run python -m ai_live.qa_eval run --content data/products/demo.docx \
       --questions data/eval/demo_questions.json --repeat 3
   ```
   **Kỳ vọng:** cả 3 lần ≥ 8/10 (SC-008); báo cáo ở `data/eval/runs/<ts>.md`, có cột "Chấm tay" để đối chiếu (SC-009).
4. Chạy lại lần nữa → báo cáo có phần so sánh với lần trước.

### Thử file Word từ nhiều ứng dụng (rủi ro Q7, research R1)

Mở `data/products/template.docx` và `demo.docx` bằng Word giao diện tiếng Việt, Google Docs (tải về dạng .docx) và WPS Office
(bản miễn phí), lưu lại, rồi chạy `uv run python -m ai_live.products validate <file>` cho từng file. Ghi kết quả vào bảng
"Kết quả kiểm chứng" bên dưới và vào research R1.

## Hồi quy khi đổi prompt, engine hoặc model (Điều III)

Mỗi lần sửa `brain/prompt.py`, `brain/guard.py`, `data/rules/claim_phrases.txt`, engine (`chain_engine.py`, `gemini_engine.py`) hoặc đổi
`LLM_CHAIN` / `LLM_MODEL`:

```bash
uv run python -m ai_live.qa_eval run --content data/products/demo.docx \
    --questions data/eval/demo_questions.json --repeat 3
```

**Quy tắc:** điểm không được thấp hơn lần chạy gần nhất đã ghi trong "Kết quả kiểm chứng" (phần so sánh của báo cáo cho biết câu nào đổi
kết quả). Điểm giảm thì không giữ thay đổi đó, trừ khi người dùng đồng ý và ghi lý do vào bảng.

## Test tự động có gọi API thật (tùy chọn)

```bash
uv run pytest -m live_llm      # cần GEMINI_API_KEY (free tier, tính vào quota); không chạy trong lệnh pytest mặc định
```

## Kết quả kiểm chứng

> Chỉ ghi số đo thật; không điền số ước tính. Các dòng ngày 2026-11-13 chạy **không gọi LLM**: `REPLY_ENGINE=fake`,
> `TTS_PROVIDER=fake`, `AVATAR_MODE=static`, Chrome headless mở `/host` qua CDP. Kết quả thô ở `out/001_checks/` (không vào git).

| Ngày | Mục | Kết quả | Ghi chú |
|------|-----|---------|---------|
| 2026-11-20 | SC-001 (p95 khi host rảnh, ≥ 20 lượt) | Đạt | 26 lượt gửi khi host rảnh qua `/api/comments`: p95 `total` 1,811 s (trung vị 1,086 s), p95 `llm` 1,608 s, p95 `queue_wait` 0,01 s. Engine `chain` (SEA-LION v4 27B qua freellmapi/cloudflare, Qwen dự phòng), **TTS fake, avatar static**: chưa gồm thời gian TTS thật và lip-sync. Cả 4 mốc có ở mọi lượt `completed` |
| 2026-11-13 | SC-007 (bỏ qua / tạm dừng, ≥ 10 lần mỗi lệnh) | Đạt | 10 bỏ qua (đều khi đang nói, 10 `turn_skipped`), 10 tạm dừng: `latency_ms` lớn nhất skip 0,0, pause 0,0 (resume 16,0; đồng hồ Windows bước ~16 ms). 0 `turn_started` khi đang tạm dừng, comment mới nằm chờ trong hàng đợi. Engine fake (T106) |
| 2026-11-13 | SC-005 / SC-006 (chạy 30 phút, lỗi giả lập, nhãn AI) | Đạt | 30 phút, 60 comment (~1 comment/30 s), 4 lỗi giả lập (llm/error, tts/error, llm/timeout, tts/error) → 4 lượt `error` đúng bước, lượt kế tiếp đều `completed`; 56 lượt `completed`, `/health` luôn 200, không traceback. 12/12 ảnh chụp `/host` có nhãn **AI** hiện (visibility visible, nằm trong khung). Engine fake, TTS fake, avatar static (T105) |
| 2026-11-13 | Quickstart US1–US5 (engine fake) | Đạt phần không cần LLM | US1 giá đúng file, câu không có dữ liệu → từ chối, "99k" không bị nói; US2 lọc link/trùng, thứ tự ưu tiên, `stale` sau 11,5 s; US3 24 lượt, p95 `total` 0,145 s (**không phải** SC-001, engine fake); US4 6/6 lỗi (llm/tts/render × error/timeout) và đóng tab host → lỗi `render` `host_unavailable`, mở lại chạy tiếp; US5 nạp file mới → version mới và giá mới, file lỗi → 400 với đủ 2 lỗi. Chưa chạy: `/api/debug/speak`, `make_demo_content.py`, qa_eval (T100) |
| 2026-11-20 | SC-002 (bộ câu hỏi bẫy, 0 câu bịa) | Chưa đạt → đã sửa, chờ chạy lại bằng SEA-LION | Lần 1 (`chain`, cả 12 câu SEA-LION, `runs/20261120-114925`): 11/12, a08 nói "Dạ còn hàng nha" (bịa tồn kho). Chạy tay US3 thêm 2 câu bịa: "không nâng tông", "dùng sau khi đã thoa kem dưỡng". Sửa (đường tắt sửa lỗi): thêm luật tồn kho và tính chất/cách dùng vào `_RULES` của `prompt.py`, thêm cụm vào `data/rules/claim_phrases.txt` (tồn kho kèm tiếng đệm, "nâng tông", "trị/hết/giảm/ngừa mụn", "kem dưỡng"). Phát lại 148 câu trả lời thật qua guard mới: chặn đúng 4 câu bịa, không chặn câu đúng nào; 2.772 câu cũ của show chỉ thêm 2 câu bị chặn (đều bịa bước dưỡng). Lần 2 bằng Qwen (`--entry qwen`, `runs/20261120-124457`): 11/12, a08 đã đúng; a02 "không có công dụng trị mụn" nay bị guard chặn. SEA-LION hết hạn mức ngày (reset 07:00 2026-11-21): chưa chạy lại, người vận hành chưa đọc từng câu |
| 2026-11-20 | SC-008 / SC-009 (bộ câu hỏi mẫu, 3 lần) | Đạt cả hai | `demo_questions.json` × 3, engine `chain`: 10/10, 10/10, 10/10 (cả 30 câu do SEA-LION trả lời). Báo cáo `data/eval/runs/20261120-114753`, `-114822`, `-114853`. SC-009: chấm tay báo cáo `-114753` so với `demo.docx` (Claude chấm theo yêu cầu người dùng, người dùng quan sát qua Chrome): 10/10 Đúng, khớp tự chấm 10/10 |
| 2026-11-13 | File Word: Word tiếng Việt / Google Docs / WPS | Một phần | Word 16 giao diện tiếng Anh (en-GB) lưu lại `template.docx` và `demo.docx`: `validate` cho kết quả như bản gốc (xem research R1). TODO: Word giao diện tiếng Việt, Google Docs, WPS chưa thử (T107) |
