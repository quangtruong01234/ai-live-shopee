# Nghiên cứu (Phase 0): 004-show-director

> Mỗi mục theo dạng **Quyết định / Lý do / Phương án đã cân nhắc**. Mọi lựa chọn dùng stack đã chốt (ADR-003, 005, 014–018, 020);
> **không thêm dependency mới**. Chỗ chưa chắc ghi `TODO:`.

## R1. Cấu trúc điều phối: mở rộng `ShowDirector` của 001, tách phần kịch bản ra hai module

- **Quyết định:** `ShowDirector` (`director/show_director.py`) vẫn là **bộ điều phối phiên duy nhất**: giữ tạm dừng, tiếp tục, bỏ
  qua, giả lập lỗi và đường trả lời comment của 001. Thêm:
  - `director/segment_planner.py`: `SegmentPlanner`, **logic thuần** (không I/O, không asyncio): chủ đề nào có dữ liệu (FR-004), xoay
    vòng (FR-005), lựa chọn của người vận hành (FR-018).
  - `director/script_runner.py`: `ScriptRunner`, chạy show: sinh chữ phân đoạn (đi trước một phân đoạn), tạo tiếng (đi trước tối đa 2
    câu), phát từng câu, chế độ dự phòng (FR-021), đo khoảng lặng (FR-022).
  - `director/show_stats.py`: `ShowStats`, thống kê khoảng lặng, số phân đoạn theo sản phẩm/chủ đề, tỷ lệ câu trùng (FR-023).
  `ShowDirector` tạo `ScriptRunner` khi bấm "Bắt đầu" và hủy khi phiên kết thúc.
- **Lý do:** Tên `ShowDirector` đã được dùng ở 001, ADR-026, ROADMAP và ARCHITECTURE cho cùng một vai trò. Tách class mới cùng cấp
  (ví dụ `ScriptDirector`) thì hai bên tranh nhau renderer, lệnh tạm dừng/bỏ qua phải đi hai nơi. Tách planner ra để test xoay vòng
  không cần asyncio (Điều V). File `show_director.py` đã 513 dòng, nên không nhét thêm logic kịch bản vào đó.
- **Phương án đã cân nhắc:** (a) dồn hết vào `ShowDirector`: file quá lớn, khó test riêng. (b) Class `ScriptDirector` độc lập chạy song
  song: cần thêm lớp phân xử renderer, lặp lại logic tạm dừng/bỏ qua. (c) Viết thành Protocol mới: thừa, mới có một hiện thực (Điều VII).

## R2. Mỗi câu kịch bản là một `Utterance` riêng có `segment_id`

- **Quyết định:** Câu kịch bản có `utterance_id` riêng, mang `segment_id` của phân đoạn. Mốc của câu gồm `segment_requested` (lúc
  phân đoạn được yêu cầu sinh), `llm_first_sentence` (lúc câu này ra khỏi LLM và qua guard), `tts_first_chunk`, `avatar_first_frame`
  (ack `playback_started` của câu, như ADR-016). Lời trả lời comment vẫn là một `Utterance` nhiều câu như 001.
- **Lý do:** `StaticRenderer` chỉ ghi lúc bắt đầu phát của câu `seq = 0` (`first_playback_at`). Mỗi câu một `utterance_id` thì đo
  được lúc bắt đầu phát của từng câu, nên đo được khoảng lặng giữa hai câu (FR-022, SC-002) mà **không đổi Protocol `AvatarRenderer`**.
  Hiến pháp 1.2.0 Điều VIII cũng viết theo câu: "Scripted sentences carry a `segment_id`".
- **Phương án đã cân nhắc:** một `Utterance` cho cả phân đoạn và thêm `playback_started_at(utterance_id, seq)` vào Protocol: phải sửa
  Protocol, ARCHITECTURE §3 và mọi renderer (cả renderer lip-sync của 005) chỉ để lấy một con số.
- **Hệ quả:** `Utterance.comment_id` thành optional; thêm `segment_id`, `show_id`. Câu kịch bản không vào `LatencyTracker` của comment
  (bảng độ trễ 001 giữ nguyên ý nghĩa), mà vào `ShowStats` (R12).
- **ADR:** ADR-032 (đề xuất), gộp với R1, R7 và R8.

## R3. Đường sinh chữ: thêm `narrate()` vào `ReplyEngine`

- **Quyết định:** `ReplyEngine` thêm `narrate(request: SegmentRequest, catalog: ProductCatalog) -> AsyncIterator[str]`. Hàm này yield
  từng câu hoàn chỉnh như `reply()`. `GeminiReplyEngine` dùng chung client, `SentenceSplitter`, ánh xạ lỗi (`rate_limited`, `api_error`,
  `provider_blocked`, `config_error`) và log `llm_usage`. Chỉ khác prompt (R4) và `max_output_tokens` (`SCRIPT_MAX_TOKENS`, mặc định
  600, vì phân đoạn 3–6 câu dài hơn lời trả lời 1–3 câu). `FakeReplyEngine` thêm kịch bản `narrate` cho test: câu đánh số theo lần gọi,
  để test chống lặp phân biệt được.
