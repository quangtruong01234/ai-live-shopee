# Kế hoạch triển khai: AI host tự nói kịch bản giới thiệu sản phẩm, sinh realtime

- **Feature ID:** `004-show-director` · **Ngày:** 2026-11-01 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/004-show-director/spec.md` (Clarified, 6 user story, 30 FR, 11 SC). Hiến pháp 1.2.0 (ADR-029).

## Tóm tắt

Người vận hành bấm "Bắt đầu show" trên trang điều khiển. `ShowDirector` của 001 tạo một `ScriptRunner`, và `ScriptRunner` chạy ba tầng
song song:
1. **Sinh chữ:** `ReplyEngine.narrate()` sinh phân đoạn 3–6 câu cho một sản phẩm và một chủ đề do `SegmentPlanner` chọn. Planner xoay
   vòng tất định và chỉ chọn chủ đề có dữ liệu. Mỗi câu ra khỏi LLM được làm sạch ký hiệu, qua guard (thêm luật link, phần trăm, cụm cơ
   chế nền tảng), rồi qua bộ chống lặp nguyên văn. Tầng này đi trước đúng một phân đoạn.
2. **Tạo tiếng:** TTS đi trước tối đa 2 câu.
3. **Phát:** renderer phát từng câu.
Mỗi câu kịch bản là một `Utterance` riêng có `segment_id`, nên đo được khoảng lặng giữa hai câu bằng ack `playback_started`
và `sentence_played` sẵn có. Comment mock của 001 vẫn chạy song song: LLM của lượt trả lời bắt đầu ngay khi comment tới, còn tầng phát
chờ host nói hết câu kịch bản đang nói ("quyền nói"). Dịch vụ sinh lỗi 3 phân đoạn liên tiếp thì chuyển sang chế độ dự phòng: đọc nguyên
văn câu của bài giới thiệu và mô tả, tiếng và hình vẫn sinh realtime. Có một lệnh tự kiểm tra kịch bản (`python -m ai_live.qa_eval script`)
làm regression cho Điều III.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, `.python-version`, ADR-020).
- **Phụ thuộc chính:** FastAPI, uvicorn, `google-genai` (Gemini free tier, ADR-018), `python-docx`, `pydantic-settings`; dev: pytest,
  httpx, ruff. **Phụ thuộc MỚI cần duyệt: không có.** Emoji được nhận bằng `unicodedata` của thư viện chuẩn (R9).
- **Lưu trữ:** không DB. Trạng thái show nằm trong bộ nhớ. Lịch sử ghi JSONL/JSON vào thư mục phiên `data/sessions/<session_id>/` của 001
  (gitignore). Kết quả tự kiểm tra ở `data/eval/script_runs/` (gitignore).
- **Kiểm thử:** pytest + `anyio` như 001. Mặc định chạy với `FakeReplyEngine` (thêm kịch bản `narrate`), `FakeTTS`, `StaticRenderer` với
  host giả (`tests/fixtures/fake_host.py`), không cần mạng, GPU hay API key. Test gọi Gemini thật (`tests/live/test_gemini_narrate.py`)
  mang marker `live_llm` và không chạy mặc định (từ ADR-035, các bước LLM thật G1–G5 dùng test `live_llm` của engine feature 008). Phiên 30 phút (SC-002 đến SC-006) đo bằng tay theo `quickstart.md`. Logic tương ứng có
  test tự động với đồng hồ và độ trễ giả.
- **Nơi chạy:** laptop dev, `AVATAR_MODE=static`, `TTS_PROVIDER=fake` mặc định. **Không có bước nào bắt buộc cần GPU hay RunPod.**
  Khi 003 (giọng thật) và 005 (lip-sync, ADR-023) xong thì đo lại SC-001 và SC-002 với cấu hình demo (Điều VI). Các bước đó được đánh dấu
  trong `quickstart.md`.
- **Adapter liên quan:**
  - `ReplyEngine` thêm `narrate()` (ADR-030): `GeminiReplyEngine`, `FakeReplyEngine`.
  - Dùng lại, không đổi Protocol: `ProductStore` (`DocxProductStore`), `TTSEngine` (`FakeTTS`; giọng của 003 khi xong),
    `AvatarRenderer` (`StaticRenderer`), `CommentSource`/`CommentQueue` (`MockSource`, `InMemoryCommentQueue`) cho US6.
  - OutputSink: không dùng.
- **Mục tiêu hiệu năng:**
  - Điều VI, kịch bản: từ "Bắt đầu show" tới câu đầu phát ≤ 5 s (SC-001); khoảng lặng giữa hai câu p95 ≤ 1,5 s, tối đa 5 s (SC-002).
  - Điều VI, comment chen vào: < 5 s p95, tính cả thời gian nói hết câu kịch bản đang nói (SC-011).
  - Lệnh điều khiển: bỏ qua ≤ 1 s, tiếp tục ≤ 3 s (SC-007).
- **Ràng buộc khác:**
  - App chỉ bind `127.0.0.1` như 001.
  - Không có biến nào tắt nhãn AI.
  - Không lưu tiếng hay hình đã phát để phát lại (Điều I). Tiếng đã tạo mà chưa phát bị bỏ khi tạm dừng (R7).
  - Mọi dòng ghi file và log đi qua `redact` (FR-027).

## Kiểm tra Constitution (cổng)

### Lần 1 (trước Phase 0)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt (kế thừa lệch có theo dõi của 001) | Mỗi câu được sinh chữ ngay trong phiên, tạo tiếng ngay trước khi phát, renderer dựng ngay lúc phát. Chế độ dự phòng đọc chữ có sẵn trong file nội dung, nhưng tiếng và hình vẫn sinh realtime, nên không phải phát file dựng sẵn. Nhãn AI: như 001, nằm trên trang host, chưa ghép vào frame. Ghép vào frame thuộc 005 (lệch đã ghi ở plan 001). 1 host 1 tài khoản: N/A, chưa có tài khoản nền tảng. |
| II. Đồng ý và bảo mật | Đạt | Không thêm nhân vật hay giọng mới. Chỉ gửi nội dung sản phẩm, câu host đã nói và chữ comment mock tới Gemini (FR-027). Key chỉ từ `.env`, ghi file qua `redact`. |
| III. Trả lời có căn cứ | Đạt | Prompt chỉ chứa dữ liệu từ file. Guard tất định chặn số tiền và phần trăm lạ, khẳng định cấm, link, cụm cơ chế nền tảng. Bộ tự kiểm tra kịch bản là regression mới. Đổi guard thì chạy lại bộ câu hỏi 001. |
| IV. Adapter trước | Đạt | Không thêm Protocol mới. `ReplyEngine` thêm `narrate()`, đúng chỗ ARCHITECTURE §3 đã ghi sẵn. Khâu kịch bản chạy độc lập bằng `python -m ai_live.brain narrate`. |
| V. Test trước | Đạt | Planner và guard là logic thuần, test red→green. Runner chạy được với fake. Test Gemini thật tách bằng marker `live_llm`. Không có việc GPU. |
| VI. Ngân sách độ trễ | Đạt | Xem bảng "Ảnh hưởng ngân sách độ trễ". Ba mục tiêu của Điều VI 1.2.0 đều có cách đo. |
| VII. Đơn giản trước | Đạt | Không thêm hạ tầng hay dependency. Ba module mới đều là lớp cụ thể (planner, runner, stats), không có abstraction. |
| VIII. Quan sát được | Đạt | Câu kịch bản có `utterance_id`, `segment_id`, mốc `segment_requested`, và log `sentence_gap`. Mọi khâu có timeout; lỗi một phân đoạn hay một câu không dừng show. |
| IX. Ngôn ngữ và tài liệu | Đạt | Định danh tiếng Anh. Prompt, câu chào kết dự phòng và thông báo lỗi bằng tiếng Việt. Chỗ chưa chắc ghi `TODO:`. |

### Lần 2 (sau Phase 1)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I | Đạt (kế thừa lệch của 001) | `research.md` R7: tiếng chỉ được giữ tối đa 2 câu và chỉ trong lúc đang chạy hoặc đang chen comment (vài giây). Khi tạm dừng, tiếng bị bỏ và được tạo lại lúc tiếp tục. Câu chào kết dự phòng là chữ, không phải file audio. `contracts/api.md`: không endpoint nào ẩn nhãn. |
| II | Đạt | `contracts/events.md`: file `segments.jsonl`, `script_sentences.jsonl` và `show_summary_*.json` chỉ chứa chữ đã nói và mốc thời gian; ghi qua `redact`. Bộ tự kiểm tra ghi vào `data/eval/script_runs/` (gitignore). |
| III | Đạt | R4 (prompt), R9 (làm sạch + guard), R11 (chống lặp), R15 (bộ tự kiểm tra). Guard mở rộng áp dụng cả đường comment, nên task cuối của pha guard **bắt buộc** chạy lại `python -m ai_live.qa_eval run` với bộ 10 câu và bộ câu gài, điểm không thấp hơn lần trước. |
| IV | Đạt | `contracts/adapters.md`: khác biệt duy nhất với ARCHITECTURE §3 là chữ ký `narrate(request: SegmentRequest, catalog)` thay cho `narrate(segment_hint, catalog)`. Chốt ở ADR-030, sửa ARCHITECTURE §3 ở pha Foundational. Có thêm lệnh độc lập `python -m ai_live.brain narrate`. |
| V | Đạt | Mỗi kịch bản chấp nhận có test (liệt kê ở `/sdd.tasks`). Các SC đo trên phiên 30 phút làm bằng tay theo `quickstart.md`. Phần tính toán (gap, p95, tỷ lệ trùng, tỷ lệ sản phẩm) có unit test riêng ở `show_stats`. |
| VI | Đạt | Guard thêm 3 regex và tra tập số, < 5 ms mỗi câu. Prefetch một phân đoạn che độ trễ LLM. Gap tính bằng ack thật (R12). Comment chen vào: LLM chạy song song với phần còn lại của câu (R8). |
| VII | Đạt | Không DB hay hàng đợi ngoài. `ShowStats` không phải `LatencyTracker` thứ hai: hai bên đo hai thứ khác nhau, không dùng chung abstraction. |
| VIII | Đạt | `Milestone.SEGMENT_REQUESTED` thêm vào enum. Câu kịch bản cần đủ 4 mốc `segment_requested`, `llm_first_sentence`, `tts_first_chunk`, `avatar_first_frame` (data-model §2). |
| IX | Đạt | |

Không có vi phạm mới. Chỗ lệch Điều I (nhãn chưa nằm trong frame ở chế độ static) kế thừa từ 001 và được giải ở 005.

## Ảnh hưởng ngân sách độ trễ

Định nghĩa đo chi tiết ở `research.md` R12. Số "ước tính" chưa đo; thay bằng số đo thật sau `/sdd.implement`.

**(a) Start → câu đầu (SC-001, ≤ 5 s):** `avatar_first_frame(câu 1 của opening) − lúc nhận POST /api/show/start`.

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| Nhận lệnh → yêu cầu phân đoạn | 0,1 s | Planner chọn `opening`, dựng prompt, ước tính < 10 ms | mốc `segment_requested` |
| LLM câu đầu | 1,5 s | Prompt kịch bản (system prompt cache được). Làm sạch + guard + chống lặp < 5 ms | `llm_first_sentence` |
| TTS chunk đầu | 1,0 s | `FakeTTS` ≈ 0 s. Giọng 003 đo lại | `tts_first_chunk` |
| Bắt đầu phát | 0,8 s (lip-sync) / < 0,1 s (static) | Không đổi | `avatar_first_frame` (ack `playback_started`) |
| **Tổng** | **≤ 5 s** | ước tính 1,6–3,4 s | `show_first_sentence_s` trong bảng tổng hợp; ≥ 10 lần bấm |

**(b) Khoảng lặng giữa hai câu (SC-002, p95 ≤ 1,5 s, tối đa 5 s):** `avatar_first_frame(câu N+1) − played_at(câu N)`.

| Khâu | Ngân sách | Feature này thay đổi gì | Cách đo |
|------|-----------|-------------------------|---------|
| Câu kế đã có chữ | 0 s khi prefetch kịp | Tầng chữ đi trước một phân đoạn (R7). Phân đoạn dài 15–40 s, nên LLM có ≥ 15 s để sinh | log `segment_ready` trước `segment_started` |
| Câu kế đã có tiếng | 0 s nếu TTS nhanh hơn thời gian phát | Tầng tiếng đi trước 2 câu. Với `FakeTTS` luôn kịp. Giọng thật có RTF > 1 thì khoảng lặng tăng (phụ thuộc 003) | `tts_first_chunk` so với `played_at` của câu trước |
| Round trip trang host | < 0,3 s | Không đổi (`sentence_played` → `sentence_start` → `playback_started`) | nhãn gap `script` / `segment_boundary` |
| **p95** | **≤ 1,5 s** | ước tính 0,1–0,4 s với `FakeTTS` | `sentence_gap` → `ShowStats` |

**(c) Comment chen vào (SC-011, < 5 s p95):** `avatar_first_frame − comment_received` của lượt trả lời.
`total ≈ max(phần còn lại của câu kịch bản đang nói, LLM câu đầu + TTS chunk đầu) + round trip`. Câu kịch bản dài 4–7 s, nên trường hợp
xấu (comment tới ngay đầu câu) khoảng 4–7 s, **có thể vượt 5 s**. p95 phụ thuộc độ dài câu. Giảm thiểu:
- Luật prompt yêu cầu câu ngắn (≤ 25 từ), nhằm câu dài khoảng 4 s.
- Đo thật ở quickstart US6.
- Nếu p95 ≥ 5 s, ghi `TODO:` và hỏi người dùng có nên cho phép cắt ở dấu phẩy không. Điều này đổi spec US6 #1, nên không tự làm.

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/004-show-director/
├── spec.md
├── plan.md            # file này
├── research.md        # Phase 0 (R1–R15)
├── data-model.md      # Phase 1
├── contracts/
│   ├── adapters.md    # ReplyEngine.narrate, guard, planner, runner; đối chiếu ARCHITECTURE §3
│   ├── api.md         # endpoint show, thay đổi ở endpoint 001, trang điều khiển
│   └── events.md      # log, file lịch sử, sự kiện EventBus
├── quickstart.md      # Phase 1
└── tasks.md           # /sdd.tasks
```

