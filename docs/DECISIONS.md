# Nhật ký quyết định (ADR)

> Mỗi quyết định có: ngày, trạng thái, quyết định, lý do, phương án đã loại.
> Trạng thái gồm: `Đã chốt` | `Đề xuất` (chờ xác nhận) | `Thay thế bởi ADR-xxx`.
> Không viết lại ADR cũ. Khi đổi ý thì thêm ADR mới và đổi trạng thái ADR cũ.

---

## ADR-001: Mô hình kinh doanh là dịch vụ làm hộ
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt
- **Quyết định:** Khách chỉ cung cấp dữ liệu sản phẩm. Mình lo avatar, giọng, kịch bản và vận hành live. Báo cáo dùng thống kê
  có sẵn của Shopee. Việc whitelist live AI với Shopee là việc của khách.
- **Lý do:** Khách không cần kỹ năng kỹ thuật. Mình kiểm soát chất lượng và tuân thủ. Không cần làm sản phẩm self-service ngay.
- **Phương án đã loại:** SaaS tự phục vụ (tốn công làm UI, onboarding và hỗ trợ; để sau khi có nhiều khách).

## ADR-002: Demo ngoài Shopee qua Google Meet, sau đó YouTube Unlisted
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt
- **Quyết định:** Demo cho 1 khách, 1 sản phẩm chính và 2–3 sản phẩm phụ. Phát qua Google Meet (chia sẻ tab Chrome có âm thanh),
  sau đó có thể livestream YouTube Unlisted. Khách xem ổn mới trả tiền.
- **Lý do:** Chưa có whitelist Shopee. Meet không cần tài khoản nền tảng và dễ kiểm soát. YouTube có Live Chat API chính thức
  để demo luồng comment thật.
- **Phương án đã loại:** Demo trực tiếp trên Shopee (chưa được phép, rủi ro tài khoản khách); gửi video ghi sẵn (không chứng minh được realtime).

## ADR-003: Stack Python 3.10+, FastAPI, asyncio; hàng đợi in-process cho demo
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt; **phiên bản Python tối thiểu đổi thành 3.12 theo ADR-020**
- **Quyết định:** Dùng Python 3.10+, FastAPI và asyncio. Hàng đợi comment là in-process (asyncio) cho demo; chuyển Redis khi chạy nhiều tiến trình hoặc nhiều khách.
- **Lý do:** Hệ sinh thái lip-sync và TTS đều là Python. Một tiến trình đủ cho 1 phiên live. Ít thành phần thì ít điểm lỗi khi demo.
- **Phương án đã loại:** Node.js (xa hệ sinh thái model); dùng Redis ngay từ đầu (thừa với 1 phiên).

## ADR-004: Lõi avatar fork từ LiveTalking (Wav2Lip hoặc MuseTalk)
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt (chọn model: Đề xuất)
- **Quyết định:** Fork `lipku/LiveTalking`. Đầu ra là WebRTC (demo), virtual cam / RTMP (OBS).
  Chọn Wav2Lip hay MuseTalk sau khi benchmark độ trễ và chất lượng trên RTX 3090/4090.
- **Lý do:** LiveTalking đã có sẵn pipeline realtime gồm audio → lip-sync → WebRTC/RTMP, giúp tiết kiệm nhiều tuần.
- **Phương án đã loại:** Tự viết từ đầu (quá lâu cho demo); dịch vụ avatar streaming SaaS (chi phí theo phút cao khi chạy 15 giờ/ngày,
  ít kiểm soát giọng Việt và overlay; TODO: chưa so sánh giá cụ thể).
- **TODO:** Tích hợp fork theo cách nào: git submodule trong `vendor/`, hay repo riêng gọi qua HTTP? (xem ARCHITECTURE §3)
- **Cập nhật:** xem ADR-041 (model giai đoạn laptop) và ADR-042 (cách tích hợp fork), cả hai Đã chốt 2026-11-06 (plan 005).

## ADR-005: LLM streaming, đưa toàn bộ dữ liệu sản phẩm vào prompt, chưa dùng vector DB
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt; **phần nhà cung cấp (Claude API) bị thay bởi ADR-018** (2026-10-30)
- **Quyết định:** Dùng Claude API ở chế độ streaming. Dữ liệu sản phẩm là JSON (có thể chuyển SQLite), truy xuất bằng tên/từ khóa,
  và đưa toàn bộ dữ liệu sản phẩm ít ỏi vào prompt (có prompt caching).
- **Lý do:** Chỉ có 1–4 sản phẩm nên đưa hết vào context đơn giản và chính xác hơn RAG.
- **Phương án đã loại:** Vector DB / RAG (thừa với vài sản phẩm, thêm độ trễ và thêm điểm lỗi).
- **Ghi chú (2026-10-30):** Đổi sang Gemini (ADR-018). Nguồn nội dung đổi từ JSON/SQLite sang file Word (ADR-014, đề xuất).
  TODO cũ "Haiku hay Sonnet" không còn áp dụng; chọn model Gemini bằng benchmark (ADR-018).

## ADR-006: TTS tiếng Việt thiết kế dạng adapter
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt (nhà cung cấp mặc định: chưa chọn)
- **Quyết định:** `TTSEngine` là interface chung, đổi được giữa model mã nguồn mở và ElevenLabs bằng `TTS_PROVIDER`.
- **Lý do:** Chưa biết bên nào cho giọng Việt tự nhiên hơn, độ trễ thấp hơn và chi phí phù hợp 15 giờ/ngày; license model OSS cũng chưa rõ.
- **Phương án đã loại:** Gắn cứng một nhà cung cấp.
- **TODO:** Model OSS cụ thể nào để thử? License có cho dùng thương mại không?

## ADR-007: Nguồn comment dạng adapter (mock, YouTube, Shopee)
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt
- **Quyết định:** `CommentSource` có 3 implementation: mock (gõ tay), YouTube Live Chat API, Shopee (làm sau, đọc từ Shopee Live PC).
- **Lý do:** Phát triển và demo không phụ thuộc Shopee. Phần dễ hỏng nhất (Shopee) bị cô lập vào một adapter.
- **Phương án đã loại:** Làm Shopee trước (chưa có whitelist, giao diện dễ đổi).

## ADR-008: Laptop chạy "avatar tĩnh"; lip-sync thật trên RunPod, chỉ bật khi cần
- **Ngày:** 2026-10-30 · **Trạng thái:** Thay một phần bởi ADR-023 (lip-sync chạy tạm trên laptop)
- **Quyết định:** Ở local dùng `AVATAR_MODE=static` (ảnh + audio). Render thật trên RunPod RTX 3090/4090, kèm tài liệu/script dựng nhanh (`docs/RUNPOD.md`).
- **Lý do:** GTX 1650 Ti 4GB không đủ chạy lip-sync realtime. Thuê theo giờ rẻ hơn mua GPU ở giai đoạn demo.
- **Phương án đã loại:** Mua GPU ngay (vốn lớn khi chưa có khách trả tiền); chạy lip-sync chậm trên laptop (không đánh giá được độ trễ thật).

## ADR-009: Tuân thủ là ràng buộc kiến trúc
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt
- **Quyết định:** (1) Mọi nội dung live được sinh realtime; không có đường phát video quay sẵn tới Shopee. (2) Nhãn "AI" được ghép vào frame
  trong pipeline. (3) Mỗi AI host gắn với đúng một tài khoản. (4) Phải có văn bản đồng ý về hình và giọng của người mẫu. (5) Kiểm tra license
  trước khi thương mại hóa. (6) Video dự phòng chỉ dùng cho demo ngoài Shopee.
- **Lý do:** Đây là chính sách Shopee và yêu cầu pháp lý/đạo đức. Vi phạm có thể làm khóa tài khoản khách.
- **Phương án đã loại:** Đặt nhãn AI trong OBS (dễ quên hoặc mất khi đổi scene).

## ADR-010: Quản lý secret và phiên Shopee
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt (cơ chế mã hóa: Đề xuất)
- **Quyết định:** Secret chỉ để trong `.env` (có `.env.example`, `.env` bị gitignore). Phiên đăng nhập Shopee của khách được lưu mã hóa,
  chỉ trên máy chạy, và khóa giải mã không nằm cùng file.
- **Lý do:** Lộ phiên Shopee nghĩa là lộ tài khoản bán hàng của khách.
- **TODO:** Dùng cơ chế nào: Fernet với khóa trong `.env`, Windows DPAPI hay OS keyring? Máy chạy giai đoạn 2 là Windows hay Linux?

## ADR-011: Quy ước ngôn ngữ trong code và tài liệu
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt; **phần comment/docstring thay thế bởi ADR-022** (2026-10-30)
- **Quyết định:** Tên biến, hàm, file, class và commit dùng tiếng Anh. Tài liệu, docstring và comment giải thích dùng tiếng Việt có dấu.
- **Lý do:** Code tương thích hệ sinh thái và thư viện. Tài liệu dễ đọc cho đội và khách Việt.
- **Phương án đã loại:** Toàn bộ tiếng Anh (khó cho người vận hành và khách); đặt tên định danh tiếng Việt không dấu (khó đọc, dễ nhầm).

## ADR-012: Quản lý môi trường bằng uv, Python 3.10
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt; **phiên bản Python đổi thành 3.12 theo ADR-020** (2026-10-30)
- **Quyết định:** Dùng uv để cài Python, tạo venv và quản lý dependency. Python được pin `3.10` trong `.python-version` (file này được commit).
  Lệnh chạy dạng `uv sync` và `uv run ...`.
- **Lý do:** Một công cụ lo cả phiên bản Python lẫn dependency, có lockfile, cài nhanh; dựng lại môi trường giống hệt nhau trên laptop và RunPod.
- **Phương án đã loại:** pip + venv (không có lockfile chuẩn, phải tự cài Python); conda (nặng, chậm, không cần thiết).
- **TODO:** (chuyển sang ADR-020) Phiên bản Python của fork LiveTalking quyết định riêng ở feature 005.

## ADR-013: Quy trình Spec-Driven Development theo spec-kit, dùng bản tự dựng
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt
- **Quyết định:** Áp dụng quy trình của github/spec-kit gồm constitution → specify → clarify → plan → tasks → analyze → implement,
  bằng các lệnh tự viết `/sdd.*` trong `.claude/commands/`. Bố cục thư mục giống spec-kit (`.specify/memory`, `.specify/templates`,
  `specs/NNN-slug/`). Hiến pháp v1.0.0 được rút từ các ràng buộc bắt buộc của dự án. Mỗi bước dừng lại cho người dùng duyệt.
- **Lý do:** Dự án có nhiều ràng buộc cứng (tuân thủ Shopee, độ trễ, license) nên cần cổng kiểm tra trước khi code. Template viết
  tiếng Việt và gắn với ADR, ROADMAP, RISKS sẵn có. Có thêm khái niệm riêng của dự án như đánh dấu task `[GPU]` để gom việc RunPod.
  Không cần chạy CLI bên ngoài (lần thử chạy `specify` qua uvx bị chặn bởi quyền auto mode).
- **Phương án đã loại:** Cài CLI `specify` chính thức (template tiếng Anh và chung chung, có thể ghi đè file, phải xác minh cách
  `init` hoạt động; vẫn chuyển sang được sau vì bố cục tương thích); làm việc không có spec (dễ trôi phạm vi, khó kiểm tuân thủ).

## ADR-014: Nội dung sản phẩm là file Word theo mẫu, đọc bằng python-docx
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt 2026-10-30, người dùng giao chọn theo đề xuất sau `/sdd.analyze` (spec 001, `specs/001-local-reply-pipeline/research.md` R1–R2)
- **Quyết định:** Nguồn nội dung sản phẩm là file `.docx` theo mẫu cố định (`Heading 1` = sản phẩm, `Heading 2` = mục), đọc bằng
  `python-docx` (dependency mới, kéo theo `lxml`). Nội dung giữ trong bộ nhớ dạng catalog bất biến; thay nội dung giữa phiên là nạp
  file mới, kiểm hết lỗi rồi mới đổi. Không dùng JSON/SQLite làm nguồn ở giai đoạn demo. Mô hình `Product` thêm `variants`
  (phân loại kèm giá), `intro` (bài giới thiệu), `link`; `price` thành tùy chọn khi có phân loại. Sửa ARCHITECTURE §2 khi implement xong.
- **Lý do:** Khách gửi tài liệu dạng Word và mình soạn lại theo mẫu (chốt khi clarify spec 001). Một file vừa là nguồn vừa là thứ khách
  đọc được. Ít sản phẩm (≤ 4) nên không cần DB.
- **Phương án đã loại:** Cho LLM đọc Word tự do rồi trích xuất (có thể bịa, spec cấm); chuyển Word sang JSON bằng tay (thêm một bước dễ lệch);
  đọc `.docx` bằng zip + XML tự viết (tốn công, dễ lỗi).
- **TODO:** Phiên bản `python-docx` tối thiểu có `iter_inner_content()`? Tên style heading trong file từ Word tiếng Việt, Google Docs, WPS?

## ADR-015: Toolchain dự án
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt 2026-10-30, người dùng giao chọn theo đề xuất sau `/sdd.analyze` (spec 001, research R3–R4)
- **Quyết định:** `pyproject.toml` quản lý bằng uv (ADR-012). Cấu hình bằng `pydantic-settings` (secret dùng `SecretStr`).
  Test: `pytest` + plugin anyio (đi kèm anyio, đã là dependency của FastAPI) + `httpx` cho `TestClient`; test gọi API thật đánh marker
  `live_llm` và bị loại khỏi lệnh mặc định. Lint/format: `ruff`. Log JSON bằng `logging` chuẩn với formatter tự viết và lớp che secret.