- **Lý do:** ARCHITECTURE §3 đã để chỗ sẵn (`# narrate(segment_hint, catalog): chưa làm ở 001, thuộc 004`). Danh sách Protocol ở Điều IV
  có `ReplyEngine`, không có `ScriptEngine`. Dùng chung adapter thì đổi nhà cung cấp LLM chỉ cần một adapter.
- **Phương án đã cân nhắc:** Protocol `ScriptEngine` riêng: thêm một mục vào Điều IV và một factory, mà hai bên dùng chung 90% mã.
- **ADR:** ADR-030 (đề xuất).

## R4. Prompt kịch bản

- **Quyết định:** `brain/script_prompt.py`.
  - **System prompt** = luật kịch bản + `render_catalog(catalog)` (dùng lại của 001). Phần này cố định trong cả phiên, nên được cache
    ngầm như 001 (ADR-018).
  - Luật kịch bản gồm:
    - vai host bán hàng nói liên tục; xưng "em", gọi "anh chị", từ ngữ miền Nam (FR-009);
    - chỉ dùng dữ liệu đã cho, viết giá bằng số như trong dữ liệu (FR-010, FR-011);
    - không đọc link (FR-012);
    - không nhắc giỏ hàng, mã giảm giá, ghim sản phẩm nếu dữ liệu không có (FR-013);
    - FAQ chỉ dùng cặp hỏi–đáp đã ghi (FR-014);
    - viết câu nói tự nhiên, không gạch đầu dòng, không ký hiệu, không biểu tượng cảm xúc (FR-009);
    - nói lại thông tin bằng câu chữ khác với các câu đã nói (FR-006).
  - **User message** = một `SegmentRequest`:
    - sản phẩm (id, tên), chủ đề và mô tả ngắn chủ đề bằng tiếng Việt;
    - số câu `min–max`;
    - câu cuối của phân đoạn trước (để nối mạch);
    - tối đa `SCRIPT_HISTORY_SENTENCES` (mặc định 12) câu đã nói gần nhất về cùng sản phẩm (gồm lời trả lời comment, FR-030), ghi rõ
      "không lặp lại nguyên văn các câu này".
  - Chào mở màn và chào kết là chủ đề không gắn sản phẩm. Chào kết tối đa 2 câu (FR-017).
- **Lý do:** Lịch sử đặt trong user message để không phá cache của system prompt. Chỉ gửi nội dung sản phẩm, câu host đã nói và chữ của
  comment mock (FR-027). Comment mock dùng lại cách chống injection của 001 (R6 của 001).
- **Phương án đã cân nhắc:**
  - Gửi toàn bộ lịch sử phiên: prompt phình theo thời gian, tốn token và có thể vượt TPM.
  - Một lần gọi sinh nhiều phân đoạn: chậm hơn cho câu đầu, và khó đổi hướng khi người vận hành chọn chủ đề (FR-018).
- Câu chữ luật kịch bản (`SCRIPT_RULES` trong `brain/script_prompt.py`) người dùng duyệt 2026-11-01 (ADR-033). Còn lại: chạy bộ tự kiểm tra
  (R10) 3 lần (SC-008) ở G3.

## R5. Chủ đề và điều kiện dữ liệu (FR-003, FR-004)

| `topic` | Tên trên trang điều khiển | Có dữ liệu khi |
|---------|---------------------------|----------------|
| `opening` | Chào mở màn | luôn có (không gắn sản phẩm, chỉ dùng đầu phiên) |
| `intro` | Giới thiệu chung | `intro` hoặc `description` không rỗng |
| `highlights` | Điểm nổi bật | `description` không rỗng |
| `specs` | Thông số | `specs` có ít nhất 1 dòng |
| `price` | Giá và phân loại | luôn có (model `Product` bắt buộc có `price` hoặc `variants`) |
| `promotion` | Khuyến mãi | `promotions` có ít nhất 1 mục |
| `faq` | Câu hỏi thường gặp | `faq` có ít nhất 1 cặp |
| `call_to_action` | Kêu gọi mua | luôn có (dựa trên phân loại/khuyến mãi; FR-013) |
| `closing` | Chào kết | luôn có (không gắn sản phẩm, chỉ dùng khi bấm "Kết thúc") |

- **Lý do:** Mẫu file Word của 001 không có mục "điểm nổi bật" riêng (spec Giả định: không thêm mục). Vì vậy điểm nổi bật lấy từ mô tả.
  Model `Product` bắt buộc có giá hoặc bảng phân loại, nên US1 #4 ("sản phẩm không có giá") không xảy ra với file hợp lệ. Planner vẫn
  kiểm tra để an toàn khi mẫu đổi.
- `TODO:` nếu sau này mẫu file cho phép sản phẩm không có giá, `price` và `call_to_action` phải đổi điều kiện. Ghi lại khi sửa mẫu (001).

## R6. Thuật toán xoay vòng (FR-005, SC-004)