### Mã nguồn (đường dẫn thật)
```
src/ai_live/
├── core/models.py              # SỬA: Utterance.comment_id optional + segment_id, show_id; Milestone.SEGMENT_REQUESTED;
│                               #       GuardReason LINK/UNKNOWN_PERCENT/PLATFORM_PHRASE; DropReason.SHOW_ENDED;
│                               #       ShowState, ShowMode, Topic, SegmentOrigin, SegmentStatus, SentenceStatus
├── core/protocols.py           # SỬA: ReplyEngine.narrate()
├── core/config.py              # SỬA: biến SCRIPT_* và PLATFORM_PHRASES_PATH
├── core/events.py              # SỬA: SHOW_STATE, SEGMENT_STARTED, SEGMENT_FINISHED, SEGMENT_NEXT, SHOW_STATS
├── brain/script_prompt.py      # MỚI: luật kịch bản + SegmentRequest → nội dung gửi Gemini
├── brain/sanitize.py           # MỚI: clean_spoken() bỏ ký hiệu, emoji
├── brain/guard.py              # SỬA: link, phần trăm lạ, cụm cơ chế nền tảng
├── brain/gemini_engine.py      # SỬA: narrate()
├── brain/fake_engine.py        # SỬA: narrate() có kịch bản
├── brain/__main__.py           # SỬA: lệnh `narrate --product ID --topic T`
├── director/segment_planner.py # MỚI: SegmentPlanner (thuần)
├── director/script_runner.py   # MỚI: ScriptRunner (3 tầng, dự phòng, gap)
├── director/show_stats.py      # MỚI: ShowStats (gap, tỷ lệ sản phẩm, trùng)
├── director/show_director.py   # SỬA: start_show/end_show/choose_next, _floor, pause/skip theo show, drop show_ended
├── director/session_log.py     # SỬA: segments.jsonl, script_sentences.jsonl, show_summary_<show_id>.json
├── qa_eval/script_grader.py    # MỚI: chấm câu kịch bản (guard + xưng hô + ký hiệu)
├── qa_eval/script_eval.py      # MỚI: chạy mọi tổ hợp, lưu, so sánh lần trước
├── qa_eval/__main__.py         # SỬA: lệnh con `script`
└── app/
    ├── routes.py               # SỬA: /api/show/*, /api/state có `show`
    └── static/control.{html,js}# SỬA: khu điều khiển show (FR-019)
data/rules/platform_phrases.txt # MỚI: cụm cơ chế nền tảng (commit)
.env.example                    # SỬA: biến mới
tests/
├── unit/test_segment_planner.py, test_script_prompt.py, test_sanitize.py, test_show_stats.py, test_script_grader.py
├── unit/test_guard.py          # SỬA: thêm link/phần trăm/cụm nền tảng
├── unit/test_config.py, test_cli.py, test_events.py   # SỬA theo biến, lệnh, sự kiện mới
├── contract/test_reply_engine_contract.py             # SỬA: narrate() yield câu hoàn chỉnh, ném ReplyEngineError
├── integration/test_script_runner.py, test_show_api.py # MỚI
├── integration/test_show_director.py                   # SỬA: comment chen vào, pause/skip trong show
└── live/test_gemini_narrate.py                         # MỚI, marker live_llm
```