- **Lý do:** Giải TODO "pydantic-settings?" trong CLAUDE.md. Ít dependency nhất mà vẫn đủ: không thêm pytest-asyncio, structlog hay
  python-multipart (upload dùng raw body).
- **Phương án đã loại:** `pytest-asyncio` (thêm dependency khi anyio đã có sẵn); `structlog` (chưa cần); đọc `os.environ` tay (không kiểm kiểu);
  black + flake8 + isort (ba công cụ thay vì một).
- **TODO:** Có thêm kiểm kiểu tĩnh (mypy hoặc pyright) không, và từ lúc nào?

## ADR-016: Chế độ static: màn hình host là trang web, audio qua WebSocket
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt 2026-10-30, người dùng giao chọn theo đề xuất sau `/sdd.analyze` (spec 001, research R10)
- **Quyết định:** Với `AVATAR_MODE=static`, `StaticRenderer` gửi PCM16 tới trang `/host` qua WebSocket; trang phát bằng Web Audio,
  hiện ảnh avatar, phụ đề và nhãn AI (CSS, không có tùy chọn ẩn). Mốc `avatar_first_frame` = lúc server nhận ack `playback_started`
  của câu đầu. Trang có nút "Bắt đầu" để mở khóa âm thanh. Thay đổi interface so với ARCHITECTURE §3: `AvatarRenderer.speak` thêm
  tham số `text`; `CommentQueue.get` trả `QueuedComment`, thêm `snapshot()`; `ProductStore` thêm `catalog`, `replace()`, chưa làm
  `search()`; `ReplyEngine` chỉ có `reply()` (nhận `ProductCatalog`), `narrate()` để 004. Chi tiết ở `specs/001-local-reply-pipeline/contracts/`.
- **Lý do:** Không thêm dependency, chạy trên mọi laptop; đo được thời điểm âm thanh thực sự bắt đầu phát. Nhãn AI ghép vào frame
  (Điều I) thuộc feature 005 khi có frame video thật.
- **Phương án đã loại:** Phát audio bằng thư viện Python phía server (thêm dependency, không đo được phía người xem); WebRTC ngay từ 001
  (phức tạp, để 005).

## ADR-017: Guard đầu ra tất định theo từng câu trước TTS
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt 2026-10-30, người dùng giao chọn theo đề xuất sau `/sdd.analyze` (spec 001, research R8)
- **Quyết định:** Mỗi câu do LLM sinh đi qua `OutputGuard` trước khi đưa sang TTS. Guard chặn khi câu chứa khẳng định bị cấm
  (so chuỗi con trên bản chuẩn hóa, bỏ dấu) hoặc chứa số tiền không có trong tập số của file nội dung (cộng các khoảng giá tính sẵn).
  Bị chặn thì dừng lượt, đọc câu từ chối cố định và log `guard_blocked`. Guard bổ sung cho prompt, không thay prompt.
- **Lý do:** Ràng buộc 7 và "KHÔNG để LLM bịa giá" là bắt buộc; prompt không bảo đảm 100%. Kiểm tất định, test được không cần mạng.
- **Phương án đã loại:** Chỉ dựa vào prompt (không có lớp chặn cuối); dùng LLM thứ hai kiểm câu (thêm độ trễ và chi phí, không tất định).
- **TODO:** Số tiền viết bằng chữ ("hai trăm rưỡi") chưa được bắt; có cần không?

## ADR-018: LLM dùng Gemini API (free tier) qua SDK google-genai
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt nhà cung cấp (người dùng quyết định); model cụ thể: Đề xuất (spec 001, research R5).
  **Đổi bởi ADR-035:** Gemini xuống vị trí cuối trong chuỗi model; `GeminiReplyEngine` vẫn giữ làm adapter.
- **Quyết định:** `ReplyEngine` gọi Gemini API ở chế độ async streaming bằng SDK chính thức `google-genai` (Apache-2.0), dùng free tier.
  Key trong `GEMINI_API_KEY`. Model mặc định ban đầu `gemini-3.8-flash`, `thinking_level=low`; benchmark với `gemini-3.5-flash-lite`
  (bộ câu hỏi mẫu × 3 lần, p95 `llm_first_sentence`) rồi ghi kết quả vào đây. Giữ nguyên cách đưa toàn bộ nội dung sản phẩm vào prompt (ADR-005).
- **Lý do:** Có free tier nên không tốn tiền khi khách chưa đồng ý dùng sản phẩm (ADR-019). Adapter `ReplyEngine` giữ lõi pipeline không đổi;
  muốn quay lại Claude hay trả phí thì thêm adapter khác.