- **Quyết định:** Planner dựng một **chu kỳ** gồm các ô sản phẩm:
  - Có k sản phẩm phụ: xen kẽ `chính, phụ1, chính, phụ2, …`, nên sản phẩm chính chiếm 50%.
  - `SCRIPT_PRIMARY_SHARE` > 0,5: thêm ô sản phẩm chính vào đầu chu kỳ cho tới khi tỷ lệ ≥ mức đặt.
  - Không có sản phẩm phụ: chu kỳ chỉ có sản phẩm chính.
  Mỗi sản phẩm có con trỏ chủ đề riêng, quay vòng qua các chủ đề có dữ liệu theo thứ tự ở R5 (bỏ `opening`, `closing`). Hai phân đoạn
  liền nhau không được trùng **cả** sản phẩm lẫn chủ đề. Khi chỉ còn một chủ đề cho một sản phẩm duy nhất thì cho phép trùng và ghi log
  `rotation_repeat`.
  - **Lựa chọn của người vận hành** (FR-018): giữ một `override` cho phân đoạn kế tiếp, gồm sản phẩm và/hoặc chủ đề.
    - Chỉ chọn sản phẩm: lấy chủ đề kế tiếp theo con trỏ của sản phẩm đó.
    - Chỉ chọn chủ đề: lấy sản phẩm đầu tiên có chủ đề đó, sản phẩm chính trước.
    - Tổ hợp không có dữ liệu: từ chối (`topic_unavailable`).
    Phân đoạn chọn tay **không tiêu** ô xoay vòng, nên sau đó xoay vòng đi tiếp từ chỗ cũ.
  - **Đổi file nội dung:** planner dựng lại chu kỳ theo catalog mới, giữ con trỏ chủ đề của sản phẩm còn trong file.
- **Lý do:** Tất định, nên test được bằng unit test thuần. Với 3 sản phẩm phụ, một chu kỳ là 6 phân đoạn (khoảng 3 phút), nên mỗi sản phẩm
  phụ xuất hiện nhiều lần trong 10 phút (SC-004).
- **Phương án đã cân nhắc:** chọn ngẫu nhiên có trọng số: khó bảo đảm SC-004 trong 10 phút và khó test. Để LLM tự chọn: không kiểm soát
  được tỷ lệ.

## R7. Ba tầng chạy song song: sinh chữ, tạo tiếng, phát