`app/static/host.{html,js}` **không đổi**: mỗi câu kịch bản là một `sentence_start` như 001. Phụ đề và nhãn AI giữ nguyên.
Cập nhật `src/README.md` khi implement (module mới trong `director/`, `brain/`, `qa_eval/`).

## Phase 0: Nghiên cứu → [`research.md`](./research.md)

15 quyết định:
- R1 cấu trúc điều phối, R2 mỗi câu một `Utterance`, R3 `narrate()`, R4 prompt.
- R5 chủ đề và điều kiện dữ liệu, R6 xoay vòng, R7 ba tầng và tạm dừng.
- R8 comment chen vào, R9 làm sạch và guard, R10 chế độ dự phòng, R11 chống lặp.
- R12 đo khoảng lặng, R13 bỏ qua, kết thúc và lịch sử, R14 ước lượng số lần gọi free tier, R15 bộ tự kiểm tra.

## Phase 1: Thiết kế

- [`data-model.md`](./data-model.md): ShowSession, Topic, Segment, SegmentRequest, ScriptSentence (Utterance mở rộng), SpokenHistory,
  SentenceGap, ShowSummary, ScriptEvalRun; chuyển trạng thái show và phân đoạn.
- [`contracts/`](./contracts/): `narrate()`, guard, planner, runner, API show, sự kiện và file lịch sử.
- [`quickstart.md`](./quickstart.md): kiểm chứng tay US1–US6 trên laptop. Đo lại với giọng 003 hoặc avatar 005 khi các feature đó xong.