- **Điều kiện free tier** (https://ai.google.dev/gemini-api/terms, https://ai.google.dev/gemini-api/docs/pricing): Google dùng dữ liệu gửi lên
  để cải thiện sản phẩm và có thể có người duyệt đọc; không gửi thông tin nhạy cảm, bí mật hay cá nhân. Giới hạn tần suất theo project,
  xem trong AI Studio (https://ai.google.dev/gemini-api/docs/rate-limits). Xem rủi ro S7, Q11.
- **Phương án đã loại:** Claude API (trả tiền theo token ngay từ giai đoạn demo); Gemini trả phí (chưa cần ở 001); model mở chạy local
  (laptop 4 GB VRAM không đủ, thuê GPU thì tốn tiền).
- **TODO:** Trước feature 006 (comment YouTube thật, có tên và nội dung của người xem): dùng gói trả phí hay chấp nhận gửi lên free tier?
  Đây là điểm có thể phát sinh chi phí, phải hỏi người dùng theo ADR-019.
- **TODO:** Giới hạn tần suất thật (RPM/RPD) của từng model ứng viên: người dùng xem trong AI Studio sau khi tạo key.

## ADR-019: Chính sách chi phí trước khi khách đồng ý dùng sản phẩm
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt (người dùng yêu cầu)
- **Quyết định:** Trong giai đoạn chưa có sản phẩm chính và khách chưa đồng ý dùng, mọi bước cần trả tiền (API trả phí, gói trả phí, thuê GPU,
  mua license, dịch vụ đám mây...) phải được **báo người dùng trước khi làm**, kèm chi phí ước tính và phương án miễn phí hoặc rẻ hơn nếu có.
  Ưu tiên lựa chọn miễn phí khi chất lượng đủ cho demo. Spec, plan và ADR nêu rõ chỗ nào có thể tốn tiền.
- **Lý do:** Chưa có doanh thu; khách chỉ trả tiền sau khi xem demo ổn (ADR-001, ADR-002).
- **Các điểm có thể tốn tiền đã biết:** TTS ở feature 003 (ElevenLabs trả phí; model mở miễn phí nhưng có thể cần GPU); thuê GPU RunPod ở
  feature 005; xử lý comment thật ở feature 006 (free tier Gemini không hợp với dữ liệu cá nhân, xem ADR-018).
- **Phương án đã loại:** Tự chọn dịch vụ trả phí khi thấy tốt hơn rồi báo sau.

## ADR-020: Nâng Python của app từ 3.10 lên 3.12
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt 2026-10-30, chọn 3.12 (người dùng giao chọn theo đề xuất sau `/sdd.analyze`; spec 001, research R5)
- **Quyết định:** Đổi `.python-version` thành `3.12` cho app (`ai_live`). Fork LiveTalking ở feature 005 chạy môi trường riêng,
  phiên bản Python của nó quyết định riêng.
- **Lý do:** `google-genai` 2.34.0 (2026-10-29) yêu cầu Python ≥ 3.11 (https://github.com/googleapis/python-genai/pull/3215,
  https://pypi.org/project/google-genai/). Python 3.10 hết hỗ trợ tháng 10/2026. Chưa có code nên đổi bây giờ không tốn công sửa.
- **Phương án bị loại:** Giữ Python 3.10 và ghim `google-genai<2.34` (không nhận bản sửa lỗi mới của SDK).
- **TODO:** Nếu fork LiveTalking ở 005 bắt buộc chạy chung môi trường với app thì phải kiểm tra lại nó có chạy được trên 3.12 không.

## ADR-021: Đóng gói thành app desktop cài trên Windows, làm sau demo
- **Ngày:** 2026-10-30 · **Trạng thái:** Đề xuất (người dùng chốt hướng: cả hai đối tượng theo giai đoạn, làm sau demo thành feature riêng)
- **Quyết định:** Sản phẩm cuối là app desktop cài được, không deploy server lên cloud (AWS…).
  - Giai đoạn demo và pilot (M1–M2): chạy bằng trình duyệt như hiện tại, trên máy vận hành của mình.
  - Sau khi khách duyệt demo: một feature riêng (đi đủ quy trình SDD) đóng gói app desktop, cài trên máy vận hành của mình trước.
  - Giai đoạn sau: mở cho khách tự cài trên máy họ. Khi đó phải sửa `docs/PRD.md` vì mô hình chuyển từ "làm hộ" sang có bán phần mềm.
  - Lõi pipeline (FastAPI + trang host/điều khiển) giữ nguyên; app desktop chỉ là vỏ cửa sổ mở các trang đó và đóng gói Python.
  - Chưa biết máy khách dùng hệ điều hành gì, nên chưa chọn nền tảng. Từ giờ lõi không được phụ thuộc hệ điều hành:
    - Dùng `pathlib`, không ghi cứng đường dẫn Windows.
    - Phần nào khác nhau giữa các hệ điều hành (lưu secret, virtual cam, ffmpeg) thì viết thành adapter.
    - Hỏi khách sau buổi demo.
- **Lý do:** Phiên Shopee của khách phải lưu mã hóa và chỉ nằm trên máy chạy (ràng buộc 6), nên chạy trên máy cục bộ hợp hơn server cloud.
  Không tốn tiền server. Kiến trúc hiện tại (server local + trang web) bọc thành desktop được mà không sửa lõi.
- **Phương án bị loại:** Deploy server lên cloud (AWS…) cho khách truy cập: phải giữ phiên Shopee của khách trên server, thêm chi phí và bảo mật.
- **TODO:** Chọn vỏ desktop (pywebview, Tauri hay Electron) và công cụ đóng gói Python (PyInstaller hay Nuitka)?
- **TODO:** Máy không có GPU mạnh thì khâu avatar realtime chạy ở đâu: avatar API ngoài (`docs/VENDORS.md`), GPU thuê, hay yêu cầu máy có GPU?
- **TODO:** Khi khách tự cài: cập nhật app, license/kích hoạt, và cách khóa avatar + giọng theo đúng 1 shop (ràng buộc 3) trên máy khách?
- **TODO:** Khi khách tự cài có cần bản macOS không? Nếu có:
  - Phải build riêng trên máy Mac, vì PyInstaller và Nuitka không build chéo.
  - Mac không có CUDA nên khâu avatar realtime phải chạy ngoài máy.
  - Phải ký và notarize app với Apple Developer ID, mất phí hằng năm; bản Windows cũng nên ký code để không bị SmartScreen cảnh báo, cũng có phí.
  - Báo chi phí trước (ADR-019).

## ADR-022: Comment, docstring và file context AI viết tiếng Anh
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt (người dùng yêu cầu). Thay một phần ADR-011.
- **Quyết định:**
  - Comment và docstring trong code viết **tiếng Anh**, cùng với định danh, tên file và commit như trước.
  - Chỉ áp dụng cho code mới và code đang sửa. Comment tiếng Việt cũ được dịch khi sửa tới file đó, không dịch hàng loạt.
  - File context cho AI viết tiếng Anh: `CLAUDE.md`, `.claude/commands/*.md`, `.specify/memory/constitution.md` (lên 1.1.0)
    và phần hướng dẫn trong `.specify/templates/`.
  - Giữ tiếng Việt có dấu cho:
    - Tài liệu cho người đọc: `docs/`, `specs/`, khung đề mục của template.
    - Chữ người dùng thấy lúc chạy: trang UI, thông báo lỗi API, prompt và câu trả lời của LLM, văn bản TTS.
  - AI vẫn trả lời người dùng bằng tiếng Việt.
- **Lý do:** Người dùng yêu cầu. Code và context AI thống nhất một ngôn ngữ, hợp với hệ sinh thái thư viện.
  Tài liệu duyệt spec/plan vẫn tiếng Việt để chủ dự án đọc dễ.
- **Phương án đã loại:**
  - Dịch ngay toàn bộ khoảng 200 comment/docstring cũ: người dùng chọn chỉ áp dụng cho code mới.
  - Chuyển cả `docs/` và `specs/` sang tiếng Anh: khó duyệt cho chủ dự án.

## ADR-023: Lip-sync chạy tạm trên GPU laptop, chấp nhận nhân vật chậm
- **Ngày:** 2026-10-31 · **Trạng thái:** Đã chốt (người dùng yêu cầu). Thay một phần ADR-008. Hiến pháp Điều V đã sửa theo ADR-029.
- **Quyết định:**
  - Feature 005 (avatar nhép miệng) làm và chạy trước trên GPU laptop (GTX 1650 Ti 4 GB, driver 565.90), không thuê RunPod.
  - Người dùng chấp nhận nhân vật chậm: FPS thấp, độ phân giải mặt thấp, độ trễ có thể vượt mục tiêu < 5 giây.
  - Vẫn phải **sinh hình realtime** (ràng buộc số 1): chậm thì giảm FPS hoặc độ phân giải, không render trước rồi phát lại.
  - `AVATAR_MODE=static` giữ nguyên làm chế độ mặc định cho test và phát triển logic. Test pipeline vẫn chạy không cần GPU.
  - RunPod vẫn là phương án dự phòng khi laptop không đủ cho buổi demo với khách. Bật lại thì báo chi phí trước (ADR-019).
- **Lý do:** Người dùng yêu cầu. Không tốn tiền thuê GPU khi khách chưa đồng ý dùng (ADR-019).
- **Hệ quả:**
  - Số đo độ trễ trên laptop không đại diện cho máy demo thật. Mục tiêu < 5 giây (p95) đo lại khi có GPU mạnh hơn.
  - 4 GB VRAM: Wav2Lip có khả năng chạy được; MuseTalk nhiều khả năng không đủ. Chưa đo. **TODO:** benchmark trên laptop rồi
    ghi ADR chọn model (ADR-004). Xem ADR-041 (Đã chốt 2026-11-06): Wav2Lip, số đo ghi vào đó.
  - Laptop vừa chạy app, TTS vừa chạy lip-sync, nên có thể nóng máy và giật. Chạy thử 30 phút để xem.
  - Các điều kiện cũ vẫn áp dụng: văn bản đồng ý của người mẫu trước khi dùng ảnh và giọng; kiểm tra license LiveTalking và Wav2Lip
    (RISKS L1, L2); tải model hoặc thêm dependency cần ADR.
- **Phương án đã loại:** Thuê RunPod ngay (tốn tiền khi chưa có khách đồng ý); chờ mua GPU (vốn lớn).

## ADR-024: Hai nguồn giọng miễn phí: VieNeu-TTS (CPU, trên laptop) và Gemini TTS (free tier)
- **Ngày:** 2026-10-31 · **Trạng thái:** Đã chốt 2026-11-07 (người dùng duyệt cài `vieneu` và tải model VieNeu-TTS v3 Turbo về cache
  ngoài repo; spec 003, plan và research R1, R2, R7). Bổ sung ADR-006.
- **Quyết định:**
  - `TTS_PROVIDER` nhận `fake | vieneu | gemini`. Bỏ `elevenlabs` và `oss` khỏi cấu hình vì chưa có adapter. ElevenLabs vẫn là ứng viên
    trong `docs/VENDORS.md`.
  - `vieneu`: gói pip `vieneu` (Apache-2.0), model VieNeu-TTS v3 Turbo, backend ONNX trên **CPU** để không tranh 4 GB VRAM với lip-sync
    (ADR-023). Giọng nữ miền Nam có sẵn, không clone. **Dependency mới**, kéo theo `onnxruntime`, `numpy`. Model tải vào cache ngoài repo.
  - `gemini`: model Gemini TTS (mặc định `gemini-3.8-flash-tts`) qua SDK `google-genai` và `GEMINI_API_KEY` đã có (ADR-018).
    Không thêm dependency. Chỉ gửi chữ cần đọc.
  - Protocol `TTSEngine` thêm `async def warm_up()` để nạp model trước phiên.
  - Nguồn mặc định: chọn sau khi so sánh theo SC-006 của spec 003, ghi bổ sung vào ADR này. **Người dùng chọn trước 2026-11-07:
    `vieneu` mặc định, `gemini` dự phòng** (lý do: Gemini từng lỗi 503 quá tải ở bước LLM (ADR-034), hạn mức free thấp (RISKS Q12),
    điều khoản thương mại chưa rõ (RISKS L9)). SC-006 vẫn chạy để xác nhận. Dependency và việc tải model đã duyệt 2026-11-07.
- **Lý do:** Spec 003 FR-003 yêu cầu hai nguồn miễn phí, một chạy laptop, một dịch vụ ngoài. Ưu tiên miễn phí (ADR-019).
  VieNeu có license Apache-2.0 và giọng có sẵn cho dùng thương mại; Gemini dùng lại SDK và key.
- **Điều kiện cần biết:** Gemini free tier dùng dữ liệu gửi lên để cải thiện sản phẩm (như ADR-018, RISKS S7). Giới hạn RPM/RPD của
  model TTS chưa biết (RISKS Q12). Gói trả phí của Gemini TTS ($0.50 / 1M token chữ, $9.00 / 1M token tiếng) **không** dùng khi chưa
  hỏi người dùng.
- **Phương án đã loại:**
  - Azure Speech F0 (0,5 triệu ký tự/tháng): cần tài khoản và SDK mới.
  - ElevenLabs free (10 nghìn ký tự/tháng): quá ít cho phiên 30 phút.
  - FPT.AI: không stream (trả đường dẫn file).
  - VieNeu trên GPU: tranh VRAM với lip-sync, thêm torch.
- **Ghi chú khi cài (2026-11-07, `/sdd.implement 003` T001–T002; chi tiết ở research R1 của spec 003):**
  - `vieneu` 3.8.3 kéo theo nhiều hơn `onnxruntime`, `numpy`: `gradio`, `librosa` (kèm `numba`, `scikit-learn`, `scipy`), `pandas`,
    `huggingface-hub`, `sea-g2p`, `soundfile`, `soxr`, `tokenizers`, `kaldi-native-fbank`. Không có `torch` hay gói GPU. Code dự án chỉ
    gọi `vieneu` và `numpy`; `soxr` có sẵn nhưng không dùng trực tiếp (ADR-025 vẫn hạ tần số bằng numpy).
  - Dung lượng model: 581 MB. Lưu ở thư mục riêng `VIENEU_MODEL_CACHE` (mặc định `~/.cache/ai-live/hf`), adapter đặt
    `HF_HUB_DISABLE_SYMLINKS=1` trước khi import `vieneu`, vì `onnxruntime` 1.31 không nạp được model từ cache symlink của
    `huggingface-hub` 2.x. Người dùng duyệt cách này 2026-11-07.
  - Tốc độ CPU đo trên laptop (6 luồng, giọng `Thục Đoan`): nạp model 5–6 s, đoạn tiếng đầu 0,32–0,41 s, hệ số thời gian thực 0,6–0,76.
- **Giọng VieNeu mặc định (2026-11-09, T049 của spec 003):** `Thùy Dung` thay cho `Thục Đoan` (tạm). Người dùng nghe `Thục Đoan`
  đọc "nắng" thành "nứng" (G2P đúng, lỗi ở bước sinh tiếng); `Thùy Dung` nghe rõ nhất trong 4 giọng nữ miền Nam. 4 luồng CPU: p95
  đoạn tiếng đầu 0,405 s (research R1 và bảng kết quả T049).
- **Đoạn mẫu giọng `VIENEU_REF_AUDIO` (2026-11-09, T049 của spec 003):** người dùng muốn cố định vân giọng `Thùy Dung` theo một
  lần đọc nghe rõ nhất (`D_ThuyDung_lan2`, 2,4 s, do chính giọng có sẵn đọc, không phải người thật nên không cần giấy đồng ý). Adapter
  mã hóa đoạn mẫu một lần lúc warm-up bằng bộ mã hóa đã có trong cache, ghép với `speaker_emb` của giọng có sẵn. Không thêm thư
  viện, không tải model (đường nhân bản giọng chính thức cần tải `speaker_encoder.onnx` nên không dùng). Rủi ro: dùng hàm nội bộ
  `engine._encode_ref_wav` của `vieneu`, có thể đổi khi nâng phiên bản; khi đó adapter báo `config_error` rõ ràng, bỏ trống biến
  để quay về giọng có sẵn. File để ngoài git (`~/.cache/ai-live/voices/`). Đo 20 lượt, 4 luồng: p95 đoạn tiếng đầu 0,516 s.
- **Kết quả so sánh và chốt nguồn (2026-11-09, T049 của spec 003):** người dùng xác nhận `vieneu` mặc định, `gemini` dự phòng (đổi
  tay bằng `TTS_PROVIDER`). VieNeu: 20/20 lượt, p95 đoạn tiếng đầu 0,516 s (giọng `Thùy Dung` + đoạn mẫu), người dùng nghe ổn,
  không tốn hạn mức. Gemini: chỉ đo đơn lẻ (T044, T045) 3,5–4,1 s, không đạt SC-003 (≤ 1,0 s); không đo đủ 20 lượt để giữ hạn mức.
  `TTS_PROVIDER` trong code và `.env.example` vẫn mặc định `fake` cho test; máy chạy phiên đặt `vieneu` trong `.env`. Bảng đầy đủ ở
  research của spec 003.
- **Giới hạn free tier Gemini TTS (2026-11-10, T048 của spec 003):** `gemini-3.8-flash-tts` 3 RPM, 10K TPM, 10 RPD (gói miễn phí, project `AIStreamming`, người dùng xem AI Studio 2026-11-10; dùng cao nhất 28 ngày: 2 RPM, 58 TPM, 7 RPD).
  Một câu là một request, nên 10 RPD chỉ đủ vài phút phát; Gemini dự phòng chỉ để thử và cầm cự vài câu, không chạy hết phiên.
  Muốn Gemini thành dự phòng thật thì cần gói trả phí: hỏi người dùng trước, chưa dùng.
- **TODO:** Tốc độ VieNeu khi chạy cùng lip-sync (SC-006 của spec 003)?

## ADR-025: Tiếng TTS là PCM16 mono 16 kHz; chuẩn hóa chữ tự viết trước mọi nguồn giọng
- **Ngày:** 2026-10-31 · **Trạng thái:** Đã chốt 2026-11-07 (người dùng duyệt; spec 003, research R3, R4, R5)
- **Quyết định:**
  - Mọi adapter `TTSEngine` trả PCM16 little-endian, mono, 16 kHz (`TTS_SAMPLE_RATE=16000`). Adapter tự đổi định dạng nếu nguồn trả
    khác (VieNeu 48 kHz float32 → hạ 3:1 bằng numpy). Giải TODO ở `docs/ARCHITECTURE.md` §3.
  - Chuẩn hóa chữ (số, giá, khoảng giá, %, đơn vị, viết tắt) là hàm thuần tự viết theo cách đọc miền Nam ("ngàn", "lẻ"), chạy trong lớp
    bọc `SpeechTTS` mà `create_tts()` luôn trả về. Phụ đề giữ chữ gốc. Viết tắt ở `data/rules/tts_abbreviations.json`.
- **Lý do:** Wav2Lip, MuseTalk và LiveTalking dùng tiếng 16 kHz; trang host 001 đã chạy 16 kHz. Thư viện chuẩn hóa có sẵn thường đọc
  theo miền Bắc; hai nguồn giọng phải đọc số giống nhau để so sánh công bằng. Lớp bọc giữ lõi pipeline không đổi.
- **Phương án đã loại:** Để renderer tự hạ tần số; gói `soxr` (dependency mới, chỉ xét nếu nghe thấy rè); gói `vinorm`; nhờ LLM viết
  sẵn chữ đọc (phá guard chặn giá bịa).

## ADR-026: Tạm không đọc chat để trả lời người xem; AI host chỉ giới thiệu sản phẩm theo kịch bản sinh realtime
- **Ngày:** 2026-10-31 · **Trạng thái:** Đã chốt (người dùng yêu cầu). Hoãn phần đọc comment của ADR-002, ADR-007; đổi thứ tự feature M1.
  Tiêu chí PRD §3 số 2–3 đã chốt lại khi làm rõ spec 004 (2026-11-01); hiến pháp Điều VI đã sửa theo ADR-029.
- **Quyết định:**
  - Hiện tại **không làm** tính năng đọc chat để trả lời người xem khi live: không làm `YouTubeChatSource` (phần đọc comment của 006),
    không làm `ShopeeSource`.
  - AI host chỉ **nói kịch bản giới thiệu sản phẩm**, vẫn sinh realtime từ dữ liệu sản phẩm (ràng buộc số 1, số 7). Feature
    `004-show-director` thành feature chính tiếp theo sau 003 và 005.
  - Code đã có của 001 (mock comment, hàng đợi, trả lời, guard, đo độ trễ) **giữ nguyên, không xóa**. Guard chặn giá bịa vẫn dùng cho kịch
    bản. Mock comment trên trang điều khiển còn dùng làm công cụ thử cho 003 và 005.
  - Các task chưa xong của 001 tạm dừng cho tới khi người dùng mở lại phần trả lời comment.
- **Lý do:** Người dùng đã xem các AI live trên Shopee: không có công cụ nào trả lời chat. Bỏ phần này giúp demo đơn giản hơn và không
  phải gửi tên, nội dung comment của người xem lên Gemini free tier (TODO ở ADR-018).
- **Hệ quả:**
  - Tiêu chí demo trong `PRD.md` §3 số 2 (trả lời đúng ≥ 8/10 câu hỏi) và số 3 (độ trễ comment → nói < 5 giây) không còn áp dụng.
    TODO: chốt tiêu chí thay thế cho phần kịch bản với người dùng.
  - Hiến pháp Điều VI (độ trễ comment → avatar < 5 giây) cần sửa qua `/sdd.constitution`, gộp cùng lần sửa Điều V (ADR-023).
  - Spec 003 và 005 dùng comment mock để thử giọng và nhân vật; vẫn chạy được với code 001 hiện có.
  - Host nói liên tục thay vì chỉ nói khi có comment, nên số câu cần đọc trong phiên 30 phút tăng nhiều. Gemini TTS free tier càng dễ hết
    hạn mức (RISKS Q12); VieNeu chạy trên laptop càng có lợi (ADR-024).
- **Phương án đã loại:** Làm tiếp `YouTubeChatSource` cho demo (người dùng thấy thị trường không cần); xóa code trả lời comment của 001
  (đã chạy được, có thể cần lại sau).

## ADR-027: Làm thẳng trên branch `main`, không tách branch theo feature
- **Ngày:** 2026-10-31 · **Trạng thái:** Đã chốt (người dùng yêu cầu). Sửa phần "Branch git trùng tên" trong quy trình của ADR-013.
- **Quyết định:** Mọi việc commit thẳng lên `main`. `/sdd.specify` không còn tạo branch `NNN-slug`; header spec ghi `Branch: main`.
  Vẫn chỉ commit khi người dùng yêu cầu.
- **Lý do:** Một người làm, chưa có remote; tách branch chỉ thêm bước merge. Commit đầu tiên (198a6d4) đã được đổi tên branch thành `main`.
- **Phương án đã loại:** Giữ branch theo feature như spec-kit (thừa khi chỉ có một người làm và không có review qua PR).

## ADR-028: Gom tiến độ vào thư mục `progress/`; lệnh và sub-agent đọc ở đó trước
- **Ngày:** 2026-10-31 · **Trạng thái:** Đã chốt (người dùng yêu cầu).
- **Quyết định:**
  - Thư mục `progress/` gồm `README.md` (file nào giữ sự thật nào, bảng "khi đổi X thì rà Y", giao thức cho lệnh), `STATUS.md`
    (ảnh chụp hiện tại dạng `key: giá trị`), `FEATURES.md` (sổ feature: bảng tổng + thẻ từng feature), `OPEN.md` (câu hỏi và quyết
    định chờ người dùng), `LOG.md` (nhật ký chỉ ghi thêm).
  - Bảng trạng thái feature chuyển từ `specs/README.md` sang `progress/FEATURES.md`; `specs/README.md` chỉ còn trỏ sang.
  - Các lệnh `/sdd.*`, `/update-context` đọc `STATUS.md` và thẻ feature trước, cuối lệnh cập nhật `progress/`. Sub-agent `ai-*` chỉ
    đọc, không sửa. `/sdd.analyze` được ghi kết luận vào dòng `analyze` của thẻ (ngoại lệ duy nhất của bước chỉ đọc).
  - Nguồn gốc vẫn là `spec.md`, `tasks.md`, `DECISIONS.md`, `ROADMAP.md`, hiến pháp; `progress/` chỉ tóm tắt và trỏ link.
- **Lý do:** Tiến độ đang rải ở ROADMAP, `specs/README.md`, từng `tasks.md`, ADR và các `TODO:`; lệnh và agent phải dò nhiều file.
  Một chỗ có link chéo giúp rà soát khi có thay đổi và giảm việc đọc thừa.
- **Phương án đã loại:** Để nguyên `specs/README.md` làm danh mục (không có chỗ cho câu hỏi chờ, phụ thuộc, nhật ký); chép toàn bộ
  ROADMAP vào `progress/` (hai nguồn sự thật dễ lệch).

## ADR-029: Sửa hiến pháp 1.1.0 → 1.2.0 (Điều V, VI, VIII) theo ADR-023 và ADR-026
- **Ngày:** 2026-11-01 · **Trạng thái:** Đã chốt (người dùng duyệt qua `/sdd.constitution`). Bản tăng MINOR (mở rộng điều khoản,
  không nới Điều I, II).
- **Quyết định:**
  - **Điều V:** việc GPU (lip-sync) kiểm bằng kịch bản tay trong `quickstart.md`, chạy trước trên GPU laptop (ADR-023: chấp nhận FPS
    và độ phân giải thấp, vẫn sinh realtime, không render trước). RunPod chỉ là phương án dự phòng: gom task `[GPU]` và xin người
    dùng duyệt chi phí trước khi bật pod.
  - **Điều VI:** hai mục tiêu thay cho một. Show kịch bản (nội dung chính, ADR-026): từ lúc bấm "Bắt đầu" đến câu đầu phát ra ≤ 5 giây,
    khoảng lặng giữa hai câu liền nhau p95 ≤ 1,5 giây, không lần nào > 5 giây (trừ lúc tạm dừng và lỗi cố ý gây ra). Trả lời comment
    (mock hiện tại, chat thật sau này): comment nhận được → avatar bắt đầu nói < 5 giây p95, ngân sách từng tầng ở `ARCHITECTURE.md` §4.
    Mục tiêu được đo trên máy và chế độ dùng cho demo; số đo lip-sync trên laptop (ADR-023) chỉ để tham khảo và phải đo lại ở đó.
  - **Điều VIII:** câu trong kịch bản mang `segment_id` và dùng mốc `segment_requested` thay cho `comment_received`; ghi log khoảng
    lặng giữa hai câu liền nhau.
- **Lý do:** Hiến pháp 1.1.0 viết trước ADR-023 (bắt việc GPU chạy RunPod) và ADR-026 (chỉ đo độ trễ comment, trong khi nội dung chính
  giờ là kịch bản). Spec 004 sau khi làm rõ (SC-002, SC-011, FR-022) cần đúng các mục tiêu này để qua cổng hiến pháp ở `/sdd.plan`.
- **Ảnh hưởng:** `plan-template.md`, `spec-template.md`, `tasks-template.md`, lệnh `/sdd.plan`, `/sdd.tasks`, `WORKFLOW.md` đồng bộ
  theo. Feature 003 (Planned) có task `[GPU]`/RunPod cần rà lại khi làm tasks; feature 005 chạy trên laptop trước.
- **Phương án đã loại:** Giữ một mục tiêu < 5 giây cho mọi câu (không đo được show kịch bản vì không có comment); ghi ngoại lệ vào bảng
  "Theo dõi độ phức tạp" của từng plan (lặp lại ở mọi feature, dễ lệch); bỏ hẳn RunPod khỏi Điều V (vẫn cần khi laptop không đủ).

## ADR-030: Thêm `narrate()` vào Protocol `ReplyEngine` cho câu kịch bản
- **Ngày:** 2026-11-01 · **Trạng thái:** Đã chốt 2026-11-01 (người dùng duyệt ngầm khi yêu cầu chạy tiếp `/sdd.tasks 004`); plan 004, research R3.
- **Quyết định:** `ReplyEngine` có thêm `narrate(request: SegmentRequest, catalog: ProductCatalog) -> AsyncIterator[str]`, yield từng câu
  hoàn chỉnh như `reply()`. `GeminiReplyEngine` dùng chung client, bộ tách câu, ánh xạ lỗi và log `llm_usage`; chỉ khác prompt
  (`brain/script_prompt.py`) và `SCRIPT_MAX_TOKENS`. `FakeReplyEngine` có kịch bản `narrate` cho test. Sửa dòng ghi chú
  `narrate(segment_hint, catalog)` ở `ARCHITECTURE.md` §3 thành chữ ký trên.
- **Lý do:** Điều IV liệt kê `ReplyEngine`, không có `ScriptEngine`; hai đường dùng chung khoảng 90% mã. Đổi nhà cung cấp LLM chỉ cần
  sửa một adapter.
- **Phương án đã loại:** Protocol `ScriptEngine` riêng (thêm một mục vào Điều IV và một factory, lặp mã).

## ADR-031: Mở rộng guard (link, phần trăm lạ, cụm cơ chế nền tảng) và làm sạch ký hiệu trước guard, cho cả hai đường
- **Ngày:** 2026-11-01 · **Trạng thái:** Đã chốt 2026-11-01 (người dùng duyệt ngầm khi yêu cầu chạy tiếp `/sdd.tasks 004`); plan 004, research R9. Mở rộng ADR-017.
- **Quyết định:**
  - `brain/sanitize.py` `clean_spoken()`: bỏ ký hiệu đầu dòng, `#`, `**`/`__`, emoji trước guard. Chữ đã làm sạch là chữ đọc và phụ đề.
  - `OutputGuard` thêm `unknown_percent`, `link`, `platform_phrase` (danh sách ở `data/rules/platform_phrases.txt`, cụm có trong file
    nội dung thì được phép). Thứ tự: `forbidden_claim` → `unknown_amount` → `unknown_percent` → `link` → `platform_phrase`.
  - Áp dụng cho cả câu kịch bản và lời trả lời comment. Câu kịch bản bị chặn thì chỉ bỏ câu đó; đường comment giữ cách của 001.
  - Vì đổi đường comment, Điều III bắt chạy lại bộ 10 câu hỏi mẫu và bộ câu gài của 001; điểm không được thấp hơn lần trước.
- **Lý do:** Số tiền, phần trăm, link và cơ chế nền tảng là thông tin sai, phải chặn tất định (ADR-017). Ký hiệu định dạng chỉ là lỗi
  hình thức nên làm sạch, không chặn.
- **Phương án đã loại:** Chỉ dặn trong prompt (không tất định); chặn câu có ký hiệu (mất câu đúng); LLM thứ hai chấm (tốn hạn mức, thêm
  độ trễ).
- TODO: người dùng duyệt danh sách `platform_phrases.txt` ban đầu.

## ADR-032: Cấu trúc show kịch bản trong `ShowDirector`
- **Ngày:** 2026-11-01 · **Trạng thái:** Đã chốt 2026-11-01 (người dùng duyệt ngầm khi yêu cầu chạy tiếp `/sdd.tasks 004`); plan 004, research R1, R2, R7, R8.
- **Quyết định:**
  - `ShowDirector` vẫn là bộ điều phối phiên duy nhất. Thêm `director/segment_planner.py` (thuần, xoay vòng chủ đề),
    `director/script_runner.py` (ba tầng: sinh chữ đi trước một phân đoạn, tạo tiếng đi trước tối đa 2 câu, phát),
    `director/show_stats.py` (khoảng lặng, tỷ lệ sản phẩm, câu trùng).
  - Mỗi câu kịch bản là một `Utterance` riêng có `segment_id`. `Utterance.comment_id` thành optional; đúng một trong hai trường có giá trị.
  - Khóa "quyền nói" `_floor` dùng chung: kịch bản giữ cho từng câu, lượt trả lời comment giữ cả lượt ở tầng phát. LLM của lượt comment
    chạy ngay, không chờ câu kịch bản nói xong.
  - Tạm dừng: tiếng đã tạo mà chưa phát bị bỏ, chữ được giữ; khi tiếp tục thì tạo tiếng lại (Điều I).
- **Lý do:** Tên và vai trò `ShowDirector` đã dùng ở 001, ADR-026, ROADMAP. Một bộ điều phối thì không có hai bên tranh renderer và lệnh
  điều khiển chỉ đi một nơi. Tách planner để test không cần asyncio (Điều V).
- **Phương án đã loại:** Dồn hết vào `show_director.py` (đã 513 dòng); class `ScriptDirector` chạy song song (cần lớp phân xử renderer);
  giữ tiếng qua lúc tạm dừng (giống phát lại bản đã dựng).

## ADR-033: Chốt các quyết định ở checkpoint US1 của 004
- **Ngày:** 2026-11-01 · **Trạng thái:** Đã chốt 2026-11-01 (người dùng: "ok đồng ý hết").
- **Quyết định:**
  - Duyệt câu chữ `SCRIPT_RULES` (`brain/script_prompt.py`) và 26 cụm trong `data/rules/platform_phrases.txt` làm bản đầu (004 research R4, R9).
  - `POST /api/show/start` kiểm show đang chạy trước kiểm host: host ngắt khi show đang chạy thì trả `already_running: true`, không trả
    `409 host_unavailable`. Show vẫn `running`, câu bị bỏ với lỗi `render` như data-model §3 (004).
  - `GET /api/show` trả `null` trước lần bắt đầu show đầu tiên.
  - Thêm `drop_reason` `segment_discarded` (câu chưa phát của phân đoạn bị bỏ vì đổi nội dung) và ghi rõ `sentence_count_exceeded`.
  - `ShowSummary.sentences.spoken` gồm cả câu dự phòng; thêm `render_error`, `interrupted` và `secondary_coverage[].window_end_s`.
    `segment_next` có thêm `segment_id`.
  - Lệnh `python -m ai_live.brain narrate`: `opening`/`closing` không nhận `--product`, chủ đề sản phẩm bắt buộc `--product`; câu bị guard
    chặn thì in ra rồi dừng phân đoạn, không có câu từ chối.
- **Lý do:** Bấm "Bắt đầu show" lần nữa không được làm mất show đang chạy; trạng thái host đã hiện riêng trên trang điều khiển. Các trường
  thêm có sẵn trong code sau US1 và giúp đọc log; ghi lại để contract khớp code.
- **Phương án đã loại:** Trả `409 host_unavailable` khi show đang chạy mà host ngắt (người vận hành dễ hiểu nhầm là show đã dừng).

## ADR-034: Cài freellmapi chạy local để quản lý nhiều key LLM miễn phí và làm bàn thử model
- **Ngày:** 2026-11-03 · **Trạng thái:** Đã chốt phần cài đặt (người dùng: "cài freellmapi đi vì hiện tôi muốn apply nhiều api token free
  khác"). Phần cho pipeline gọi qua freellmapi lúc live: Đề xuất, cần feature riêng (`/sdd.specify`). **Đổi bởi ADR-035:** đã chốt
  chuỗi model và adapter dùng lúc live.
- **Quyết định:**
  - Cài [freellmapi](https://github.com/tashfeenahmed/freellmapi) (MIT) bằng Docker Compose ở thư mục `~/freellmapi`, **ngoài repo** này.
    Chỉ nghe ở `127.0.0.1:3001` (mặc định `HOST_BIND`), không mở ra mạng LAN.
  - Key của từng nhà cung cấp do người dùng tự nhập trên dashboard `http://localhost:3001` (trang Keys); freellmapi mã hóa AES-256-GCM
    trong SQLite của nó. `ENCRYPTION_KEY` nằm trong `~/freellmapi/.env`, không vào repo này. Key chung `freellmapi-…` khi dùng sẽ để
    trong `.env` của project (tên biến chốt ở feature router).
  - Trước mắt dùng làm **bàn thử**: chạy benchmark (prompt, bộ tách câu, `qa_eval` reply + script của project) cho từng model qua một API
    OpenAI-compatible, chọn ra model đạt.
  - Lúc live chỉ gọi model **đã qua benchmark** và **ghim tên model** (không dùng `model="auto"`), để biết chắc host đang nói bằng model
    nào và giọng văn không đổi giữa show.
- **Lý do:** Benchmark 2026-11-02 (31 lần gọi mỗi model, cùng prompt và bộ chấm): Gemini `gemini-3.8-flash` lỗi 30/31 (503 quá tải,
  429 hết quota); Groq `qwen/qwen3.8-27b` 8/10 câu hỏi, 0 vi phạm kịch bản, câu đầu trung vị 0,54–0,56 s; `openai/gpt-oss-120b` 9/10,
  7 vi phạm (bịa giá 169.000đ, gọi "bạn"); `openai/gpt-oss-20b` 8/10, 15 vi phạm. Giới hạn chặt nhất của Groq là 200K token/ngày mỗi
  model (khoảng 1 giờ show), nên cần gom thêm nhà cung cấp miễn phí. freellmapi có sẵn quản lý key, đếm RPM/RPD/TPM/TPD theo từng
  key và model, chuyển model khi 429/5xx; tự viết adapter cho từng nơi chỉ để thử thì tốn công hơn.
- **Điều kiện và rủi ro:**
  - README ghi "Personal experimentation only", không SLA, độ trễ thay đổi, chất lượng giảm cuối ngày khi model tốt hết quota. Free tier
    của nhiều nhà cung cấp không cho dùng thương mại hoặc dùng dữ liệu gửi lên để train. TODO: kiểm điều khoản từng nhà cung cấp trước
    khi dùng cho khách thật (ràng buộc số 5).
  - Chỉ gửi dữ liệu sản phẩm và comment giả; không gửi dữ liệu cá nhân của người xem qua các nhà cung cấp chưa kiểm điều khoản.
  - Thêm Docker Desktop vào môi trường dev; dependency Python của project không đổi.
- **Phương án đã loại:** Script cài một dòng `curl … | bash` (chạy script tải từ mạng mà không đọc trước); bản desktop `.exe` (khó kiểm
  soát cổng và dữ liệu); `npm run dev` từ mã nguồn (chế độ dev, không phải cách chạy ổn định); để freellmapi chọn model tự động lúc live.

## ADR-035: `ReplyEngine` OpenAI-compatible qua freellmapi, chuỗi model ghim sẵn và tự chuyển khi lỗi
- **Ngày:** 2026-11-03 · **Trạng thái:** Đã chốt thứ tự model và hướng adapter (người dùng: "ok chốt thứ tự đó, sửa danh sách bạn rồi viết
  ADR-035"). Phần code: chưa làm. Người dùng chọn 2026-11-03: làm feature mới `008-llm-provider-chain` qua `/sdd.specify`, không sửa spec 004.
  Các bước LLM thật G1–G5 của 004 (T075–T079, research R14) chạy bằng engine này, không gọi Gemini trực tiếp; lần G1 bằng Gemini 2026-11-02 giữ làm lịch sử.
- **Quyết định:**
  - Thêm **một** adapter `ReplyEngine` nói chuyện với API Chat Completions kiểu OpenAI (stream SSE), dùng chung bộ prompt, `SentenceSplitter`,
    `OutputGuard` như `GeminiReplyEngine`. Chọn bằng `REPLY_ENGINE` (giá trị mới, tên chốt ở spec). Cùng một adapter gọi được freellmapi
    (`http://127.0.0.1:3001/v1`, ADR-034) hoặc gọi thẳng Groq / nhà cung cấp OpenAI-compatible khác, chỉ khác base URL và tên biến chứa key.
  - Cấu hình là **một chuỗi model theo thứ tự ưu tiên**, mỗi mục gồm endpoint, tên model ghim cứng (không `auto`) và tham số riêng
    (`reasoning_effort`). Thứ tự đã chốt (**đổi bởi ADR-040**: bỏ `gpt-oss-120b` vì không đạt SC-001 ở T055 của 008):
    1. `gemma-sea-lion-v4-27b` (Cloudflare Workers AI, qua freellmapi)
    2. `gpt-oss-120b` (Groq, qua freellmapi, `reasoning_effort: low`)
    3. Qwen3.8 27B (Groq gọi thẳng với `reasoning_effort: none`, hoặc IteraCompute qua freellmapi khi người dùng thêm key)
    4. Gemini (key Gemini trên dashboard freellmapi, hoặc `GeminiReplyEngine` sẵn có)
  - Tự chuyển xuống mục kế khi gặp 429, 5xx, hết giờ, hoặc stream không ra chữ nào (freellmapi trả 502 `empty_completion`). Chuyển chỉ ở
    **ranh giới một lượt gọi** (một câu trả lời hoặc một phân đoạn), không đổi model giữa chừng một phân đoạn. Mục bị lỗi nghỉ một
    khoảng rồi mới thử lại; khoảng nghỉ và cách quay lại mục 1 chốt ở spec. Hết cả chuỗi thì báo `ReplyEngineError` như hiện tại, để
    `ShowDirector` vào chế độ dự phòng (ADR-032).
  - Mỗi lượt gọi ghi log model và nhà cung cấp đã trả lời (cùng `utterance_id` / `segment_id`), để biết host đang nói bằng model nào.
  - `httpx` chuyển từ nhóm `dev` sang `dependencies` runtime trong `pyproject.toml` (đã có trong `uv.lock`, cùng bản `>=0.28.1`). Không
    dùng SDK `openai`: chỉ cần POST + đọc SSE, thêm SDK không đáng.
  - Key: `FREELLMAPI_KEY` (key chung của freellmapi) và `GROQ_API_KEY` nằm trong `.env` của project; key từng nhà cung cấp nằm trong
    freellmapi (ADR-034). Tên biến cho base URL và chuỗi model chốt ở spec.
- **Lý do:** Benchmark 2026-11-02 và 2026-11-03, cùng prompt, bộ câu hỏi `data/eval/demo_questions.json` (10 câu, ngưỡng 8) và
  `qa_eval script` (21 phân đoạn). Thời gian là giây tới câu đầu tiên:

  | Model / nhà cung cấp | Trả lời đúng | Vi phạm kịch bản | Câu đầu reply (trung vị / p95) | Câu đầu kịch bản (trung vị / p95) | Hạn mức free |
  |---|---|---|---|---|---|
  | SEA-LION v4 27B, Cloudflare (qua freellmapi) | 10/10, 0 lỗi | 6, đều là "nhiều bạn" / "những bạn" ở ngôi thứ ba; chấm lại theo luật mới (research R15 004): 0 | 1,17 / 2,40 | 0,97 / 2,81 (cả phân đoạn p95 5,62) | khoảng 50 neuron mỗi lượt kịch bản |
  | gpt-oss-120b, Groq (qua freellmapi) | 9/10 | 0 | 0,65 / 1,39 | 0,78 / 1,04 | 1K RPD, 200K TPD |
  | Qwen3.8 27B, Groq gọi thẳng (2026-11-02) | 8/10 | 0 | 0,56 / 0,96 | 0,54 / 1,40 | 1K RPD, 200K TPD |
  | Gemini `gemini-3.8-flash` (2026-11-02) | — | — | lỗi 30/31 lượt (503, 429) | — | theo project, xem ADR-018 |

  - SEA-LION đứng đầu vì đúng nhất và văn tiếng Việt tự nhiên nhất; câu đầu vẫn trong ngân sách Điều VI (≤ 5 s). Hai model Groq nhanh hơn
    nhưng kém hơn về độ đúng; gpt-oss-120b từng bịa giá 169.000đ và gọi "bạn" khi gọi thẳng Groq ngày 2026-11-02 (7 vi phạm), nên xếp sau.
  - Mỗi nơi free chỉ đủ khoảng 1 giờ show; ghép chuỗi thì các hạn mức cộng lại và một nơi quá tải không làm dừng show.
  - Overhead của freellmapi đo được không đáng kể so với thời gian model.
- **Điều kiện và rủi ro:**
  - freellmapi ép `reasoning_effort` của Groq về low/medium/high (`server/src/lib/sampling-params.ts`), nên Qwen qua freellmapi suy luận
    ngầm và hay ra 502 `empty_completion` (17/21 phân đoạn lỗi lần chạy 2026-11-03). Vì vậy Qwen gọi thẳng Groq hoặc qua IteraCompute.
  - Với một key mỗi nơi, một lỗi rỗng làm key nghỉ 2–9 phút trong freellmapi, kéo theo chuỗi 429 (lần chạy gpt-oss-120b lúc 03:05: 20/21
    phân đoạn lỗi). Đây là lý do cần chuỗi nhiều nhà cung cấp, không chỉ thử lại.
  - freellmapi gom các nhà cung cấp có **cùng tên model** thành một nhóm và tự chuyển trong nhóm; không ghim được nhà cung cấp chỉ bằng
    tên model.
  - Model khác nhau thì giọng văn khác nhau: khi show chuyển model, người xem có thể nhận ra. Ghi log để đo số lần chuyển trong một show.
  - TODO: hạn mức free thật của Cloudflare Workers AI (đang tin là 10.000 neuron/ngày, khoảng 200 lượt, khoảng 1–1,5 giờ show): người dùng
    xem trong dashboard Cloudflare.
  - TODO: IteraCompute: khuyến mãi miễn phí hết hạn 2026-11-24; giờ cao điểm phải xếp hàng; request giữ chỗ theo `max_tokens`; chưa đọc
    chính sách bảo mật. Kiểm trước khi đưa vào chuỗi.
  - TODO: điều khoản dùng dữ liệu và dùng thương mại của Cloudflare Workers AI, Groq, IteraCompute ở gói free (ràng buộc số 5, rủi ro S7,
    ADR-034). Trước mắt chỉ gửi dữ liệu sản phẩm và comment giả.
  - Mỗi model mới vào chuỗi phải chạy lại cùng benchmark (reply + `qa_eval script`) và đạt ngưỡng trước khi dùng lúc live.
- **Phương án đã loại:**
  - OpenRouter free (Gemma 4, Nemotron, Dots3): 429 từ upstream "Provider returned error", stream rỗng, khoảng 50 request/ngày; 0/10.
  - Llama 3.3 70B fp8-fast (Cloudflare): 7/10, làm rơi số tiền ("đơn từ đ"), câu đầu p95 5,1 s.
  - Gemma 4 26B-A4B, Gemma 4 31B (Cloudflare và OpenRouter): lỗi nhà cung cấp, 0/10.
  - `model="auto"` của freellmapi: không biết model nào đang nói, giọng văn đổi bất kỳ lúc nào (ADR-034).
  - Mỗi nhà cung cấp một adapter riêng: cùng một API OpenAI-compatible nên một adapter là đủ.
  - SDK `openai`: thêm dependency trong khi `httpx` đã có.

## ADR-036: Tạo clip nền nhân vật offline bằng ComfyUI trên GPU cloud miễn phí (Kaggle, Colab)
- **Ngày:** 2026-11-03 · **Trạng thái:** Chấp nhận (2026-11-03). Người dùng chọn gương mặt AI, "thử Kaggle/Colab trước", và quyết định
  "hiện tại cứ dùng [Kaggle] do đang làm demo cho khách" sau khi được báo rủi ro điều khoản phi thương mại.
- **Bối cảnh:** spec 005 sửa phạm vi ngày 2026-11-03: nhân vật chạy trên bộ clip nền có chuyển động tự nhiên (chờ, nói, cử chỉ), miệng tạo
  realtime bằng LiveTalking (ADR-004). Đây là loại AI host phổ biến trên Shopee Live và livestream Trung Quốc. Clip nền phải tạo từ ảnh
  gương mặt AI bằng model tạo video, mà laptop (GTX 1650 Ti 4 GB, ADR-023) không chạy nổi.
- **Quyết định:**
  - Tạo ảnh gương mặt và clip nền bằng **ComfyUI** (GPL-3.0, chỉ dùng làm công cụ; license không áp lên ảnh và clip tạo ra). Đây là bước
    chuẩn bị offline, làm một lần cho mỗi nhân vật; **không nằm trong pipeline live** và không là dependency của `pyproject.toml`.
  - Model đề xuất (chọn cuối cùng sau khi chạy thử, ghi vào hồ sơ nguồn gốc):
    - Tạo ảnh: **SDXL base 1.0** (CreativeML Open RAIL++-M, cho dùng thương mại kèm danh sách cấm dùng) hoặc **FLUX.1-schnell**
      (Apache-2.0). Không dùng FLUX.1-dev (license phi thương mại).
    - Tạo video từ ảnh: **Wan 2.2 TI2V-5B** (Apache-2.0; 720p 24 fps; ComfyUI có workflow mẫu, có offload xuống khoảng 8 GB VRAM). Dự phòng:
      Wan 2.2 I2V A14B bản GGUF (đẹp hơn, nặng hơn nhiều).
  - Nơi chạy, theo thứ tự:
    1. **Kaggle Notebooks** (GPU T4 hoặc P100, khoảng 30 giờ GPU mỗi tuần, cần bật Internet trong notebook). Dùng cho **giai đoạn demo**,
       kể cả nhân vật demo cho khách: người dùng chấp nhận rủi ro điều khoản ngày 2026-11-03.
    2. **Google Colab bản miễn phí** (GPU thường là T4 16 GB, phiên tối đa 12 giờ). Chạy ComfyUI **không giao diện web**: notebook bật
       server ComfyUI trong máy Colab rồi gửi workflow JSON từ cell Python. Bản miễn phí cấm "bypassing the notebook UI to interact
       primarily via a web UI" và cấm tunnel, remote desktop.
    3. **RunPod** khi Kaggle và Colab không đủ (hết quota, quá chậm, lỗi bộ nhớ). Hỏi người dùng về chi phí trước khi bật pod (ADR-019).
  - Notebook đặt trong repo ở `scripts/avatar_clips/`, chạy được trên cả Kaggle và Colab, không chứa key. Model tải vào máy cloud,
    **không tải về laptop, không đưa vào git**. Ảnh, clip và hồ sơ nguồn gốc tải về laptop, lưu ở `assets/avatars/` (đã gitignore).
  - Mỗi ảnh và clip ghi hồ sơ nguồn gốc: model và bản checkpoint, prompt, seed, nơi chạy, ngày, người tạo (spec 005 FR-004).
- **Lý do:**
  - Theo đúng loại AI host đang dùng trên thị trường để làm nhanh: video nền có chuyển động + nhép miệng realtime.
  - Chỉ tạo clip một lần, nên GPU cloud miễn phí là đủ; không tốn tiền khi khách chưa đồng ý (ADR-019).
  - ComfyUI có workflow mẫu cho Wan 2.2 và là cách người dùng đã tìm hiểu (video hướng dẫn chạy AI local với ComfyUI).
  - SDXL, FLUX.1-schnell và Wan 2.2 có license cho dùng thương mại.
- **Điều kiện và rủi ro:**
  - T4 là GPU đời Turing, không có bf16; có thể phải dùng bản fp16, fp8 hoặc GGUF và chạy chậm. Đã đo 2026-11-06 (Kaggle, Tesla T4,
    notebook `scripts/avatar_clips/` lượt 2, ComfyUI `fb2b26fdac`): SDXL base 1.0 khoảng 30 s một ảnh 832×1216 (ảnh đầu 60 s);
    Wan 2.2 TI2V-5B bản fp16, 480×832, 121 frame (khoảng 5 s ở 24 fps), 20 step: 565–590 s một clip (khoảng 9,5 phút), không lỗi bộ nhớ.
    Cả lượt (cài đặt, tải model, 4 ảnh, 4 clip) khoảng 45 phút. Số đo này đưa vào plan 005 khi chạy `/sdd.plan`.
  - TODO: điều khoản Google Colab bản miễn phí không nói rõ có cho dùng thương mại không; Colab cấm "creating deepfakes" ở mọi runtime.
    Gương mặt là người không có thật nên không phải deepfake, nhưng phải đọc điều khoản của Google trước khi tạo nhân vật **giao cho khách**.
    Nếu không rõ thì tạo bản giao khách trên RunPod.
  - **Kaggle:** điều khoản chỉ cho "internal, personal, non-commercial use" (chưa đọc lại nguyên văn trên kaggle.com/terms). Người dùng
    chấp nhận dùng Kaggle cho giai đoạn demo. TODO: trước khi khách trả tiền (pilot, Shopee), đọc lại điều khoản Kaggle và Colab; nếu
    không cho phép thì tạo lại bộ clip giao khách trên nơi được phép (RunPod), ghi nơi chạy mới vào hồ sơ nguồn gốc.
  - TODO: đọc kỹ model card và license của checkpoint đã chọn (kể cả VAE, text encoder đi kèm) trước khi thu tiền khách (RISKS L10).
  - Clip nền lặp có thể bị Shopee coi là nội dung quay sẵn (RISKS P2). Không ảnh hưởng demo qua Meet hay YouTube.
  - Model tạo video có thể tự thêm cử động miệng vào clip chờ, hoặc làm mặt biến dạng giữa clip; spec 005 bắt từ chối các clip như vậy.
- **Phương án đã loại:**
  - Chạy ComfyUI trên laptop: 4 GB VRAM không đủ cho model tạo video.
  - Mở giao diện web ComfyUI trên Colab qua tunnel: Colab bản miễn phí cấm.
  - Mua PC GPU mạnh như máy trong video (RTX 5080): vốn lớn khi chưa có khách.
  - Quay người thật: người dùng chọn gương mặt AI.
  - Dịch vụ tạo video trên web (trả phí, điều khoản thương mại mỗi nơi mỗi khác) và avatar API trả phí theo phút (VENDORS.md).
  - Chạy LLM local bằng Hermes như trong video: không cần cho việc tạo nhân vật; LLM đã chốt ở ADR-035.

## ADR-037: Cấu hình chuỗi model LLM (`REPLY_ENGINE=chain`, `LLM_CHAIN`)
- **Ngày:** 2026-11-03 · **Trạng thái:** Đã chốt 2026-11-03 (người dùng: "ok duyệt ADR-037–039 và httpx, chạy /sdd.tasks 008"); plan 008, research R2, R4, R9; sửa cùng ngày theo làm rõ sau plan
- **Bối cảnh:** freellmapi và chuỗi model miễn phí chỉ dùng cho **một ngày demo**; nếu demo đạt thì đổi sang dịch vụ khác bằng ADR mới.
  Vì vậy cấu hình ưu tiên **chính xác** (đúng key, đúng model, đúng nền tảng đã benchmark) hơn khả năng chạy liên tục nhiều ngày.
- **Quyết định:**
  - `REPLY_ENGINE` nhận `chain | gemini | fake`; **mặc định đổi từ `gemini` sang `chain`**. `gemini` giữ lại để so sánh, không xóa.
  - `LLM_CHAIN` là JSON một dòng, danh sách mục theo thứ tự ưu tiên. Mỗi mục: `label`, `base_url`, `model`, `key_env`, `platform`,
    `first_sentence_timeout_s`, `params`.
  - `key_env` chỉ được là tên một trường secret của `Settings`: `FREELLMAPI_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`. Cấu hình không chứa key.
  - `platform` là id nền tảng của freellmapi mà benchmark đã chạy; **bắt buộc khi `base_url` là loopback** (dịch vụ gom key). Mục có
    `platform` gửi `X-FreeLLM-Cache: off` để không nhận câu trả lời lưu sẵn.
  - Từ chối lúc khởi động (kiểm cấu hình, không cần mạng):
    - model `auto`, `auto:*` hoặc `fusion`; trường trống; biến key chưa có giá trị; nhãn trùng; mục loopback thiếu `platform`;
    - `params` ghi đè khóa do engine quản lý (`model`, `messages`, `stream`, …);
    - tổng `first_sentence_timeout_s` > min(`LLM_TIMEOUT_S`, `SCRIPT_LLM_TIMEOUT_S`).
  - **Kiểm qua mạng một lần lúc khởi động:** một `GET {base_url}/models` (giới hạn 5 s) cho mỗi cặp (`base_url`, `key_env`). Không kết nối
    được, key bị từ chối, không có model hoặc model báo chưa dùng được → **app không khởi động**, thông báo nêu mục lỗi, không in key.
    `execution_status: exhausted` chỉ là cảnh báo. `qa_eval` chạy cùng lần kiểm này.
  - `LLM_CHAIN_COOLDOWN_S=60` là thời gian nghỉ cố định (ADR-038).
  - Chuỗi mặc định (thứ tự của ADR-035; **đổi bởi ADR-040**: còn `sealion` 2,5 s → `qwen`, bỏ `gptoss`):
    1. `sealion` qua freellmapi, `platform: cloudflare`, chờ câu đầu 3,5 s;
    2. `gptoss` qua freellmapi, `platform: groq`, 2,0 s, `reasoning_effort: low`;
    3. `qwen` gọi thẳng Groq, không có `platform`, 2,0 s, `reasoning_effort: none`.
  - Gemini (mục 4 của ADR-035) chỉ thêm vào chuỗi sau khi qua benchmark lại.
- **Lý do:**
  - Một biến JSON đọc được bằng `pydantic-settings` có sẵn, không thêm file cấu hình mới (ADR-015).
  - Ghim tên model và nền tảng giữ chất lượng đã chấm ở ADR-035; `auto` và `fusion` để freellmapi tự chọn model nên bị cấm.
  - Giới hạn chờ theo mục chia ngân sách 8 s của một lượt; SEA-LION chậm hơn nên được nhiều thời gian hơn (p95 2,81 s).
  - Demo chỉ có một ngày: sai key hay sai tên model phải lộ ra trước khi mở Meet, không phải giữa show.
- **Phương án đã loại:**
  - Biến môi trường đánh số (`LLM_CHAIN_1_MODEL`, …): dài, dễ lệch thứ tự.
  - File YAML riêng: thêm dependency và nơi cấu hình thứ hai.
  - Ghi key thẳng trong cấu hình chuỗi: lộ key khi dán cấu hình vào log hay tài liệu.
  - Một giới hạn chờ chung cho mọi mục: mục 1 hết giờ thì không còn thời gian cho mục sau.
  - Khởi động dù lần kiểm lỗi, chỉ cảnh báo: dễ vào show với một mục hỏng mà không ai để ý (người dùng chọn "Không khởi động").

## ADR-038: Phân loại lỗi nhà cung cấp và nghỉ mục
- **Ngày:** 2026-11-03 · **Trạng thái:** Đã chốt 2026-11-03 (người dùng: "ok duyệt ADR-037–039 và httpx, chạy /sdd.tasks 008"); plan 008, research R3, R5, R6, R7; sửa cùng ngày theo làm rõ sau plan
- **Quyết định:**
  - Chỉ chuyển sang mục kế khi lỗi xảy ra **trước câu đầu**. Lỗi sau câu đầu (`interrupted`) dừng lượt ở câu cuối đã nhận, báo `api_error`,
    mục nghỉ.
  - Mọi lỗi trước câu đầu làm mục nghỉ **cố định** `LLM_CHAIN_COOLDOWN_S` (60 s), không đọc `Retry-After` hay `retryAtMs`:
    - 429 → `rate_limited`;
    - 5xx hoặc khung lỗi SSE → `overloaded`;
    - luồng không có chữ → `empty`;
    - lỗi kết nối → `connection`;
    - quá giờ chờ câu đầu → `timeout`;
    - 4xx khác 429, 502 `provider_authentication_failed`, 502 `provider_error`, 503 `no_providers_configured` → `rejected`;
    - `X-Routed-Via` không khớp `platform` (khác nền tảng, thiếu header, `cache`, `idempotency`) → `wrong_platform`; đóng response trước
      khi đọc dòng SSE nào.
  - `content_filter` mà không có chữ → `blocked`: chuyển mục kế, không nghỉ.
  - Chỉ hai trạng thái: `ready` và `resting`. **Không có trạng thái tắt**; mục nghỉ hết hạn thì sẵn sàng lại ngay, không cần thử dò.
  - Hủy lượt (bỏ qua, dừng show, comment chen ngang) không phạt mục.
  - Một `ChainState` dùng chung cho câu trả lời và phân đoạn.
  - Hết chuỗi: `ReplyEngineError` với `kind`:
    - `rate_limited` khi mọi lý do là hết hạn mức;
    - còn lại là `api_error`.
    - Thông báo tiếng Việt liệt kê lý do từng mục (đã che key). `config_error` chỉ xảy ra lúc khởi động (ADR-037).
- **Lý do:**
  - Chuyển sau câu đầu sẽ làm một câu trả lời có hai giọng văn và có thể lặp ý.
  - Nghỉ tránh mất thời gian chờ ở mỗi lượt khi mục đang lỗi (spec 008 SC-004).
  - Chuỗi chỉ dùng một ngày: một khoảng nghỉ cố định đủ cho show vài giờ, đơn giản hơn đọc `Retry-After` (Điều VII). Lỗi cấu hình đã bị
    lần kiểm lúc khởi động chặn, nên lỗi kiểu này giữa show hiếm; nghỉ rồi thử lại không làm hỏng show.
  - Kiểm nền tảng chặt bảo đảm câu được nói đến từ đúng nền tảng đã benchmark (RISKS Q16).
  - Dùng `kind` có sẵn nên đếm lỗi và chế độ dự phòng của 004 chạy như cũ.
- **Phương án đã loại:**
  - Thử lại cùng mục với backoff: tốn ngân sách câu đầu.
  - Đoán hạn mức trước theo bộ đếm request: freellmapi đã làm, và đoán sai thì bỏ phí mục còn chạy được.
  - Thử dò mục đang nghỉ bằng request phụ: tốn hạn mức.
  - Nghỉ theo `Retry-After` (có thể tới hết ngày): cần cho chạy nhiều ngày, không cần cho một ngày demo (làm rõ sau plan).
  - Tắt mục tới hết phiên khi lỗi cấu hình: thêm một trạng thái và một loại cảnh báo; lần kiểm lúc khởi động đã thay vai trò này.
  - Chỉ ghi log khi sai nền tảng mà vẫn dùng câu trả lời: model chưa chấm có thể nói tới người xem (người dùng chọn "Chặt").

## ADR-039: Bề mặt quan sát và giả lập lỗi của chuỗi model
- **Ngày:** 2026-11-03 · **Trạng thái:** Đã chốt 2026-11-03 (người dùng: "ok duyệt ADR-037–039 và httpx, chạy /sdd.tasks 008"); plan 008, research R6, R8, R9, R12; sửa cùng ngày theo làm rõ sau plan
- **Quyết định:**
  - `ChainReplyEngine` có observer cho từng lượt và cho trạng thái chuỗi. Observer chỉ có ở engine này; Protocol `ReplyEngine` không đổi.
  - Nhà cung cấp thật lấy từ header `X-Routed-Via` của freellmapi, nếu không có thì lấy host của `base_url`. Phần trước dấu `/` đầu tiên
    so (không phân biệt hoa thường) với `platform` của mục (ADR-038). Gửi `stream_options.include_usage`.
  - Log mới: `llm_preflight` (lúc khởi động), `llm_attempt` (có `routed_via`), `llm_switch`, `llm_entry_rest`, `llm_chain_exhausted`,
    `llm_turn`. `llm_usage` mỗi lượt thêm `label`, `model`, `provider`.
  - `EventType.LLM_CHAIN`; khóa `llm_chain` trong `/api/state` (mỗi mục có `platform`); `/health` thêm `reply_engine` và `llm_ready`.
  - Trang điều khiển có khu "Model LLM", không có nút (làm rõ 2026-11-03). Chỉ một cảnh báo đỏ: không mục nào sẵn sàng.
  - Không có tác vụ nền kiểm gateway; freellmapi tắt giữa show hiện thành các mục loopback nghỉ vì `connection`.
  - Bản tổng hợp show thêm phần `llm_chain`: lượt, lần chuyển, lỗi theo mục; không có request hay token.
  - Giả lập lỗi (chỉ `APP_ENV=dev`):
    - `FaultIn.entry` chọn mục bị lỗi;
    - mode theo mục: `rate_limited`, `overloaded`, `timeout`, `empty`, `wrong_platform`, `interrupted`;
    - mục không có trong chuỗi → 422.
  - `qa_eval run/script --entry LABEL` chạy chuỗi một mục, nghỉ 0 s, vẫn kiểm lúc khởi động và kiểm nền tảng; nhãn engine `chain` hoặc
    `chain:<label>`; mỗi kết quả ghi `model_label`, `model`, `provider`.
  - `security/redact.py` thêm mẫu `gsk_…`, `freellmapi-…`, `sk-…` (theo `error-redaction.ts` của freellmapi). Che thêm theo chính giá trị
    key, áp dụng cả cho thông báo lỗi lúc khởi động.
- **Lý do:**
  - Spec 008 FR-005, FR-017–FR-021: người vận hành phải thấy model đang nói và lý do chuyển mà không đọc log.
  - Giả lập lỗi theo mục giúp kiểm SC-002, SC-003 mà không phải đợi hết hạn mức thật.
  - Body lỗi của nhà cung cấp có thể chứa lại key (RISKS S8).
  - Một ngày demo không cần theo dõi hạn mức dài hạn; thống kê token có sẵn ở dashboard freellmapi.
- **Phương án đã loại:**
  - Thêm trường model vào Protocol `ReplyEngine`: buộc sửa engine Gemini và engine giả mà không có lợi.
  - Nút đổi model trên trang điều khiển: người dùng chọn không có nút (làm rõ Q2).
  - Kiểm `GET /models` mỗi 15 s trong show: thêm tác vụ nền mà một ngày demo không cần (làm rõ sau plan).
  - Kiểm sức khỏe cả Groq: tốn hạn mức và request.
  - Request và token theo mục trong bản tổng hợp: chỉ có ích khi chạy nhiều ngày.

## ADR-040: Chuỗi model mặc định còn SEA-LION → Qwen3.8, SEA-LION chờ câu đầu 2,5 s
- **Ngày:** 2026-11-05 · **Trạng thái:** Đã chốt 2026-11-05 (người dùng: "hạ đi, gptoss thì cái nào tốt bạn làm giúp tôi"); kết quả T055
  của spec 008. Đổi chuỗi mặc định của ADR-037 và thứ tự của ADR-035.
- **Bối cảnh:** Ở T055 (quickstart 008, 2026-11-04):
  - `gptoss` (gpt-oss-120b qua freellmapi, nền tảng Groq) **không đạt SC-001**:
    - bộ câu hỏi tốt nhất 6/8 câu chấm được, q05 dùng cụm cấm "chưa có thông tin", q10 thiếu giá "259.000đ";
    - kịch bản 2–4 vi phạm (xưng "bạn" / "các bạn", nói "giỏ hàng");
    - hay hết giờ ở 2,0 s, có một lần `wrong_platform`.
  - Cổng Q18 chạm ngưỡng: khi `sealion` hết giờ ngay câu chào, câu đầu mất 4,25 / 4,39 / 4,44 / 4,61 / 7,08 s (1/5 lần > 5 s). Lần 7,08 s
    là 3,5 s chờ `sealion`, cộng `gptoss` cũng hết giờ thật (2,016 s), rồi `qwen` mới nói.
  - Câu đầu SEA-LION đo ở T055: p95 1,30 s, lớn nhất 2,11 s.
- **Quyết định:**
  - Chuỗi mặc định (`DEFAULT_LLM_CHAIN`, `.env.example`, contracts/config.md §2 của spec 008):
    1. `sealion` qua freellmapi, `platform: cloudflare`, chờ câu đầu **2,5 s** (trước là 3,5 s);
    2. `qwen` gọi thẳng Groq, 2,0 s, `reasoning_effort: none`.
  - `gptoss` bỏ khỏi chuỗi mặc định. Mục cũ để lại thành dòng chú thích trong `.env.example`. Chỉ thêm lại sau khi qua bộ kiểm US4
    (`qa_eval run/script --entry gptoss`), và phải có ADR mới.
- **Lý do:**
  - SC-001 bắt từng mục định dùng lúc live phải đạt riêng. Qwen đạt bộ câu hỏi 9/10 và 0 vi phạm kịch bản; gpt-oss-120b không đạt.
  - `gptoss` đi qua freellmapi như `sealion`. Khi freellmapi tắt, cả hai cùng hỏng, nên nó không thêm dự phòng cho trường hợp đó. Qwen gọi
    thẳng Groq nên vẫn trả lời được.
  - 2,5 s ≈ p95 × 1,9 và trên mức lớn nhất đo được (2,11 s). Khi `sealion` hết giờ: 2,5 s + Qwen p95 1,26 s ≈ 3,8 s tới câu đầu,
    thay vì tới 7,08 s.
  - Tổng giờ chờ 4,5 s, còn dư nhiều trong 8 s (FR-009). Ở chế độ dự phòng của 004 (4 s tổng) Qwen còn 1,5 s, thay vì 0,5 s như trước.
- **Điều kiện và rủi ro:**
  - Benchmark ADR-035 từng đo p95 câu đầu kịch bản của SEA-LION là 2,81 s. Lượt chậm như vậy giờ bị cắt và chuyển sang Qwen. Chấp nhận
    được vì Qwen đạt SC-001, nhưng cần xem tỉ lệ `llm_switch` vì `timeout` trong show thật.
  - Chỉ còn một mục dự phòng. Hạn mức dự phòng giảm (Groq tính hạn mức theo từng model: mất phần 1K RPD / 200K TPD của gpt-oss-120b). Với
    một ngày demo, Qwen chỉ nói khi SEA-LION lỗi nên vẫn đủ.
  - Bộ lọc khi live chưa chặn lỗi xưng "bạn" ở ngôi thứ hai. Đó là lý do không giữ một mục đã biết hay mắc lỗi này.
- **Phương án đã loại:**
  - Đổi thứ tự thành SEA-LION → Qwen → gpt-oss: vẫn đưa một mục không đạt SC-001 vào live.
  - Giữ `gptoss` và sửa prompt hoặc bộ lọc trước: tốn thêm một vòng chấm và hạn mức, trong khi đã có Qwen đạt.
  - Hạ giờ chờ SEA-LION xuống 2,0 s: sát mức lớn nhất đo được (2,11 s), dễ cắt nhầm lượt bình thường.

## ADR-041: Model nhép miệng giai đoạn laptop là Wav2Lip (`wav2lip256` của LiveTalking)
- **Ngày:** 2026-11-06 · **Trạng thái:** Đã chốt (người dùng duyệt 2026-11-06; plan 005, research R1). Chốt phần "chọn model" của ADR-004 cho giai đoạn laptop.
- **Quyết định:**
  - Dùng Wav2Lip với checkpoint `wav2lip256.pth` mà LiveTalking phát hành, đổi tên thành `models/wav2lip.pth` theo hướng dẫn của fork.
  - Không dùng MuseTalk khi còn chạy trên GTX 1650 Ti 4 GB. Xét lại MuseTalk khi chuyển sang GPU mạnh hơn (RunPod hoặc máy demo).
  - Khi có số đo SC-006 (fps, VRAM đỉnh, độ trễ bước tạo hình p50/p95, kết quả chạy 30 phút), ghi bổ sung vào ADR này.
- **Lý do:** ADR-023 đã nhận định MuseTalk nhiều khả năng không đủ 4 GB VRAM. README LiveTalking chỉ có số hiệu năng trên GPU lớn, nên trên
  laptop chỉ Wav2Lip có cơ hội chạy realtime. Bản 256 px nét hơn bản 96 px gốc.
- **Phương án đã loại:**
  - MuseTalk: thiếu VRAM và quá chậm trên laptop.
  - Wav2Lip 96 px gốc: mờ hơn. Có thể giữ làm phương án dự phòng nếu bản 256 px quá chậm.
- **Số đo (2026-11-07, T044):** bước `prepare` (S3FD + genavatar 256 px) cho 4 clip × 121 khung 832×480 mất 145 s, RAM đỉnh 1,3 GB,
  VRAM đỉnh 2,1 GB, với batch phát hiện mặt 4. Batch 16 (mặc định upstream) cần ~4,8 GB VRAM, tràn bộ nhớ chung của Windows và mất 759 s.
  Chi tiết ở quickstart 005 bước 4.
- **Số đo (2026-11-11, T046):** nhép miệng trên 1650 Ti với 12 đoạn tiếng VieNeu (5,0–34,9 s, thêm 1 đoạn im lặng):
  `first_frame_s` 0,92–1,16 s, `render_fps` 24,8–25,3, VRAM 2 656 MB không tăng sau đoạn 34,9 s. Người dùng chấm khớp miệng 10/10.
  Chi tiết ở quickstart 005 bước 6.
- **TODO:**
  - Đo fps và VRAM khi chạy 30 phút, độ trễ bước tạo hình p50/p95 (SC-006).
  - Xác minh license và nguồn gốc checkpoint (RISKS L11).

## ADR-042: Tích hợp LiveTalking bằng fork chạy process riêng, venv riêng, ngoài git
- **Ngày:** 2026-11-06 · **Trạng thái:** Đã chốt (người dùng duyệt 2026-11-06; plan 005, research R2). Trả lời TODO "tích hợp fork theo cách nào" của ADR-004.
- **Quyết định:**
  - Clone `lipku/LiveTalking` vào `vendor/livetalking/` (thêm `vendor/` vào `.gitignore`). Làm việc trên nhánh `ailive`, ghim SHA upstream.
  - Fork có venv riêng Python 3.12 (`vendor/livetalking/.venv`), không dùng chung `uv.lock` với app.
  - Code của mình nằm trong `ailive_ext/` (ingest, xoay clip, nhãn, prepare). Chỉ sửa nhỏ vào file gốc (`app.py`, `avatars/base_avatar.py`)
    để rebase dễ.
  - Dựng fork một lần bằng `scripts/livetalking/setup.ps1`. Người vận hành bật fork bằng `scripts/livetalking/run.ps1` ở terminal riêng.
  - App chỉ nói chuyện với fork qua HTTP/WebSocket trên `127.0.0.1` (ADR-043).
- **Lý do:**
  - torch/CUDA và requirements của LiveTalking rất nặng, có bản ghim riêng (ví dụ `websockets==12.0`). Tách venv giữ test app nhẹ, không
    cần GPU.
  - Suy luận GPU chạy ở process riêng nên không chặn event loop của app (Điều VI).
  - Clone ngoài git tránh vướng submodule khi làm thẳng trên `main` (ADR-027) và khi sub-agent chạy song song.
- **Phương án đã loại:**
  - git submodule: vướng khi nhiều agent cùng sửa và khi làm trên `main`.
  - Import LiveTalking vào process app: xung đột phiên bản, suy luận GPU dùng chung event loop.
  - Dùng nguyên LiveTalking với TTS của nó: mất TTS tiếng Việt của 003 và ack từng câu.
- **TODO:**
  - Giữ fork ở đâu: repo riêng trên GitHub hay chỉ trên máy?
  - Ghi SHA upstream lúc dựng.

## ADR-043: Đưa tiếng vào fork qua WebSocket `/ailive/ws`, đưa hình tới `/host` bằng WebRTC của LiveTalking
- **Ngày:** 2026-11-06 · **Trạng thái:** Đã chốt (người dùng duyệt 2026-11-06; plan 005, research R3, R4)
- **Quyết định:**
  - App gửi fork: `sentence_start` (JSON), các khung nhị phân PCM16 mono 16 kHz (ADR-025), `sentence_end`, `stop`.
  - Fork gửi app: `hello` (`boot_id`, `fork_commit`), `playback_started`, `sentence_played`, `stats`, `health`, `error`.
  - Chi tiết giao thức ở `specs/005-lipsync-livetalking/contracts/fork-protocol.md`.
  - Trang `/host` của app gọi `POST {LIVETALKING_URL}/offer` để nhận hình và tiếng bằng WebRTC, phát trong `<video>`. Trang báo `sessionid`
    cho app qua tin `ready` / `lipsync_session` trên `/ws/host`. Fork chạy `max_session` 1.
  - **Không làm `OutputSink` ở 005.** LiveTalking tự xuất WebRTC. Virtual cam / RTMP để dành cho feature OBS sau.
- **Lý do:**
  - Giữ được TTS và lõi pipeline của mình.
  - Từ vựng ack giống `/ws/host` (ADR-016), nên `LiveTalkingRenderer` có cấu trúc giống `StaticRenderer`.
  - Dùng lại WebRTC sẵn có của LiveTalking, không tự encode.
- **Phương án đã loại:**
  - Gửi tiếng qua HTTP `/humanaudio` của LiveTalking: gửi theo file, không có ack từng câu.
  - App tự nhận khung hình rồi encode: thêm việc nặng vào process app.

## ADR-044: Nhãn "AI" vẽ trong khung hình của fork; giữ watermark "LiveTalking"
- **Ngày:** 2026-11-06 · **Trạng thái:** Đã chốt (người dùng duyệt 2026-11-06; plan 005, research R5)
- **Quyết định:**
  - Fork vẽ nhãn trong `process_frames` trên mọi khung (chờ, nói, câm), trước khi đẩy ra output. Chữ và vị trí lấy từ `AI_LABEL_TEXT`,
    `AI_LABEL_POSITION`.
  - Không có cờ hay API để tắt nhãn. Nhãn vẽ bằng `cv2.putText`, nên fork không khởi động khi chữ nhãn rỗng hoặc không phải ASCII.
  - Giữ nguyên watermark "LiveTalking" mà code gốc vẽ. Không xóa, không che.
  - Khi tự về ảnh tĩnh (ADR-046), nhãn hiện bằng CSS như ADR-016.
- **Lý do:**
  - Ràng buộc số 2 và Điều I: nhãn nằm trong khung hình, không phụ thuộc OBS.
  - README LiveTalking yêu cầu watermark và logo trên một số nền tảng (RISKS L1).
- **Phương án đã loại:**
  - Nhãn CSS phủ lên `<video>`: không nằm trong khung hình.
  - Vẽ bằng Pillow để có chữ tiếng Việt: thêm phụ thuộc, chưa cần.
- **Kiểm chứng (2026-11-11, T047 của 005):** 12/12 ảnh chụp `/host` (6 lúc chờ, 6 lúc nói) có nhãn "AI" trong khung hình; nhãn CSS
  ẩn khi video của fork đang chạy. Quickstart 005 bước 6.
- **TODO:** YouTube và Shopee có bắt hiện thêm logo LiveTalking không? (RISKS L1)

## ADR-045: Hồ sơ nhân vật `character.json` gắn với một khách; chuẩn bị từng clip, xoay vòng và chuyển dần ở fork
- **Ngày:** 2026-11-06 · **Trạng thái:** Đã chốt (người dùng duyệt 2026-11-06; plan 005, research R7, R13)
- **Quyết định:**
  - Mỗi nhân vật có `AVATAR_DIR/character.json` gồm `character_id`, `customer_id`, `face`, `provenance` và danh sách clip `idle` / `talk`.
  - Thêm biến `CUSTOMER_ID` và `AVATAR_DIR`. Ở `AVATAR_MODE=livetalking`, app không mở khi:
    - thiếu `CUSTOMER_ID`;
    - nhân vật chưa `ready`;
    - `customer_id` khác `CUSTOMER_ID`;
    - `character_id` khác `AVATAR_ID`.
  - Lệnh `uv run python -m ai_live.avatar prepare <dir>`:
    - kiểm hồ sơ nguồn gốc (`adult_fictional_confirmed`, nguồn gốc từng clip);
    - gọi `ailive_ext.prepare` bằng Python của venv fork;
    - yêu cầu mỗi clip có đúng một gương mặt ở mọi khung.
  - Phát clip:
    - dùng clip gốc, không dùng bản `_pingpong`, vì fork đã phát kiểu đi tới rồi đi lùi;
    - fork chọn clip bằng `pick_next`, khác clip vừa dùng của cùng loại;
    - chuyển dần giữa hai clip trong `LIVETALKING_TRANSITION_S` (0,3 s);
    - giữ clip nói (miệng khép) tối đa `LIVETALKING_HOLD_S` (1,5 s) sau mỗi câu, để không về clip chờ giữa hai câu của cùng lượt (research R7, analyze A1);
    - phát 25 khung/giây.
- **Lý do:** ràng buộc số 3 và Điều I (một host cho một tài khoản, RISKS P4); FR-001–005, FR-009, FR-012, FR-013 của spec 005.
- **Phương án đã loại:**
  - Sổ đăng ký host ↔ tài khoản dùng chung: để dành cho mốc Multi-customer.
  - Chỉ dựa vào tên thư mục: dễ nhầm.
  - Ghép mọi clip nói thành một clip dài: nhảy hình ở chỗ nối.
  - Nội suy clip lên 25 fps: thêm bước xử lý mà không thấy lợi ích.
- **TODO:**
  - Quy ước đặt `CUSTOMER_ID`.
  - RAM có đủ để nạp mọi clip không (RISKS G11).

## ADR-046: `SwitchingRenderer` và Protocol tùy chọn cho kết quả và số đo render; tự về ảnh tĩnh sau 2 lượt lỗi
- **Ngày:** 2026-11-06 · **Trạng thái:** Đã chốt (người dùng duyệt 2026-11-06; plan 005, research R9, R10)
- **Quyết định:**
  - Thêm vào `core/protocols.py`:
    - `RenderOutcomeSink.record_render_outcome(utterance_id, ok)`;
    - `RenderStatsSource.render_stats(utterance_id)`;
    - `RendererError(kind, message)`.
  - Lõi (`ShowDirector`, `ScriptRunner`) gọi các Protocol này qua `isinstance`, không biết LiveTalking.
  - `SwitchingRenderer` bọc `LiveTalkingRenderer` và `StaticRenderer` (ảnh `AVATAR_DIR/face.png`), chọn renderer ở đầu mỗi lượt:
    - sau `AVATAR_FALLBACK_AFTER` (2) lượt lỗi render liền nhau thì chuyển sang ảnh tĩnh, báo trang host và trang điều khiển;
    - `POST /api/avatar/lipsync` bật lại lip-sync từ lượt kế tiếp.
  - `/ws/host` vẫn do `StaticRenderer` giữ (một kết nối, ADR-016). `StaticRenderer` thỏa `HostLink`, để `LiveTalkingRenderer` biết
    `sessionid` và gửi được phụ đề.
  - `AVATAR_MODE=static` trả thẳng `StaticRenderer`, không bọc.
  - Thời gian chờ và nối lại:
    - chờ khung đầu tối đa `LIVETALKING_FIRST_FRAME_TIMEOUT_S` (10 s);
    - nối lại fork với backoff tối đa `LIVETALKING_RECONNECT_MAX_S`;
    - `boot_id` đổi thì log `renderer_restarted`.
- **Lý do:**
  - FR-021, FR-022 của spec 005: lỗi render không được dừng show; phải tự về ảnh tĩnh.
  - Lõi phải báo được kết quả từng lượt, kể cả lỗi giả lập của `check_render`, mà không phụ thuộc lớp avatar cụ thể (Điều IV).
- **Phương án đã loại:**
  - Lõi gọi thẳng `SwitchingRenderer`: lõi phụ thuộc lớp avatar cụ thể.
  - Renderer tự đếm lỗi trong `speak`: không thấy lỗi giả lập ném ra trước `speak`.
  - Dừng show khi fork chết: trái FR-021.

## ADR-047: Mốc `avatar_first_frame` ở chế độ nhép miệng là ack `playback_started`; thêm `LIVETALKING_LEAD_S` cho khoảng lặng giữa câu
- **Ngày:** 2026-11-06 · **Trạng thái:** Đã chốt (người dùng duyệt 2026-11-06; plan 005, research R6, R15)
- **Quyết định:**
  - `avatar_first_frame` là lúc app nhận `playback_started` của câu đầu từ fork. Fork gửi ack này khi khung tiếng đầu của câu rời WebRTC.
  - Cuối mỗi câu, fork gửi `stats` (`frames`, `render_fps`, `infer_fps`). App ghi `render_stats` và thêm các trường này vào `TurnLatency`.
  - `LIVETALKING_LEAD_S` (mặc định 0 = tắt): khi > 0, `speak` trả về sớm lúc phần tiếng còn lại của câu ≤ giá trị này. Nhờ vậy câu sau vào
    hàng đợi của fork trong lúc câu trước còn phát. Chỉ bật khi đo thấy khoảng lặng p95 > 1,5 s.
- **Lý do:**
  - Khớp định nghĩa ở ARCHITECTURE §4: "frame đầu tiên ra khỏi output".
  - App không gắn được khung Chrome đang vẽ với một câu cụ thể.
  - Mỗi ranh giới câu thêm chừng một lô suy luận (≥ 0,84 s ở `batch_size` 16). Trả về sớm xử lý việc này trong renderer, không đổi lõi.
- **Phương án đã loại:**
  - Trang host báo bằng `requestVideoFrameCallback`: không gắn được với câu.
  - Ước từ thời lượng audio: 004 R12 đã loại.
  - Lõi gửi trước câu kế tiếp: phải đổi `ShowDirector` / `ScriptRunner`.
- **TODO:**
  - Đo lệch giữa ack và lúc hiển thị (RISKS G13).
  - Chọn giá trị `LIVETALKING_LEAD_S` theo số đo.

## ADR-048: Dependency và model cho feature 005
- **Ngày:** 2026-11-06 · **Trạng thái:** Đã chốt (plan 005). Phần **repo app** (khai báo `websockets`) người dùng duyệt 2026-11-06;
  phần **venv fork** và **model** người dùng duyệt 2026-11-07 ("làm a"). LiveTalking ghim ở commit upstream
  `c7269433a2b6ecebcd9342445d2ecc882c98b0da` (main ngày 2026-11-07).
- **Quyết định:**
  - **Repo app:** khai báo trực tiếp `websockets` trong `pyproject.toml`. Gói đã có trong `uv.lock` qua `uvicorn[standard]`, không tải thêm.
  - **Venv fork:**
    - Python 3.12;
    - torch 2.9.1 + torchvision + torchaudio từ `https://download.pytorch.org/whl/cu128`, nếu không chạy trên driver 565.90 thì dùng bản
      cu126;
    - `requirements.txt` của LiveTalking ở SHA ghim: aiortc, aiohttp, opencv-python-headless, librosa, resampy, soundfile, numpy, scipy,
      einops, transformers, diffusers, accelerate, cùng các gói upstream không dùng như edge_tts, flask, dashscope, openai,
      `websockets==12.0`.
  - **Model (tải tay, ngoài git):**
    - `wav2lip256.pth` (thư mục Google Drive / Quark trong README LiveTalking) → `vendor/livetalking/models/wav2lip.pth`;
    - `s3fd.pth` từ `https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth`;
    - sau khi tải, ghi sha256 của hai file vào ADR này.
- **Kết quả dựng (2026-11-07, T008–T009):**
  - Bản torch chạy được: `2.9.1+cu128`; `torch.cuda.is_available()` = True trên GTX 1650 Ti, danh sách arch có `sm_75`. Không cần cu126.
  - Torch tải 2,7 GiB; cả venv fork sau khi cài `requirements.txt` chiếm 5,1 GB trên đĩa.
  - `wav2lip.pth` (file `wav2lip256.pth` trong thư mục Google Drive của README): 214 670 409 byte,
    sha256 `b22d7ac86295df667644b17254dc71250c2600b89e20403e90e58812450bc173`.
  - `s3fd.pth`: 89 843 225 byte, sha256 `619a31681264d3f7f7fc7a16a42cbbe8b23f31a256f75a366e5a1bcd59b33543` (khớp tiền tố trong tên file gốc).
  - Cả hai nạp được bằng `torch.load` mặc định của torch 2.9 (`weights_only=True`).
  - `.gitignore` của fork thêm `*.pth` và `.venv/` (dòng `# ailive:`).
  - Venv fork cài thêm `pytest` (chỉ để chạy `ailive_ext/tests`, fork-protocol §6); `setup.ps1` cài cùng lúc.
- **Lý do:** cần cho ADR-041–043. Tách venv giữ app nhẹ. Mọi thứ đều miễn phí (ADR-019).
- **Phương án đã loại:**
  - Cài torch vào venv của app: test app phải kéo theo CUDA.
  - Để `setup.ps1` tự tải model: tải ngầm, khó kiểm license.
- **TODO:**
  - License của checkpoint (RISKS L11).

## ADR-049: `TTS_TIMEOUT_S` áp cho mỗi lần chờ chunk tiếng, không cho cả câu
- **Ngày:** 2026-11-09 · **Trạng thái:** Đã chốt (người dùng chọn phương án (b) sau T026 của feature 003; đổi 003 research R9)
- **Quyết định:**
  - `TTS_TIMEOUT_S` (mặc định 5) là thời gian chờ tối đa cho chunk đầu của một câu và giữa hai chunk liền nhau. Không còn giới hạn cả câu.
  - Áp như nhau ở `ShowDirector` (lượt comment 001, `speak_text`) và `ScriptRunner` (show 004). Thời gian chờ hàng đợi phát không tính.
  - Không thêm biến cấu hình mới; thông báo lỗi giữ `TTS quá N s`, `kind=timeout`.
- **Lý do:**
  - T026 đo VieNeu CPU trên laptop khoảng 0,63 s cho mỗi giây tiếng. Câu 9,6 s tiếng cần khoảng 6 s để tạo, nên giới hạn 5 s cho cả câu
    cắt câu ở 6,6 s và làm mất câu sau. Chuẩn hóa số (US2) còn làm câu dài hơn.
  - Engine treo vẫn bị phát hiện sau tối đa `TTS_TIMEOUT_S`, như trước.
  - `ShowDirector` cũ còn tính cả lúc chờ hàng đợi phát (tối đa 2 câu) vào thời gian TTS; cách mới bỏ lỗi này.
- **Phương án đã loại:**
  - Tăng `TTS_TIMEOUT_S` lên 15: câu dài hơn vẫn bị cắt, engine treo bị phát hiện chậm.
  - Thêm biến riêng cho thời gian chờ giữa hai chunk: chưa có số đo cần hai giá trị khác nhau.