- **Quyết định:** `ScriptRunner` có ba task.
  1. **Sinh chữ** (`_write`): gọi `narrate()` cho phân đoạn kế tiếp. Mỗi câu ra khỏi LLM được làm sạch (R9), qua guard (R9), chống trùng
     (R11), rồi vào hàng chữ của phân đoạn. Tầng này **đi trước đúng một phân đoạn**: sinh xong chữ của N+1 thì chờ N+1 bắt đầu phát mới
     sinh N+2. Sinh N+1 bắt đầu ngay khi chữ của N đã đủ, tức lúc N còn gần như cả phân đoạn chưa phát (khoảng 20–40 s). Vì vậy câu đầu
     của N+1 có tiếng trước khi N nói xong (FR-007), và một lần LLM quá giờ (≤ `SCRIPT_LLM_TIMEOUT_S`) vẫn không gây lặng (SC-006).
  2. **Tạo tiếng** (`_voice`): lấy câu chữ theo thứ tự, gọi TTS, đưa vào hàng câu đã có tiếng (tối đa `SENTENCE_QUEUE_MAX` = 2, như 001).
     Câu TTS lỗi hoặc một lần chờ chunk quá `TTS_TIMEOUT_S` (ADR-049) thì bỏ câu đó, ghi lỗi, làm câu kế (FR-020, US3 #4). Khác 001 ở chỗ 001 dừng cả lượt.
  3. **Phát** (`_play`): lấy từng câu đã có tiếng, giữ "quyền nói" (R8), gọi `renderer.speak()`, rồi ghi khoảng lặng (R12).
  Trước khi phát câu đầu của một phân đoạn, kiểm tra `catalog_version` của phân đoạn còn khớp nội dung đang nạp. Không khớp thì bỏ phân
  đoạn đã chuẩn bị và sinh lại theo nội dung mới. Khi sản phẩm bị bỏ khỏi file, mọi câu chưa phát của sản phẩm đó cũng bị bỏ (trường hợp
  biên "Đổi file", "Sản phẩm bị bỏ").
- **Tạm dừng** (FR-015): tầng phát nói hết câu đang nói rồi chờ. Tầng tạo tiếng bị hủy và **tiếng đã tạo mà chưa phát bị bỏ**, chữ được
  giữ lại. Khi "Tiếp tục", câu kế được tạo tiếng lại, mất thêm một lần chờ chunk đầu của TTS (≤ 1 s, trong SC-007 ≤ 3 s). Phân đoạn đang
  sinh dở khi bấm tạm dừng vẫn sinh tiếp vào hàng chữ, nên không mất (trường hợp biên).
- **Lý do:** Điều I: tiếng phát ra phải được tạo ngay trước khi phát. Giữ tiếng qua một lần tạm dừng có thể kéo dài nhiều phút thì giống
  phát lại bản đã dựng. Giữ chữ thì không sao, vì chữ chưa phải tiếng hay hình. Tầng chữ đi trước một phân đoạn là đủ che độ trễ LLM, mà
  không tốn thêm lần gọi khi người vận hành đổi hướng (FR-018).
- **Phương án đã cân nhắc:**
  - Giữ nguyên hai tầng của 001 (LLM+TTS chung một task): không giữ được chữ khi tạm dừng (US2 #2), và lỗi TTS dừng cả phân đoạn.
  - Sinh trước nhiều phân đoạn: tốn hạn mức free tier, phải bỏ nhiều khi đổi nội dung hoặc đổi hướng.

## R8. Comment mock chen vào kịch bản (US6, FR-028 đến FR-030, SC-011)

- **Quyết định:** `ShowDirector` có thêm khóa `_floor` (quyền nói). Tầng phát kịch bản giữ `_floor` cho **từng câu**. Lượt trả lời
  comment của 001 giữ `_floor` cho **cả lượt**, nhưng chỉ ở tầng phát. Vòng `run()` của 001 vẫn lấy comment ngay khi comment tới và
  bắt đầu lượt ngay. Tầng LLM của lượt chạy luôn trong lúc host nói nốt câu kịch bản; tầng phát của lượt chờ `_floor`. Sau mỗi câu,
  tầng phát kịch bản kiểm tra "có lượt comment đang chạy hoặc comment đang chờ" (`director.busy` hoặc `queue.size() > 0`). Nếu có thì
  nhả `_floor` và chờ tới khi hàng đợi trống và không còn lượt nào, rồi mới nói câu kế (FR-029).
  - Tiếng kịch bản đã tạo sẵn (tối đa 2 câu) được **giữ** qua lượt trả lời comment, vì lượt này chỉ dài vài giây đến khoảng 15 giây.
  - Lúc tạm dừng thì tiếng kịch bản đã tạo sẵn bị bỏ (R7).
  - Lúc `closing` và `ended`, vòng `run()` không trả lời comment. Comment còn trong hàng đợi và comment tới sau đó được ghi `dropped`
    với lý do mới `show_ended` (FR-030).
  - Lúc tạm dừng, comment nằm trong hàng đợi như 001 và quá hạn thì bị bỏ như 001.
  - Khi chưa bấm "Bắt đầu" (`idle`), đường comment chạy y như 001, nên 003 và 005 vẫn dùng làm công cụ thử.
  - Lời trả lời comment (cả câu, kèm comment gốc) được thêm vào lịch sử đã nói của show (FR-030). Lời trả lời không tính vào xoay vòng
    (FR-029).
- **Lý do:** SC-011 tính cả thời gian nói nốt câu đang nói. Câu kịch bản dài khoảng 4–7 s, LLM câu đầu khoảng 1,5 s. Nếu chờ hết câu mới
  gọi LLM thì p95 dễ vượt 5 s. Cho LLM chạy song song với phần còn lại của câu thì độ trễ ≈ max(phần còn lại của câu, LLM + TTS).
- **Phương án đã cân nhắc:** dừng kịch bản ở ranh giới câu rồi mới gọi LLM: đơn giản hơn nhưng có thể trượt SC-011. Cắt ngang câu đang
  nói: trái US6 #1.
- **Ranh giới:** comment tới đúng lúc tầng phát kịch bản vừa kiểm tra xong thì kịch bản nói thêm tối đa một câu. Không câu nào bị cắt
  giữa chừng, nên vẫn đúng US6 #1.

## R9. Guard và làm sạch cho câu kịch bản (FR-009, FR-011, FR-012, FR-013)

- **Quyết định:**
  - **Làm sạch** (`brain/sanitize.py`, `clean_spoken(text) -> str`): bỏ ký hiệu đầu dòng (`-`, `*`, `•`, số thứ tự `1.` đầu câu),
    dấu `#` tiêu đề, `**`/`__` nhấn mạnh, biểu tượng cảm xúc (Unicode `So` và các khối emoji). Gộp khoảng trắng. Câu còn dưới 4 ký tự chữ
    thì bỏ, ghi `sentence_dropped` lý do `empty_after_clean`. Chữ đã làm sạch là chữ đọc và cũng là phụ đề (FR-008).
  - **Guard** (`OutputGuard.check`) thêm ba kiểm tra, áp dụng cho **cả hai đường** (kịch bản và comment):
    - `link`: câu có đường link (dùng `contains_link` sẵn có ở `core/text.py`; FR-012).
    - `unknown_percent`: số đứng trước `%` hoặc "phần trăm" không có trong tập số của file (FR-011). Tập số lấy như `known_amounts`
      (`extract_numbers` đã gồm mọi số nguyên trong file).
    - `platform_phrase`: cụm từ cơ chế nền tảng (giỏ hàng, mã giảm giá, voucher, ghim sản phẩm, bấm link…) **không có** trong chữ của
      file nội dung (FR-013). Danh sách ở `data/rules/platform_phrases.txt`, chỉnh được.
  - **Câu kịch bản bị chặn:** chỉ bỏ câu đó (spec, trường hợp biên). Không nói câu từ chối như 001, vì không có ai hỏi. Cả phân đoạn bị
    chặn hết thì phân đoạn có kết quả `blocked` và chuyển sang phân đoạn kế. `blocked` không tính là lỗi dịch vụ để vào chế độ dự phòng
    (R10).
  - Đường comment giữ cách của 001: dừng ở câu bị chặn và nói câu từ chối.
- **Lý do:** Ký hiệu định dạng là lỗi hình thức, nên làm sạch thay vì chặn (spec: "bị loại khỏi câu đọc và phụ đề"). Số tiền, phần trăm,
  link và cơ chế nền tảng là thông tin sai, nên chặn. Đưa vào guard chung thì đường comment cũng được bảo vệ.
- **Hệ quả:** đổi guard là đổi đường trả lời comment, nên Điều III bắt chạy lại bộ 10 câu hỏi mẫu của 001 (`python -m ai_live.qa_eval
  run`) và bộ câu gài. Điểm không được thấp hơn lần chạy trước.
- **Phương án đã cân nhắc:**
  - Chỉ dặn trong prompt: không tất định, trái ADR-017.
  - Chặn câu có ký hiệu: mất câu đúng chỉ vì một dấu sao.
  - Dùng LLM thứ hai để chấm: tốn hạn mức và độ trễ.
- **ADR:** ADR-031 (đề xuất).
- Danh sách `platform_phrases.txt` ban đầu (26 cụm) người dùng duyệt 2026-11-01 (ADR-033). Thêm cụm mới khi gặp cách nói riêng của Shopee.
- Thêm 2026-11-12 (ADR-050): kiểm tra thứ năm `unsupported_claim`, chạy sau `platform_phrase`, cùng cách so khớp, danh sách
  `data/rules/claim_phrases.txt`. Lý do: G5 cho thấy host tự thêm "an toàn cho da", lời khen của khách, "số lượng có hạn" khi hết thông tin.
  `TODO:` người dùng duyệt danh sách cụm này.

## R10. Chế độ dự phòng (FR-021, US3 #3)

- **Quyết định:**
  - **Lỗi dịch vụ** là `narrate()` ném lỗi hoặc quá `SCRIPT_LLM_TIMEOUT_S` (mặc định 10 s). Bị guard chặn hết không tính là lỗi dịch vụ.
  - **Vào dự phòng:** `SCRIPT_FALLBACK_AFTER` (mặc định 3) phân đoạn **liên tiếp** lỗi dịch vụ.
  - **Phân đoạn dự phòng:** tách `intro` rồi `description` của từng sản phẩm thành câu bằng `SentenceSplitter`, xoay vòng sản phẩm theo
    chu kỳ ở R6, mỗi lần lấy 3–6 câu kế tiếp. Mỗi sản phẩm có con trỏ riêng, hết thì quay lại đầu. Câu dự phòng vẫn qua làm sạch, guard,
    TTS và renderer realtime. Câu dự phòng không tính vào tỷ lệ trùng SC-005.
  - **Thử sinh lại:** trước mỗi phân đoạn dự phòng, tầng sinh chữ gọi `narrate()` cho ô xoay vòng kế tiếp với thời hạn
    `SCRIPT_RETRY_TIMEOUT_S` (mặc định 4 s). Thành công thì dùng kết quả đó và về chế độ `normal`. Thất bại thì dùng phân đoạn dự phòng.
  - Mỗi lần đổi chế độ: log `mode_changed`, sự kiện `show_state`, dòng trong `segments.jsonl`.
- **Lý do:** Tầng chữ đi trước một phân đoạn (R7), nên cả lần thử lại cũng nằm trong lúc phân đoạn trước đang phát và không gây lặng.
  Thời hạn thử lại ngắn hơn để không phí thời gian khi dịch vụ đang chết.
- **Phương án đã cân nhắc:** đọc FAQ làm dự phòng: câu hỏi–đáp đọc nguyên văn nghe lạ. Im lặng: người dùng đã loại khi làm rõ.

## R11. Chống lặp nguyên văn (FR-006, SC-005)

- **Quyết định:** dạng so khớp của câu là `word_form` (của guard: bỏ dấu, chữ thường, gộp dấu câu). Có hai lớp:
  - **Lớp 1, prompt:** gửi các câu gần nhất về cùng sản phẩm (R4).
  - **Lớp 2, tất định:** câu sinh ra trùng `word_form` với một câu đã nói trong show thì bỏ, ghi `sentence_dropped` lý do `duplicate`.
  Bảng tổng hợp (FR-023) đếm tỷ lệ trùng **trước** lớp 2, để biết prompt có làm đúng việc không, và **sau** lớp 2 (tức số câu thật sự
  nói ra, SC-005).
- **Lý do:** Lớp 2 bảo đảm "không có hai phân đoạn giống hệt nhau", kể cả khi LLM lặp. Tốn một tập `set[str]` trong bộ nhớ, khoảng vài
  trăm câu mỗi phiên.
- **Phương án đã cân nhắc:** so độ giống gần đúng (n-gram, embedding): spec chỉ đòi trùng nguyên văn; embedding cần dependency mới.

## R12. Đo khoảng lặng (FR-022, SC-002, SC-006)

- **Quyết định:** `gap = avatar_first_frame(câu N+1) − played_at(câu N)`. `played_at` là lúc `renderer.speak()` trả về, tức khi trang host
  đã ack `sentence_played`. Mỗi khoảng lặng có nhãn:
  - `script`: hai câu kịch bản liền nhau, không có gì xen giữa.
  - `segment_boundary`: câu cuối của phân đoạn N và câu đầu của N+1. Vẫn tính vào SC-002.
  - `comment`: có lượt trả lời comment xen giữa. Không tính vào SC-002 vì SC-011 đo riêng.
  - `paused`: có tạm dừng xen giữa. Không tính.
  - `fault`: có lỗi giả lập ở câu hoặc phân đoạn xen giữa. Không tính vào SC-002, nhưng kiểm ≤ 8 s cho SC-006.
  - `error`: có lỗi thật. Tính vào SC-002 vì lỗi thật cũng là im lặng người xem nghe thấy.
  Log `sentence_gap` cho mỗi khoảng lặng. `ShowStats` tính trung vị, p95 (cần ≥ 20 mẫu, như 001) và giá trị lớn nhất theo từng nhãn.
- **Start → câu đầu (SC-001):** `avatar_first_frame` của câu đầu phân đoạn `opening` trừ lúc server nhận `POST /api/show/start`. Ghi
  `show_first_sentence_s` vào bảng tổng hợp.
- **Lý do:** dùng đúng các ack đã có (ADR-016), không đoán thời lượng audio.
- **Phương án đã cân nhắc:** ước gap từ thời lượng PCM: sai khi trình duyệt đệm hoặc tab bị nền.

## R13. Bỏ qua, kết thúc, lịch sử phiên

- **Bỏ qua** (FR-016):
  - Đang trả lời comment thì làm như 001.
  - Đang nói câu kịch bản thì:
    - hủy task phát, gọi `renderer.interrupt()`;
    - bỏ phần còn lại của phân đoạn (cả chữ lẫn tiếng);
    - phân đoạn có kết quả `skipped`;
    - phân đoạn kế, thường đã sinh sẵn, nói luôn.
  - Đang chào kết thì dừng ngay và sang `ended`.
- **Kết thúc** (FR-017):
  - Trạng thái `closing`: bỏ hàng chữ và hàng tiếng của kịch bản, không nhận comment.
  - Câu đang nói được nói hết, rồi sinh phân đoạn `closing` (tối đa 2 câu).
  - LLM lỗi thì nói một câu chào kết cố định (`CLOSING_FALLBACK_SENTENCE`, không có số, luôn qua guard; tiếng và hình vẫn sinh realtime).
  - Sau đó sang `ended`, ghi bảng tổng hợp.
- **Bắt đầu lại sau `ended`:** "Bắt đầu" tạo show mới (`show_id` mới, lịch sử mới). Không tự chạy lại (FR-017). Bấm "Bắt đầu" khi đang
  `running`, `paused` hoặc `closing` thì trả về show hiện tại, không tạo show thứ hai.
- **Lịch sử** (FR-023): ghi vào thư mục phiên của 001, `data/sessions/<session_id>/`, đã nằm trong `.gitignore`:
  - `segments.jsonl`, một dòng mỗi phân đoạn;
  - `script_sentences.jsonl`, một dòng mỗi câu: đã nói, bị chặn, bị bỏ, hay lỗi;
  - `show_summary_<show_id>.json`, ghi khi sang `ended`, hoặc khi app tắt giữa show.
  Lời trả lời comment vẫn ở `utterances.jsonl` và `comments.jsonl` của 001, có thêm `show_id`.
  Mọi dòng đi qua `redact` (FR-027). Ghi ở worker thread của `SessionLog` như 001.

## R14. Ước lượng số lần gọi dịch vụ free tier (spec Giả định, RISKS Q12)

- Phân đoạn 3–6 câu, mỗi câu khoảng 4–7 s, nên một phân đoạn dài khoảng 15–40 s.
- **LLM, phiên 30 phút:** khoảng 45–110 lần `narrate()`, cộng số comment mock (≤ 10 ở SC-011) và các lần thử lại trong dự phòng. Vậy
  một phiên 30 phút cần **khoảng 60–120 request**, tức khoảng 2–4 request/phút.
- **Token:** system prompt (luật + catalog 4 sản phẩm) ước khoảng 3–5 nghìn token mỗi lần, được cache ngầm. Một phút khoảng 15–20 nghìn
  token vào.
- **Bộ tự kiểm tra (R15):** khoảng 4 sản phẩm × 7 chủ đề + mở màn + kết, tức khoảng 30 request mỗi lần chạy. SC-008 cần 3 lần, tức khoảng
  90 request.
- **TTS:** mỗi câu một request, phiên 30 phút khoảng 250–450 câu. Đó là lý do P1 chạy với `FakeTTS`. Giọng thật theo 003: VieNeu chạy
  local không giới hạn; Gemini TTS có thể vượt RPD (Q12).
- **Kết luận:** tải RPM nhỏ. Rủi ro nằm ở **RPD**: một ngày có tổng duyệt 30 phút, 3 lần tự kiểm tra và vài lần thử thì khoảng 250–350
  request LLM.
- `TODO:` người dùng xem giới hạn RPM/RPD/TPM thật của từng model trong chuỗi ADR-035 (feature 008; trước đây là `LLM_MODEL` trong AI Studio).
  Nếu tổng RPD của chuỗi < 400 thì:
  - (a) bộ tự kiểm tra mặc định chỉ sinh 1 phân đoạn mỗi tổ hợp, và không chạy cùng ngày tổng duyệt;
  - (b) tăng độ dài phân đoạn lên 5–8 câu.
  Theo ADR-019, không bật gói trả phí khi chưa hỏi.
- Rủi ro mới Q14 (`docs/RISKS.md`).

### Lịch test LLM thật chia giai đoạn (chốt 2026-11-01, đổi engine theo ADR-035 ngày 2026-11-03)

> Cập nhật 2026-11-03 (ADR-035): G1–G5 và ngày demo chạy bằng engine chuỗi model free qua freellmapi của feature
> `008-llm-provider-chain` (giá trị `REPLY_ENGINE` chốt ở spec 008), không gọi Gemini trực tiếp; Gemini chỉ còn là mục cuối của chuỗi.
> Hạn mức tính theo từng nhà cung cấp trong chuỗi, không còn là một project Gemini. Các dòng dưới về "một project/key" và điều khoản
> Google vẫn áp dụng cho từng nhà cung cấp: mỗi nhà cung cấp một tài khoản, không lập nhiều tài khoản free để né giới hạn.

Mục đích: không ngày nào dồn quá nhiều lần gọi, và ngày demo còn nguyên hạn mức. Số request là ước tính từ các mục trên, chưa đo.
Mọi giai đoạn đều chạy trên một project/key free tier duy nhất. **Không** dùng nhiều tài khoản free để né giới hạn: trái điều khoản API
của Google, có nguy cơ bị khóa đúng ngày demo.

| Giai đoạn | Khi nào | Việc | `REPLY_ENGINE` | Request LLM ước tính |
|-----------|---------|------|----------------|----------------------|
| G0. Code và test | mọi ngày trong lúc `/sdd.implement` | `uv run pytest` (bỏ `live_llm`), chạy show với giọng giả, bộ tự kiểm tra chế độ fake | `fake` | 0 |
| G1. Thử nhanh | sau checkpoint US1, một ngày | `python -m ai_live.brain narrate` cho vài tổ hợp, test `live_llm` của `narrate()` với engine 008 (G1 ngày 2026-11-02 đã chạy `tests/live/test_gemini_narrate.py` bằng Gemini), một show ngắn 5 phút | engine 008 | khoảng 30–40 |
| G2. Hồi quy guard | sau khi sửa guard (ADR-031), ngày riêng hoặc gộp G1 nếu RPD cho phép | bộ 10 câu hỏi của 001 (`qa_eval run`) và bộ tự kiểm tra kịch bản lần 1 | engine 008 | khoảng 10 + 30 |
| G3. SC-008 | 3 lần chạy liên tiếp, mỗi lần một ngày nếu RPD < 400 | `qa_eval script` lần 1, 2, 3 (lần có lỗi 429 thì không tính, chạy lại ngày khác) | engine 008 | khoảng 30 / lần |
| G4. SC-001 | một ngày, không cùng ngày G5 | 10 lần **Bắt đầu show** → **Kết thúc** (mỗi lần gồm mở màn, 1–2 phân đoạn, chào kết) | engine 008 | khoảng 30–40 |
| G5. Tổng duyệt | ngày riêng, không chạy gì khác | phiên 30 phút (US3) có ≥ 10 comment mock (US6), chấm SC-009 | engine 008 | khoảng 70–130 |
| Ngày demo | | chỉ chạy phiên demo; không chạy bộ tự kiểm tra hay thử nghiệm | engine 008 | khoảng 60–120 / 30 phút |

- Trong lúc phát triển, bộ tự kiểm tra dùng `--per-combo 1` (mặc định). Nếu RPD thấp, tăng `SCRIPT_SEGMENT_MIN_SENTENCES` /
  `SCRIPT_SEGMENT_MAX_SENTENCES` lên 5–8 để giảm số lần gọi mỗi phút show.
- Đổi `LLM_MODEL`, prompt kịch bản, guard hoặc bộ làm sạch: chạy lại G2 và G3 (Điều III), ở ngày khác ngày tổng duyệt hoặc demo.
- Ghi số request thật của mỗi giai đoạn (log `llm_usage`) vào "Kết quả kiểm chứng" của `quickstart.md`, để thay các số ước tính ở trên.

**Số đo thật 2026-11-12 (T080).** G1–G5 chạy hết trong **một ngày** (không theo lịch ngày riêng ở trên), engine 008, máy dev:

| Giai đoạn | Request LLM thật | Ước tính ở trên |
|-----------|------------------|-----------------|
| G1 | 8 | 30–40 (không chạy show 5 phút, thay bằng G4) |
| G2 | 20 + 21 | 10 + 30 |
| G3 | 42 (2 lần) | 60 |
| G4 | 30 | 30–40 |
| G5, show 30 phút | 57 (50 phân đoạn + 7 câu trả lời; 7 phân đoạn lỗi giả lập không gọi model) | 70–130 |
| Chạy lại SC-011, show 10 phút | 31 (SEA-LION 16, Qwen 15) | — |

- Tổng: khoảng **194 request SEA-LION thành công** thì freellmapi bắt đầu trả `rate_limited` cho SEA-LION (18:00 giờ máy). Từ đó chuỗi tự
  chuyển sang Qwen trên Groq và mọi lượt vẫn có lời (`llm_switch`, nghỉ 60 s rồi thử lại SEA-LION, lần nào cũng bị chặn). Lần chạy
  `qa_eval script --entry sealion` ngay sau đó: 42/42 phân đoạn lỗi `rate_limited`.
- Một show 30 phút thật tốn khoảng 2 request/phút, đúng khoảng ước tính dưới (60–120).
- Kết luận: một ngày dồn G1–G5 đã chạm giới hạn của SEA-LION. Ngày demo **chỉ chạy phiên demo**, như lịch trên. Qwen là dự phòng đủ dùng.
- `TODO:` giới hạn SEA-LION là theo ngày hay theo cửa sổ ngắn hơn, và reset lúc mấy giờ? (xem log freellmapi / bảng điều khiển Cloudflare
  của người dùng). Nếu reset theo ngày UTC thì là 07:00 giờ Việt Nam.
- `TODO:` sau khi có RPD thật (mục trên), xem có gộp được G1 với G2, G3 với G4 không. Không gộp G5 với bất cứ việc gì.
- Phương án hợp lệ nếu hạn mức vẫn thiếu (đều cần người dùng duyệt): thêm adapter LLM thứ hai (cần ADR; đã chọn: ADR-035, feature 008), hoặc chỉ bật trả phí riêng
  ngày demo (ADR-019).

## R15. Bộ tự kiểm tra kịch bản (FR-025, FR-026, US4)

- **Quyết định:** `qa_eval/script_eval.py` và lệnh `python -m ai_live.qa_eval script [--content PATH] [--per-combo N]`.
  - Với mỗi tổ hợp sản phẩm × chủ đề có dữ liệu (R5), cộng `opening` và `closing`, gọi đúng `engine.narrate()` của live
    (`create_reply_engine(settings)`). Mặc định N = 1 lần mỗi tổ hợp. Giữa hai lần gọi Gemini nghỉ `GEMINI_PACE_S` như runner 001.
  - **Chấm từng câu trên chữ thô** (trước khi làm sạch):
    - số tiền hoặc phần trăm lạ, khẳng định bị cấm, link, cụm cơ chế nền tảng: dùng đúng `OutputGuard`;
    - sai xưng hô: có "tôi", "bạn", "quý khách", "quí khách", "các bạn" ở vai người nói hoặc người nghe; danh sách trong
      `qa_eval/script_grader.py`. Nguyên từ, không phân biệt hoa thường, giữ dấu (để "bán", "tối" không bị bắt). "bạn" ở ngôi
      thứ ba (host nói **về** khách khác, không gọi người xem) không tính: đứng sau "nhiều", "những", "mấy", "một số", "một vài",
      "vài", hoặc "bạn"/"các bạn" đứng trước "khác", "nào", "ấy" (vd "nhiều bạn hỏi", "những bạn da khô", "các bạn khác",
      "bạn nào da dầu"). Có "ơi" ngay sau thì vẫn là gọi người xem, vẫn tính (vd "mấy bạn ơi");
    - ký hiệu định dạng: `clean_spoken(x) != normalize_text(x)`;
    - số câu ngoài khoảng min–max của phân đoạn (cảnh báo, không tính vi phạm).
  - Kết quả lưu ở `data/eval/script_runs/<timestamp>.json`, đã nằm trong `.gitignore`. Báo cáo gồm từng phân đoạn, câu vi phạm kèm lý
    do, tổng số vi phạm theo loại, và so sánh với lần chạy trước (tăng hay giảm theo loại).
  - Mã thoát khác 0 khi có vi phạm, để dùng làm regression (Điều III).
  - Chạy với `REPLY_ENGINE=fake` để test.
- **Lý do:** dùng lại guard của live thì "đạt kiểm tra" nghĩa là "đạt guard lúc live". Chấm trên chữ thô để bắt được prompt kém, kể cả lỗi
  mà bộ làm sạch che đi.
- **Phương án đã cân nhắc:** gộp vào runner 001: định dạng khác (001 có ý bắt buộc theo câu hỏi, kịch bản thì không). Để LLM chấm: tốn
  hạn mức, không tất định.
- Danh sách "sai xưng hô": người dùng duyệt 2026-11-03, sau lần chạy thử SEA-LION (6 vi phạm đều là "nhiều bạn" / "những bạn" ở ngôi
  thứ ba), kèm luật ngôi thứ ba ở trên. "mình" bị bỏ khỏi danh sách vì người miền Nam dùng "bên mình" theo nghĩa "shop mình".