### Biến môi trường mới (cập nhật `.env.example`; `tests/unit/test_config.py` kiểm khớp mặc định)

| Biến | Mặc định | Ghi chú |
|------|----------|---------|
| `SCRIPT_SEGMENT_MIN_SENTENCES` | `3` | FR-003 |
| `SCRIPT_SEGMENT_MAX_SENTENCES` | `6` | FR-003. Phải ≥ min, nếu không app không khởi động |
| `SCRIPT_PRIMARY_SHARE` | `0.5` | FR-005, khoảng `0.5`–`0.9` |
| `SCRIPT_FALLBACK_AFTER` | `3` | FR-021: số phân đoạn liên tiếp lỗi dịch vụ |
| `SCRIPT_LLM_TIMEOUT_S` | `10` | timeout cả phân đoạn (Điều VIII) |
| `SCRIPT_RETRY_TIMEOUT_S` | `4` | thời hạn thử sinh lại trong chế độ dự phòng (R10) |
| `SCRIPT_HISTORY_SENTENCES` | `12` | số câu gần nhất gửi kèm prompt (R4) |
| `SCRIPT_MAX_TOKENS` | `600` | `max_output_tokens` của `narrate()` |
| `PLATFORM_PHRASES_PATH` | `data/rules/platform_phrases.txt` | FR-013 |

Biến của 001 không đổi. Giả lập lỗi dùng lại `POST /api/debug/fault` (bước `llm` áp dụng cho cả `narrate()`, FR-024).

## ADR cần ghi

- **ADR-030 (Đề xuất):** Thêm `narrate(request: SegmentRequest, catalog)` vào Protocol `ReplyEngine` thay vì tạo Protocol mới; sửa chữ ký
  ghi sẵn ở ARCHITECTURE §3.
- **ADR-031 (Đề xuất):** Mở rộng `OutputGuard` (link, phần trăm lạ, cụm cơ chế nền tảng) cho cả hai đường, thêm bộ làm sạch ký hiệu trước
  guard; chạy lại bộ câu hỏi 001.
- **ADR-032 (Đề xuất):** Cấu trúc show: `ShowDirector` vẫn là bộ điều phối duy nhất, thêm `SegmentPlanner`, `ScriptRunner`, `ShowStats`.
  Mỗi câu kịch bản là một `Utterance` (`comment_id` thành optional). Có "quyền nói" chung giữa kịch bản và comment. Tiếng chưa phát bị bỏ
  khi tạm dừng.

## Rủi ro mới

- **Q14:** Hạn mức free tier Gemini (RPD) không đủ cho show liên tục, tổng duyệt và bộ tự kiểm tra trong một ngày (R14). Thêm vào
  `docs/RISKS.md`.
- **Q15:** Guard chặn nhiều câu kịch bản làm phân đoạn bị cụt, mất mạch, nghe lủng củng (SC-009). Thêm vào `docs/RISKS.md`.
- Đã có, nay tăng mức: **P7** (nội dung lặp giống video quay sẵn) được giảm bằng R11. **Q12** (RPD của Gemini TTS) nặng hơn vì nói liên
  tục: khoảng 250–450 câu mỗi 30 phút. Cập nhật mô tả hai mục này.

## Theo dõi độ phức tạp

Không có vi phạm mới. Chỗ lệch Điều I (nhãn AI chưa ghép vào frame ở chế độ static) đã ghi ở `specs/001-local-reply-pipeline/plan.md`
và giải ở 005.
