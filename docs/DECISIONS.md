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
  Hướng cho khách dùng (app nhẹ + GPU thuê theo giờ) đề xuất thay một phần ở ADR-091 (feature 015).
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
  của spec 008. Đổi chuỗi mặc định của ADR-037 và thứ tự của ADR-035. Bổ sung bởi ADR-073 (thêm Gemini làm mục thứ ba).
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
- **Số đo (2026-11-12, T073, SC-006):** fork `477d4e4`, batch 16, `LIP_EVERY_N` 1, VieNeu trên CPU, engine trả lời giả (không tính LLM).
  - 20 lượt bình luận: 0 lỗi; `tts_first_chunk → avatar_first_frame` p50 1,29 s / p95 1,71 s; cả lượt p50 1,84 s / p95 2,15 s;
    `render_fps` p50 18,0 nhưng `infer_fps` p50 24,8 (tiếng VieNeu tới chậm hơn thời gian thực khi vừa tổng hợp vừa phát).
  - Show 30 phút: 322 câu, 0 lỗi tts/render, 0 `vram_oom` / `renderer_restarted`, cùng một `boot_id`; `render_fps` p50 25,1 (p5 23,8);
    VRAM 2 656 MB không đổi suốt 30 phút; câu đầu show 1,64 s; lặng giữa câu p95 2,98 s (vượt 1,5 s của Điều VI).
  - VRAM đỉnh trong `avatar.jsonl` thiếu vì lỗi nối log (sửa ở commit `2c7bbf3`).
  - Chi tiết, so sánh `LIVETALKING_LEAD_S` và `LIVETALKING_BATCH_SIZE` (T075): quickstart 005 bước 9.
- **Số đo (2026-11-12, T075, `LIVETALKING_LEAD_S` 2,5, show 3 phút mỗi cấu hình):**
  - Show `render_fps` p50 (p5): batch 16 24,0 (21,6), batch 8 20,0 (18,6), batch 4 19,1 (15,8), batch 16 với `LIP_EVERY_N` 2 20,1 (16,0).
  - Khung đầu lượt bình luận p50: 1,36 / 0,73 / 0,45 / 1,06 s; lặng nghe được p95: 0,86 / 0,58 / 1,03 / 1,05 s.
  - VRAM 2 656 / 1 004 / 894 / 2 660 MB; 0 lỗi, 0 `vram_oom` ở mọi cấu hình.
  - `LIP_EVERY_N` 2 gần gấp đôi `infer_fps` (38) nhưng không tăng `render_fps`, nên nút cổ chai không nằm ở suy luận.
  - Giữ mặc định batch 16, `LIP_EVERY_N` 1. ~~TODO: người dùng chọn batch 16 hay 8; bộ clip nhỏ hơn hoặc RunPod.~~ _Người dùng chốt
    2026-11-16: batch 16 (show mượt hơn; `LEAD_S` 2,5 đã che độ trễ khung đầu); không làm bộ clip nhỏ hơn, không thuê RunPod lúc này. Lượt
    bình luận ~18 khung/giây (VieNeu vừa tổng hợp vừa phát) được chấp nhận vì đường bình luận đang tạm dừng (ADR-026)._ Bảng đầy đủ:
    quickstart 005 bước 9.
- **TODO:**
  - ~~Đo fps và VRAM khi chạy 30 phút, độ trễ bước tạo hình p50/p95 (SC-006).~~ _Đã đo 2026-11-12 (T073), xem trên._
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
> Phần giữ watermark "LiveTalking" sửa bởi ADR-075 (có công tắc `LIVETALKING_WATERMARK`, demo tắt). Kiểu và vị trí mặc định của
> nhãn sửa bởi ADR-076 (chữ viền không nền, giữa trên); phần "luôn vẽ, không có công tắc tắt" không đổi.
- **Ngày:** 2026-11-06 · **Trạng thái:** Đã chốt (người dùng duyệt 2026-11-06; plan 005, research R5). Chữ mặc định đổi từ
  "AI" thành "AI-GENERATED CONTENT" bởi ADR-065
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
  - Vẽ bằng Pillow để có chữ tiếng Việt: thêm phụ thuộc, chưa cần. _(Sửa bởi ADR-051: Pillow đã khai báo cho cảnh 009; nhãn vẫn vẽ bằng cv2.)_
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
    - giữ clip nói (miệng khép) tối đa `LIVETALKING_HOLD_S` (1,5 s) sau mỗi câu, để không về clip chờ giữa hai câu của cùng lượt (research R7, analyze A1); _mặc định đổi 2,5 s và câu `seq 0` trong khoảng giữ nói tiếp trên clip đang giữ (2026-11-12, T067, spec 005 Làm rõ 2026-11-12)_;
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
  - `LIVETALKING_LEAD_S` (mặc định 0 = tắt; **đổi thành 2,5 ngày 2026-11-16**, xem TODO dưới): khi > 0, `speak` trả về sớm lúc phần tiếng còn lại của câu ≤ giá trị này. Nhờ vậy câu sau vào
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
  - ~~Đo lệch giữa ack và lúc hiển thị (RISKS G13).~~ _Đã đo 2026-11-12 (T074): Chrome phát tiếng chậm hơn ack trung vị 0,28 s, p95
    0,64 s, chung cho tiếng và hình; chi tiết research 005 R6._
  - ~~Chọn giá trị `LIVETALKING_LEAD_S` theo số đo.~~ _Đã đo 2026-11-12 (T073/T075, quickstart 005 bước 9): khoảng lặng nghe được trong
    Chrome có p95 3,19 s với `LEAD_S` 0, 1,96 s với 1,3, và 0,76–1,00 s với 2,5. Đề xuất `LIVETALKING_LEAD_S=2.5`. Người dùng duyệt 2026-11-16: mặc định
    trong `Settings` và `.env.example` đổi từ 0 thành 2,5; app không mở nếu `LEAD_S` ≥ `LIVETALKING_FIRST_FRAME_TIMEOUT_S`._
- **Bổ sung 2026-11-12 (sửa lỗi đo, T075):** với `LEAD_S > 0`, lúc `speak` trả về không còn là lúc câu phát xong. Vì vậy `sentence_gap`
  tính từ `RenderTurnStats.last_played_at` (ack `sentence_played`). Số đo của lượt lấy sau khi renderer báo lượt đã xong qua Protocol tùy
  chọn `RenderSettleSource.turn_settled`; `TurnLatency` đã ghi thì được bổ sung (contracts 005 adapters.md §2).

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

## ADR-050: Guard chặn cụm "khẳng định không có căn cứ" (`unsupported_claim`) khi file nội dung không có
- **Ngày:** 2026-11-12 · **Trạng thái:** Đã áp dụng (sửa lỗi theo FR-010 của 004 và ràng buộc 7). `TODO:` người dùng duyệt danh sách
  `data/rules/claim_phrases.txt`, như danh sách cơ chế nền tảng ở ADR-033.
- **Bối cảnh:** tổng duyệt G5 của 004 (phiên `data/sessions/20261112-170251`): khoảng 30/279 câu đã nói có khẳng định file nội dung
  không có. Đó là "an toàn cho da", "không gây kích ứng", "kể cả da nhạy cảm", "da mềm mại", lời khen bịa ("nhiều khách hàng feedback",
  "ai dùng cũng ưng"), tồn kho ("có sẵn hàng", "số lượng có hạn") và hối thúc ("khuyến mãi có thể kết thúc bất cứ lúc nào"). Host hay
  thêm các câu này khi đã nói hết thông tin của chủ đề mà còn thiếu câu. Bộ chấm SC-003 không bắt được vì guard chỉ kiểm số, phần trăm,
  khẳng định bị cấm, link và cơ chế nền tảng.
- **Quyết định:**
  - Prompt kịch bản (`SCRIPT_RULES`) dặn thêm: không kể lời khen hay trải nghiệm của khách, không tự thêm công dụng, cảm giác trên da hay
    độ an toàn, không nói còn hàng, số lượng có hạn hay hối thúc theo thời gian, hết thông tin thì nói lại ý đã có hoặc mời nhắn shop.
  - Guard thêm kiểm tra tất định `unsupported_claim` (nhãn "khẳng định không có trong dữ liệu"). Kiểm tra chạy **sau** `platform_phrase`,
    cùng cách so khớp: so nguyên từ trên `word_form` (bỏ dấu, chữ thường). Cụm có trong chữ của file nội dung thì được nói.
  - Danh sách ở `data/rules/claim_phrases.txt` (biến `CLAIM_PHRASES_PATH`). File thiếu thì app, `brain` CLI và `qa_eval` không chạy
    (`GuardConfigError`). Mọi chỗ chạy thật tạo guard qua `load_guard(platform_path, claim_path)`.
  - Áp cho cả hai đường. Câu kịch bản bị chặn thì bỏ câu đó; câu trả lời comment bị chặn thì nói câu từ chối (R9).
  - Danh sách ban đầu có 38 cụm, lấy từ câu thật của G5. Không ghi cụm trùng với cách nói thường gặp khi bỏ dấu ("có sẵn" trùng "có sản
    phẩm", "còn hàng" trùng "con hàng", "cũng ưng" trùng "cung ứng").
- **Số đo:**
  - Chạy danh sách trên các câu khác nhau trong log phiên 2026-11-10 đến 2026-11-12 (835 câu kịch bản, 687 câu trong
    `utterances.jsonl`): bắt 31 câu kịch bản. Câu bị bắt trong `utterances.jsonl` là cùng các câu đó. Câu nào bị bắt cũng là câu bịa thật,
    không chặn nhầm câu nào.
  - Chấm lại phiên G5 bằng `qa_eval script --session`: 24 vi phạm `unsupported_claim` trên 73 phân đoạn (trước đây 0).
  - Prompt mới, `qa_eval script --entry qwen` (`20261112-181302`, SEA-LION đang bị `rate_limited`): 1 vi phạm ("da nhạy cảm") trên 13
    phân đoạn chấm được; 8 phân đoạn lỗi `rate_limited` của Groq. `TODO:` đo lại bằng SEA-LION khi hạn mức reset (3 lần, SC-008). 2026-11-13 07:25 gọi thử vẫn `rate_limited`, freellmapi
    hẹn reset 07:00 2026-11-14, chưa đo được.
- **Lý do:** prompt không tất định (ADR-017). Danh sách cụm có thể sửa mà không đổi code. Cách làm giống `platform_phrases` đã có test.
- **Hệ quả:**
  - Guard đổi là đường comment đổi: chạy lại bộ 10 câu hỏi mẫu và bộ câu gài của 001 (Điều III).
  - ~~Câu trả lời trung thực kiểu "shop chưa có thông tin về kích ứng" cũng bị chặn và thay bằng câu từ chối.~~ _Sửa 2026-11-16 (người dùng
    chọn): guard miễn cụm khẳng định nằm ngay sau cụm báo thiếu thông tin trong cùng vế câu (004 FR-010 bổ sung, contracts/adapters.md
    §4). Miễn áp cho cả đường kịch bản và đường bình luận; vế khác của câu vẫn bị kiểm. TODO: chạy lại hồi quy Điều III bằng LLM thật._
  - Danh sách chỉ bắt cách nói đã gặp; cách nói mới vẫn lọt. Thêm cụm khi thấy trong `qa_eval script --session`.
- **Phương án đã loại:**
  - Chỉ siết prompt: G5 cho thấy model vẫn độn câu khi thiếu thông tin.
  - Dùng LLM thứ hai để chấm căn cứ: tốn hạn mức và thêm độ trễ trước TTS.
  - Gộp vào `platform_phrases.txt`: lý do chặn khác nhau, người vận hành cần thấy đúng lý do.

## ADR-051: Pillow là phụ thuộc trực tiếp để vẽ lớp cảnh và chữ tiếng Việt ở app; font lấy từ máy
- **Ngày:** 2026-11-13 · **Trạng thái:** Đã chốt (tự chốt theo ủy quyền của người dùng 2026-11-13, plan 009 research R2–R3; chờ xác
  nhận trong gói duyệt)
- **Quyết định:**
  - Khai báo `pillow` trong `[project.dependencies]` của `pyproject.toml`. Pillow 12.3.0 đã nằm trong `uv.lock` (gói kéo theo), nên không
    tải gói mới.
  - App vẽ bàn, ảnh sản phẩm, thẻ tên/giá, hiệu ứng làm nổi và phụ đề bằng Pillow (FreeType), chữ tiếng Việt đủ dấu.
  - Font: `SCENE_FONT_PATH`; trống thì tìm `segoeuib.ttf`, `arialbd.ttf`, `segoeui.ttf` trong `C:/Windows/Fonts`, rồi
    `DejaVuSans-Bold.ttf` trên Linux. Bật cảnh mà không có font thì app không mở, báo lỗi tiếng Việt. Không tải hay đóng gói font.
  - Nhãn "AI" vẫn vẽ bằng cv2 ở fork như ADR-044 (không đổi).
- **Lý do:** cv2 `putText` không có dấu tiếng Việt; Pillow đã có sẵn, nhỏ, ổn định.
- **Phương án đã loại:** opencv trong app (vẫn không dấu); skia/cairo (phụ thuộc mới); vẽ bằng canvas trình duyệt rồi chụp (chậm, không
  dùng được ở fork).
- **Hệ quả:** sửa phần "Phương án đã loại: Vẽ bằng Pillow… chưa cần" của ADR-044: nay đã cần cho cảnh (chỉ cảnh, không cho nhãn).
- **TODO:** license dùng Segoe UI / Arial trong luồng thương mại (RISKS L12). Nếu cần font thương hiệu (Be Vietnam Pro, OFL) thì ADR mới.

## ADR-052: Cảnh live (bàn, sản phẩm, thẻ) do app vẽ, fork trộn vào mọi khung trước watermark và nhãn; bộ cảnh ngoài git
- **Ngày:** 2026-11-13 · **Trạng thái:** Đã chốt (tự chốt theo ủy quyền của người dùng 2026-11-13, plan 009 research R1, R5–R9; chờ
  xác nhận trong gói duyệt)
- **Quyết định:**
  - App vẽ lớp RGBA (`base`: bàn + sản phẩm + thẻ + làm nổi; `subtitle`), chỉ vẽ lại khi trạng thái đổi, gửi cho fork bằng tin
    `scene_layer` (contracts 009 `fork-protocol.md`). Fork trộn trong `process_frames` sau chuyển dần clip, **trước** watermark
    "LiveTalking" và nhãn "AI".
  - Fork từ chối lớp có điểm ảnh trong vùng mặt (y < face_bottom + 8), hộp nhãn hoặc hộp watermark (`error scene_rejected`), giữ lớp cũ;
    gửi `hello.scene` (face_bottom, keep_out) để app vẽ khớp. Lỗi cảnh không làm hỏng lượt nói (FR-021).
  - Chế độ ảnh tĩnh và khi tự về ảnh tĩnh: app ghép ảnh tĩnh của nhân vật với cùng các lớp (`/api/scene/still.png`).
  - Sản phẩm nổi đổi theo ack `playback_started` của câu kịch bản (Protocol `PlaybackListener`), không theo lúc chuẩn bị.
  - Bộ cảnh của khách (`SCENE_DIR`: `scene.json`, `desk.png`, `products/`, `originals/`, `provenance.json`) nằm ngoài git
    (`assets/scenes/`), có `customer_id` phải khớp `CUSTOMER_ID`. Ảnh sản phẩm: chỉ ảnh thật của khách, cắt nền thủ công trên máy (Paint
    Windows 11 / GIMP), thao tác chỉnh nằm trong danh sách cho phép. Ảnh AI chỉ cho bàn.
  - Bật bằng `SCENE_ENABLED` (mặc định tắt); `SCENE_SUBTITLES` mặc định tắt.
- **Lý do:** Ràng buộc số 2 và 7, Điều I và III; một nguồn vẽ cho hai chế độ; fork chỉ trộn mảng nên rẻ (~1–2 ms/khung).
- **Phương án đã loại:** cảnh bằng CSS trên trang host (không nằm trong khung, mất khi ra OBS); fork tự vẽ chữ (trùng logic, mang dữ liệu
  sản phẩm sang fork); rembg / remove.bg để cắt nền (tải model / gửi ảnh khách ra ngoài); tạo lại clip nền có bàn (hướng A).
- **Kiểm chứng (2026-11-13, laptop GTX 1650 Ti, TTS/lời thoại giả):** SC-004: hai show 10 phút, `render_fps` trung vị 25,10 cả khi tắt và bật cảnh (giảm 0%); `scene_ms` trung vị 4,66, max 6,09 ms/khung (dự kiến 1–2 ms, vẫn trong ngân sách 40 ms/khung); khoảng lặng p95 3,05 s (tắt) → 2,14 s (bật), không tăng; 0 `scene_rejected`; app vẽ lại lớp trung vị 63 ms, max 112 ms trong thread. SC-001: 30/30 ảnh ở thời điểm ngẫu nhiên không đổi trong vùng mặt, nhãn, watermark. Fork: `hello.scene` 480×832, `face_bottom` 304; cảnh nằm trong WebRTC dưới watermark và nhãn; tắt fork giữa show → ảnh tĩnh giữ cảnh và món nổi.

## ADR-053: MediaPipe Face Landmarker đo hình miệng trong bộ đo 010 (chỉ đo, không chạy live)
- **Ngày:** 2026-11-13 · **Trạng thái:** Đã chốt (người dùng cho phép cài tool/repo cho 010 ngày 2026-11-13; chờ xác nhận trong gói
  duyệt 010)
- **Quyết định:** cài `mediapipe` 1.2.3 vào **venv của fork** (`vendor/livetalking/.venv`, kéo theo `absl-py`, `flatbuffers`,
  `sounddevice`, `opencv-python-headless`). Tải `face_landmarker.task` (khoảng 3,6 MB, float16, Google) vào `vendor/livetalking/models/`
  (ngoài git). Chỉ bộ đo `ailive_ext/mouth_eval` dùng; đường live không import. Chạy offline sau khi tải.
- **Lý do:** cần điểm mốc môi (độ mở, độ rộng, khép môi) chạy CPU nhanh, offline, license thương mại được (Apache-2.0 cho cả mã và
  model). Không cài vào venv app (app không đo khẩu hình).
- **Phương án đã loại:** dlib 68 điểm (ít điểm môi trong, cần build); face-alignment (PyTorch, nặng hơn, tải model lớn hơn); đo bằng mắt
  hoàn toàn (không lặp lại được, SC-007).
- **Rủi ro:** `mediapipe` kéo `opencv-python-headless` cùng venv với OpenCV sẵn có của fork; test fork vẫn qua (178 test, 2026-11-13).
  Ghi ở `docs/RISKS.md`.
- _(Sửa bởi ADR-056: `prepare` của fork cũng dùng Face Landmarker để đo góc đầu clip nói, lúc chuẩn bị nhân vật, vẫn không chạy live.)_

## ADR-054: SyncNet (joonson/syncnet_python) chấm khớp tiếng–miệng LSE-C/LSE-D trong bộ đo 010
- **Ngày:** 2026-11-13 · **Trạng thái:** Đã chốt (như ADR-053)
- **Quyết định:** chép mạng `SyncNetModel.S` và cách chấm `evaluate` (MIT, Joon Son Chung) vào `ailive_ext/mouth_eval/syncnet.py`, bỏ
  bước ffmpeg và bộ dò mặt (dùng hộp mặt có sẵn của nhân vật). Trọng số `syncnet_v2.model` (khoảng 52 MB) vào
  `vendor/livetalking/models/` (ngoài git). MFCC bằng `python_speech_features` 0.6 (MIT) cài vào venv fork. Chỉ bộ đo dùng, không chạy live.
- **Lý do:** LSE-C/LSE-D là thước đo khớp tiếng chuẩn của các bài Wav2Lip/MuseTalk; FR-006a cần một điểm tự động. SyncNet còn cho độ
  lệch hình–tiếng theo khung, nhờ đó tìm ra miệng đi trước tiếng (research R7).
- **Ghi chú:** điểm chỉ dùng để so các cách tạo miệng trên cùng nhân vật; không so được với số trong bài báo (khác bộ dò mặt và dữ liệu).
  `torchaudio` của venv fork hỏng từ trước, không dùng.
- **Phương án đã loại:** bản SyncNet của repo Wav2Lip (`color_syncnet`, chấm trên 96×96, lệch với cách chấm phổ biến); LatentSync
  SyncNet (cần tải thêm, nặng hơn).

## ADR-055: Cách tạo miệng của fork chọn bằng `LIVETALKING_MOUTH_METHOD`; giữ wav2lip256, mặc định vẫn `w2l`
- **Ngày:** 2026-11-13 · **Trạng thái:** Đã chốt cơ chế; giá trị mặc định chờ người dùng xem gói A/B 010 (r4)
- **Quyết định:** fork đọc `LIVETALKING_MOUTH_METHOD` một lần lúc bật: preset `w2l` hoặc chuỗi khóa `ref`, `paste`, `color`, `sharpen`,
  `gain_db`, `shift` (`specs/010-natural-mouth-shapes/contracts/mouth-method.md`). Chuỗi sai → `w2l` và log lỗi. Mặc định của dự án
  (`.env.example`) **giữ `w2l`**. Ứng viên thay: `shift=-1` (SyncNet báo hết lệch −1 khung ở cả 24 câu, tương quan độ mở–độ to +16%,
  LSE-C −0,7%, khép môi −6%); đổi mặc định khi người dùng xem gói A/B và thấy `shift=-1` hơn.
- **Lý do:** đo 4 lần (r1–r4, 24 câu, `out/mouth/runs/`) không cách hậu kỳ nào đạt SC-001 (≥ 2/4 chỉ số tốt hơn 15% mà LSE-C không
  giảm). Hình miệng do model wav2lip256 quyết định; dán mềm, chỉnh màu, làm nét chỉ đổi đường viền, ảnh tham chiếu môi khép không làm khép
  môi tốt lên (research R6, R10). Vì thế không đổi mặc định khi chưa có bằng chứng.
- **Phương án đã loại:** MuseTalk 1.5 trên laptop (~0,7 khung/giây so với ngưỡng 20, research R4; xét lại khi có GPU mạnh hơn, cần hỏi
  chi phí); một ảnh tham chiếu cố định cho mọi khung (mắt và tư thế đầu lệch khỏi clip, R5); tăng độ to cho model (`gain_db`, miệng mở ít
  hơn, R6); `ref=closed:W` ở live (R10, chỉ giữ trong bộ đo).
- **Hệ quả:** muốn miệng giống người hơn nữa phải đổi **đầu vào** (clip nói có môi khép rõ ở b/m/p, quay thẳng mặt) hoặc **model** (GPU
  mạnh hơn); cả hai ghi vào gói duyệt 010.

## ADR-056: `prepare` loại khung clip nói có góc đầu lệch quá ngưỡng; fork chỉ phát các đoạn dùng được
- **Ngày:** 2026-11-13 · **Trạng thái:** Đã chốt (010 US3)
- **Quyết định:** sau `genavatar`, `prepare` đo góc đầu từng khung clip nói bằng MediaPipe Face Landmarker (ADR-053, đã có trong venv
  fork), so với tư thế trung vị của các clip chờ, loại khung lệch quá roll 35° / pitch 20° / yaw 30° (cờ `--max-roll`, `--max-pitch`,
  `--max-yaw`) và đoạn còn lại ngắn hơn 2 s, ghi `ailive_pose.json` vào thư mục avatar của clip. Fork lúc bật cắt mỗi clip nói thành các
  đoạn dùng được (`talk_01~1`, ...). Không đo được thì `prepare` vẫn `ready`, clip phát nguyên đoạn. Còn < 4 s dùng được → cảnh báo
  `talk_too_short`, không tự làm lại clip.
- **Lý do:** model vẽ miệng theo hướng mặt của khung nền; khung quay hẳn đi cho miệng sai hướng. Lấy idle làm gốc bù được lệch cố định
  của bộ đo và tư thế nghỉ nghiêng của host. Đo trên demo_host_01 (research R11): độ mở miệng không phụ thuộc rõ vào góc đầu, nên ngưỡng
  để rộng; với ngưỡng mặc định không khung nào bị loại. Siết roll 20° sẽ loại hết talk_02. Người dùng chốt 2026-11-16: giữ ngưỡng
  35/20/30.
- **Phương án đã loại:** dùng S3FD/hộp mặt có sẵn (không cho góc đầu); bộ ước lượng tư thế riêng (thêm model, ADR mới); tự quay lại
  hoặc xoay khung (đổi hình nền thật, dễ lộ).

## ADR-057: Sẵn sàng demo: canh show chỉ cảnh báo và tự bỏ câu kẹt một lần; video dự phòng ghi từ đường realtime
- **Ngày:** 2026-11-13 · **Trạng thái:** Đề xuất (007), chờ người dùng xác nhận sau khi xem video dự phòng (OPEN §4)
- **Quyết định:**
  - (a) Canh show (`ops/watchdog.py`) chỉ quan sát và cảnh báo trên trang điều khiển. Việc tự làm duy nhất: khi im lặng giữa hai câu
    tới `WATCHDOG_AUTOSKIP_S` (15 s) thì gọi `director.skip_current()` đúng một lần cho khoảng im lặng đó, rồi nâng mức "cần người vận
    hành" nếu vẫn im thêm `WATCHDOG_SILENCE_S`.
  - (b) Hình đứng và mất tiếng dựa vào nhịp `host_status` mỗi giây của tab host (`framesDecoded` của WebRTC, trạng thái `AudioContext`,
    thẻ `<video>`), không phân tích hình.
  - (c) Video dự phòng làm bằng show chế độ nội dung `verbatim` (đọc nguyên văn giới thiệu + mô tả, không gọi LLM) qua đúng đường
    realtime, ghi bằng recorder của fork (005), kiểm bằng `ailive_ext.analyze`. Không cắt, không ghép, không dựng hậu kỳ. App không có
    route nào phát file video (FR-021).
  - (d) Nguồn điện đọc qua `ctypes` (`GetSystemPowerStatus`) của stdlib, ổ đĩa qua `shutil.disk_usage`; không thêm thư viện.
- **Lý do:** spec 007 (Làm rõ 2026-11-13); `skip_current` là nút "Bỏ qua câu đang nói" đã có test 004. `getStats` chạy cả khi tab ở nền.
  Recorder ghi đúng khung đã ghép nhãn "AI", cảnh và watermark.
- **Phương án đã loại:** tự khởi động lại TTS/fork (M2); bỏ câu nhiều lần; phân tích ảnh trên app; quay màn hình tab `/host`; dựng video
  từ ảnh + tiếng; `psutil` cho nguồn điện (phụ thuộc mới chỉ cho một mục Cảnh báo).
- **Hệ quả:** thêm cấu hình `WATCHDOG_*`, `READINESS_MIN_FREE_GB`, `BACKUP_VIDEO_DIR`; log phiên thêm `gaps.jsonl`, `alerts.jsonl`,
  `readiness.jsonl`, `session.json`. Video dự phòng chỉ dùng cho demo Meet/YouTube, không phát trên Shopee Live.
  - Sau đo GPU (007 T054): hạn báo mất tiếng tách hai ngưỡng, `WATCHDOG_AUDIO_ACK_S` 3 s cho ảnh tĩnh và
    `WATCHDOG_AUDIO_ACK_LIPSYNC_S` 6 s khi đang nhép miệng, vì fork vốn bắt đầu câu sau ~3 s (2 cảnh báo sai trong show 30 phút).

## ADR-058: Bỏ YouTube (M1c); 006 là đầu ra OBS qua Browser Source trang `/obs`
- **Ngày:** 2026-11-13 · **Trạng thái:** Chấp nhận (người dùng xác nhận 2026-11-19 trong gói duyệt 006)
- **Quyết định:**
  - (a) Bỏ mốc M1c "YouTube Unlisted" và feature `006-youtube-live` đã đề xuất: người dùng không live trên YouTube (2026-11-13). Demo vẫn
    qua Google Meet; giai đoạn sau là Shopee Live qua OBS.
  - (b) Feature 006 là `006-obs-output`: OBS thêm một **Browser Source** mở trang mới `/obs` của app (cùng `host.html` + `host.js`, lớp
    `obs` trên `<body>`), tự phát tiếng không cần bấm (CEF của OBS chạy `--autoplay-policy=no-user-gesture-required`), không lớp phủ,
    không chữ trạng thái, không phụ đề web. Tiếng vào OBS bằng "Control audio via OBS".
  - (c) `/ws/host` thêm query `role=obs|host` (thiếu = `host`). Ưu tiên cố định obs > host: trang host bị nhường hoặc bị từ chối nhận mã
    đóng 4001 `CLOSE_YIELDED` (`reason` `obs_active`); cùng vai thì kết nối mới thắng (4000 như cũ). Trang nhận 4000/4001 đóng
    `RTCPeerConnection` để nhả phiên duy nhất của fork.
  - (d) `OUTPUT_MODE=meet|obs`, mặc định `meet`; `webrtc` cũ hiểu là `meet` (log cảnh báo), giá trị khác là lỗi cấu hình. Chế độ chỉ đổi
    điều kiện của kiểm tra trước demo và canh show (007).
- **Lý do:** không thêm thư viện, không đổi fork; giữ ảnh tĩnh dự phòng (005 FR-022), ack phát tiếng và nhịp `host_status` mà show,
  bảng độ trễ và canh show đang dựa vào (research R1). Ưu tiên cố định để lỡ mở `/host` giữa live không cướp tiếng của OBS (spec FR-006/007).
- **Phương án đã loại:** fork `--transport virtualcam` (thêm `pyvirtualcam` + cáp âm thanh ảo, mất WebRTC và ack); fork `--transport rtmp`
  qua RTMP server cục bộ (thêm phụ thuộc, thêm 1–3 s trễ); Window Capture Chrome + Application Audio Capture (hai nguồn, vẫn phải bấm);
  "ai tới sau thắng" giữa hai trang.
- **Hệ quả:** `OutputSink` (ARCHITECTURE §3) vẫn chưa làm; RTMP/virtualcam trực tiếp từ fork để M2 nếu cần. Runbook thêm §8 OBS. Sửa lỗi
  tiềm ẩn: trang host bị thay trước đây vẫn phát `<video>` của fork (nói đôi) và giữ phiên fork.

## ADR-059: OBS Studio portable là công cụ kiểm trên máy dev, ngoài repo
- **Ngày:** 2026-11-13 · **Trạng thái:** Chấp nhận (Tự chọn khuyến nghị theo ủy quyền làm liên tục; người dùng xác nhận 2026-11-19 trong gói duyệt 006)
- **Quyết định:** để kiểm 006 không cần người, tải bản zip chính thức của OBS Studio (GitHub `obsproject/obs-studio` releases), giải nén
  ở `%LOCALAPPDATA%\ai-live\obs`, chạy `obs64.exe --portable --collection ailive --startrecording` với cấu hình cảnh và profile ghi
  dựng sẵn trong thư mục portable đó. Không cài vào hệ thống, không vào git, app không gọi hay phụ thuộc OBS. Máy demo dùng bản OBS
  người vận hành tự cài.
- **Lý do:** cần chứng minh trong OBS thật (không chỉ Chrome mô phỏng) rằng Browser Source có hình WebRTC, có tiếng vào mixer và nhãn "AI"
  trong khung ghi (research R3, R10). OBS là GPL-2.0, chỉ chạy như công cụ, không phân phối kèm.
- **Phương án đã loại:** chỉ kiểm bằng Chrome `--autoplay-policy` (không chứng minh được mixer OBS); thêm `obs-websocket` client
  (`obsws-python`) để điều khiển OBS (phụ thuộc mới, không cần cho app); cài OBS bằng winget (ghi vào hệ thống).
- **Hệ quả:** quickstart §4 có bước dựng `config/obs-studio` portable; dừng ghi bằng tắt tiến trình nên ghi dạng Fragmented MP4. Xóa thư
  mục khi xong cũng được, không ảnh hưởng app.
- **Ghi chú 2026-11-13:** đã tải OBS 33.0.1 (zip x64, 224 MB) và dựng cấu hình portable; bộ phân quyền của Claude Code chặn
  chạy `obs64.exe` vừa tải, nên lần ghi thử chờ người dùng cho phép (006 quickstart §5).

## ADR-060: Thử Ultralight-Digital-Human trong fork để miệng giống người hơn; video huấn luyện tạo từ nhân vật AI
- **Ngày:** 2026-11-17 · **Trạng thái:** Chấp nhận để thử, chưa đổi mặc định.
  - Người dùng chọn hướng 2 của research R13 010 ("thử hướng 2 Ultralight, viết ADR đi").
  - Cùng ngày, người dùng chọn quay người thật ("tôi dùng cách 2"), rồi đổi lại: "dùng AI thôi không dùng người thật".
  - Nhân vật vẫn là gương mặt AI của ADR-036. Không cần người mẫu ký đồng ý.
  - Người dùng xác nhận InfiniteTalk trên Kaggle ("Dùng InfiniteTalk trên Kaggle") và cài `ffmpeg` bằng winget (mục 1, 2).
- **Bối cảnh:**
  - wav2lip256 không đạt SC-001 của 010 dù đã thử mọi núm hậu kỳ (ADR-055, research R6, R10, R12). Hình miệng do model quyết định.
  - MuseTalk quá chậm trên GTX 1650 Ti, chỉ khoảng 0,7 khung/giây (R4).
  - Ultralight-Digital-Human (anliyuan) huấn luyện một UNet nhỏ riêng cho từng người, từ 3–5 phút video có tiếng.
    Theo tác giả, model chạy realtime được trên điện thoại.
  - Fork LiveTalking của mình **đã có sẵn đường suy luận** `--model ultralight` (`avatars/ultralight_avatar.py`, `avatars/ultralight/`).
    Code huấn luyện thì không có trong fork.
- **Quyết định (thử nghiệm, chưa đổi mặc định):**
  1. **Video huấn luyện tạo offline từ nhân vật AI** (người dùng xác nhận 2026-11-17). *Sửa bởi ADR-063 (2026-11-18): InfiniteTalk
     trên T4 quá chậm cho 3–5 phút; đang thử MuseTalk 1.5 làm thầy lồng miệng trên nền chuyển động InfiniteTalk ngắn.*
     - Dùng **InfiniteTalk** (MeiGen-AI, Apache-2.0, dựa trên Wan2.1) trên Kaggle miễn phí, theo cách ADR-036 đã làm với ComfyUI.
     - Đầu vào là clip nói hoặc ảnh của nhân vật hiện tại, cộng 3–5 phút tiếng VieNeu đọc nội dung sản phẩm. Chế độ video-to-video giữ
       chuyển động đầu của clip và chỉ tạo lại miệng, mặt, cử động theo tiếng.
     - Notebook `scripts/avatar_clips/make_infinitetalk_video.ipynb`: ComfyUI headless + kijai ComfyUI-WanVideoWrapper (ghim commit
       `a7439db`), model chính Wan2.1 I2V 480p GGUF Q6_K, InfiniteTalk Single Q8, LoRA lightx2v 6 bước, fp16, block swap để vừa T4.
       Đầu vào là dataset Kaggle riêng tư (`start.png` + `*.wav`) do người dùng tải lên, vì MCP Kaggle không tạo được dataset.
     - **Ghim `transformers==4.57.6` trong notebook** (2026-11-18, chỉ trong phiên Kaggle, không đổi `pyproject.toml` của repo):
       - Kaggle cài sẵn transformers 5.x. Wrapper tự viết lớp `Wav2Vec2Model` riêng (`multitalk/wav2vec2.py`) gọi encoder với
         `output_hidden_states`; transformers 5 không trả `hidden_states` theo cách đó, nên nút `MultiTalkWav2VecEmbeds` lỗi
         `TypeError: 'NoneType' object is not subscriptable` (version 4, khoảng 4,5 phút GPU).
       - Nhánh `main` của wrapper chưa sửa file này từ 2025-07-01, nên đổi commit wrapper không giúp được.
       - 4.57.6 là bản 4.x cuối; ComfyUI chỉ cần `transformers>=4.50.3`. Notebook in và ghi phiên bản vào `run.json`.
     - Dataset phải gắn trên giao diện Kaggle (Add Input → Save Version): `save_notebook` của MCP bỏ qua trường dataset, và mỗi lần
       đẩy code bằng API có thể làm mất dataset đã gắn.
     - Nhân vật (người dùng đổi 2026-11-17): không dùng lại `demo_host_01`. Tạo nhân vật AI mới `demo_host_02` theo kiểu một buổi live
       bán hàng: ngồi sau bàn, sau lưng là kệ shop mỹ phẩm, áo polo trơn. Ảnh tạo bằng FLUX.1-schnell (Apache-2.0, đã cho phép ở ADR-036)
       qua notebook `scripts/avatar_clips/make_host_scene.ipynb`. Ảnh chụp màn hình live mẫu người dùng gửi chỉ dùng để tham khảo bố
       cục, không đưa vào notebook, không chép gương mặt hay logo trong đó. Ảnh đã có bàn, nên khi live bằng nhân vật này cần tắt lớp
       bàn của cảnh 009.
     - Chạy thử 13 giây trước để xem khẩu hình tiếng Việt và đo tốc độ, rồi mới chạy 3–5 phút.
     - Ra 480p, 25 khung/giây. 20 giây đầu là tiếng im để có khung lúc host không nói.
     - Trên T4 chạy khoảng 0,5–1 khung/giây (theo README notebook Colab), nên 3 phút (4.500 khung) mất khoảng 1,5–2,5 giờ. Vừa trong
       hạn mức GPU Kaggle.
     - Đây là việc tạo dữ liệu huấn luyện, không phải video phát live. Live vẫn sinh realtime (ràng buộc 1).
     - Ultralight sẽ học khẩu hình của InfiniteTalk, nên chất lượng miệng không vượt được InfiniteTalk.
  2. **Huấn luyện:**
     - Mã `anliyuan/Ultralight-Digital-Human` đã clone (`--depth 1`) vào `vendor/ultralight/`, ngoài git.
     - Chạy `data_utils/process.py --asr hubert`, rồi `train.py --asr hubert`.
     - Thử trên laptop trước (UNet nhỏ). Nếu thiếu VRAM hoặc quá chậm thì chuyển sang Kaggle.
     - Dùng **HuBERT**, không dùng WeNet: tác giả nói HuBERT đẹp hơn, và fork chỉ hỗ trợ HuBERT.
     - `process.py` gọi `ffmpeg` trên PATH. Đã cài bằng `winget install Gyan.FFmpeg` (bản 9.0.2, 2026-11-17), là công cụ hệ thống,
       không phải dependency Python.
     - **Chạy thử trên laptop ngày 2026-11-18**, dùng venv của fork. Dữ liệu là video 13 giây ghép từ `talk_01` của `demo_host_01`
       và `preview.wav`, 337 khung, chỉ để thử đường chạy, không để đánh giá chất lượng:
       - Phải sửa 2 chỗ trong `vendor/ultralight` (ngoài git):
         - Bỏ dòng `from os import wait3` không dùng trong `get_landmark.py`, vì Windows không có hàm này.
         - `hubert.py` đọc biến `HUBERT_MODEL_PATH` để nạp bản HuBERT đã tải, không tải lại lần nữa.
       - Lỗi trong venv của fork: `torchaudio` 2.11 không khớp `torch` 2.9.1, nên mọi model của `transformers` không import được.
         Lỗi này chặn cả HuBERT của đường suy luận `--model ultralight`. Đã cài lại `torchaudio==2.9.1` và ghim cùng phiên bản với
         torch trong `scripts/livetalking/setup.ps1`. Wav2Lip không dùng torchaudio nên cấu hình demo không bị ảnh hưởng.
       - Tốc độ tiền xử lý: dò điểm mặt dưới 1 phút cho 391 khung; HuBERT 12 giây cho 13 giây tiếng.
       - Tốc độ huấn luyện: khoảng **3,3 ảnh/giây** (batch 16), VRAM đỉnh khoảng 3,9 GB. Nút thắt là GPU, không phải đọc dữ liệu
         (bộ đọc ra 148 mẫu/giây trên một tiến trình). Video 3 phút (4.500 khung) sẽ mất khoảng 23 phút mỗi epoch. Với 200 epoch
         mặc định là khoảng 76 giờ, nên **không huấn luyện đủ trên laptop**. Sẽ chuyển sang Kaggle như đã dự phòng ở trên.
       - `train.py` tự tải trọng số VGG19 ImageNet của torchvision (548 MB, vào `~/.cache/torch/hub/checkpoints/`, ngoài git) để
         tính perceptual loss. Đây là model phụ của bước huấn luyện, không chạy lúc live. TODO: kiểm license trọng số VGG19 trước M2.
     - **Ghim commit Ultralight `ff0454d31059a95ff230cedbd11222f36441555d`** (2026-11-18): commit sau đó `b2dd34a` đổi tên khoá
       của UNet, nên model huấn luyện bằng code mới không nạp được vào `avatars/ultralight/unet.py` của fork. Đã thử nạp strict
       vào fork: khớp.
     - **Trainer riêng `scripts/avatar_clips/ultralight_train.py`** thay cho `train.py` gốc. Dùng cùng `unet.Model` và cùng loss
       (L1 + perceptual VGG19), thêm:
       - Sửa lỗi `__len__` của `datasetsss.py` gốc.
       - Chạy tiếp từ `last.pt` (Kaggle dừng phiên sau 12 giờ), giới hạn thời gian `--max_minutes`, xuất `ultralight.pth` khi hết giờ.
       - AMP fp16 (`--amp`). Trên GTX 1650 Ti, VGG19 chạy fp16 ra NaN, nên perceptual loss luôn chạy fp32.
       - Đo nhanh `--bench_steps`, ảnh xem trước, `history.json`, `--pth_every` để đầu ra Kaggle không quá nặng (mỗi file ~49 MB).
     - **AMP trên laptop** (batch 16): 3,33 → **17,2 ảnh/giây**, VRAM đỉnh 5,24 → 3,33 GB (số 3,9 GB ở trên đo bằng `train.py` gốc).
       Video 3 phút sẽ khoảng 4,5 phút mỗi epoch, 200 epoch khoảng 15 giờ: vẫn dài cho laptop, nên vẫn huấn luyện trên Kaggle.
     - **Notebook Kaggle `scripts/avatar_clips/train_ultralight.ipynb`** (2026-11-18, chưa chạy; đã đẩy lên Kaggle dạng
       riêng tư, T4, chỉ lưu chưa chạy: `jintran0501/ai-host-train-ultralight-demo-host-02`, version 1):
       - Đầu vào: đầu ra của notebook InfiniteTalk (video `<CHARACTER_ID>_train_v1.mp4`), gắn trong giao diện Kaggle.
         *Đổi bởi ADR-064:* chọn thầy bằng biến `TEACHER` (`musetalk` cho dev, `infinitetalk` cho prod).
       - Đổi video sang 25 khung/giây nếu cần, chạy `process.py --asr hubert`, kiểm số khung/điểm mặt/đặc trưng tiếng
         (vì `process.py` gọi lệnh qua `os.system`, lỗi không làm dừng), lưu ảnh kiểm vùng cắt miệng.
       - HuBERT ghim revision `ece5fabbf034c1073acae96d5401b25be96709d8` (Apache-2.0), chỉ tải `*.json` và `pytorch_model.bin`.
       - Đo fp32 và AMP trên 40 bước, chọn AMP nếu nhanh hơn ≥ 1,1 lần; huấn luyện trong ngân sách 690 phút của phiên; tự chạy tiếp
         nếu gắn đầu ra của chính notebook này; kiểm nạp strict + chạy thử model; ghi `provenance_train.json`.
       - Đầu ra (ngoài git): `ultralight.pth`, `last.pt`, `loss.png`, ảnh xem trước, log. Lưu về
         `assets/avatars/<CHARACTER_ID>/ultralight/` (*đổi bởi ADR-064:* `ultralight/<TEACHER>/`).
       - TODO: đo tốc độ thật trên T4.
       - TODO: batch 16 khác mặc định 1 của tác giả; so chất lượng với batch nhỏ hơn nếu kết quả miệng mờ.
       - TODO: kiểm license mã Ultralight-Digital-Human trước M2.
     - `genavatar.py` của fork gọi `os.system("cp ...")`, không chạy trên Windows. **Đã sửa 2026-11-18** (fork, chưa commit):
       - Thêm hàm `generate_avatar(video_path, avatar_id, checkpoint, save_path, img_size=168)` giống kiểu của wav2lip; chép bằng
         `shutil.copy`; `argparse` chuyển vào `__main__`. Chạy từ gốc fork: `python -m avatars.ultralight.genavatar ...`.
       - Bỏ `from os import wait3` (chỉ có trên Unix, không dùng) ở `face_detect_utils/get_landmark.py`.
       - Bản gốc truyền `cv2.INTER_AREA` vào chỗ tham số `dst` nên thực ra cắt mặt bằng nội suy mặc định; giờ dùng `INTER_AREA`
         đúng như `ultralight_train.py`.
       - `Landmark` cần `models/scrfd_2.5g_kps.onnx` (3,3 MB) và `models/checkpoint_epoch_335.pth.tar` (5 MB) trong fork, cùng
         file trong `data_utils/` của repo Ultralight lúc huấn luyện. `train_ultralight.ipynb` chép 2 file này vào
         `landmark_models/` của đầu ra (kèm sha256 trong `provenance_train.json`); tải về thì chép vào `vendor/livetalking/models/`
         (ngoài git). `Landmark` gọi `.cuda()` nên dựng avatar cần GPU laptop.
       - Notebook trên Kaggle (`ai-host-train-ultralight-demo-host-02`) phải đẩy lại bản này trước khi chạy.
  3. **Suy luận trên laptop:**
     - Đã tải `facebook/hubert-large-ls960-ft` (1,26 GB) vào `vendor/livetalking/models/hubert-large-ls960-ft/`, ngoài git, ngày
       2026-11-17. Không tải `tf_model.h5`.
     - Chạy fork với `--model ultralight`, avatar dựng từ video huấn luyện (`genavatar.py`).
     - Nhãn "AI", watermark, cảnh 009 và bản ghi tự kiểm nằm trong `base_avatar`, nên dùng chung được.
     - Thư viện clip của nhân vật (`--ailive_character`: xoay vòng clip, cắt theo góc đầu, `LIVETALKING_MOUTH_METHOD`) hiện chỉ chạy với
       wav2lip. Phần này **chưa** nối cho Ultralight trong lần thử đầu.
  4. **So sánh:**
     - Dùng bộ đo 010 với bộ câu v2 (27 câu, tiếng VieNeu), so với số r5 của wav2lip256.
     - Chỉ số: hình miệng MediaPipe (ADR-053), LSE-C/LSE-D SyncNet (ADR-054), `render_fps` và VRAM đỉnh khi chạy show.
     - Cuối cùng là một cặp xem mù A/B.
  5. **Ngưỡng thành công để làm tiếp:**
     - Đạt SC-001 của 010: ≥ 2/4 chỉ số hình miệng tốt hơn 15% và LSE-C không giảm.
     - `render_fps` p50 ≥ 20 trên laptop.
     - VRAM đỉnh ≤ 3,5 GB.
     - Không lỗi trong show 10 phút.

     Đạt thì mở feature mới qua `/sdd.specify` để đưa Ultralight vào luồng chính: thư viện clip, biến chọn model, readiness, RUNBOOK.
     Không đạt thì giữ wav2lip256 và ghi số đo vào ADR này.
- **Lý do:**
  - Đây là hướng duy nhất miễn phí còn lại mà vẫn đổi được **model** trên GPU 4 GB.
  - Fork đã có code suy luận, nên phần việc chủ yếu là dữ liệu và huấn luyện.
  - Lý do chọn InfiniteTalk:
    - Mở nguồn, miễn phí, được dùng nhiều (có workflow ComfyUI), và tạo video dài không giới hạn.
    - Theo TalkVerse (CVPR 2026), các model tạo video dài đều xuống chất lượng theo thời gian. Vì vậy nên tạo từng đoạn ngắn rồi nối lại.
  - Điểm cộng của nhân vật AI: không cần người mẫu, không có dữ liệu cá nhân, giữ đúng nhân vật đang dùng.
- **Phương án đã loại:**
  - Quay người thật: người dùng đổi ý cùng ngày. Hướng dẫn quay vẫn để ở 010 quickstart §8 nếu cần sau này.
  - HeyGen Avatar IV: được dùng nhiều nhất ở Việt Nam và miệng rất giống người, nhưng có nhược điểm:
    - Gói free chỉ 720p, có watermark, và theo các bài tổng hợp chỉ cho dùng cá nhân, phi thương mại. Không hợp với dịch vụ có thu tiền.
    - Gói trả phí khoảng 24 USD/tháng: tốn tiền, phải hỏi trước.
  - Kling AI Avatar 2.0: free 66 credit/ngày, mà 8 credit đổi được 1 giây, tức khoảng 8 giây mỗi ngày. Không đủ 3–5 phút.
  - LatentSync 1.5: chỉ sửa vùng miệng trên clip có sẵn, kém tự nhiên hơn InfiniteTalk. Để làm dự phòng.
  - Huấn luyện từ chính đầu ra wav2lip256: model sẽ học lại đúng khẩu hình đang muốn bỏ.
  - WeNet: tác giả nói kém đẹp hơn HuBERT, và fork không có đường suy luận cho nó.
  - Bản thương mại LiveTalking, MuseTalk trên RunPod: tốn tiền, để dành nếu hướng này trượt (R13).
- **Rủi ro:**
  - HuBERT `ls960` học trên tiếng Anh, có thể bắt âm tiếng Việt kém hơn. Bộ đo 010 sẽ cho biết.
  - InfiniteTalk học chủ yếu trên tiếng Trung và tiếng Anh, nên khẩu hình tiếng Việt chưa được kiểm. Cần xem 20–30 giây thử trước khi
    chạy đủ 3 phút.
  - Video 480p: khung mặt nhỏ, có thể hơi mờ so với ảnh crop 168 px của Ultralight.
  - Có issue "cằm to nhỏ thất thường" ở FeatherTalk (bản kế tiếp của Ultralight).
  - Live dùng video AI lặp lại làm nền: cùng câu hỏi P2 với Shopee như video nền hiện tại.
- **TODO:**
  - Ultralight-Digital-Human: README gắn badge Apache-2.0 và trỏ tới `./LICENSE`, nhưng repo không có file LICENSE và GitHub API trả
    `license: null`. Không có file license thì mặc định mọi quyền được bảo lưu. Cần hỏi tác giả hoặc chốt trước M2 (RISKS).
  - `facebook/hubert-large-ls960-ft`: thẻ model ghi Apache-2.0.
  - InfiniteTalk và Wan2.1: Apache-2.0; kiểm lại trên repo khi tải. TODO: kiểm license bản GGUF và LoRA lightx2v mà notebook tải.

## ADR-061: Sửa ảnh host cho giống ảnh chụp thật bằng Qwen-Image-Edit-2511 trên Kaggle
- **Ngày:** 2026-11-17 · **Trạng thái:** Chấp nhận để thử (người dùng: "ok bắt đầy triển khai").
- **Bối cảnh:**
  - Người dùng nói việc cần nhất lúc này là "digital human phải tốt nhất" và gửi một prompt sửa ảnh: giữ nguyên danh tính, dáng ngồi,
    quần áo, tay, bố cục và shop; chỉ làm da, mắt, nét mặt, tay, ánh sáng kiểu máy ảnh DSLR và nền shop thật hơn.
  - Ảnh đang chọn của `demo_host_02` là `scene_real_chest_up_seed606.png` (FLUX.1-schnell, ADR-060). Ảnh còn dấu hiệu AI: ngón tay
    rối, da mịn, ánh sáng phẳng, kệ hàng quá sạch.
  - Thử làm lại da bằng img2img FLUX.1-schnell (lượt 2, `make_host_scene.ipynb` §5b) chỉ đổi da, không sửa được tay, và mức nhiễu cao
    thì mặt lệch khỏi ảnh gốc.
  - Ảnh này sẽ là `start.png` của InfiniteTalk, nên mọi lỗi trong ảnh sẽ đi vào video huấn luyện Ultralight.
- **Quyết định:**
  - Dùng **Qwen-Image-Edit-2511** (Alibaba Qwen, Apache-2.0), model sửa ảnh theo câu lệnh, giữ danh tính tốt hơn img2img. Chạy bằng
    ComfyUI headless trên Kaggle T4, như ADR-036. Đây là bước chuẩn bị offline, **không nằm trong pipeline live**, không thêm gì vào
    `pyproject.toml`, model không tải về laptop.
  - Notebook mới `scripts/avatar_clips/edit_host_photo.ipynb`. Đầu vào là output của notebook Kaggle `ai-host-scene-demo-host-02`,
    gắn vào bằng nguồn dữ liệu kernel (không cần tạo dataset).
  - Model (kiểm trên Hugging Face ngày 2026-11-17, ghim revision trong notebook và ghi vào `provenance_edit.json`):
    - Model chính: `unsloth/Qwen-Image-Edit-2511-GGUF`, file `qwen-image-edit-2511-Q4_K_M.gguf` (12,84 GB), revision `52838251db`.
      GGUF vì T4 không có bf16 và chỉ có 15 GB VRAM. Bản gốc: `Qwen/Qwen-Image-Edit-2511` @ `6f3ccc0b56`.
    - LoRA 8 bước: `lightx2v/Qwen-Image-Edit-2511-Lightning`, `Qwen-Image-Edit-2511-Lightning-8steps-V1.0-bf16.safetensors` @ `107d238d68`.
    - Bộ mã hoá chữ và VAE: `Comfy-Org/Qwen-Image_ComfyUI` @ `1f12b17be1`, file `qwen_2.5_vl_7b_fp8_scaled.safetensors` và
      `qwen_image_vae.safetensors`.
    - Node đọc GGUF: `city96/ComfyUI-GGUF` (Apache-2.0), ghim commit `6ea2651e7d`.
  - Đồ thị node theo template chính thức `image_qwen_image_edit_2511.json` của Comfy-Org: `ModelSamplingAuraFlow` 3,1 → `CFGNorm` →
    LoRA Lightning, `TextEncodeQwenImageEditPlus` có ảnh gốc, `FluxKontextMultiReferenceLatentMethod` = `index_timestep_zero`,
    KSampler euler/simple, cfg 1, denoise 1.
  - Ảnh đưa vào được phóng lên 776×1352. Ở cỡ này, ảnh tham chiếu mà node tự thu về khoảng 1 megapixel có đúng cỡ ảnh ra, nên ảnh sửa
    không bị lệch hay phóng to so với ảnh gốc. Ảnh ra thu lại về 768×1344 như ảnh gốc.
  - Prompt chia làm 3 lần sửa ngắn, nối tiếp nhau: (1) da và mắt, (2) tay trên bàn, (3) ánh sáng, độ sâu trường ảnh và kệ shop. Mỗi
    lần đều yêu cầu giữ người, dáng, áo, bố cục, và **môi khép, thả lỏng, không lộ răng** (khung chờ của lip-sync cần miệng đóng). Có
    thêm một lần sửa gộp cả 3 ý để so. Mỗi cách chạy 3 seed.
  - Người dùng chọn ảnh bằng mắt từ `contact_sheet_edit.jpg` và `face_compare_edit.jpg`. Sau khi chọn mới tạo lại `start.png`
    480×832 cho InfiniteTalk.
- **Lý do:**
  - Qwen-Image-Edit-2511 là model sửa ảnh mở nguồn có license thương mại, chạy được trên GPU miễn phí, và bản 2511 được làm để giữ
    nhân vật nhất quán hơn bản 2509.
  - Sửa ảnh giữ được gương mặt đã chọn; tạo mặt mới thì phải chọn lại từ đầu.
  - Chia nhỏ câu lệnh vì model sửa ảnh làm tốt từng việc một; câu lệnh dài nhiều ý dễ đổi cả bố cục.
- **Phương án đã loại:**
  - FLUX.1 Kontext dev: license phi thương mại (như FLUX.1-dev, ADR-036).
  - Gemini, ChatGPT bản web: điều khoản và quyền với ảnh ra chưa rõ, không ghi được hồ sơ nguồn gốc theo revision, và có thể tốn tiền.
  - Chỉ inpaint bằng FLUX.1-schnell: model chưng cất 4 bước, sửa tay kém và không có chế độ làm theo câu lệnh.
  - Bản `fp8mixed` hoặc bf16 của Comfy-Org (20 GB và 40 GB): không vừa VRAM T4.
- **Rủi ro:**
  - T4 chạy fp16, Qwen-Image có thể ra ảnh đen. Notebook kiểm độ sáng ảnh đầu; nếu ảnh đen thì bật lại ComfyUI với `--bf16-unet` (chạy
    giả lập, chậm hơn) và thử lại một lần.
  - RAM Kaggle khoảng 30 GB, VRAM 15 GB: model 12,8 GB cộng bộ mã hoá chữ khoảng 9 GB. ComfyUI tự tải từng phần; nếu vẫn thiếu thì đổi
    sang `Q3_K_M` (9,9 GB).
  - Sửa ảnh vẫn có thể đổi nhẹ gương mặt. Người dùng so mặt trước và sau bằng `face_compare_edit.jpg`.
  - Ảnh trông thật hơn cũng làm người xem khó nhận ra đây là AI, nên nhãn "AI" trên khung hình càng phải luôn hiện (ràng buộc 2).
- **TODO:**
  - Đọc lại license LoRA Lightning (thẻ model ghi Apache-2.0) và bản GGUF của unsloth (thẻ ghi Apache-2.0) trước khi khách trả tiền,
    cùng lúc với TODO điều khoản Kaggle của ADR-036.
- **Kết quả lần chạy đầu** (Kaggle `jintran0501/ai-host-edit-demo-host-02`, xong 2026-11-18; ảnh tải về
  `assets/avatars/demo_host_02/run3/`, ngoài git):
  - Ảnh gốc đúng `scene_real_chest_up_seed606.png` (768×1344, sha256 `3c8002881857`). Tesla T4, torch 2.11.0+cu130, ComfyUI
    `5071348042`. Không có ảnh đen, không phải bật `--bf16-unet`; độ sáng trung bình 155,1–159,0 so với ảnh gốc 158,9.
  - Thời gian: tải model 71 s (12,84 GB) + LoRA 8 s + bộ mã hoá chữ 46 s (9,38 GB) + VAE 2 s; ComfyUI sẵn sàng ở giây 242.
    12 lần sửa mất 555,8–615,8 s mỗi lần (khoảng 9,5 phút); cả notebook 7124 s (khoảng 1 giờ 59 phút).
  - Nhận xét bằng mắt (người dùng chưa duyệt):
    - Lần sửa ánh sáng và nền (`3_light_bg`) làm tường phía trên kệ có vết lem ở cả 3 seed.
    - Seed 22 và 33 thêm chấm đen giả lỗ chân lông và vệt trên trán, mặt lệch khỏi ảnh gốc nhiều hơn (cười ít hơn, mặt rộng hơn).
    - Seed 11 giữ mặt gần ảnh gốc nhất. Bản gộp `seed11_combined.png` sạch nhất: tường không lem, tay rõ ngón, môi khép.
  - Người dùng duyệt `seed11_combined.png` ngày 2026-11-18 ("ok ổn tiếp tục đi"). Đã làm lại `training/kaggle_input/start.png` theo
    cách cũ: thu về 480×840 (Lanczos, khớp từng điểm ảnh với `start.png` trước), cắt 8 px phía trên, ra 480×832. Bản chưa sửa giữ
    ở `training/start_seed606_raw.png`; ghi vào `provenance.json` mục `edited`.

## ADR-062: Giữ nguyên cấu hình demo ở Wav2Lip `w2l`; Ultralight và `demo_host_02` làm song song
- **Ngày:** 2026-11-18 · **Trạng thái:** Chấp nhận (người dùng: "1 đồng ý", trả lời đề xuất ngày 2026-11-17 ở `progress/OPEN.md` §4).
  Bổ sung bởi ADR-066: `demo_host_02` là host của khách demo khi 011 đạt; đánh giá làm sau khi project xong (sửa 2026-11-19: đánh giá ngay khi model Kaggle xong, không chờ cả project xong).
- **Bối cảnh:**
  - Cấu hình demo hiện tại đã qua kiểm luồng ngày 2026-11-17: fork LiveTalking với wav2lip256, `LIVETALKING_MOUTH_METHOD=w2l`
    (ADR-055), nhân vật `demo_host_01`, cảnh 009.
  - Hướng Ultralight (ADR-060) với nhân vật mới `demo_host_02` (ADR-061) còn nhiều bước chưa chắc đạt: chọn ảnh, video InfiniteTalk,
    huấn luyện trên Kaggle, đo so sánh theo ngưỡng ở ADR-060 mục 5.
- **Quyết định:**
  - Buổi demo với khách dùng cấu hình hiện tại. Không đổi mặc định, nhân vật hay model của cấu hình demo vì việc Ultralight.
  - Ultralight và `demo_host_02` chạy song song: notebook Kaggle, file ngoài git, lệnh fork chạy riêng với `--model ultralight`.
  - Chỉ thay cấu hình demo khi Ultralight đạt ngưỡng ở ADR-060 mục 5, qua feature mới (`/sdd.specify`), và còn kịp tổng duyệt
    30 phút trước ngày demo. Ngày demo chưa chốt nên chưa có hạn cụ thể.
- **Lý do:** cấu hình hiện tại đã chạy được và đã kiểm; đổi model sát ngày demo có thể làm hỏng buổi demo mà khách chỉ trả tiền nếu demo tốt.
- **Phương án đã loại:** chờ Ultralight xong mới demo (lùi ngày demo mà chưa chắc tốt hơn).

## ADR-063: Thử MuseTalk 1.5 làm "thầy" thay InfiniteTalk cho video huấn luyện Ultralight; so sánh trước trên Kaggle
- **Ngày:** 2026-11-18 · **Trạng thái:** Chấp nhận để thử (người dùng: "tôi đồng ý", trả lời đề xuất đổi sang model nhanh hơn chạy
  trên Kaggle free). Sửa ADR-060 mục 1: InfiniteTalk không còn là đường duy nhất để tạo video huấn luyện.
- **Bối cảnh:**
  - InfiniteTalk trên T4 (notebook `ai-host-infinitetalk-demo-host-02`, version 6) mất khoảng **26,5 phút cho một cửa sổ 81 khung**,
    chậm hơn nhiều so với ước tính 0,5–1 khung/giây ở ADR-060 mục 1. Video 4 phút sẽ mất khoảng 37 giờ, quá hạn mức GPU Kaggle.
    ComfyUI còn chết sau cửa sổ 1 (có thể hết RAM, máy Kaggle khoảng 30 GB).
  - Người dùng xem 81 khung đầu và thấy hình đạt ("ảnh tôi thấy ổn rồi đấy").
  - MuseTalk 1.5 chỉ đổi vùng miệng trên khung có sẵn, chạy một bước (không khuếch tán nhiều bước), nên nhanh hơn InfiniteTalk rất
    nhiều. Trên laptop chỉ khoảng 0,7 khung/giây (010 research R4) nên đã loại cho live, nhưng **chưa ai xem chất lượng miệng** của nó.
- **Quyết định:**
  1. **Chạy so sánh trước** (khoảng 1 giờ GPU Kaggle, miễn phí): MuseTalk 1.5 lồng tiếng lại đúng 81 khung InfiniteTalk với cùng
     đoạn tiếng 0–3,24 giây của `preview.wav`, ra video đặt cạnh nhau (InfiniteTalk | MuseTalk) và cận cảnh miệng. Người dùng xem và
     chấm: môi khép ở m/b/p, môi tròn ở ô/u/o, răng, độ mờ, rung, đường nối quanh cằm. Thêm một bản MuseTalk dài 13,5 giây (khung chạy
     tới rồi lùi) để xem nói lâu hơn.
  2. Notebook `scripts/avatar_clips/musetalk_compare.ipynb`, chỉ chạy trên Kaggle (`jintran0501/ai-host-musetalk-compare-demo-host-02`,
     riêng tư, T4, Internet; đầu vào: dataset `ai-live-infinitetalk-input`, bản thêm thư mục `infinitetalk_v6_frames/` gồm 81 khung version 6 của
     notebook InfiniteTalk, vì Kaggle không cho gắn đầu ra của lần chạy lỗi):
     - Mã MuseTalk chính thức (TMElyralab/MuseTalk, MIT), ghim commit `0a89dec45a0192b824e3cf4daf96c239440c5ed8`, clone trong phiên
       Kaggle, **không** thêm vào `pyproject.toml` của repo.
     - Trọng số tải trong phiên, ghim revision Hugging Face:
       - `TMElyralab/MuseTalk` @ `2bcb936e2fddb4d86db4c62fd45b387d0c061571`: `musetalkV15/musetalk.json`, `musetalkV15/unet.pth` (MIT).
       - `stabilityai/sd-vae-ft-mse` @ `31f26fdeee1355a5c34592e401dd41e45d25a493` (MIT), bản `.safetensors`.
       - `openai/whisper-tiny` @ `169d4a4341b33bc18d8881c4b69c2e104e1cc0af` (Apache-2.0), bản `.safetensors`.
       - BiSeNet face-parse `79999_iter.pth` (zllrunning/face-parsing.PyTorch) qua gdown như script chính thức; dự phòng là bản sao
         `ManyOtherFunctions/face-parse-bisent` @ `0073b233a5a3c4b1377d4dbf49245017938a72b5`. Nạp bằng `torch.load` chế độ
         `weights_only`, ghi sha256 vào `run.json`. `resnet18-5c106cde.pth` tải từ download.pytorch.org, kiểm tiền tố sha256
         `5c106cde` khi tải; file này ở định dạng tar cũ mà torch ≥ 2.6 không mở được ở chế độ `weights_only` (FaceParsing của
         MuseTalk nạp bằng mặc định đó), nên notebook nạp một lần rồi lưu lại dạng zip (state dict), ghi cả sha256 sau chuyển đổi.
     - **Thay DWPose bằng gói `face-alignment`** (BSD-3) để lấy 68 điểm mặt: bước tiền xử lý chính thức cần mmcv/mmpose, rất khó cài
       trên Kaggle. 68 điểm của face-alignment cùng thứ tự iBUG với điểm mặt 23:91 của DWPose, nên công thức khung cắt giữ nguyên.
     - Ghim `transformers==4.57.6` (giống notebook InfiniteTalk) và `diffusers==0.30.2` (bản MuseTalk chính thức dùng), chỉ trong phiên.
     - Tham số v15 mặc định của script chính thức: `bbox_shift=0`, `extra_margin=10`, má 90/90, ghép kiểu `jaw`, đệm tiếng 2/2,
       batch 8, fp16.
     - Đầu ra (ngoài git): video so sánh, cận cảnh miệng, ảnh ghép khung, `run.json` (phiên bản, sha256, tốc độ khung/giây trên T4).
  3. **Nếu MuseTalk đạt** (người dùng thấy miệng bằng hoặc tốt hơn InfiniteTalk): đi đường lai.
     - InfiniteTalk chỉ tạo 15–20 giây chuyển động nền (đầu, mắt, vai), phát tới rồi lùi cho đủ 3–5 phút.
     - MuseTalk lồng miệng theo 3–5 phút tiếng VieNeu đọc kịch bản phủ đủ âm tiếng Việt.
     - Ultralight huấn luyện trên video đó (ADR-060 mục 2 giữ nguyên).
     - Vẫn là dữ liệu huấn luyện offline, không phát live (ràng buộc 1).
  4. **Nếu không đạt:** quay lại InfiniteTalk đủ dài trên GPU thuê (Modal có khoảng 30 USD credit/tháng, hoặc RunPod). Phải hỏi người
     dùng về chi phí trước khi bật.
  - *Đổi bởi ADR-064:* không chọn một trong mục 3 và 4 nữa mà dùng cả hai: MuseTalk làm thầy dev ngay, InfiniteTalk làm thầy prod
    trước buổi demo.
- **Kết quả lần chạy so sánh** (Kaggle version 5, xong 2026-11-18, khoảng 5 phút; đầu ra tải về ngoài git):
  - Tốc độ trên T4: 81 khung 5,43 khung/giây tính cả bước ghép mặt (riêng UNet+VAE 8,34); bản dài 337 khung 7,18 khung/giây.
    VRAM đỉnh 6,86 GB. Video 4 phút (6.000 khung) ước khoảng 15–20 phút, so với khoảng 37 giờ của InfiniteTalk.
  - Khung cắt từ face-alignment khớp mặt (ảnh kiểm khung cắt); mặt chỉ rộng 122–132 px trong khung 480×832.
  - Chấm sơ bộ của Claude qua ảnh ghép khung (chưa nghe tiếng): miệng MuseTalk **mở ít hơn rõ rệt** so với InfiniteTalk (chỗ
    InfiniteTalk há rộng thấy răng thì MuseTalk chỉ hé), ít thấy răng, môi chưa tròn ở khung 52, vùng miệng mờ hơn phần mặt còn
    lại, màu môi tối hơn. Môi khép ở các khung im lặng thì ổn. Nghiêng về **không đạt** mục 3, chờ người dùng xem có tiếng và chấm.
  - TODO: người dùng chấm `side_by_side.mp4` và `mouth_closeup.mp4` theo bảng cuối notebook; nếu trượt, chọn giữa chỉnh tham số
    MuseTalk thêm một lần (miễn phí) và GPU thuê cho InfiniteTalk (hỏi giá trước).
- **Lý do:**
  - Rẻ nhất để biết sớm: test dùng lại 81 khung đã có, không phải chạy lại InfiniteTalk.
  - MuseTalk một bước nên tạo 3–5 phút trên T4 là khả thi; InfiniteTalk thì không.
  - Ultralight học khẩu hình từ video thầy, nên chất lượng miệng của thầy là trần chất lượng (ADR-060 mục 1).
- **Phương án đã loại:**
  - Chạy InfiniteTalk đủ 3–5 phút trên Kaggle: khoảng 37 giờ GPU, vượt hạn mức tuần và dễ chết giữa chừng.
  - Cài mmpose/DWPose trên Kaggle cho đúng y bản gốc: mmcv phải build theo phiên bản torch/CUDA, tốn thời gian và dễ vỡ.
  - LatentSync 1.5: nặng hơn MuseTalk (khuếch tán nhiều bước), để dự phòng nếu MuseTalk trượt.
- **Rủi ro:**
  - whisper-tiny và MuseTalk học chủ yếu trên tiếng Anh/Trung; khẩu hình tiếng Việt chưa kiểm. Test này sẽ cho biết.
  - MuseTalk tạo miệng ở 256×256 rồi thu lại, vùng miệng có thể mờ hơn phần mặt còn lại.
  - Khung cắt từ face-alignment có thể lệch nhẹ so với DWPose; notebook lưu ảnh kiểm khung cắt để xem.
- **TODO:**
  - Kiểm license trước M2: trọng số BiSeNet face-parse (repo zllrunning MIT, bản sao HF ghi WTFPL), trọng số S3FD/2DFAN4 của
    face-alignment, whisper-tiny (Apache-2.0), sd-vae-ft-mse (MIT). Ghi vào `docs/RISKS.md` khi chọn đường lai.
  - Đo tốc độ thật của MuseTalk trên T4 (notebook ghi vào `run.json`).

## ADR-064: Hai "thầy" cho Ultralight: MuseTalk cho dev, InfiniteTalk cho prod, đổi bằng một biến
- **Ngày:** 2026-11-18 · **Trạng thái:** Chấp nhận. Người dùng: "bản InfiniteTalk tốt hơn nhỉ nhưng hiện tại tôi thấy bên MuseTalk
  cũng ổn … hiện giờ triển khai theo MuseTalk trước => đến khi chuẩn bị demo thì đổi sang InfiniteTalk => … dễ chuyển đổi như 1 bên
  dev bên còn lại là prod". Sửa ADR-063 mục 3 và 4, ADR-060 mục 2 (đầu vào và thư mục kết quả). Đổi bởi ADR-066: thầy
  prod không bắt buộc cho buổi demo; model thầy MuseTalk đạt ngưỡng thì demo dùng nó.
- **Bối cảnh:**
  - Lần so sánh ADR-063: InfiniteTalk cho miệng tốt hơn, MuseTalk tạm chấp nhận được. MuseTalk làm video 3–5 phút trong khoảng
    20–30 phút trên T4 miễn phí; InfiniteTalk cần khoảng 37 giờ GPU, không làm được trên Kaggle free.
  - Người dùng muốn làm tiếp cả đường Ultralight ngay với MuseTalk, rồi đổi sang InfiniteTalk trước buổi demo mà không phải sửa lại.
- **Quyết định:**
  1. **Notebook mới `scripts/avatar_clips/make_musetalk_video.ipynb`** (chỉ chạy trên Kaggle,
     `jintran0501/ai-host-musetalk-video-demo-host-02`, riêng tư, T4, Internet): MuseTalk 1.5 lồng miệng theo cả `train_v1.wav`
     (khoảng 4,9 phút tiếng VieNeu, 20 giây im lặng đầu) lên 81 khung InfiniteTalk version 6, khung chạy tới rồi lùi.
     - Dùng lại nguyên các ô môi trường, trọng số và điểm mặt của `musetalk_compare.ipynb` (cùng commit, revision, phiên bản gói đã
       ghim ở ADR-063), nên không thêm gì vào `pyproject.toml`.
     - Khung ghép xong ghi thẳng vào ffmpeg qua pipe (không giữ khoảng 7.300 khung trong RAM).
     - Đầu ra ở `musetalk_out/train_v1/` (ngoài git): `<CHARACTER_ID>_musetalk_train_v1.mp4`, `preview.mp4` (15 giây sau đoạn im lặng),
       `mouth_sheet.png`, `crop_check.png`, `run.json`.
  2. **Hợp đồng chung của video thầy:** một file mp4 có tiếng, 25 khung/giây, nằm cùng thư mục với `run.json`. `run.json` của
     MuseTalk có trường `"teacher": "musetalk"`; `run.json` của InfiniteTalk chưa có trường này và được chấp nhận như hiện tại.
  3. **Công tắc `TEACHER` trong `train_ultralight.ipynb`:**
     - `"musetalk"` (dev, mặc định bây giờ): video `<CHARACTER_ID>_musetalk_train_v1.mp4`, notebook nguồn
       `jintran0501/ai-host-musetalk-video-demo-host-02`.
     - `"infinitetalk"` (prod): video `<CHARACTER_ID>_train_v1.mp4`, notebook nguồn `jintran0501/ai-host-infinitetalk-demo-host-02`.
     - Kết quả ở `ultralight_out/<CHARACTER_ID>/<TEACHER>/`, trên laptop ở `assets/avatars/<CHARACTER_ID>/ultralight/<TEACHER>/`:
       model dev không ghi đè model prod.
     - `run.json` cạnh video được chép thành `teacher_run.json`; `provenance_train.json` ghi `teacher` và tóm tắt lần chạy thầy.
       Notebook dừng nếu `run.json` hoặc `last.pt` để học tiếp ghi thầy khác `TEACHER`.
  4. **Chọn model khi live** (biến môi trường kiểu `ULTRALIGHT_TEACHER` hoặc đường dẫn model) thuộc feature tích hợp Ultralight sau
     này, làm qua `/sdd.specify` (ADR-060 mục 5). Chưa thêm vào `.env.example`.
  5. **Tốc độ nói:** không làm chậm riêng file tiếng huấn luyện, vì Ultralight sẽ học khẩu hình ở tốc độ khác tiếng TTS khi live.
     MuseTalk tạo từng khung theo đúng khung tiếng nên miệng không bị trễ; cái thấy "không theo kịp" chủ yếu là miệng mở ít và mờ.
     Nút thử trước là `EXTRA_MARGIN` (thêm chỗ cho cằm). Nếu vẫn muốn nói chậm hơn, phải đổi tốc độ VieNeu ở cả tiếng huấn luyện và
     khi live cho đồng nhất.
- **Lý do:**
  - Làm và thử được cả đường Ultralight → fork → live ngay bằng GPU miễn phí, không chờ InfiniteTalk.
  - Ultralight chép khẩu hình của thầy (ADR-060 mục 1), nên đổi thầy chỉ cần tạo video mới và huấn luyện lại, không đổi mã.
  - Mỗi thầy một thư mục giúp so model dev với model prod trên cùng kịch bản.
- **Phương án đã loại:**
  - Chỉ dùng MuseTalk: miệng mở ít và mờ hơn, người dùng muốn bản tốt hơn cho buổi demo.
  - Chờ InfiniteTalk rồi mới làm Ultralight: chặn mọi việc phía sau bằng một bước cần GPU thuê.
  - Hai notebook huấn luyện riêng: hai bản mã dễ lệch nhau.
- **Rủi ro:**
  - Model dev học từ miệng MuseTalk nên cũng mở ít; không dùng model dev để chấm chất lượng cuối.
  - Kiểu chuyển động của hai thầy khác nhau, nên các tham số chỉnh trên model dev (epoch, batch) có thể phải chỉnh lại cho prod.
- **TODO:**
  - Video InfiniteTalk đủ dài cho prod cần GPU thuê (RunPod hoặc Modal): hỏi người dùng về chi phí trước khi bật.
  - Thử `EXTRA_MARGIN` 15–20 nếu `preview.mp4` của MuseTalk mở miệng quá ít.
  - Người dùng xem `preview.mp4` có tiếng sau lần chạy đầu.

## ADR-065: Theo quy định nội dung AI của Shopee: nhãn mặc định "AI-GENERATED CONTENT", ghi các quy định vào ràng buộc
- **Ngày:** 2026-11-19 · **Trạng thái:** Chấp nhận (người dùng gửi ảnh chụp quy định và chọn "Đổi chữ nhãn" 2026-11-19). Đổi chữ
  mặc định của nhãn trong khung của fork (ADR-044) và nhãn trên trang host.
- **Bối cảnh:**
  - Người dùng gửi ảnh chụp quy định nội dung AI của Shopee và nhờ "thêm vào qui định". Sáu mục trong ảnh:
  1. Mọi nội dung do AI tạo (chữ, ảnh, video) phải gắn nhãn rõ ràng, ví dụ watermark "AI-generated"; banner mẫu trong ảnh ghi
     "AI-GENERATED CONTENT".
  2. Không dùng tài sản của bên thứ ba (logo, ảnh cá nhân) khi chưa được phép.
  3. Không dùng ảnh AI giống thật của người dưới 18 tuổi.
  4. Không dùng người nổi tiếng hoặc nhân vật giống họ khi chưa được phép.
  5. Không tạo nội dung gây hiểu nhầm (sai thông tin sản phẩm, đánh giá giả).
  6. Tránh nội dung chất lượng thấp: hình hoặc tiếng kém, không tương tác với người xem, nội dung lặp lại, cùng một host AI trên
     nhiều tài khoản.
  - Nguồn: chỉ có ảnh chụp. TODO: URL trang gốc, bản của Shopee nước nào, ngày hiệu lực; có áp cho Shopee Live Việt Nam không?
  - Trước đây nhãn mặc định chỉ là "AI": ngắn, người xem có thể không hiểu cả hình và tiếng đều do AI tạo.
- **Quyết định:**
  1. `AI_LABEL_TEXT` mặc định **"AI-GENERATED CONTENT"** (đúng chữ banner mẫu) ở app (`core/config.py`, `.env.example`) và fork
     (`ailive_ext/label.py`). Vẫn đổi được bằng biến môi trường; vẫn không có cách tắt nhãn.
  2. Fork thu nhỏ chữ khi nhãn rộng hơn khung trừ lề, để nhãn không bị cắt ở mép. Hộp nhãn ước lượng của app (`scene/layout.py`)
     cũng không vượt khung. Trên khung 480×832 nhãn mặc định nằm ở x 51–468, y 12–70 (cao 58 px như nhãn "AI" cũ), không phải thu nhỏ.
  3. Trang host: nhãn luôn một dòng (`white-space: nowrap`); khi bật cảnh 009 cỡ chữ 2,8vh thay 3,6vh để vừa khung 9:16.
  4. Ghi sáu mục vào `docs/RISKS.md` §1 (P9 cập nhật, P11–P15 mới) và CLAUDE.md (ràng buộc 8).
  5. Mục 6 "không tương tác với người xem" ngược với ADR-026 (tạm không trả lời chat). Demo ngoài Shopee không bị ảnh hưởng. Chưa đổi
     ADR-026; phải xem lại trước giai đoạn Shopee (RISKS P11, `progress/OPEN.md` §4).
  6. Đề xuất sửa hiến pháp (chưa làm, cần `/sdd.constitution`): Điều I ghi "nhãn AI rõ ràng theo quy định nền tảng"; Điều II thêm
     không dùng hình người dưới 18 tuổi, người nổi tiếng, logo hay ảnh của bên thứ ba khi chưa được phép.
- **Lý do:**
  - Chữ trùng banner mẫu của Shopee giảm rủi ro bị coi là gắn nhãn không rõ.
  - Tiếng Anh vì fork vẽ nhãn bằng font Hershey của OpenCV, chỉ vẽ được ASCII (ADR-044).
- **Phương án đã loại:**
  - "AI-generated" (rộng 233 px): gọn hơn, cũng là chữ ví dụ trong quy định, nhưng không giống banner mẫu.
  - Nhãn tiếng Việt như "Nội dung do AI tạo": phải đổi cách vẽ chữ có dấu trong fork (Pillow). Làm sau nếu Shopee Việt Nam yêu cầu.
  - Bỏ nhãn: trái ràng buộc 2 và mục 1 của quy định.
- **Rủi ro:**
  - Nhãn chiếm gần hết chiều ngang phần trên khung; khung cắt sát đầu thì nhãn có thể che tóc. Kiểm khi xem bản ghi tiếp theo.
  - `.env` đang đặt `AI_LABEL_TEXT` thì vẫn dùng giá trị trong `.env`; người dùng tự sửa (không sửa `.env` thay người dùng).
- **TODO:** URL nguồn của ảnh quy định. Shopee Việt Nam có bắt nhãn tiếng Việt không?

## ADR-066: `demo_host_02` là host của khách demo; đánh giá Ultralight khi project xong, đạt thì demo dùng model thầy MuseTalk
- **Ngày:** 2026-11-19 · **Trạng thái:** Chấp nhận. Người dùng trả lời hai câu làm rõ của spec 011: "FR-015 sẽ đánh giá sau khi project
  làm xong hết nếu ok thì cứ lấy MuseTalk làm demo thôi. FR-016: dùng cho 1 khách nên lấy 02 mới nhất". Bổ sung ADR-062, sửa ADR-064
  mục "InfiniteTalk cho prod trước buổi demo".
- **Bối cảnh:**
  - Spec 011 (Ultralight trong show live) còn hai câu: model dev (thầy MuseTalk) có được dùng cho buổi demo không; `demo_host_02` thuộc
    khách nào.
  - ADR-064 định đổi sang thầy prod InfiniteTalk trước buổi demo; video thầy prod 3–5 phút cần GPU thuê (tốn tiền).
  - Ràng buộc 3 của CLAUDE.md và RISKS P15: một host AI cho một tài khoản.
- **Quyết định:**
  1. `demo_host_02` là host của khách demo hiện tại (khách duy nhất). Khi 011 đạt, `demo_host_02` thay `demo_host_01`; trên một tài khoản
     chỉ một trong hai nhân vật lên live.
  2. So sánh Ultralight với Wav2Lip theo ngưỡng ADR-060 mục 5 (US2 của 011) làm sau khi các phần khác của project xong. Đạt thì buổi demo
     dùng model thầy MuseTalk; model thầy InfiniteTalk không bắt buộc cho buổi demo, không thuê GPU cho nó lúc này.
     **Sửa 2026-11-19** (người dùng: "hiện tại tôi chỉ muốn hoàn thành sớm và chất lượng tốt để share bằng cách call meeting share
     màn hình => luôn luôn chạy trên máy này", duyệt bằng "ok run đi"): so sánh làm **ngay khi model Kaggle xong**, không chờ cả
     project xong. Demo luôn chạy trên laptop, miễn phí, share qua Meet.
  3. Đến lúc đánh giá, cấu hình demo vẫn như ADR-062 (Wav2Lip `w2l`, `demo_host_01`) và là phương án dự phòng nếu chưa đạt.
  4. Đường đổi sang thầy prod vẫn làm trong 011 (US3) để dùng sau mà không phải sửa code.
- **Lý do:** model dev đã có (Kaggle, miễn phí); không tốn tiền GPU thuê trước khi khách đồng ý trả; chọn nhân vật mới nhất vì ảnh đã được
  duyệt và có bàn trong cảnh shop.
- **Phương án đã loại:** bắt buộc model prod cho buổi demo (tốn tiền GPU thuê, chưa chắc tốt hơn đủ để đáng); để `demo_host_02` cho khách
  khác (chỉ có một khách).

## ADR-067: Chọn model nhép miệng khi live bằng `LIVETALKING_MODEL` + `LIVETALKING_ULTRALIGHT_TEACHER`; fork kiểm bản ghi cài đặt
- **Ngày:** 2026-11-19 · **Trạng thái:** Chấp nhận (người dùng duyệt 2026-11-19: "ok run đi") (plan 011, research R1–R5, R8)
- **Bối cảnh:** ADR-064 mục 4 để việc "chọn model khi live" cho feature tích hợp. Fork đã có đường `--model ultralight` và công cụ
  `ailive_ext.ultralight install` (avatar `<nhân vật>__ultralight_<thầy>`, bản ghi `ultralight_install.json`), nhưng `app.py` từ chối
  `--ailive_character` với model khác `wav2lip`, app không biết fork đang chạy model nào, và `character.json` đòi clip idle/talk.
- **Quyết định:**
  1. Hai biến môi trường, app và `scripts/livetalking/run.ps1` cùng đọc: `LIVETALKING_MODEL=wav2lip|ultralight` (mặc định `wav2lip`),
     `LIVETALKING_ULTRALIGHT_TEACHER=musetalk|infinitetalk` (mặc định `musetalk`, ADR-066). Nhân vật vẫn chọn bằng `AVATAR_ID`/`AVATAR_DIR`.
  2. Fork nhận `--ailive_teacher`; với `ultralight` + `--ailive_character` tự suy tên avatar, kiểm bản ghi cài đặt (nhân vật, thầy, sha256
     `ultralight.pth`) trước khi nạp HuBERT, sai thì thoát với thông báo tiếng Việt. Không dùng thư viện clip cho Ultralight.
  3. `hello` và `/ailive/health` thêm khối tùy chọn `lipsync` (model, thầy, nhân vật, avatar, sha256); `mouth_method` = `ultralight`.
  4. `character.json` thêm `lipsync_models` (mặc định `["wav2lip"]`); clip idle/talk và `prepare` chỉ bắt buộc khi có `wav2lip`.
  5. Kiểm tra trước demo thêm mục "Model nhép miệng": thiếu cài đặt, sai nhân vật, sai thầy, sai sha256, fork chạy model khác cấu hình → LỖI.
  6. Với `ultralight`, `run.ps1` không truyền các biến chỉ có tác dụng với wav2lip/thư viện clip (`LIVETALKING_MOUTH_METHOD`,
     `LIVETALKING_LIP_EVERY_N`, `LIVETALKING_TRANSITION_S`, `LIVETALKING_HOLD_S`) và báo bỏ qua.
- **Lý do:** một nguồn cấu hình cho app và fork; đổi thầy dev/prod không phải sửa code (FR-006); sha256 là bằng chứng không nhầm model
  (FR-007); mặc định giữ đúng cấu hình demo ADR-062.
- **Phương án đã loại:** một biến gộp `ultralight_musetalk`; ghi model vào `character.json`; truyền thẳng `--avatar_id`; tự đổi model
  giữa show (FR-014; đổi cả mặt host).

## ADR-068: Nhân vật có sẵn bàn trong ảnh: `character.json` `scene.desk_in_image` + `scene.desk_top`, cảnh 009 bỏ lớp bàn
- **Ngày:** 2026-11-19 · **Trạng thái:** Chấp nhận (người dùng duyệt 2026-11-19: "ok run đi") (plan 011, research R9)
- **Bối cảnh:** ảnh `demo_host_02` có bàn (provenance), cảnh 009 luôn vẽ lớp bàn ở `layout.desk_top` của `scene.json` → hai bàn chồng nhau.
- **Quyết định:** `character.json` thêm khối tùy chọn `scene: {desk_in_image, desk_top}`; khi `desk_in_image` là true, cảnh 009 không vẽ
  bàn và đặt thẻ sản phẩm trên `desk_top` của nhân vật (0,55–0,92); kiểm "bàn không chạm mặt" giữ nguyên. Đo khung của fork dùng nhánh
  `frame_list_cycle`/`coord_list_cycle` sẵn có (chạy được với `LightReal`).
- **Lý do:** bàn thuộc ảnh nhân vật, không thuộc cảnh dùng chung; khai một số đo tay rẻ hơn tự dò mép bàn.
- **Phương án đã loại:** tự dò mép bàn bằng xử lý ảnh; sửa `scene.json` dùng chung.

## ADR-069: Lệnh `ai_live.ops lipsync-compare`: gộp bộ đo 010 với hai show 10 phút, kết luận theo ADR-060 mục 5
- **Ngày:** 2026-11-19 · **Trạng thái:** Chấp nhận (người dùng duyệt 2026-11-19: "ok run đi") (plan 011, research R10)
- **Bối cảnh:** US2 của 011 cần một báo cáo so Ultralight với Wav2Lip đủ để quyết cấu hình demo (ADR-066). Số khẩu hình ở bộ đo 010 (venv
  fork), số show (câu đầu, lặng p95, fps, VRAM, lỗi) ở bản ghi phiên của app.
- **Quyết định:** lệnh mới ở app đọc `report.json` của `mouth_eval --methods w2l,ultralight` (khối `sc001`) và bản ghi hai phiên (dùng lại
  phần đọc của báo cáo tổng duyệt 007), viết `out/011_compare/<ngày-giờ>/report.md` + `verdict.json`; mỗi ngưỡng ADR-060 mục 5 (và SC-002:
  lặng p95 không quá +10% so với Wav2Lip) một dòng Đạt / Chưa đạt / Thiếu số, kết luận Đạt chỉ khi mọi dòng Đạt. Không hạ ngưỡng, không
  đoán số thiếu. Gói xem mù 010 chỉ được trỏ tới, không mở khóa.
- **Lý do:** không làm lại bộ đo; không trộn hai venv; báo cáo chạy lại được khi đánh giá (ngay khi có model Kaggle, ADR-066 mục 2 sửa 2026-11-19).
- **Phương án đã loại:** mở rộng `mouth_eval` đọc bản ghi phiên của app; so `demo_host_02` Wav2Lip trong show (không có thư viện clip).

## ADR-070: Giữ trước `LIVETALKING_PREBUFFER_S` (0,6 s) tiếng TTS trước khi gửi câu cho fork
- **Ngày:** 2026-11-20 · **Trạng thái:** Chấp nhận (người dùng duyệt 2026-11-20: "cái 1 đề xuất của bạn ok") (sửa lỗi, WORKFLOW §2)
- **Bối cảnh:** demo2 (2026-11-20) nghe tiếng hơi giật, đều từ đầu show. Log fork cho thấy mỗi câu chuyển "nói → lặng" khoảng 5–6 lần
  giữa câu: hàng đợi tiếng của fork cạn nên fork chèn khoảng lặng. WebRTC 0 mất gói, GPU không nóng; CPU ~85% (Chrome, fork, app). Đo
  VieNeu lúc máy rảnh: 0,63 s tạo 1 s tiếng, nhưng đoạn đầu (0,32 s) tới lúc 0,33 s, nên tiếng chỉ đi trước lúc phát ~0,1 s; CPU bận một
  chút là đoạn sau tới trễ.
- **Quyết định:** `LiveTalkingRenderer.speak` gom tiếng của câu tới khi đủ `LIVETALKING_PREBUFFER_S` giây (mặc định 0,6) hoặc hết câu, rồi mới
  gửi; sau đó gửi từng đoạn ngay như cũ. 0 = tắt. Mỗi câu đều gom (câu giữa đoạn không mất gì vì `LIVETALKING_LEAD_S` đã cho TTS chạy song song
  với câu đang phát).
- **Đánh đổi:** câu đầu mỗi đoạn trễ thêm ~0,2 s lúc máy rảnh (đoạn thứ hai 0,64 s tới lúc ~0,53 s), có thể hơn khi CPU bận. Câu đầu show
  demo2 đo 4,6 s, gần ngân sách 5 s (Hiến pháp VI). Với câu ~4 s, 0,6 s đỡ được TTS chậm tới ~1,15 lần thời gian thực; chậm hơn thì vẫn giật.
- **Phương án đã loại:** gom cả câu (câu đầu trễ cả câu); sửa fork để chờ đủ tiếng (đụng vendor, khó thử).
- **TODO:** đo lại ở show demo2 tiếp theo: số lần "nói → lặng" giữa câu và câu đầu show; còn giật thì thử 1,0 và giảm tải CPU (đóng tab Chrome
  thừa, tắt FxSound).

## ADR-071: Ảnh tải từ trang điều khiển nằm ở `SCENE_DIR/uploads/`, xác nhận quyền dùng thay hồ sơ nguồn 009
- **Ngày:** 2026-11-20 · **Trạng thái:** Chấp nhận (người dùng duyệt 2026-11-20)
- **Bối cảnh:** 012 cho người vận hành tải và thay ảnh sản phẩm giữa live trên trang điều khiển. Hợp đồng bộ cảnh 009 đòi mỗi ảnh có mục
  `provenance.json` và ảnh gốc trong `originals/`, làm bằng tay trước demo. Làm rõ 012 (2026-11-20): bỏ hồ sơ nguồn chi tiết cho ảnh tải
  lên, chỉ cần người vận hành tích ô xác nhận; nhận cả ảnh còn nền.
- **Quyết định:** mỗi lần tải lưu một phiên bản PNG RGBA đã chuẩn hóa (cạnh dài ≤ 1280 px) ở `uploads/<product_id>/<version_id>.png`;
  `uploads/images.json` (ghi qua file tạm + `os.replace`) chọn ảnh đang dùng (`vid` | `null` = đã gỡ | `"kit"` = ảnh 009) và giữ lịch sử.
  Bộ nạp cảnh ưu tiên sổ này hơn `products/`. Với ảnh tải lên, `rights_confirmed_at` thay cho `provenance.json` + ảnh gốc; thiếu là lỗi
  `missing_confirmation` (ảnh không vẽ, kiểm trước demo báo LỖI); sổ hỏng là `bad_uploads`. Ảnh không nền được nhận, chuyển sang RGBA đặc,
  trang báo "ảnh còn nền". Không xóa phiên bản tự động. Không thêm thư viện (Pillow đã có). Chi tiết: `specs/012-product-image-upload/`
  research R1, R2, R6, R9, contracts/scene-set.md.
- **Đánh đổi:** bằng chứng nguồn gốc mỏng hơn 009 (RISKS Q37); `uploads/` lớn dần tới khi dọn tay.
- **Phương án đã loại:** ghi thẳng đè `products/<id>.png` (mất ảnh cũ, không hoàn tác được, phải sửa `provenance.json` bằng code); bắt
  điền hồ sơ nguồn trên trang (chậm giữa live, người dùng đã bỏ ở làm rõ); chỉ nhận PNG trong suốt (khách thường gửi JPEG).

## ADR-072: "Áp dụng bộ mới" đổi catalog và ảnh trong một lần, bộ chuẩn bị chỉ ở bộ nhớ
- **Ngày:** 2026-11-20 · **Trạng thái:** Chấp nhận (người dùng duyệt 2026-11-20)
- **Bối cảnh:** US2 của 012: chuẩn bị file nội dung mới và gán ảnh cho món mới mà live không đổi, rồi áp một lần. `store.install` phát
  `CONTENT_REPLACED` bất đồng bộ, nên một lần vẽ lại (vì phụ đề) có thể vẽ thẻ mới với ảnh cũ.
- **Quyết định:** `StagedSet` (catalog đã đọc bằng `store.parse` + ảnh gán) chỉ ở bộ nhớ, một bộ mỗi lúc. Áp dụng: `SceneController`
  giữ khóa vẽ (`scene.hold()`), ghi `images.json` một lần, `store.install`, `director.on_catalog_replaced`, nhả khóa rồi nạp lại cảnh. Lỗi
  ở bước nào thì live giữ bộ cũ và sổ ảnh được trả lại. Còn món thiếu ảnh thì hỏi lại (409 `missing_images`). Chi tiết: research R7,
  contracts/api.md §2.
- **Đánh đổi:** tắt app thì mất bộ chuẩn bị (ảnh đã tải vẫn còn trong `uploads/`); khung hình đứng thêm tối đa một lần vẽ trong lúc giữ khóa.
- **Phương án đã loại:** lưu bộ chuẩn bị xuống đĩa (thêm trạng thái phải dọn, ít lợi cho demo); áp catalog trước rồi ảnh sau (có khung ghép
  thẻ mới với ảnh cũ, trái SC-006).

## ADR-073: Thêm Gemini 3.5 Flash-Lite (gọi thẳng Google) làm mục thứ ba, cuối chuỗi LLM mặc định
- **Ngày:** 2026-11-20 · **Trạng thái:** Đã chốt 2026-11-20 (người dùng: "ok tiep tuc" sau đề xuất thứ tự SEA-LION → Qwen → Gemini).
  Bổ sung ADR-040; không đổi hai mục đầu.
- **Bối cảnh:** Chuỗi ADR-040 chỉ có hai mục; khi SEA-LION (hạn mức ngày freellmapi) và Groq cùng lỗi thì host im lặng. Mục 4 "Gemini
  qua freellmapi" ở contracts/config.md §2 của 008 còn `TODO` (tên model, nền tảng, giờ chờ). Chấm thử 2026-11-20 (pin `--entry gemini`,
  `LLM_CHAIN` qua biến môi trường, gói free):
  - `gemini-3.8-flash` qua endpoint OpenAI của Google treo hơn 30 s (Google báo HTTP 503 "high demand" cùng ngày): không dùng được.
  - `models/gemini-3.5-flash-lite`, `reasoning_effort: low`: bộ demo 10/10 (`data/eval/runs/20261120-190545`); bộ bẫy SC-002 10/10 câu
    được chấm, 0 câu bịa, 2 câu quá 2,0 s thành lỗi dịch vụ (`runs/20261120-190820`). Câu đầu với prompt thật: trung vị 1,13 s,
    1/10 lần 10 s.
- **Quyết định:** `DEFAULT_LLM_CHAIN` và `.env.example` thêm mục cuối `{"label":"gemini","base_url":
  "https://generativelanguage.googleapis.com/v1beta/openai","model":"models/gemini-3.5-flash-lite","key_env":"GEMINI_API_KEY",
  "first_sentence_timeout_s":2.0,"params":{"reasoning_effort":"low"}}`. Gọi thẳng Google (không qua freellmapi) nên không khai
  `platform`. Model ghi kèm tiền tố `models/` vì lần kiểm `GET /models` lúc khởi động so đúng chuỗi id Google trả về. Tổng giờ chờ câu
  đầu 2,5 + 2,0 + 2,0 = 6,5 s ≤ 8 s (`LLM_TIMEOUT_S`).
- **Đánh đổi:**
  - Chỉ khi hai mục đầu cùng lỗi mới tới Gemini; câu đầu khi đó khoảng 4,5 + 1,1 s, quá mốc 5 s của Điều VI nhưng hơn im lặng.
  - Gemini thỉnh thoảng chậm đột ngột (khoảng 1/10 lần); khi đó lượt vẫn hết chuỗi như trước ADR này.
  - `GEMINI_API_KEY` thành bắt buộc khi dùng chuỗi mặc định (thiếu key thì app không khởi động, contracts/config.md §3).
  - Gói free gửi dữ liệu sản phẩm cho Google (đã chấp nhận ở ADR-018/024 cho Gemini). TODO: hạn mức RPD free của flash-lite chưa kiểm.
  - Lượt kịch bản thử lại (`SCRIPT_RETRY_TIMEOUT_S` 4 s) hết giờ trước khi tới mục 3, như với mục 2 trước đây.
- **Phương án đã loại:** xếp Gemini đầu chuỗi (chậm đột ngột làm mất 2 s mỗi lần trước khi chuyển; mới chấm một lần); `gemini-3.8-flash`
  (treo); Gemini qua freellmapi (thêm một tầng và hạn mức chung, không cần vì gọi thẳng được).

## ADR-074: Bày sản phẩm "như thật" trên bàn và bỏ nền ảnh tải lên bằng IS-Net ONNX chạy trên máy
- **Ngày:** 2026-11-22 · **Trạng thái:** Chấp nhận (2026-11-22, người dùng duyệt plan 013; khai phụ thuộc ở 013 T001, người dùng tải model ở T002)
- **Bối cảnh:** Cách bày hàng của 009 xếp sản phẩm ở mép dưới khung kèm thẻ tên/giá, món chính đứng giữa che tay host, ảnh có nền trông như
  dán lên. Người dùng muốn sản phẩm đứng trên bàn như ảnh mẫu Shopee (spec 013). Làm rõ 2026-11-22: ảnh nền phức tạp dùng model tách nền
  chạy trên máy (FR-013), mặc định không thẻ (FR-019), bỏ nhắc ghim vì không có người trực. Bản dựng thử 2026-11-22 với ảnh thùng Coca nền
  trắng cho thấy loang màu từ viền đủ sạch cho nền trơn.
- **Quyết định:**
  - `scene.json` thêm `layout.mode` (`rows` mặc định | `realistic`), `layout.cards` (`none|one|all`, mặc định `none` ở `realistic`),
    `layout.brightness` (0,85–1,10). `realistic` đặt tối đa 5 món ở 5 chỗ đứng cố định hai bên tay host (plan 013 research R1), có bóng
    hai lớp. `character.json` thêm `scene.hands_zone`; thiếu thì dùng vùng mặc định kèm cảnh báo.
  - Bỏ nền khi tải ảnh lên (012): nền trơn bằng loang màu từ viền (Pillow + numpy); nền phức tạp bằng `isnet-general-use.onnx` (IS-Net/DIS,
    bản ONNX trong release rembg, md5 `fc16ebd8b0c10d971d3513d564d01e29`) chạy trên `onnxruntime` trong **tiến trình con** ưu tiên thấp,
    2 luồng, một ảnh một lúc, hết giờ 60 s. Tự viết tiền/hậu xử lý; không cài `rembg`.
  - Khai trực tiếp `onnxruntime>=1.31.1` và `numpy` trong `pyproject.toml` (cả hai đã có trong `uv.lock` qua `vieneu`, ADR-024). Model lưu
    ngoài git ở `models/matting/`, chọn bằng `MATTING_MODEL_PATH` (rỗng = chỉ bỏ nền phẳng). `MATTING_DURING_SHOW` (mặc định `true`) tắt
    model khi show đang chạy nếu đo thấy tiếng giật.
  - Bản bỏ nền là một phiên bản ảnh mới trong `uploads/images.json` (`derived_from`, `bg_removal`, `cutout_version`), nên mọi thao tác 012
    không đổi. Hệ thống kiểm độ chắc của mặt nạ và không bao giờ chọn sẵn bản lỗi; ảnh tải lên luôn được giữ.
- **Đánh đổi:**
  - File model khoảng 170 MB phải tải tay mỗi máy chạy live (TODO: ghi kích thước, sha256 khi tải).
  - Model tranh CPU với VieNeu khi tải ảnh nền phức tạp giữa show (RISKS Q40); nạp model lại mỗi lần (1–3 s) để không giữ RAM cả buổi.
  - Giấy phép trọng số IS-Net general-use chưa rõ phần dữ liệu huấn luyện (RISKS L15): chưa thu tiền khi chưa đọc điều khoản DIS5K.
    Cập nhật 2026-11-22 (013 T056): điều khoản DIS5K chỉ cho dùng phi thương mại và cấm dùng thương mại khi chưa xin phép tác giả;
    BiRefNet_lite cũng học trên DIS5K. Chưa rõ trọng số có bị tính là dữ liệu đã xử lý không: hỏi tác giả trước khi dùng model cho ảnh
    của khách (RISKS L15). Đường bỏ nền phẳng không dùng model nên không vướng.
  - Tải ảnh lên chờ bỏ nền xong mới trả lời (tới 20 s với nền phức tạp).
- **Phương án đã loại:** `rembg` (kéo OpenCV, scikit-image, scipy, pymatting, tự tải model vào thư mục nhà); BRIA RMBG-1.4/2.0 (giấy phép
  không thương mại); dịch vụ tách nền trả phí (ảnh rời máy, tốn tiền); BiRefNet_lite làm mặc định (nặng hơn; giữ làm dự phòng nếu IS-Net
  dưới 7/10 ảnh nền phức tạp, khi đó ghi ADR mới); chạy model trong luồng phụ cùng tiến trình (không hạ ưu tiên được, crash kéo sập app);
  dò tay bằng model tư thế (thêm phụ thuộc; khai `hands_zone` một lần là đủ).

## ADR-075: Công tắc `LIVETALKING_WATERMARK` cho chữ "LiveTalking"; demo tắt
- **Ngày:** 2026-11-23 · **Trạng thái:** Đã chốt (người dùng cho phép bỏ watermark "LiveTalking" ngày 2026-11-23). Sửa phần watermark của
  ADR-044
- **Bối cảnh:** chữ xám nhỏ "LiveTalking" ở góc trái trên mọi khung trông thừa vì khung đã có nhãn "AI-GENERATED CONTENT" (ADR-065). File
  LICENSE của LiveTalking là Apache-2.0, không có điều khoản bắt giữ watermark. README chỉ yêu cầu watermark và logo cho video đăng trên
  Bilibili, WeChat Channels, Douyin (RISKS L1).
- **Quyết định:**
  - Fork thêm `ailive_ext/watermark.py`: `LIVETALKING_WATERMARK=on|off` (mặc định `on`, giá trị khác thì fork không khởi động). `off` bỏ chữ
    trên khung live (`process_frames`) và bỏ chữ in sẵn khi `genavatar` của Wav2Lip, MuseTalk tạo ảnh chuẩn bị.
  - `scripts/livetalking/run.ps1` chuyển biến này cho fork. App không đọc (biến chỉ của fork, như `LIVETALKING_BATCH_SIZE`).
  - `.env` của máy demo đặt `off`. `.env.example` giữ `on` để bản chạy mới giống code gốc.
  - Nhãn AI vẫn không có công tắc tắt (ràng buộc 2, ADR-044). Vùng cấm `WATERMARK_BOX` của cảnh giữ nguyên để bật lại không phải sửa cảnh.
- **Hệ quả:**
  - Avatar Ultralight `demo_host_02__ultralight_musetalk` không có chữ in sẵn, nên tắt là hết chữ. Các avatar Wav2Lip đã chuẩn bị
    (`demo_host_01__*`, `demo_host_02__w2l_musetalk`) có chữ in sẵn trong `full_imgs`: còn hiện chữ khi dùng Wav2Lip dự phòng cho tới khi
    chạy lại `prepare` với `LIVETALKING_WATERMARK=off`.
  - Trước khi phát trên YouTube hay Shopee vẫn phải trả lời TODO của RISKS L1.
- **Phương án đã loại:** xóa hẳn dòng `putText` (khó bật lại, lệch code gốc nhiều hơn); che chữ bằng lớp cảnh (vẫn vẽ rồi che, tốn công vô
  ích).

## ADR-076: Nhãn AI là chữ trắng viền tối không nền, đặt giữa trên
- **Ngày:** 2026-11-23 · **Trạng thái:** Đã chốt (người dùng yêu cầu "chỉnh lại chính giữa và bỏ nền đen đi hoặc đổi form chữ có màu
  sao cho đẹp" ngày 2026-11-23; chọn kiểu A trong 4 kiểu thử). Sửa phần kiểu nhãn của ADR-044. Vị trí mặc định sửa bởi ADR-085 (`shopee-top`); font ở `shopee-top` sửa bởi ADR-089 (Bahnschrift Bold Condensed)
- **Bối cảnh:** nhãn "AI-GENERATED CONTENT" (ADR-065) vẽ bằng font Hershey trên ô đen đặc, gần kín bề ngang khung 480 px và lệch phải,
  che phông nền và trông thô. Live bán hàng thật dùng chữ trắng đậm viền đen.
- **Quyết định:**
  - Fork (`ailive_ext/label.py`) vẽ chữ trắng đậm, viền tối (0,08 × cỡ chữ) và bóng mờ, không có ô nền. Font TrueType hệ thống tìm theo
    tên file: `seguibl.ttf` (Segoe UI Black) → `segoeuib.ttf` → `arialbd.ttf` → `DejaVuSans-Bold.ttf`; không có font nào thì vẽ bằng
    Hershey cùng kiểu viền. Pillow đã có trong venv của fork (không thêm thư viện). Nhãn dựng một lần cho mỗi cỡ khung thành ảnh RGBA rồi
    trộn vào từng khung.
  - Cỡ chữ 0,031 × chiều cao khung (26 px ở khung 832), vẫn tự thu nhỏ khi chữ dài hơn khung (ADR-065).
  - `AI_LABEL_POSITION` thêm `top-center`, `bottom-center`; mặc định đổi từ `top-right` sang `top-center` ở fork, app, `.env.example`.
    Danh sách vị trí của app nằm ở `AI_LABEL_POSITIONS` trong `core/config.py`.
  - Nhãn CSS của trang host (ảnh tĩnh, lúc chờ khung lip-sync) cùng kiểu: chữ trắng `-webkit-text-stroke` tối và `text-shadow`, không nền.
  - Bộ tự kiểm luồng (`analyze.label_ok`) so độ sáng phần chữ với phần viền theo mặt nạ của nhãn, thay cho đếm điểm đen của ô nền.
  - Vẫn không có công tắc tắt nhãn (ràng buộc 2).
- **Hệ quả:** chữ đọc được trên nền trắng và đen nhờ viền (có test). Máy không có font nào trong danh sách sẽ thấy chữ Hershey có viền,
  kém đẹp hơn nhưng vẫn rõ. Ô vùng cấm `ai_label` của cảnh theo hộp mới (fork báo trong `hello.scene`; app ước lượng giống vậy).
- **Phương án đã loại:** viên thuốc nền xám trong mờ (kiểu B: vẫn là một khối nền); chữ viền cam Shopee (kiểu C: chói, dễ lẫn với thẻ
  giá); font Bahnschrift (kiểu D: mảnh, kém rõ khi nén video); đóng gói file font vào repo (cần xét giấy phép font, chưa cần).

## ADR-077: Trả lời lời chào bằng câu mẫu, giới hạn comment theo người xem
- **Ngày:** 2026-11-23 · **Trạng thái:** Đã chốt (người dùng yêu cầu "nếu có user gửi comment có mấy key thì trả lời họ ví dụ hello,
  hi,... Và check 1 tài khoản mà spam nhiều và nhanh thì coi nên giải quyết như nào" ngày 2026-11-23). Thêm FR-026, FR-027, FR-028 vào
  spec 001. ADR-026 (tạm hoãn đọc chat thật) vẫn giữ: luồng comment hiện chỉ nhận comment giả qua `POST /api/comments` và CLI
- **Bối cảnh:** lời chào ("hi", "hello shop", "chào shop") không cần dữ liệu sản phẩm, gửi cho LLM chỉ tốn một lượt gọi và vài giây.
  Một tài khoản gửi nhiều và nhanh thì mỗi comment đều được một lượt nói, chiếm host; bộ lọc trùng lặp (`CommentFilter`) bỏ lỡ các tin
  khác nhau vài chữ.
- **Quyết định:**
  - **Lời chào (FR-026):** `comments/greetings.py`. Comment là lời chào khi có một từ khóa trong `data/rules/greetings.json` (đứng riêng
    thành từ), xếp ưu tiên Thấp (không có từ hỏi giá, đặt hàng, câu hỏi) và tối đa `max_words` = 8 từ. So khớp trên chữ thường **giữ
    dấu**, để "cháo" và "hì" không thành "chao", "hi". Lời chào được gắn `meta.kind = "greeting"`; `ShowDirector` nói câu mẫu
    (`GreetingReplier`: một câu chào và một câu mời xem sản phẩm chính, lần lượt xoay vòng) thay vì gọi LLM. Câu mẫu vẫn qua output guard
    và không nhắc giá, khuyến mãi. Mỗi người chỉ được chào một lần trong `COMMENT_GREETING_REPEAT_S` = 600 s; lời chào lặp bị bỏ với lý
    do `greeted`. "Chào shop, giá bao nhiêu?" xếp Cao nên vẫn sang LLM.
  - **Giới hạn theo người (FR-027):** `comments/author_limits.py`, `AuthorLimiter` chạy đầu tiên trong `CommentIntake`, trước bộ lọc,
    nên mọi comment đều được đếm. Quá `COMMENT_AUTHOR_MAX` = 3 comment trong `COMMENT_AUTHOR_WINDOW_S` = 30 s thì tạm bỏ qua người đó
    `COMMENT_AUTHOR_MUTE_S` = 120 s (lý do `spam`, log `author_muted`). Thời gian tạm bỏ qua không tự kéo dài; hết hạn thì đếm lại từ đầu.
  - **Một comment chờ mỗi người (FR-028):** `InMemoryCommentQueue.put` thay comment chờ cũ của cùng người bằng comment mới nếu ưu tiên
    cao hơn, hoặc bằng và mới hơn; ngược lại bỏ comment mới (lý do `superseded`).
  - **Nhận diện người xem:** `Comment.author_key` lấy `meta.author_key` do nguồn comment điền (sau này nguồn Shopee điền mã người dùng),
    không có thì dùng dạng so khớp của tên hiển thị. Nguồn giả điền `match_form(author)`.
  - Trang điều khiển hiện ba lý do bỏ mới: "gửi quá nhanh", "đã chào rồi", "đã có comment khác của cùng người".
- **Hệ quả:** lời chào được đáp ngay, không tốn lượt LLM và không thể bịa. Một người spam tối đa có 3 comment được xét mỗi 30 s và chỉ
  1 comment nằm chờ, nên không chiếm host. Với nguồn giả, hai người cùng tên bị gộp làm một; nguồn thật phải điền `meta.author_key`.
  Các ngưỡng chỉnh được qua `.env`, chưa đo trên chat thật (ADR-026).
- **Phương án đã loại:** nhờ LLM phân loại spam (tốn lượt gọi và thêm độ trễ cho mọi comment, luật đơn giản đã đủ); chặn vĩnh viễn
  cả buổi live (người xem gõ nhanh vì hào hứng cũng bị mất); giới hạn chung cho cả phòng (một người spam làm mất lượt của người khác);
  nút chặn hoặc tạm bỏ qua người xem trên trang điều khiển (chỉ đề xuất, ghi ở `progress/OPEN.md`, chờ người dùng quyết; **đổi bởi
  ADR-078**: người dùng đồng ý, đã làm).

## ADR-078: Người vận hành chặn hoặc tạm bỏ qua một người xem từ trang điều khiển
- **Ngày:** 2026-11-23 · **Trạng thái:** Đã chốt (người dùng đồng ý đề xuất, "ok triển khai cả 2 đi" ngày 2026-11-23). Thêm FR-029 vào
  spec 001. Sửa phương án đã loại cuối của ADR-077.
- **Bối cảnh:** luật tự động của ADR-077 (3 comment/30 s → tạm bỏ qua 2 phút) không bắt được người gửi chậm mà quấy rối, hoặc người
  đã hết thời gian tạm bỏ qua rồi quay lại. Người vận hành cần một thao tác tay, nhanh, không phải sửa file luật.
- **Quyết định:**
  - Nút "Chặn" cạnh từng comment trong "Hàng đợi", "Comment bị loại gần đây" và "Lượt đang nói", với 3 lựa chọn: **5 phút**,
    **30 phút**, **cả phiên** (đến khi tắt app). Ô "Người xem bị chặn" liệt kê cả người bị chặn tay và người bị luật tự động tạm bỏ
    qua, có thời gian còn lại và nút "Bỏ chặn".
  - Chặn tay nằm trong `AuthorLimiter` (`block`, `unblock`, `viewers`), tách khỏi tạm bỏ qua tự động. Intake xét chặn tay trước giới
    hạn tốc độ; comment của người bị chặn bị bỏ với lý do mới `blocked` ("người vận hành đã chặn") và không tính vào giới hạn tốc độ.
  - Lúc chặn, comment đang chờ của người đó trong hàng đợi bị bỏ luôn (lý do `blocked`). Lượt đang nói không bị cắt: muốn cắt thì bấm
    "Bỏ qua" như cũ, để một cú bấm nhầm không làm host im giữa câu.
  - "Bỏ chặn" gỡ cả chặn tay lẫn tạm bỏ qua tự động, và đếm tốc độ lại từ đầu.
  - API: `POST /api/viewers/block {author_key, author?, minutes}` (`minutes` 1–240 hoặc `null` = cả phiên), `POST /api/viewers/unblock
    {author_key}`; `GET /api/state` có `viewers`; sự kiện `viewers_changed {viewers}`. `author_key` được thêm vào payload
    `comment_accepted`, `comment_dropped`, `turn_started` và phần tử hàng đợi để trang biết chặn ai.
  - Chỉ giữ trong bộ nhớ: tắt app là hết chặn. Log `viewer_blocked`, `viewer_unblocked` ghi `author_key`, không ghi nội dung comment.
- **Hệ quả:** người vận hành gạt một người quấy rối trong một cú bấm, không cần dừng show. Với nguồn giả, chặn theo dạng so khớp của
  tên nên người khác trùng tên cũng bị chặn (như ADR-077); nguồn Shopee sau này phải điền mã tài khoản thật.
- **Phương án đã loại:** lưu danh sách chặn ra file để dùng qua các phiên (chưa cần cho demo, và là dữ liệu người xem phải tính chuyện
  bảo mật); chặn kèm cắt lượt đang nói (bấm nhầm thì host im giữa câu); tự chặn theo từ khóa (đã có bộ lọc từ ngữ của 001).

## ADR-079: Cách bày `showcase` (món chính giữa trước host, bục và sticker giá tùy chọn) và cảnh báo ảnh độ phân giải thấp
- **Ngày:** 2026-11-23 · **Trạng thái:** Đã chốt (người dùng đồng ý đề xuất, "ok triển khai cả 2 đi" ngày 2026-11-23). Thêm FR-025–FR-028
  vào spec 013. Không đổi ADR-074 (cách bày `realistic` vẫn giữ). Luật "che ≤ 40%" đổi bởi ADR-081 (không món nào che món nào). Cỡ món chính và sticker đổi bởi ADR-082.
- **Bối cảnh:** so với ảnh một phiên live thật, cách bày `realistic` để sản phẩm nhỏ ở hai bên tay host; trên live thật món chính to,
  đứng giữa ngay trước host, món phụ xếp chồng phía sau, thường có bục và sticker giá. Thùng Coca phóng to thì mờ vì ảnh nguồn nhỏ.
- **Quyết định:**
  - Thêm `layout.mode = "showcase"` (bộ cảnh chọn, như `realistic`). Món chính cao mục tiêu 0,38 H (trần 0,40 H, ngang ≤ 0,8 W), giữa
    khung, đáy gần mép dưới bàn; tối đa 3 món phụ cao 0,30 H / 0,27 H…, đáy lùi về sau, đặt sát hai bên món chính sao cho phần bị che
    ≤ 40%. Luật cỡ FR-004 giữ nguyên. Cụm sản phẩm được che tay và ngực (bỏ vùng tay), nhưng ảnh, bóng, bục, sticker và ánh sáng làm
    nổi không chạm vùng cấm 009 (mặt từ cằm trở lên, nhãn AI, watermark); không vừa thì thu nhỏ dần, vẫn không vừa thì ẩn món (`no_room`).
  - `layout.riser` (mặc định tắt): bục trụ tròn trắng rộng 1,1 × món chính, cao khoảng 0,035 H, vẽ bằng Pillow, món chính đứng trên mặt bục.
  - `layout.sticker` (mặc định tắt): sticker tròn ở góc trên phải món chính (không có chỗ thì góc trên trái), chữ CHỈ là `price_text`
    (giá hoặc khoảng giá từ file dữ liệu). Không đưa chữ khuyến mãi vào sticker: khuyến mãi là câu tự do, không vừa hình tròn, và tự
    rút gọn có thể làm sai nghĩa (ràng buộc 7). Không có giá → `sticker_no_price`; không có chỗ → `sticker_no_room`.
  - Cảnh báo `art_low_resolution` khi chiều cao ảnh nguồn < 1,5 × chiều cao vẽ lúc món nổi (1,5 ≈ 1280/832, tỷ lệ phóng khung lên đầu
    ra OBS). Có ở mọi cách bày, trong kiểm tra cảnh và trong phản hồi tải ảnh của 012 (`warnings: ["low_resolution"]`), không chặn áp dụng.
  - Nâng `ART_MAX_SIDE` (cỡ ảnh sản phẩm bộ cảnh giữ lại) từ 640 lên 960 px: món chính `showcase` nổi rộng khoảng 450 px trên khung
    480×832, nên 640 px chỉ được khoảng 1,4 lần và thùng Coca vẫn bị cảnh báo dù ảnh gốc to. Ảnh đã đạt 960 px thì không cảnh báo
    (tải to hơn cũng vô ích). Tốn thêm khoảng 2 lần bộ nhớ cho mỗi ảnh (tối đa 4 ảnh × 960² × 4 byte ≈ 15 MB).
  - Không thêm thư viện, model hay biến môi trường.
- **Hệ quả:** sản phẩm chiếm chỗ nổi bật như phiên live thật, che tay host (tay vẫn cử động phía sau, ít lộ chỗ lip-sync làm méo tay).
  Món chính to gấp khoảng 1,5 lần `realistic`, nên ảnh nhỏ lộ mờ rõ hơn, vì vậy có cảnh báo độ phân giải thấp. `realistic` và `rows`
  giữ nguyên cho bộ cảnh cũ.
- **Phương án đã loại:** sticker tự ghi "giảm X%" tính từ giá (dễ sai so với khuyến mãi thật trên Shopee); dùng ảnh bục chụp sẵn (thêm
  tài sản phải lo bản quyền, khó khớp ánh sáng); để cụm sản phẩm che miệng khi món chính quá cao (vi phạm vùng cấm 009).

## ADR-080: Thêm API SEA-LION chính chủ (AI Singapore) vào freellmapi để tăng hạn mức
- **Ngày:** 2026-11-23 · **Trạng thái:** Đề xuất (người dùng đồng ý lấy key, "note lại trước và chỉ tôi từng cái để lấy key về";
  chốt sau benchmark). Bổ sung ADR-035/073, không đổi chuỗi hiện tại cho tới khi benchmark đạt.
- **Bối cảnh:** chỗ "không đủ" của chuỗi LLM là hạn mức ngày của SEA-LION trên Cloudflare (hết ngày 2026-11-13 và 2026-11-20,
  khoảng 194 request/ngày, Q14). Mỗi nhà cung cấp chỉ có một key: Cloudflare, Groq, OpenRouter. freellmapi có sẵn nền tảng
  `sealion` trỏ tới API chính chủ `https://api.sea-lion.ai/v1` (OpenAI-compatible), chưa có key.
- **Quyết định (đề xuất):**
  1. Người dùng lấy key ở SEA-LION Playground (`playground.sea-lion.ai`, đăng nhập Google, mục "API Key", nút
     "Create New Trial API Key"), nhập vào trang Keys của freellmapi với nền tảng SEA-LION, rồi chạy `scripts/freellmapi/backup.ps1`.
  2. Claude đọc `GET /v1/models` qua freellmapi để biết model nào thật sự có. Danh mục freellmapi ghi `aisingapore/Gemma-SEA-LION-v4-27B-IT`
     (cùng model mục 1 của chuỗi đang gọi qua Cloudflare), nhưng trang hướng dẫn của SEA-LION chỉ nêu `aisingapore/Qwen-SEA-LION-v4.5-27B-IT`
     và `aisingapore/Llama-SEA-LION-v3.5-70B-R`. Chưa được coi là cùng model khi chưa thấy trong danh sách.
  3. Benchmark reply + `qa_eval script` cho model chọn được, theo ngưỡng ADR-035, chạy ngoài khung hạn mức ngày demo (RUNBOOK §2).
     Đạt thì thêm một mục `platform: sealion` vào `LLM_CHAIN`, đề xuất đứng đầu: SEA-LION chính chủ → SEA-LION qua Cloudflare →
     Qwen trên Groq → Gemini. Kiểm `X-Routed-Via` như các mục khác.
- **Hạn mức (theo docs.sea-lion.ai, đọc 2026-11-23):** 10 request/phút mỗi người dùng; mỗi người chỉ 1 key. Trang không nêu giới
  hạn theo ngày, theo token, giá hay thời hạn của key "Trial". Show 30 phút dùng 60–120 request (2–4 request/phút), dưới mức 10/phút.
  TODO: key "Trial" có hết hạn không, và có giới hạn theo ngày không (đo khi benchmark).
- **Hệ quả:** thêm một hạn mức riêng, không chung với Cloudflare. Dữ liệu sản phẩm trong prompt được gửi thêm tới AI Singapore;
  điều khoản sử dụng (19/11/2024) nói họ "may use the Content to provide, maintain, develop and improve our Services", chính sách
  riêng tư không nói prompt có được dùng để huấn luyện hay không. Prompt chỉ có dữ liệu sản phẩm của khách, không có dữ liệu cá nhân,
  nhưng phải hỏi khách trước khi dùng cho dữ liệu thật (giống Cloudflare). Điều khoản không cấm hay cho phép rõ việc dùng thương mại:
  kiểm lại trước khi khách trả tiền (CLAUDE.md ràng buộc 5).
- **Phương án đã loại:**
  - **IteraCompute** (Qwen3.8 27B, 30 triệu token/tháng): bản miễn phí chỉ dùng model `Auto`, không ghim model hay phiên bản (trái
    ADR-035: phải biết đúng model đang nói); chỉ một request đang chạy mỗi tài khoản; khuyến mãi miễn phí kết thúc 00:00 giờ Thái
    Bình Dương ngày 2026-11-24, sau đó chỉ tài khoản đã nạp tiền mới được dùng free.
  - Các cổng trung gian trong danh mục freellmapi (ElectronHub, Gizmo, BlazeAPI, LLMTR): hạn mức dùng chung, không rõ gửi request tới đâu.
  - Tạo nhiều tài khoản ở cùng nhà cung cấp: trái điều khoản (IteraCompute cấm rõ "multiple-account limit circumvention").


## ADR-081: Cách bày `showcase` không cho sản phẩm che nhau; món chính demo đổi thành lốc 6 chai
- **Ngày:** 2026-11-23 · **Trạng thái:** Đã chốt (người dùng: "đổi 1 thùng thành 1 lóc đi và các sản phẩm không bị che nhau").
  Đổi một phần ADR-079 (luật che ≤ 40%) và FR-025 của spec 013. Món chính demo đổi bởi ADR-096 (thùng quà Tết).
- **Bối cảnh:** trên khung live, thùng Coca to giữa bàn che mất một phần hai chai phía sau, sticker giá cũng đè lên chai. Người dùng
  muốn thấy trọn từng món.
- **Quyết định:**
  - Trong `showcase`, khung ảnh của hai sản phẩm bất kỳ không chồng lên nhau, cách nhau ít nhất 8 px (trên khung cao 832 px). Món phụ
    phải tránh cả cỡ món chính lúc được làm nổi (×`highlight_scale`) và mặt bục, để lúc món chính nói nó không đè lên món phụ. Món phụ
    đang nói chỉ lớn tới mức chưa chạm món khác.
  - Thiếu chỗ hai bên: món chính thu nhỏ dần (bước 0,95, không thấp hơn 0,22 H) cho tới khi mọi món phụ đứng được với ít nhất 85% cỡ
    mục tiêu. Không được thì món chính giữ 0,22 H và món phụ thu nhỏ dần (bước 0,95, tới 30% cỡ mục tiêu, không dưới `MIN_ART_HEIGHT`);
    hết cách mới ẩn món phụ (`no_room`).
  - Món phụ được xếp vào chỗ trống gần món chính nhất; tên trạm `showcase_left|right` theo chỗ món thật sự đứng.
  - Sticker giá không đè lên món phụ (vẫn đè góc trên món chính như ADR-079).
  - Dữ liệu demo `data/products/coca.docx`: món chính "Lốc 6 chai Coca-Cola 355ml" (chai thủy tinh, hộp giấy có quai) thay cho thùng
    24 lon; giá, khuyến mãi vẫn là số demo, không phải dữ liệu thật của hãng. Chọn lốc chai vì Wikimedia Commons không có ảnh lốc 6 lon
    Coca-Cola nền sạch; ảnh dùng: "6 Pack of Mexican Coca Cola" của Willis Lam, CC BY-SA 2.0
    (https://commons.wikimedia.org/wiki/File:6_Pack_of_Mexican_Coca_Cola_(23105300426).jpg), chỉ dùng cho demo, tải qua trang điều
    khiển (012) và bỏ nền như ảnh cũ. Ảnh demo không nằm trong git.
  - Không thêm thư viện, model hay biến môi trường.
- **Hệ quả:** món chính nhỏ hơn ADR-079 khi nó rộng (lốc 6 chai), đổi lại mọi món đều thấy trọn. Cụm sản phẩm trông như bày hàng ngang
  trên bàn hơn là xếp chồng như phiên live tham khảo.
- **Phương án đã loại:** thêm tùy chọn `overlap` trong `scene.json` để chọn che hay không (người dùng chỉ cần một kiểu, thêm khóa là thêm
  chỗ cấu hình sai); đặt món phụ lên cao phía trên món chính (trông như bay, sai luật đáy FR-002).


## ADR-082: Cảnh `showcase` theo cỡ thật, làm mềm ảnh sản phẩm cho hợp camera; thêm skill đo độ thật của cảnh live
- **Ngày:** 2026-11-23 · **Trạng thái:** Đã chốt (người dùng: "hiện ảnh nhìn không được đẹp lắm bạn viết thêm skill để điều chỉnh bố cục
  live sao cho giống real nhất"). Đổi một phần ADR-079 (cỡ món chính) và FR-025 của spec 013; thêm FR-029.
- **Bối cảnh:** skill mới `.claude/skills/live-scene-realism/` đo khung live demo (host `demo_host_02`, 3 món Coca). Kết quả:
  - đường bàn trong `character.json` (0,78 H) cao hơn mép gỗ thấy trên hình (0,874 H), nên hai chai phụ lơ lửng trước người host;
  - lốc 25 cm vẽ cao 316 px trong khi đầu host (khoảng 23 cm) cao 178 px: to gấp 1,63 lần cỡ thật, che gần hết thân host;
  - sản phẩm sáng hơn phòng (p95 230 so với 209) và nét hơn hình host 9–16 lần (đo phương sai Laplace), nên trông như ảnh dán.
- **Quyết định:**
  - `SHOWCASE_MAIN_HEIGHT` 0,38 → 0,28 H; `SHOWCASE_BACK` cao 0,22/0,20/0,18 H (trước 0,30/0,27/0,24), giữ nguyên bên và độ lùi. Món
    trước host trông to hơn cỡ thật 1,0–1,45 lần, món sau 0,85–1,2 lần (gần camera hơn); cỡ mới cho 1,2 / 1,07 / 1,1. FR-025 đổi khoảng
    cao món chính thành 0,26–0,30 H.
  - `STICKER_PX` 96 → 72 (khung 832): sticker 96 px che cổ chai của lốc khi món chính nhỏ lại.
  - FR-029: ở `realistic` và `showcase`, ảnh sản phẩm được làm mờ 0,7 px (nhân trước theo alpha để mép không đen) và làm mềm mép alpha
    0,8 px, theo cỡ khung. Không đổi màu, chữ, hình (FR-006). Cách bày `rows` (009) không đổi.
  - Không cân màu ánh sáng (thử gray-world làm ấm ảnh hợp phòng hơn, nhưng FR-006 cấm đổi sắc độ sản phẩm; skill chỉ dùng nó để chẩn
    đoán). Độ sáng chỉnh bằng `layout.brightness` sẵn có (demo: 0,9).
  - Cấu hình demo cục bộ: `character.json` `scene.desk_top` 0,874, `scene.json` `layout.brightness` 0,9.
    **Sửa cùng ngày:** `desk_top` trả về 0,78. Mép 0,874 đo trên `face.png`, chỉ là ảnh xem trước khi fork không chạy; khung
    live thật của fork (`full_imgs` Ultralight, chụp khác `face.png`) có mép bàn gỗ ở 645/832 px (0,775), đúng giá trị đo ở US1.
    Skill nay bắt đo trên khung fork.
  - Skill chỉ render ảnh thử vào `out/realism/` với hằng số và cấu hình tạm; đổi hằng số hay hiệu ứng thật vẫn đi qua spec, ADR và test.
    Ngưỡng trong báo cáo là ước lượng đo trên khung demo, không phải luật.
  - Không thêm thư viện, model hay biến môi trường.
- **Hệ quả:** thấy rõ thân và tay host sau cụm sản phẩm, chai đứng đúng mặt gỗ, sản phẩm hòa vào hình hơn. Cụm sản phẩm chiếm 13% khung
  thay vì 23%; chữ trên sản phẩm hơi mềm hơn nhưng vẫn đọc được. Màu ánh sáng ảnh sản phẩm vẫn lạnh hơn phòng (cần ảnh chụp dưới đèn ấm).
- **Phương án đã loại:** tính cỡ từ chiều cao thật trong file dữ liệu (file chưa có trường này, phải thêm vào 002/012; để sau nếu nhiều
  khách); thêm `soften` vào `scene.json` (một mức cố định đủ cho demo, thêm khóa là thêm chỗ cấu hình sai).

## ADR-083: Tách người cho nền sau host: mặt nạ chuẩn bị một lần mỗi nhân vật, cách `plate` mặc định, MediaPipe dự phòng
- **Ngày:** 2026-11-24 · **Trạng thái:** Đã chấp nhận 2026-11-24 (người dùng chạy `/sdd.implement 014`). Chưa tải model nào: tải
  MediaPipe `selfie_multiclass_256x256.tflite` vẫn cần người dùng đồng ý riêng ở T033.
- **Bối cảnh:** 014 thay phòng phía sau host bằng nền của shop ở mọi khung của đoạn lặp (host cử động). Bản dựng thử bằng GrabCut từng khung
  lọt mảng kệ cũ quanh vai và dải LED trên đầu khi host nghiêng. Venv fork đã có mediapipe 1.2.3 (ADR-053) nhưng không kèm file `.tflite`
  tách người; cv2 trong venv fork không có `ximgproc`. IS-Net/DIS5K bị loại cho việc này vì giấy phép bộ dữ liệu chưa rõ (RISKS L15).
- **Quyết định:**
  - Mặt nạ người được **chuẩn bị một lần cho mỗi nhân vật** trên laptop (CPU), cho mọi khung fork sẽ phát (`full_imgs` và clip), lưu ở
    `assets/avatars/<id>/background/` (đã nằm trong `.gitignore`) kèm `manifest.json` ghi dấu vân crc32 từng khung. Lúc live chỉ tra mặt nạ,
    không chạy model.
  - Cách mặc định `plate`: ảnh phòng trung vị qua các khung + hiệu so với ảnh đó làm mặt nạ thô, GrabCut khởi tạo từ mặt nạ thô, làm mượt
    theo thời gian (trung vị 3 khung kề), guided filter bằng `cv2.boxFilter` (bán kính ~4) và co 1 px, dốc mặt bàn 6 px. Không tải gì.
  - Cách dự phòng `mediapipe` (`selfie_multiclass_256x256.tflite`, đường dẫn qua biến `BACKGROUND_SEGMENTER_MODEL`): chỉ dùng khi `plate`
    không đạt SC-001/002 của spec 014, và chỉ tải sau khi xác minh giấy phép trên trang chính thức (`TODO:` thẻ model ML Kit ghi Apache 2.0,
    bản đăng lại của Qualcomm ghi "other": giấy phép nào áp cho file tải từ `storage.googleapis.com/mediapipe-models`?) và ghi cỡ, sha256.
  - Người duyệt xem `review.jpg` rồi đánh dấu `reviewed`; chưa duyệt thì kiểm tra sẵn sàng cảnh báo (không chặn).
- **Hệ quả:** demo không phải tải gì nếu `plate` đạt; chuẩn bị mất vài phút mỗi nhân vật (`TODO:` đo thật). Làm lại đoạn lặp thì phải chuẩn
  bị lại (dấu vân không khớp → phòng gốc). Chất lượng viền tóc phụ thuộc phòng gốc có đủ khác màu người hay không.
- **Phương án đã loại:** GrabCut từng khung không có ảnh phòng (lọt như bản thử); tách người lúc live mỗi khung (tốn GPU/CPU trong ngân sách
  40 ms, viền nhấp nháy); IS-Net/BiRefNet của 013 (giấy phép dữ liệu, model tách vật thể chứ không phải người); quay lại host trước phông
  xanh (cần người mẫu quay lại, ngoài tầm demo).

## ADR-084: Ghép nền sau host trong fork, ngay dưới người, kiểu nền chọn trước giờ live
- **Ngày:** 2026-11-24 · **Trạng thái:** Đã chấp nhận 2026-11-24 (người dùng chạy `/sdd.implement 014`).
- **Bối cảnh:** khung live do fork LiveTalking dựng (paste_back miệng → cảnh 009/013 → watermark → nhãn AI). Lớp cảnh 009 bị cấm điểm ảnh
  trong vùng mặt (`Geometry.guarded()`), nên không thể làm nền bằng một lớp cảnh. Clarify 014: demo chỉ cần "kệ hàng"; bỏ kiểu làm mờ.
  Khi duyệt plan (2026-11-24) người dùng bỏ yêu cầu bật/tắt nền khi đang live (FR-017 cũ).
- **Quyết định:**
  - Fork thêm bước `ailive_background.apply` **sau khi dán miệng, trước `ailive_scene.apply`**, áp cho cả khung đứng yên và khung đang nói.
    Ghép bằng `cv2.copyTo` với mặt nạ nền + trộn dải viền (~1,7 nghìn điểm ảnh) bằng uint16; đo thử 0,18 ms/khung; mục tiêu ≤ 4 ms, báo
    `stats.background_ms`.
  - Giao thức: `hello` thêm khối `background` (`status` valid/missing/mismatch, `reason`, cỡ khung, `method`, `reviewed`); app gửi
    `{"type":"scene_background","png_b64":str|null}` (ảnh nền đục, đúng cỡ khung, ≤ 4 MB; `null` = phòng gốc) sau mỗi `hello` và khi
    vẽ lại ảnh nền (áp bộ sản phẩm mới); lỗi `background_rejected` / `background_failed` (lỗi ghép thì fork tự về phòng gốc, khung vẫn
    đẩy ra). Fork cũ không có khối → phòng gốc.
  - App: khối `background` trong `scene.json` (`style` goc/ke_hang/bang_shop/anh_shop, `softness_px` 3,0, `brightness` 0,95,
    `max_items` 12); `src/ai_live/scene/backdrop.py` vẽ kệ hàng bằng Pillow một lần (chỉ ảnh sản phẩm đã bỏ nền đang dùng, không chữ, không
    giá, không logo); Protocol tuỳ chọn `BackgroundSink` chỉ `LiveTalkingRenderer` cài; route `GET /api/scene/background` (chỉ đọc trạng thái),
    `GET /api/scene/background/preview.png`; `check_background` chỉ cảnh báo, không chặn.
  - Không có công tắc bật/tắt khi live: kiểu nền (kể cả `goc`) chọn trong `scene.json` trước giờ live rồi khởi động lại. `bang_shop` /
    `anh_shop` (US3) rơi về phòng gốc với lý do `style_not_available` cho tới khi làm.
- **Hệ quả:** `/host` và `/obs` cùng nền (cùng luồng fork). Chế độ `static` không có nền. Thêm khác biệt với ARCHITECTURE §3 (Protocol tuỳ
  chọn mới, tin fork mới), cập nhật ở `/update-context`.
- **Phương án đã loại:** ghép sẵn nền vào 81 khung gốc lúc nạp (hộp mặt dán đè mang phòng cũ về, đổi ảnh nền phải dựng lại cả bộ khung); ghép ở trình duyệt
  (OBS và Meet nhận khung từ fork, mặt nạ phải gửi theo từng khung); làm nền thành lớp cảnh 009 (vùng mặt bị cấm, lớp cảnh nằm trên người).

## ADR-085: Nhãn AI mặc định dời xuống dải trống dưới tiêu đề app Shopee; bảng vùng che của app
- **Ngày:** 2026-11-25 · **Trạng thái:** Đã chấp nhận 2026-11-25 (người dùng: "ok làm điểm 1 và 5 trước đi" sau khi so cảnh với ảnh chụp
  một live AI thật trên Shopee). Sửa phần vị trí mặc định của ADR-076 (bổ sung bởi ADR-087: bày hàng né vùng che); kiểu chữ trắng viền tối không nền giữ nguyên. Cỡ ~15 px sửa bởi ADR-089 (font hẹp đậm, ~20 px). Vị trí mặc định đổi lại `top-center` bởi ADR-090 (`shopee-top` để dành cho Shopee qua OBS).
- **Bối cảnh:** trên app Shopee (điện thoại dọc, ảnh chụp 900×2000 ngày 2026-11-25), dải tiêu đề live và tên shop phủ khoảng 11,5% trên
  cùng màn hình, đúng chỗ nhãn `top-center` (ADR-076, y 12 px trên khung 832). Nhãn AI bị che là rủi ro tuân thủ (ràng buộc 2, ADR-065).
  Phía dưới, bình luận (y 83–91%) và ô chat (y 93–98,5%) che chân sản phẩm và bục.
- **Quyết định:**
  - Thêm vị trí `shopee-top` cho `AI_LABEL_POSITION` ở fork (`ailive_ext/label.py`), app (`AI_LABEL_POSITIONS`), trang host (CSS) và ước
    lượng hộp nhãn (`scene/layout.py`). Nhãn ở giữa, mép trên tại 12,5% chiều cao khung, rộng tối đa 26% bề ngang khung; chữ dài hơn thì
    tách thành hai dòng ở khoảng trắng gần giữa nhất, rồi mới thu cỡ chữ. "AI-GENERATED CONTENT" thành "AI-GENERATED" / "CONTENT" cỡ
    ~15 px trên khung 480×832 (hộp x 177–302, y 104–150, trên đỉnh đầu host ở ~163; mép phải chip trái ở x 176).
  - Mặc định đổi từ `top-center` sang `shopee-top` ở fork, app và `.env.example`; dùng chung cho Meet và OBS để buổi demo trông như trên
    Shopee. `top-center` và các vị trí cũ vẫn chọn được.
  - Bảng vùng che của app (tỷ lệ màn hình điện thoại 9:20) nằm ở `src/ai_live/scene/shopee_overlay.py`, kèm cách quy về khung video với
    giả định app phủ kín màn hình (cắt hai bên khoảng 11% bề ngang khung). Công cụ đo độ thật (`realism_report.py`) báo phần trăm nhãn AI
    và từng sản phẩm nằm trong vùng che, và tô các vùng lên ảnh `_zones.png`.
- **Lý do:** dải trống giữa tiêu đề app (hết ở ~11,5%) và các nút hai bên (chip "Streamer AI" bên trái tới x 33%, ô quà bên phải từ x 69%)
  là chỗ duy nhất phía trên không bị che và không đè lên mặt host. Một dòng "AI-GENERATED CONTENT" ở đó phải nhỏ dưới 10 px, không đọc được.
- **Hệ quả:** vùng che đo từ một ảnh chụp: TODO kiểm lại bằng live thử trên Shopee hay điện thoại thật (app phủ kín hay co khung có viền
  đen). Nhãn hai dòng nhỏ hơn nhãn một dòng cũ; khi xem trên Meet ở màn hình ngang vẫn đọc được vì khung được phóng theo chiều cao.
- **Phương án đã loại:** giữ `top-center` (bị tiêu đề app che); đặt dưới đáy (bình luận và ô chat che); đặt giữa cạnh phải (bị ô quà và nút
  thả tim che một phần, đè lên vai host); bỏ nhãn trong khung vì Shopee đã gắn chip "Streamer AI" (ràng buộc 2 yêu cầu nhãn nằm trong khung
  của mình, không phụ thuộc app).

## ADR-086: Nền "kệ hàng" vẽ thành dãy kệ có chiều sâu, khớp sáng bằng đường cong tông; độ mềm mặc định 1,5
- **Ngày:** 2026-11-25 · **Trạng thái:** Đã chấp nhận 2026-11-25 (người dùng: "ok làm điểm 1 và 5 trước đi" sau khi so cảnh với một live AI
  thật trên Shopee). Sửa cách vẽ của research R10 và cách khớp sáng, độ mềm mặc định của R11 (spec 014).
- **Bối cảnh:** kệ cũ là hai khoang tủ phẳng, mỗi tầng vài món (mặc định 12 món cho cả kệ), nhiều mảng tường trống. Trong phòng sáng của
  `demo_host_02` (độ sáng phòng cũ 183), phép nhân sáng tuyến tính đẩy cả ảnh lên gần trắng: trung vị 189 ≈ p95 193, độ bão hoà 0,17
  (bạc màu). Live đối thủ có kệ kín hàng, có chiều sâu, màu rõ (FR-018).
- **Quyết định:**
  - Vẽ dãy kệ nhìn từ giữa lối đi, phối cảnh một điểm tụ ở (giữa khung, 32% chiều cao, ngang mắt host): hai kệ bên chạy từ mép khung vào
    trong, gặp một kệ sau nhỏ hơn (hệ số 0,55) và tối hơn (0,72 độ sáng phía trước); 6 tầng, tầng dưới cùng nằm trên mép bàn, kệ bên vượt
    quá mép trên khung; trần có dải đèn, ván trắng, dải LED ấm trên mép mỗi ván, cột đứng ở góc và giữa kệ bên.
  - Mỗi tầng xếp kín từ mép này sang mép kia bằng các "đơn vị" của ảnh sản phẩm đang dùng, lặp vòng theo thứ tự `items`; cao 62% tầng, thu
    theo chiều sâu; hàng trên kệ bên hẹp lại 0,78 (nhìn xiên). Kệ sau vẽ trước, đơn vị cuối của kệ bên được vượt qua góc để không hở dải
    trống. Vẫn chỉ ảnh của shop, không chữ, giá, logo (FR-007). `max_items` giờ là độ dài vòng sản phẩm lặp lại, không còn là số món vẽ.
  - Khớp sáng: thay phép nhân tuyến tính bằng đường cong gamma, tìm bằng chia đôi sao cho độ sáng trung bình trên mép bàn bằng phòng cũ ×
    `brightness`; đen và trắng giữ nguyên nên không cháy, giữ thứ tự tông và độ tương phản hàng/kệ. Dời cân bằng trắng giữ như R11 (±12).
  - `softness_px` mặc định 3,0 → **1,5**: đo bằng `realism_report --background-frames` trên khung ghép với `demo_host_02`, tỷ lệ nét nền/người
    là 6,38 (0), 0,36 (1), **0,10 (1,5)**, 0,04 (2), 0,01 (3); nền gốc của camera là 0,09. 1,5 khớp độ sâu trường ảnh của camera và nhìn rõ
    hàng hơn; 3,0 mờ hơn cả nền thật.
- **Kết quả đo (plate `demo_host_02`, 3 món Coca):** độ sáng 174 (đích 174), p5 116, p50 173, p95 218, cháy trắng 0%; vẽ một lần lúc
  khởi động ~0,5 s trên laptop.
- **Hệ quả:** kệ trông dày đặc và lặp lại (giống live đối thủ); với shop ít món thì cùng một món lặp nhiều lần. Plate vẫn tất định (cùng bộ
  → cùng byte). Ảnh xem trước của fork (`preview_frame`) vẫn còn nhãn AI cũ in sẵn, không ảnh hưởng khung live.
- **Phương án đã loại:** thêm tầng cho hai khoang tủ cũ (vẫn phẳng, không có chiều sâu); ảnh kệ có sẵn hay sinh bằng AI (không có quyền,
  có hàng của hãng khác, R10); giữ nhân tuyến tính nhưng giảm `brightness` (tối cả cảnh mà vẫn dồn tông về một chỗ).

## ADR-087: Cụm sản phẩm `showcase` co chiều sâu để đứng trên vùng bình luận của app Shopee (khóa `avoid_app_overlay`)
- **Ngày:** 2026-11-25 · **Trạng thái:** Đã chấp nhận 2026-11-25 (người dùng: "ok sửa đi" sau báo cáo đo độ thật: lốc 6 chai chính bị
  vùng bình luận che 30%, chai coca-zero 15%). Bổ sung ADR-085 (trước đó cảnh không tự dời gì vì vùng che) và FR-019 của spec 014.
- **Bối cảnh:** trên khung 480×832, vùng bình luận của app (bảng ở `scene/shopee_overlay.py`) phủ x 0–326, y ~691–757 và ô chat từ y ~774.
  Cách bày `showcase` đặt chân món chính ở mép bàn + 0,8 × dải bàn (bục chạm bàn ở 795, món đứng ở 766), các món sau ở 0,35 (713): phần đáy
  của món chính và món sau bên trái nằm dưới bình luận khi xem trên điện thoại.
- **Quyết định:**
  - Khóa mới `layout.avoid_app_overlay` (bool, mặc định `false` như `riser`/`sticker`; chỉ `showcase` đọc). Bật thì tìm "sàn" là mép trên
    cao nhất của các vùng che bắt đầu dưới mép bàn, trừ khoảng cách `SHOWCASE_GAP_PX`, rồi co dải bàn dùng để tính chiều sâu sao cho món chính
    (đứng trên bục nếu có) chạm sàn. Mọi món dùng cùng dải đã co nên thứ tự trước/sau giữ nguyên; dải không co dưới 30% dải bàn thật để món
    vẫn đứng trên mặt bàn. Chỉ ảnh sản phẩm phải ra khỏi vùng che; bục và bóng được nằm dưới.
  - Bộ cảnh demo bật khóa này. Công cụ đo độ thật tiếp tục báo phần trăm bị che để kiểm.
- **Lý do:** dời riêng từng món bị che làm món chính đứng sau các món nhỏ bên phải (sai phối cảnh); dời cả cụm cùng một khoảng thì các món sau
  rơi lên trên mép bàn. Co chiều sâu theo một tỷ lệ giữ cụm liền và đúng thứ tự.
- **Hệ quả:** cụm đứng sát mép bàn hơn (gần host hơn), che ngực/tay host nhiều hơn một chút; xem trên Meet (màn hình ngang, không có vùng
  che) cũng thấy cụm lùi vào. Bảng vùng che vẫn từ một ảnh chụp (TODO của ADR-085). Cỡ món không đổi theo chiều sâu mới.
- **Phương án đã loại:** thu nhỏ món để vừa phía trên vùng che (sản phẩm nhỏ, khó thấy); dời từng món bị che (sai thứ tự trước/sau); bỏ bục
  (vẫn bị che, chỉ đỡ 29 px); để nguyên và chấp nhận (người dùng xem live trên điện thoại, đáy sản phẩm và giá dán bị che).

## ADR-088: Host tư vấn theo ngân sách, thành phần và thể trạng; khi không ai hỏi thì lặp một đoạn cố định có câu mời hỏi (`SHOW_CONTENT=loop`)
- **Ngày:** 2026-11-25 · **Trạng thái:** Đã chấp nhận 2026-11-25 (người dùng: "bên reply cần trả lời về giá tiền user hiện có và cần tư vấn,
  thành phần trong sản phẩm để phù hợp với thể trạng từng người... Bỏ cái tự hỏi tự trả lời trong bộ content đi. Nếu không ai hỏi thì AI chỉ
  nói lập đi lập lại 1 đoạn content và luôn có các câu để được tư vấn"). Sửa FR-012, thêm FR-030 đến FR-032 của spec 001; sửa FR-014, thêm
  FR-031 của spec 004; §2 contract api của 007.
- **Bối cảnh:** câu trả lời chỉ đọc giá và mô tả, không biết tư vấn theo số tiền người xem có; bộ chặn chặn mọi số tiền không có trong file
  nên câu "2 lốc là 210.000đ" hay "100k thì anh chị mua được..." đều bị chặn. Kịch bản LLM có chủ đề FAQ: host tự đặt câu hỏi rồi tự trả
  lời, nghe như dàn dựng. File demo chưa có thành phần nên không tư vấn được theo thể trạng.
- **Quyết định:**
  - **Nguồn nội dung `loop`, mặc định** (`SHOW_CONTENT=loop`, `POST /api/show/start` không gửi `content` thì lấy giá trị này): mở show nói
    lời chào, tên các món và câu mời hỏi một lần; sau đó mỗi phân đoạn (xoay chính, phụ như cũ) đọc giới thiệu, mô tả, câu giá, câu khuyến
    mãi lấy từ file rồi một câu mời hỏi tư vấn. Câu mời đổi lần lượt: ngân sách; thành phần và thể trạng (chỉ khi file có mục "Thành phần");
    so sánh chọn loại (chỉ khi có hơn một món); giá, khuyến mãi, bảo quản. Không gọi engine, mỗi câu vẫn qua bộ chặn, tiếng và hình vẫn sinh
    realtime. Comment vẫn được trả lời bằng chuỗi LLM. Thống kê phiên đếm `loop_spoken`; nguồn `script` và `verbatim` vẫn chọn được.
  - **Bỏ FAQ khỏi vòng xoay** (`ROTATION_TOPICS`): host không tự hỏi rồi tự trả lời; cặp hỏi–đáp trong file vẫn dùng khi trả lời comment.
    Prompt kịch bản cấm kiểu tự hỏi tự đáp và cho mời người xem bình luận hỏi.
  - **Prompt trả lời** thêm các mục: tư vấn theo ngân sách (gợi ý món vừa túi tiền kèm giá, tổng = số lượng × giá, không tính tiền thừa,
    ship, không cộng dồn khuyến mãi; không vừa thì nói giá thấp nhất), thành phần và thể trạng (đọc đúng "Thành phần", "Lưu ý", không kết
    luận an toàn, khuyên hỏi bác sĩ), so sánh và chọn giúp, câu hỏi hay gặp trên live (ship, đổi trả, hàng thật, thanh toán không có trong
    file thì nói chưa có thông tin). Tư vấn được nói tối đa 4 câu.
  - **Bộ chặn** cho qua thêm: tổng tính được từ giá trong file (giá × 1..20; trừ số tiền giảm ghi trong khuyến mãi của món đó; i × giá a +
    j × giá b với i, j ≤ 3); số tiền chính người xem viết trong comment (kể cả "100k", "50 nghìn", số trần 1–999 hiểu là nghìn), nhưng chỉ
    khi cùng câu có một giá lấy từ file. Tổng suy ra chỉ được cho qua khi câu ghi đúng số lượng (số hoặc chữ "hai",
    "mười"...; mua ghép hai món thì ghi cả hai số lượng), để "giảm còn 2 triệu" không lọt vì trùng 20 × giá. Số khác vẫn bị chặn. Danh sách khẳng định cấm thêm nhóm "an toàn cho bà bầu", "uống thoải mái"...
  - **File demo `coca.docx`** thêm mục "Thành phần" và "Lưu ý" cho ba món (đường, caffeine; Zero có chất tạo ngọt, phenylalanin).
- **Lý do:** đoạn lặp dựng từ file không thể bịa và không tốn lượt gọi LLM khi không có ai xem; câu mời cho người xem biết hỏi gì. Tổng tiền
  tính từ giá trong file là sự thật suy ra được, còn số của người xem chỉ được nhắc lại cạnh giá thật nên host không thể tự nói một số lạ.
- **Hệ quả:** không ai comment thì host nói lặp lại, nghe đơn điệu hơn kịch bản LLM (người dùng chủ động chọn vậy). "Bỏ qua tới chủ đề FAQ"
  trên trang điều khiển không còn. Một câu ghép tổng tiền phức tạp hơn (3 món, khuyến mãi phần trăm) vẫn bị chặn và câu đó bị bỏ.
  TODO: thành phần và lưu ý trong `coca.docx` là văn bản demo, cần đối chiếu nhãn thật trên sản phẩm của khách trước buổi demo.
- **Phương án đã loại:** để LLM tự tính tổng và tắt kiểm số tiền (có thể bịa giá); kịch bản LLM có câu mời (vẫn tốn lượt gọi và có thể lạc
  đề); cho host nói "phù hợp với người tiểu đường" khi thấy "không đường" (là khẳng định sức khỏe, vi phạm luật số 7 và quy định Shopee).
- **Bổ sung 2026-11-28** (người dùng: "Bỏ khuyến mãi, giữ giá", khi soạn lại nội dung cho video quay thử 5 phút trên OBS): `coca.docx` bỏ hai mục "Khuyến mãi", viết lại giới thiệu và mô tả bốn món (giá giữ nguyên, vẫn là số demo). Câu mời chung của đoạn lặp chỉ nhắc "khuyến mãi" khi file có ít nhất một khuyến mãi; không có thì mời hỏi "giá, quy cách hay cách bảo quản" (`loop_script._GENERAL_INVITE_NO_PROMO`), vì mời hỏi khuyến mãi khi file không có chỉ dẫn tới câu "chưa có thông tin". Sửa FR-031 spec 004.
- **Bổ sung 2026-11-28 (2)** (người dùng: "viết lại cho khác kịch bản không bị lặp nhiều"; video lần 4 đọc câu giá món chính 4 lần y hệt trong 5 phút, vì món chính chiếm mỗi lượt xen kẽ và khối của mỗi món cố định): mục "Bài giới thiệu" và "Mô tả" viết được nhiều đoạn, mỗi đoạn một dòng. Mỗi lượt của một món chỉ đọc một đoạn giới thiệu và một đoạn mô tả, lần lượt rồi quay vòng, mỗi món đếm lượt riêng (`ScriptRunner._loop_turns`). Câu giá đổi lần lượt giữa 3 mẫu câu cố định (`loop_script.PRICE_TEMPLATES`), tên và giá vẫn lấy từ file nên không bịa được số. Món chỉ có một đoạn đọc như cũ, file cũ không phải sửa. `coca.docx` viết lại: món chính 4 đoạn giới thiệu và 4 đoạn mô tả, ba món phụ mỗi mục 3 đoạn (nguồn ở `scripts/make_demo_content.py`); 205 câu của 12 lượt mỗi món qua `OutputGuard` không câu nào bị chặn. Sửa FR-031 spec 004, hướng dẫn trong `template.docx`.

## ADR-089: Nhãn AI ở `shopee-top` dùng font hẹp đậm (Bahnschrift Bold Condensed) để chữ to và rõ
- **Ngày:** 2026-11-25 · **Trạng thái:** Đã chấp nhận 2026-11-25 (người dùng gửi ảnh nhãn hai dòng mờ và nói "form chữ bị tệ đi rồi"). Người dùng xem live thấy còn tệ hơn; demo Meet chuyển sang `top-center` một dòng bởi ADR-090, font hẹp đậm chỉ còn ở `shopee-top`.
  Sửa phần font và cỡ chữ ở `shopee-top` của ADR-085 và ADR-076; vị trí, bề rộng 26%, kiểu chữ trắng viền tối bóng mờ không nền giữ nguyên.
- **Bối cảnh:** ADR-085 giới hạn nhãn trong dải trống rộng 26% khung (125 px ở khung 480×832). Segoe UI Black là font rất đậm và rộng nên
  phải thu xuống 15 px; ở cỡ đó viền 1 px và bóng mờ lấp khe giữa các nét, video WebRTC nén thêm làm chữ nhòe.
- **Quyết định:**
  - Fork (`ailive_ext/label.py`): ở `shopee-top`, thử font hẹp đậm trước (`NARROW_FONT_CANDIDATES`): `bahnschrift.ttf` đặt biến thể
    "Bold Condensed" → `DejaVuSansCondensed-Bold.ttf` → `ARIALNB.TTF` (Arial Narrow Bold), rồi mới tới danh sách font cũ. Bahnschrift chỉ
    dùng khi đặt được biến thể Bold Condensed (không bao giờ dùng bản Regular mảnh mà ADR-076 đã loại).
  - Nhãn ở `shopee-top` còn phải vừa chiều cao: hộp kể cả bóng kết thúc trên đỉnh đầu host (19,5% chiều cao khung,
    `SHOPEE_TOP_BOTTOM_RATIO`). Khi thu nhỏ, nhãn dưới 40 px giảm từng 1 px (trước giảm 5%, bỏ qua cỡ vừa chỗ).
  - Kết quả: khung 480×832 cỡ 20 px (trước 15 px), hộp x 183–297, y 104–158; 1080×1920 cỡ 48 px; 360×640 cỡ 16 px.
  - App: `estimate_label_box` lấy cả dải trống (rộng 26%, cao tới 19,5%) làm hộp nhãn hai dòng; trang host (CSS `.label-shopee-top`) dùng
    `Bahnschrift` / `Arial Narrow` co hẹp, cỡ 2,4vh.
- **Lý do:** so 6 kiểu trên khung thật, nén JPEG chất lượng 45 rồi phóng 2,5 lần (ảnh so trong scratchpad phiên 2026-11-25): Bahnschrift
  Bold Condensed rõ nhất vì nét đậm, khe giữa chữ rộng và lên được cỡ lớn nhất trong cùng bề rộng; Impact lên 20 px nhưng nét quá dày,
  khe hẹp; Arial Narrow Bold 19 px nét mảnh hơn; Segoe UI Bold 16 px vẫn nhỏ. Không tải font mới: Bahnschrift và Arial Narrow có sẵn
  trên Windows; máy Linux thiếu cả hai thì về DejaVu như cũ.
- **Hệ quả:** máy Linux (RunPod) chỉ có DejaVuSansCondensed-Bold khi cài gói `fonts-dejavu-extra`; không có thì nhãn về DejaVuSans-Bold
  cỡ nhỏ như trước. TODO: kiểm font trên pod trước khi dùng GPU thuê. Bóng mờ ở mép dưới nhãn chạm sát đỉnh tóc (y 158 so với đầu ~163).
- **Phương án đã loại:** nới bề rộng dải lên 28% (chỉ thêm ~1 px cỡ chữ, sát chip trái của app); bỏ bóng mờ (chữ lẫn vào kệ sáng); Impact
  (nét dày, khe hẹp khi nén); đổi về một dòng `top-center` (bị tiêu đề app Shopee che, ADR-085).


## ADR-090: Nhãn AI mặc định về lại một dòng `top-center` cho demo Meet; `shopee-top` để dành cho Shopee qua OBS
- **Ngày:** 2026-11-25 · **Trạng thái:** Đã chấp nhận 2026-11-25 (người dùng gửi ảnh nhãn hai dòng Bahnschrift trên trang `/host` và
  nói "không để 1 hàng được à … nó càng tệ hơn hồi nãy, bạn run chrome dev tool check đi"). Sửa vị trí mặc định của ADR-085; font hẹp
  của ADR-089 chỉ còn dùng ở `shopee-top`.
- **Bối cảnh:** ở `shopee-top`, dải trống giữa các nút hai bên của app Shopee chỉ rộng 26% khung, nên "AI-GENERATED CONTENT" phải tách
  hai dòng ~20 px. Video WebRTC 480×832 bị trình duyệt phóng ~1,5 lần khi chia sẻ tab, chữ nhỏ thành nhòe. Ảnh so offline (ADR-089)
  không giống cái người dùng thấy trên trang thật. Một dòng ở cỡ đọc được thì luôn chạm chip trái hay ô quà phải của app (vùng ở
  `scene/shopee_overlay.py`), nên không có chỗ một dòng nào né được app. Buổi demo chạy trên Google Meet, không có giao diện app.
- **Quyết định:**
  - Mặc định `AI_LABEL_POSITION` đổi từ `shopee-top` về `top-center` ở fork (`ailive_ext/label.py`), app (`core/config.py`),
    `.env.example` và `.env` của máy demo: một dòng Segoe UI Black 26 px, hộp x 63–417, y 12–54 trên khung 480×832 (1080×1920: 60 px).
  - `shopee-top` giữ nguyên (hai dòng, font hẹp đậm) và vẫn chọn được; khi phát lên Shopee qua OBS phải đặt `AI_LABEL_POSITION=shopee-top`
    (spec 014 FR-019, SC-008 chỉ còn áp cho `shopee-top`).
  - Mọi thay đổi về hình (nhãn, cảnh, trang `/host`, `/obs`, trang điều khiển) phải kiểm trên trang thật bằng Chrome DevTools (chụp màn
    hình khi fork đang phát), không chỉ bằng ảnh dựng offline (CLAUDE.md, Code conventions).
- **Lý do:** chụp trang `/host` bằng Chrome DevTools với fork đang phát: nhãn một dòng to, rõ, nằm trên tường trống phía trên kệ, không
  chạm đầu host; nhãn hai dòng `shopee-top` trước đó nhỏ và nhòe.
- **Hệ quả:** trên app Shopee, `top-center` nằm dưới dải tiêu đề live (bị che quá nửa). TODO: trước khi lên Shopee, kiểm nhãn
  `shopee-top` trên điện thoại thật qua OBS và quyết lại cỡ chữ hoặc chữ ngắn hơn (vd "AI") nếu vẫn nhòe; có nên cho kiểm tra sẵn sàng
  báo lỗi khi `OUTPUT_MODE=obs` mà nhãn không ở `shopee-top`?
- **Phương án đã loại:** giữ `shopee-top` và nới bề rộng cho một dòng (đè chip và ô quà của app, mất ý nghĩa của vị trí này); một dòng
  ngay dưới dải tiêu đề (chỉ còn ~12 px chiều cao trước hàng chip); vẽ nhãn bằng HTML trên trang host (OBS/Meet phải nhận nhãn trong
  khung, ràng buộc 2).

## ADR-091: Khách dùng bằng app desktop nhẹ, phần nặng chạy trên GPU thuê theo giờ (feature 015, làm sau khi khách chốt thuê)
- **Ngày:** 2026-11-25 · **Trạng thái:** Đề xuất (người dùng: "note trước 015, sẽ làm sau khi khách chốt thuê khi demo"). Nếu chấp nhận
  thì thay phần "không deploy server lên cloud" và "chạy trên máy cục bộ" của ADR-021.
- **Bối cảnh:** người dùng muốn khách cài app như phần mềm desktop thông thường (tải bộ cài, cài, mở là dùng), còn GPU nhép miệng thì
  thuê theo giờ. Hiện app chỉ chạy từ mã nguồn trên laptop dev: `uv sync`, `.env` điền tay, fork LiveTalking dựng bằng
  `scripts/livetalking/setup.ps1`, model tải tay, freellmapi chạy trong Docker; nhánh `ailive` của fork chỉ có trên laptop (remote là
  repo gốc `lipku/LiveTalking`).
- **Quyết định (đề xuất):** tách hai phần.
  - **Máy khách:** vỏ desktop nhẹ (đề xuất Tauri; bộ cài `.msi`/`.exe`, tự cập nhật, ký code). Chỉ có đăng nhập, nút "Bắt đầu live" /
    "Dừng", cửa sổ trang điều khiển và trang host/`/obs` của pod. Không cần GPU, CUDA, Python hay Docker trên máy khách.
  - **GPU thuê (RunPod, theo giờ):** một Docker image dựng sẵn gồm app FastAPI, VieNeu, fork LiveTalking (nhánh `ailive`), model và
    bộ nhân vật/cảnh của đúng khách đó (ràng buộc 3).
  - **Server điều phối nhỏ của mình:** giữ key RunPod và key LLM (khách không thấy key), bật/tắt pod, tự tắt pod khi bỏ quên, đếm giờ
    GPU để tính tiền, cấp token vào pod.
  - Số feature **015** giữ cho việc này; đi đủ 7 bước SDD, bắt đầu bằng `/sdd.specify` **sau khi khách chốt thuê sau buổi demo**.
- **Việc phải làm trong 015 (ghi để không quên):**
  - Đưa nhánh `ailive` của fork (và `vendor/ultralight`) lên repo private hoặc `git bundle`; hiện chỉ có trên laptop.
  - App hiện chỉ nghe `127.0.0.1` và không có đăng nhập: thêm xác thực bằng token và HTTPS trước khi mở ra mạng.
  - Hình + tiếng từ pod về máy khách qua mạng: WebRTC có thể cần TURN (`docs/RUNPOD.md`); đo độ trễ và độ ổn định trước.
  - Bỏ phụ thuộc Docker của freellmapi trên máy khách (chạy trong server hoặc pod, hoặc gọi thẳng nhà cung cấp).
  - Khách tải file sản phẩm và ảnh qua trang điều khiển (012 đã có).
- **Lý do:** bộ cài nhỏ, máy khách không cần card NVIDIA (chạy được cả Mac), key không nằm trên máy khách, đếm được giờ GPU để báo giá.
- **Phương án đã loại:** gói trọn trên máy khách (Python + torch CUDA + model, bộ cài vài GB): bắt máy khách có card NVIDIA, trái ý thuê
  GPU theo giờ, và giao model cho bên thứ ba.
- **Hệ quả:** phải sửa `docs/PRD.md` (từ dịch vụ làm hộ sang có phần mềm cho khách); phiên Shopee sau này nằm trên pod chứ không ở máy
  khách, phải xem lại ADR-010 và ràng buộc 6; vẫn vướng giấy phép Wav2Lip thương mại (RISKS L2) vì chạy dịch vụ thu tiền.
- **TODO:** Chi phí GPU thật mỗi giờ (15 giờ/ngày ≈ 450 giờ/tháng/khách) và ai trả: mình gộp vào giá hay khách trả riêng? Hỏi giá
  trước khi bật pod (ADR-019).
- **TODO:** Server điều phối chạy ở đâu và có tốn phí không? Chứng chỉ ký code Windows (và Apple nếu cần bản Mac) mất phí hằng năm.

## ADR-092: Tắt chữ câu đang nói trên trang host (`HOST_SUBTITLES`, mặc định tắt)
- **Ngày:** 2026-11-25 · **Trạng thái:** Đã chấp nhận 2026-11-25 (người dùng gửi ảnh khung chữ "Coca-Cola chai 500 ml nắp vặn…" trên
  trang `/host` và nói "bỏ cái hiển thị script nói ra đi"). Đổi hành vi phụ đề web của 005 (contracts/api.md §3, §4) và 001.
- **Bối cảnh:** trang `/host` hiện chữ của câu host đang nói trong một hộp nền tối ở giữa khung (ngang ngực host khi bật cảnh 009). Hộp
  này che người host và phần trên sản phẩm chính; buổi live bán hàng thật không có phụ đề như vậy. Trang `/obs` vốn đã ẩn phụ đề (006).
- **Quyết định:** thêm biến `HOST_SUBTITLES` (mặc định `false`). `GET /api/host-config` trả thêm `"subtitles"`; trang host chỉ hiện chữ
  khi giá trị là `true`. Server vẫn gửi `subtitle`/`subtitle_clear`, ack và watchdog không đổi. Phụ đề vẽ trong khung của cảnh
  (`SCENE_SUBTITLES`) giữ nguyên, vẫn tắt mặc định.
- **Lý do:** một công tắc, không xóa code: bật lại được khi cần (vd thử tiếng trên máy không loa, hay khách muốn phụ đề).
- **Phương án đã loại:** xóa hẳn phụ đề web (mất công cụ kiểm tiếng khi tập dượt); chỉ ẩn bằng CSS cố định (không bật lại được).

## ADR-093: Ánh sáng làm nổi ở `showcase` còn 60 (thay 230) và tắt bục trong cảnh demo
- **Ngày:** 2026-11-25 · **Trạng thái:** Đã chấp nhận 2026-11-25 (người dùng gửi ảnh vùng cạnh chai Coca-Cola Zero và nói "bỏ cái bục
  và check lại mản hình ở đây, bạn thấy không?"). Chỉnh mức sáng của spec 013 FR-022 cho cách bày `showcase` (ADR-079); `realistic` giữ
  mức đã duyệt.
- **Bối cảnh:** ở `showcase` sản phẩm đứng sát trước áo polo xanh đậm của host. Quầng sáng kem quanh món đang nói (`HIGHLIGHT_ALPHA = 230`,
  làm mờ 12 px) phủ lên áo thành một mảng xám sữa có cạnh rõ, cạnh đó lộ viền cam thật của áo ở khe hẹp giữa chai Zero và lốc 6 chai,
  nhìn như lỗi ghép. Bục (`riser`) cũng không còn cần: người dùng muốn bỏ.
- **Quyết định:**
  - Thêm `SHOWCASE_HIGHLIGHT_ALPHA = 60` (`src/ai_live/scene/layout.py`); `render_base` dùng mức này khi `layout.mode == "showcase"`,
    các cách bày khác vẫn dùng `HIGHLIGHT_ALPHA = 230`. Món đang nói vẫn được làm nổi nhẹ (FR-022 "ánh sáng dịu") và vẫn phóng to như cũ.
  - Cảnh demo `assets/scenes/demo/scene.json` (không vào git) đặt `"riser": false`; tính năng bục vẫn còn trong code.
- **Lý do:** so ba mức 230 / 110 / 60 bằng công cụ của skill `live-scene-realism` (lốc 6 chai sáng và chai Zero sáng): 60 vẫn tách được
  món, áo giữ màu xanh đậm. Kiểm live trên `/host` bằng Chrome DevTools lúc nói lốc 6 chai và lúc nói chai Zero: không còn quầng sữa,
  nhãn AI vẫn hiện.
- **Phương án đã loại:** bỏ hẳn ánh sáng (trái FR-022); giữ 230 và cắt vùng áo khỏi quầng (cần mặt nạ áo theo từng khung, tốn CPU, mà
  showcase không có `hands_zone`).

## ADR-094: Khoanh tay vùng phòng cũ còn sót (khe dưới nách) lúc chuẩn bị nền, và không vẽ nhãn lên khung gốc của clip
- **Ngày:** 2026-11-25 · **Trạng thái:** Đã chấp nhận 2026-11-25 (người dùng gửi ảnh: "thấy chỗ nách dưới host có vùng cam á"). Bổ sung
  spec 014 (hợp đồng `prepare-cli.md` §1, §2; data-model `manifest.json`).
- **Bối cảnh:**
  - Ở `demo_host_02`, giữa cánh tay và thân dưới hai nách có khe nhỏ lộ phòng cũ màu cam/gỗ. GrabCut giữ khe trái (màu gần da và viền
    cam của áo), bước lấp lỗ của `clean_binary` lấp lại khe phải. So với ảnh nền trung vị (plate) cũng không được: host gần như đứng yên
    nên trung vị trong khe chứa cả áo, so với nó thì xóa luôn áo xanh đậm.
  - Lúc kiểm live còn thấy lỗi thứ hai ở fork: ở nhánh khung nghỉ, `process_frames` đưa thẳng mảng khung gốc của clip vào bước vẽ nhãn AI
    (vẽ tại chỗ). Những lúc chưa có nền mới và chưa có lớp cảnh (đầu mỗi phiên) nhãn bị in vĩnh viễn vào khung gốc, nên khi nạp lại mặt
    nạ (manifest đổi) dấu vân tay crc32 không còn khớp: fork báo `ailive background not used: frame_not_prepared:81` và phát phòng cũ.
- **Quyết định:**
  - Thêm `--room-area "x,y x,y x,y ..."` (lặp lại được) cho `background-prepare` của app và `ailive_ext.background_prep` của fork. Sau
    bước lấp lỗ, `clear_room_areas` xét từng đa giác (bỏ phần từ `desk_top_px` trở xuống): Otsu trên độ sáng Lab của mọi khung chia hai
    lớp; lớp có màu trung bình xa màu người ở vành 4 px ngoài đa giác (`ROOM_AREA_RING_PX`) hơn là phòng và được đặt 0 trên từng khung.
  - Manifest ghi `room_areas`; lần chuẩn bị sau không truyền `--room-area` thì app dùng lại các vùng đó, `--no-room-areas` để bỏ.
  - Fork chép khung nghỉ (`target_frame.copy()` trong `avatars/base_avatar.py`) trước mọi bước vẽ, để nhãn và watermark không bao giờ
    chạm khung gốc. Test `ailive_ext/tests/test_idle_frame.py`.
  - Vùng dùng cho `demo_host_02` (khung 480×832): trái `146,549 149,551 145,572 142,599 125,599 124,590 127,584 132,568 140,556`, phải
    `361,565 366,565 372,582 379,591 380,597 368,602 356,608 352,606 357,590`. Chạy lại: 162 khung, 18 khung có cờ lọt (trước 19), mảng
    lọt lớn nhất 214 px; đánh dấu đã soát bởi Claude, chờ người dùng xem `review.jpg`.
- **Lý do:** khe chỉ vài chục pixel, cố định theo dáng ngồi; khoanh tay một lần rẻ hơn và chắc hơn tìm luật tự động. Tách sáng/tối trong
  vùng giữ được áo dù áo và phòng cùng nằm trong đa giác. Kiểm live trên `/host` bằng Chrome DevTools sau khi khởi động lại fork: nền mới
  được dùng (không còn cảnh báo), khe dưới nách hiện nền mới, nhãn AI vẫn hiện.
- **Phương án đã loại:** so với plate trong vùng (xóa áo); tắt lấp lỗ (mở ra lỗ ở chỗ khác trên áo); tải model tách người mới (cần ADR
  riêng, ADR-083 vẫn chờ).

## ADR-095: Bàn `showcase` kiểu "hot live": nhóm hàng, tem giá và băng khuyến mãi (đều là cờ, mặc định tắt)
- **Ngày:** 2026-11-26 · **Trạng thái:** Đã chấp nhận 2026-11-26 (người dùng: "về sản phẩm đặc trước bàn thấy không thu hút lắm => bạn
  thêm vài item với nhiều loại coca với trưng sản phẩm cuốn hút vào", "quan trọng trình bày sản phẩm như 1 buổi hot live"). Thêm spec
  013 FR-030–FR-032. Cùng ngày người dùng xem live và bỏ tem giá, băng khuyến mãi khỏi cảnh demo (ADR-096); code vẫn giữ. Nhóm chai
  "hàng ba" đổi thành cụm hai hàng so le bởi ADR-098.
- **Bối cảnh:** mỗi món chỉ có một đơn vị đứng lẻ trên bàn, nhìn như bàn trưng mẫu chứ không như phiên live bán hàng có hàng sẵn.
- **Quyết định:**
  - `src/ai_live/scene/merchandise.py`: nhóm hàng dựng một lần lúc nạp cảnh từ chính ảnh tách nền của món, chọn theo tỉ lệ rộng/cao
    một đơn vị: ≤ 0,45 hàng ba (chai, hai chai sau nhỏ hơn và tối hơn), ≤ 0,65 tháp ba (lon), ≤ 1,2 cặp (lốc), rộng hơn thì giữ một
    đơn vị (thùng). Chỉ đổi độ sáng các đơn vị phía sau (FR-006). Ảnh còn nền hoặc ảnh giữ chỗ không dựng nhóm.
  - `src/ai_live/scene/layout.py`: tem giá dưới chân mỗi món, chữ lấy nguyên từ giá trong file dữ liệu (`price_text`); không có chỗ
    mà không che món khác thì không vẽ và báo `price_tag_no_room`. Băng khuyến mãi dưới cụm sản phẩm liệt kê nguyên văn khuyến mãi của
    file (`promo_banner_lines` trong `render.py` thu chữ trước, bỏ nguyên khuyến mãi cuối sau, không cắt nửa câu); thiếu chỗ báo
    `promo_banner_no_room`.
  - `LayoutParams` thêm `stock`, `price_tags`, `promo_banner` (mặc định `false`), chỉ có tác dụng ở `showcase`.
  - Dữ liệu demo `data/products/coca.docx` (qua `scripts/make_demo_content.py`) thêm các món Coca khác nhau. Ảnh lon "Can of Coca Cola
    (26899145485).jpg" (Willis Lam, CC BY-SA 2.0) dùng cho món lon 355 ml trong vòng này; ADR-096 đã bỏ món đó khỏi dữ liệu.
  - Test `tests/unit/test_hot_live_desk.py`.
- **Lý do:** nhóm hàng làm từ ảnh của chính món nên không bịa hình, màu, chữ; giá và khuyến mãi chỉ chép từ file nên không trái ràng
  buộc 7. Để là cờ vì khách khác có thể không muốn giá trên hình.
- **Phương án đã loại:** dùng ảnh hàng loạt tải trên mạng (cần thêm giấy phép từng ảnh, ảnh khác món thật của khách); để LLM viết dòng
  khuyến mãi (có thể bịa).

## ADR-096: Thùng quà Tết làm món chính giữa bàn, 3 món trên bàn, tắt tem giá và băng khuyến mãi trong cảnh demo
- **Ngày:** 2026-11-26 · **Trạng thái:** Đã chấp nhận 2026-11-26 (người dùng: "không hiện giá trên này hoặc khuyến mãi chỉ có sản phẩm
  trên bàn thôi => bạn coi sắp xếp lại sản phẩm trang trí đẹp, ví dụ dùng hộp quà hoặc sản phẩm nổi bật hiện nay nếu có"). Đổi lựa chọn
  món chính của ADR-081 (lốc 6 chai). Thêm spec 013 FR-033.
- **Bối cảnh:** "hộp quà" chung chung sẽ gợi ý một khuyến mãi không có trong dữ liệu. Dữ liệu demo đã có một món đúng là quà: thùng 24 lon
  Coca-Cola Tết 320ml (in hình Tết, giá 235.000đ trong file). Thùng rộng hơn cao, mà `SHOWCASE_MAIN_MAX_WIDTH = 0,8` W cho nó rộng tới
  khoảng 270 px trên khung 480 px: hai dãy chai hai bên chỉ còn 90–105 px, và lốc 6 chai không còn chỗ nào không che món khác (FR-025).
- **Quyết định:**
  - `scripts/make_demo_content.py`: thùng Tết lên đầu danh sách, là món "chính"; sau đó chai 500ml, chai thủy tinh Zero 237ml, lốc 6 chai
    355ml (phụ). Món lon 355ml của ADR-095 bỏ. Tạo lại `data/products/coca.docx`.
  - `SHOWCASE_MAIN_MAX_WIDTH` 0,8 → 0,5 (`src/ai_live/scene/layout.py`): món chính rộng bị giữ trong nửa khung trước khi xét mức sàn
    0,22 H, để món phụ còn chỗ đứng hai bên.
  - Cảnh demo `assets/scenes/demo/scene.json` (không vào git): `max_slots` 3, `price_tags` false, `promo_banner` false, `stock` true.
    Trên bàn: thùng Tết giữa (cao khoảng 170 px), dãy Zero bên trái và dãy chai 500ml bên phải (khoảng 110–127 px). Lốc 6 chai vẫn
    trong dữ liệu, host vẫn giới thiệu, nhưng không đứng trên bàn (báo `overflow`).
  - Test: `test_a_wide_gift_box_in_the_middle_leaves_the_bottles_room_beside_it` (`tests/unit/test_hot_live_desk.py`), sửa mức sàn
    trong `test_a_wide_main_product_shrinks_to_make_room_beside_it` (`tests/unit/test_showcase_layout.py`).
- **Lý do:** thùng Tết là món có thật trong file, nhìn như hộp quà mà không cần bịa gì. Thùng nhỏ đi (190 → 170 px) là đi theo hướng an
  toàn với luật không làm món to hơn thật. So hai phương án bằng skill `live-scene-realism` (`out/realism/sheet_fin.png`: A giữ 0,8, B
  chọn 0,5), rồi kiểm live trên `/host` bằng Chrome DevTools: nhãn AI vẫn hiện, không còn giá và băng khuyến mãi, không món nào che món
  nào. pytest 3595 passed, ruff sạch.
- **Phương án đã loại:** đặt lốc 6 chai ở góc trước (che món khác hoặc vượt giới hạn cỡ); 4 món trên bàn (món nào cũng nhỏ đi); tăng
  `SHOWCASE_BACK_MIN_SCALE` lên 0,75 (không cần sau khi giới hạn bề rộng thùng); hộp quà vẽ thêm (gợi ý khuyến mãi không có trong file).
- TODO: cỡ thật của thùng 24 lon Tết (đoán khoảng 35 cm rộng, 14–16 cm cao, chưa kiểm) — người dùng/khách xác nhận để so với `--real-cm`.
- Bề rộng tối đa món chính đổi bởi ADR-097 (0,5 → 0,42).

## ADR-097: Bày bàn `showcase` theo bậc trước–sau: thùng quà ra trước, hàng lùi sau hai bên, cảnh Meet tắt `avoid_app_overlay`
- **Ngày:** 2026-11-26 · **Trạng thái:** Đã chấp nhận 2026-11-26 (người dùng: "cái góc để đồ á nó hơi xấu, bạn research cách chưng bày
  sản phẩm để thu hút người xem và áp dụng vào trong này đi"). Thêm spec 013 FR-034. Đổi `SHOWCASE_MAIN_MAX_WIDTH` của ADR-096.
  `SHOWCASE_MAIN_MAX_WIDTH` 0,42 đổi thành 0,38 bởi ADR-098.
- **Bối cảnh:** sau ADR-096 bàn trông dẹt: ba nhóm hàng đứng gần như trên một đường (chân thùng ~688 px, chai ~665 px trên khung
  832 px), rải đều thành ba "đảo" sát mép khung, thùng đỏ rộng che hết phần dưới người host, và mặt bàn trước trống khoảng 1/5 khung.
  Nguyên nhân chính: `avoid_app_overlay` (ADR-087) ép dải độ sâu để mọi món đứng trên vùng bình luận của app Shopee, trong khi demo hiện
  chiếu qua Meet, không có lớp app đó.
- **Nguyên tắc tham khảo (bày hàng bán lẻ và chụp ảnh đồ uống):** bố cục tam giác/kim tự tháp với món chủ đạo làm tâm; nhóm số lẻ (quy
  tắc 3); món thấp ở trước, món cao ở sau, đặt ở các độ sâu khác nhau để có chiều sâu; gom thành một cụm thay vì dàn đều. Nguồn: Shopify
  "visual merchandising", Fiverr "rule of 3 for visual merchandising", Repsly "visual merchandising display techniques", PetaPixel
  "props for better beverage photography" (đường dẫn trong `progress/LOG.md` ngày 2026-11-26).
- **Quyết định:**
  - `SHOWCASE_MAIN_DEPTH` 0,8 → 0,7 và `SHOWCASE_MAIN_MAX_WIDTH` 0,5 → 0,42 (`src/ai_live/scene/layout.py`): thùng quà đứng trước ở giữa,
    lùi khỏi mép trước bàn một dải mỏng, thấp hơn hai nhóm chai đứng sau hai bên (cụm tam giác có bậc). Thùng cao 170 → 143 px (khoảng
    1,3 lần cỡ thật theo `--real-cm` 15 cm, trong khoảng 1,0–1,45 của món trước), tay host vẫn lộ trên nắp thùng.
  - Cảnh demo `assets/scenes/demo/scene.json` (không vào git): `avoid_app_overlay` false khi chiếu qua Meet. Khi lên Shopee qua OBS phải
    bật lại (thùng sẽ lùi lên trên vùng bình luận như ADR-087).
  - Test: `test_the_gift_box_stands_in_front_and_the_stock_steps_back_beside_it` (`tests/unit/test_hot_live_desk.py`).
- **Lý do:** so 7 phương án bằng skill `live-scene-realism` (`out/realism/sheet_disp1.png`, `sheet_disp2.png`): d0 hiện tại, d1 tắt
  `avoid_app_overlay` (thùng 170 px, 1,5 lần cỡ thật: quá to), d4 chỉ thu thùng, d2 tắt + thu thùng (thùng sát mép dưới khung), d5 thêm
  độ sâu 0,7 (chọn), d6 đẩy hàng sau ra trước (lại dẹt). Kiểm live trên `/host` bằng Chrome DevTools.
- **Phương án đã loại:** vẽ thêm khăn trải bàn đỏ hoặc đồ trang trí Tết để lấp mặt bàn trống (không cần khi thùng ra trước; dễ gợi ý
  quà/khuyến mãi không có trong file); đặt nhóm chai sau lưng thùng (che nhau, trái FR-025); tự tắt `avoid_app_overlay` theo
  `OUTPUT_MODE` (đổi nghĩa cờ của ADR-087; để sau nếu hay quên).
- TODO: chế độ OBS chưa có mục kiểm sẵn sàng nhắc bật `avoid_app_overlay` — có cần thêm vào `python -m ai_live.ops` trước khi lên Shopee không?

## ADR-098: Chai trên bàn `showcase` thành cụm hai hàng so le theo ảnh mẫu, thùng quà thu còn 0,38 khung
- **Ngày:** 2026-11-26 · **Trạng thái:** Đã chấp nhận 2026-11-26 (người dùng gửi ảnh mẫu bàn Coca-Cola Tết tạo bằng Gemini: "bạn học
  cách triển khai như hình này được không"). Thêm spec 013 FR-035; đổi FR-030 (hàng ba → cụm hai hàng) và FR-034 (0,42 → 0,38).
- **Bối cảnh:** ảnh mẫu là một bàn dày hàng: hai thùng Tết chồng ở giữa, lốc lon hai bên, cụm chai hai hàng ở hai bên (chai Zero phía
  sau bên trái), hàng lon Tết và Zero rời ở mép trước (một lon nằm), thêm ly Coca đá, bao lì xì, cành mai đào và đồng xu. Bàn hiện tại
  sau ADR-097 mỗi bên chỉ có ba chai (một chai trước, hai chai ló sau), trông thưa hơn nhiều.
- **Phân tích phần học được:**
  - Khung dọc 480 px chỉ cho mặt bàn rộng khoảng 65 cm ở cỡ thật (~7,4 px/cm theo đầu host 23 cm). Thử thêm món thứ tư: mọi món co còn
    0,28–0,41 lần cỡ thật, nên ảnh mẫu chỉ đạt độ dày nhờ cho các món khác nhau chồng lên nhau, điều FR-025 (ADR-081) cấm.
  - Lon rời, lon Zero, lốc lon, ly đá, hoa, lì xì, đồng xu không có ảnh thật và không có trong file sản phẩm; ảnh Gemini có chữ bao bì
    méo và dấu nước nên không dùng làm tài sản được (ràng buộc 8: không ảnh sai lệch). Lì xì, đồng xu dễ gợi ý khuyến mãi không có
    trong file (ADR-096). Hai thùng chồng sẽ che tay và ngực host.
  - Phần làm được trong luật: nhiều đơn vị của cùng một món đứng thành cụm có chiều sâu, chính là thứ làm ảnh mẫu trông "đầy hàng".
- **Quyết định:**
  - `src/ai_live/scene/merchandise.py`: nhóm chai thành cụm hai hàng so le, `STOCK_ROW_FRONT` 2 chai trước sát nhau, `STOCK_ROW_BACK`
    3 chai sau lệch nửa chai, `STOCK_ROW_BACK_SCALE` 0,85 và tối 0,86 (`STOCK_BACK_SHADE`); đỉnh hai hàng ngang nhau nên cả cụm cao một
    chai (luật cỡ thật ADR-082 vẫn tính theo một chai). Mỗi bên 5 chai thay vì 3. Bỏ `STOCK_BACK_SHOWN`.
  - `src/ai_live/scene/layout.py`: `SHOWCASE_MAIN_MAX_WIDTH` 0,42 → 0,38 để cụm chai rộng hơn còn chỗ; thùng quà còn ~1,16 lần cỡ thật
    (trước ~1,29), trong khoảng 1,0–1,45 của món trước.
  - Test: `test_bottles_stand_as_two_staggered_rows_one_bottle_tall` (`tests/unit/test_hot_live_desk.py`).
- **Lý do:** so phương án bằng skill `live-scene-realism`. `out/realism/sheet_e.png`: nâng hàng sau cao hơn cho giống ảnh mẫu làm cụm
  cao hơn một chai, layout chia theo chiều cao nên mỗi chai co còn ~0,7 cỡ thật (loại). `out/realism/sheet_g.png` (đỉnh ngang): hiện
  tại, 3+2, 3+2 ở 0,38, 2+3 ở 0,38 (chọn: hàng sau dài hơn ló ra hai bên nên cụm đầy hơn mà chai trước không bị nhỏ), 3+3 ở 0,38 (chai
  co thêm). Chai còn ~0,79 (500 ml) và ~0,85 (Zero 237 ml) lần cỡ thật theo báo cáo, do bề rộng khung giới hạn; nhỏ hơn thật thì không
  gây hiểu lầm (Shopee chỉ cấm làm to hơn thật). Kiểm live `/host` bằng Chrome DevTools: hai cụm chai hai hàng, thùng giữa, tay host
  và nhãn AI vẫn hiện.
- **Phương án đã loại:** cho các món khác nhau chồng nhau theo chiều sâu như ảnh mẫu (trái FR-025); thêm món thứ tư (mọi món co dưới
  nửa cỡ thật); chồng hai thùng (che tay host, thùng cao gấp đôi); vẽ lon, ly, hoa, lì xì, đồng xu không có ảnh thật; dùng thẳng ảnh
  Gemini (chữ méo, dấu nước, không phải ảnh sản phẩm thật); hàng sau nâng cao (chai co còn ~0,7).
- TODO: khách hàng có ảnh thật (hoặc ảnh có giấy phép) của lon Tết rời, lon Zero, lốc lon, ly Coca đá và đồ trang trí Tết không? Có
  ảnh thì thêm được món và đạo cụ; đạo cụ không phải sản phẩm cần quyết có cho host nhắc tới hay không.
- TODO: người dùng có muốn nới FR-025 cho phép món ở xa đứng khuất một phần sau món gần (đúng phối cảnh, như ảnh mẫu) không? Đổi này
  cần ADR riêng vì ADR-081 đặt ra theo yêu cầu "các sản phẩm không bị che nhau".

## ADR-099: Bày sản phẩm bằng lớp ảnh trong OBS trên mặt bàn sâu hơn (ý tưởng làm sau)
- **Ngày:** 2026-11-26 · **Trạng thái:** Đề xuất (người dùng: "note trước idea này để làm sau"). Chưa sửa code, spec hay cảnh demo.
- **Bối cảnh:** người dùng hỏi có thể dùng OBS ghép sản phẩm lên mặt bàn không, vì bản ghép thử (ảnh phòng Gemini + host
  `demo_host_02` + sản phẩm cắt từ ảnh Gemini, chỉ ở thư mục tạm) "sản phẩm bị hẹp 2 bên, không giống buổi live chuyên nghiệp".
  Điều đo được ở bản thử:
  - Tay host đặt trên bàn ở khoảng hàng 620–640 của khung 480×832, mép trước bàn ở khoảng hàng 686. Phía trước tay chỉ còn dải bàn
    cao khoảng 50 px, giữa bàn là tay host, nên sản phẩm chỉ còn chỗ ở hai góc.
  - Ảnh Gemini đặt sản phẩm lấn vào vùng tay host cử động (hợp của 81 khung). Cắt theo mép vùng thì sản phẩm bị cụt; dời và thu nhỏ
    cả nhóm (còn 80–85%) thì nguyên vẹn nhưng nhỏ và dồn góc. Hộp quà Gemini có chữ in méo nên phải bỏ (P11 trong RISKS).
  - Live chuyên nghiệp (ảnh mẫu đối thủ, 2026-11-25) có một hàng sản phẩm chạy suốt mặt quầy ngay trước người dẫn, thấp hơn tay.
- **Quyết định (đề xuất):**
  1. Đổi khung: đẩy host lên hoặc thu nhỏ một chút để mặt bàn phía trước sâu ra khoảng 150–180 px, đủ cho một hàng sản phẩm trải
     ngang, nằm trước và thấp hơn tay host, không chạm tay ở khung nào.
  2. Sản phẩm là ảnh thật của khách đã tách nền (bước tách nền của 013/012), không dùng ảnh Gemini.
  3. Xếp hàng sản phẩm bằng lớp ảnh PNG trong OBS (kéo thả, xem tận mắt) trên Browser Source trang `/obs` (006), trong vùng an toàn
     do mình xuất ra (ngoài vùng tay host cử động). Nhãn AI vẫn vẽ trong pipeline (ràng buộc 2).
  4. Bước đầu khi làm: dựng ảnh thử bố cục bàn sâu, đặt cạnh ảnh live đối thủ để so, người dùng duyệt rồi mới cài OBS.
- **Giới hạn đã biết:** OBS chỉ chồng lớp, không biết trước sau: lớp sản phẩm hoặc che tay host, hoặc bị host che, nên vẫn phải giữ
  vùng an toàn. Demo qua Meet sẽ phải dùng OBS Virtual Camera thay chia sẻ tab Chrome, cần sửa `docs/RUNBOOK.md`. Đi lại cảnh bàn của
  013 (`showcase`, ADR-079/081/096–098) đang vẽ sản phẩm trong pipeline: khi làm phải quyết giữ cách nào, hay OBS chỉ cho Shopee.
- TODO: người dùng gửi ảnh chụp buổi live đối thủ làm mẫu để so bố cục?

## ADR-100: Nền `anh_shop`: ảnh shop sau host, cho phép ảnh do AI tạo cảnh shop chung
- **Ngày:** 2026-11-28 · **Trạng thái:** Chấp nhận (người dùng: "làm A trước xem"). Spec 014 FR-009a, Phase 10 (T082–T086).
- **Bối cảnh:** kệ hàng vẽ bằng code (`ke_hang`, ADR-086) vẫn kém ảnh live đối thủ. Người dùng đã nhờ Gemini tạo một ảnh cửa hàng tạp
  hoá chung (kệ hàng, tủ lạnh, cây xanh, không người). Spec cũ để `anh_shop` sau demo và chỉ nghĩ tới ảnh chụp thật của khách.
- **Quyết định:**
  1. Làm `anh_shop` ngay: ảnh shop ghép sau host qua mặt nạ nền của nhân vật (014 US1), phủ kín bằng cắt giữa giữ tỷ lệ, làm mềm, khớp
     ánh sáng với phòng gốc như `ke_hang`. Chạy được cả Meet (`/host`) và OBS (`/obs`); nhãn AI vẫn ghép trong pipeline.
  2. Ảnh ghi nguồn `photo` hoặc `ai_generated` trong `shop_photo.json` (cùng sha256, `confirmed_by`, `confirmed_at`, `original_name`).
     Ảnh AI chỉ được là cảnh shop chung: không người, không sản phẩm của khách, không logo bên thứ ba đọc được; người vận hành xác nhận.
  3. Ảnh AI luôn mềm ít nhất `AI_MIN_SOFTNESS_PX = 4.0` px trên khung rộng 480 px, để nhãn hàng AI vẽ trên kệ chỉ còn mảng màu.
  4. Sản phẩm của khách (trên bàn hay trên nền) không bao giờ là ảnh AI tạo: bàn vẫn dùng ảnh thật đã tách nền (013).
     Ngoại lệ chỉ cho demo qua OBS: ADR-102.
  5. Đưa ảnh vào bằng lệnh `python -m ai_live.scene shop-photo ... --confirmed-by ... [--ai-generated]`; nút tải trên trang điều khiển
     (T064) để sau. Sửa hay thay file thì sha256 lệch, nền rơi về phòng gốc với lý do `shop_photo_unconfirmed`.
- **Lý do:** ảnh thật nhìn giống phòng live hơn mọi kệ vẽ bằng code, và mất ít công. Làm mờ đủ mạnh vừa giống độ sâu trường ảnh của máy
  quay, vừa giảm rủi ro logo bên thứ ba (RISKS P14) và chữ méo của ảnh AI. Không thêm thư viện, không tải mô hình.
- **Phương án đã cân nhắc:** ghép ảnh nền bằng lớp OBS (ADR-099): không biết trước sau so với host và không chạy trên Meet; tự gọi API tạo
  ảnh trong hệ thống: ngoài phạm vi (spec 014, làm rõ 2026-11-28).
- **Hệ quả:** cảnh demo `assets/scenes/demo/scene.json` đổi `style` từ `ke_hang` sang `anh_shop`. Ảnh nền là nội dung AI nằm trong khung đã
  có nhãn "AI-GENERATED CONTENT" (ADR-065). TODO: người dùng xem trên điện thoại thật xem còn đọc được chữ hay logo nào trên kệ không (T086).

## ADR-101: Bàn sản phẩm kiểu editor là lớp ảnh riêng trong OBS, không sửa app
- **Ngày:** 2026-11-28 · **Trạng thái:** Chấp nhận (người dùng: "đừng bỏ vào app hãy tách riêng show ghép ảnh cùng với app vào obs",
  "kiểu lắp vào á chứ không apply thẳng vào app"). Làm một phần ADR-099; không sửa code app, spec hay test.
  Mở rộng bởi ADR-102 (nền và bàn đều là lớp ảnh OBS, nguồn này ẩn).
- **Bối cảnh:** người dùng muốn bàn sản phẩm trông như ảnh ghép của editor chuyên nghiệp: cụm hàng dày, có hàng trước hàng sau, bóng đổ,
  phản chiếu trên mặt bàn, ánh sáng bên. Ghép thẳng trong pipeline (013 `showcase`) bị luật FR-025 (không chồng nhau) và giới hạn số món.
- **Quyết định:**
  1. Script độc lập `scripts/obs/desk_overlay.py` (chỉ PIL/numpy) xuất `assets/scenes/<id>/obs_overlay/desk_overlay.png` 1080×1872,
     nền trong suốt, gồm mặt bàn đục vẽ y như app (cùng `desk.png`, cùng mép bàn `desk_top` của nhân vật, cùng cách phóng 480×832 →
     1080×1872) và các cụm sản phẩm. Bố cục đọc từ `obs_overlay/arrangement.json` (tạo mẫu bằng `--write-arrangement`).
  2. Chỉ dùng ảnh cắt thật của khách đang `active` và có `rights_confirmed_at` trong `uploads/images.json` (ADR-100 mục 4); không ảnh AI.
  3. Script từ chối món nào có chân ở trên mép bàn (để không che tay và người host) và báo lỗi nếu dải 12% trên cùng không trong suốt hẳn:
     nhãn "AI-GENERATED CONTENT" vẫn ghép trong pipeline và không bao giờ bị lớp này che (ràng buộc 2).
  4. Trong OBS, nguồn ảnh "Bàn sản phẩm (ghép)" nằm **trên** nguồn `AI host`, vị trí (0, 24), tỉ lệ 1, khóa.
  5. Cảnh demo đặt `layout.max_slots` 1 để app chỉ vẽ một món (thùng) nằm hẳn dưới mép bàn, bị mặt bàn đục của lớp OBS che.
- **Lý do:** tách lớp giữ app nguyên vẹn và ra đúng kiểu xếp lớp như Photoshop; lớp tĩnh không tốn GPU. Host, giọng và nhép miệng vẫn tạo
  theo thời gian thực; lớp ảnh là đồ trang trí trên bàn, không phải video quay sẵn.
- **Giới hạn:** lớp ảnh không đổi theo lời host nên mất phần làm nổi món đang nói (highlight của 009/013). Đổi ảnh sản phẩm hay mép bàn
  thì phải chạy lại script (OBS tự nạp lại file; nếu không thì chuột phải nguồn → Reload). Chỉ chạy qua OBS: demo Meet chia sẻ tab
  `/host` không thấy lớp này (cần OBS Virtual Camera, ADR-099).
- **Hoàn tác:** xóa hoặc ẩn nguồn trong OBS; trả `scene.json` từ `scene.json.before-obs-overlay`; cảnh OBS có bản sao
  `AI_Live.json.before-desk-overlay`.

## ADR-102: Ba lớp ảnh trong OBS: nền shop sau host, ảnh bàn sản phẩm Gemini trước host, app chỉ vẽ host trên phông xanh
- **Ngày:** 2026-11-28 · **Trạng thái:** Chấp nhận (người dùng gửi ảnh Gemini bàn gỗ có Coca-Cola: "lấy ảnh này", "với cái layout đằng
  sau cũng ghép tương tự ảnh sản phẩm", "AI host thì trên bàn không có gì"). Mở rộng ADR-101; không sửa code app, spec hay test.
- **Bối cảnh:** ADR-101 chỉ ghép bàn bằng ảnh cắt thật của khách, nền vẫn do app vẽ. Người dùng muốn làm như editor: nền sau host và bàn
  sản phẩm trước host đều là lớp ảnh riêng trong OBS, host do app tạo đứng giữa, trên bàn của app không có gì.
- **Quyết định:**
  1. Cảnh mới `assets/scenes/obs_layers` (thư mục `assets/scenes` không vào git): `anh_shop` với ảnh phông xanh đặc, bàn trống,
     `max_slots` 1 nhưng không có sản phẩm, `cards` none. App chạy với `SCENE_DIR=assets/scenes/obs_layers` và `OUTPUT_MODE=obs`.
  2. Script độc lập `scripts/obs/photo_layers.py` (PIL, numpy, scipy.ndimage; scipy đã có sẵn qua vieneu → librosa, không cài thêm)
     xuất `layers/background.png` và `layers/desk_front.png` 1080×1920:
     - nền: ảnh shop đã xác nhận của cảnh `demo` (ADR-100), cắt phủ khung, **để nét** (recipe `background_blur_px`, mặc định 0;
       trước là mờ 9 px như app làm mờ ảnh shop do AI tạo, người dùng bỏ ngày 2026-11-28: "nền shop không cần làm mờ");
     - bàn: ảnh nguồn `layers/source/desk_photo.png` (cần `desk_photo.json` có `confirmed_by` và sha256, sửa file là bị từ chối), đặt mép
       sau mặt bàn đúng mép bàn của nhân vật (`desk_top` 0.78, y 1484 trên khung OBS). Sản phẩm tách bằng độ nét cục bộ và độ bão hoà (phòng
       sau mờ, sản phẩm nét); bỏ thùng giữa của Gemini (chữ méo) và vá gỗ bằng các hàng gỗ sạch phía trước, ép lại theo phối cảnh;
     - thay vào giữa là ảnh cắt thật thùng 24 lon của khách (`hero`; bóng tiếp xúc bỏ ngày 2026-11-28, xem dưới) dùng hàm của `desk_overlay.py`;
     - cách cắt nằm trong recipe (`--write-recipe`, sửa tay ở `layers/recipe.json`); script báo lỗi nếu lớp bàn lấn vào dải nhãn AI trên cùng.
  3. Thứ tự nguồn OBS từ dưới lên: "Nền shop (ảnh)" (0,0) → "AI host" (Browser Source `/obs`, (0,24), bộ lọc Chroma Key xanh lá,
     similarity 490, smoothness 15, spill 40; đổi từ 460/40/60, xem khối "Sửa vệt đen viền tóc") → "Bàn sản phẩm (ảnh)" (0,0). Nguồn cũ "Bàn sản phẩm (ghép)" của ADR-101 ẩn, giữ file.
  4. **Ảnh sản phẩm do Gemini tạo chỉ dùng cho buổi demo qua Meet/YouTube bằng OBS, không bao giờ lên Shopee.** Điều này là ngoại lệ của
     ADR-100 mục 4 và ADR-101 mục 2, theo yêu cầu rõ của người dùng. Trước khi lên Shopee phải thay bằng ảnh chụp thật bàn hàng của khách.
- **Lý do:** ra đúng kiểu xếp lớp Photoshop mà người dùng muốn, ảnh Gemini có bàn hàng dày và ánh sáng đẹp hơn mọi cách ghép bằng code.
  Host, giọng và nhép miệng vẫn tạo theo thời gian thực; hai lớp ảnh là cảnh tĩnh, không phải video quay sẵn.
- **Đã kiểm tra (2026-11-28):** chụp cửa sổ OBS thật: nhãn "AI-GENERATED CONTENT" còn nguyên, không còn điểm ảnh xanh lá nào trong khung,
  tay host nằm trên bàn trống, sản phẩm đứng trước tay hai bên. `desk_overlay.py` sau khi tách hàm `draw_units` cho ra ảnh lệch tối đa
  1/255 so với file cũ (do ghép hai bước).
- **Giới hạn và rủi ro:** chữ trên lon Gemini vẫn méo ("…NGUYÊN BẢN") nhưng nhỏ trong khung; logo Coca-Cola là logo thương hiệu của chính
  sản phẩm khách bán (RISKS P14); dấu Gemini nằm ở góc ảnh ngoài phần dùng, không bị xoá. Lớp ảnh không đổi theo lời host (mất highlight
  009/013). Trang `/host` chia sẻ qua Meet không thấy các lớp này (cần OBS Virtual Camera, ADR-099). Phông xanh: host không được mặc đồ xanh lá.
- **Sửa viền sáng và bậc ở đỉnh khung (2026-11-28, người dùng: "AI host có line sáng bọc xung quanh", "góc trên đang bị lệch"):**
  - Nguyên nhân: app chỉnh ánh sáng ảnh shop (`_tone` gamma rồi `_match_light` lệch cân bằng trắng tối đa ±12) nên phông (0,177,64)
    thành xanh ngọc (0,219,217). Chroma Key xanh lá chỉ bỏ được một phần: cả nguồn host còn alpha ≈ 39 màu xám, thành bậc sáng ở y=24
    (mép trên Browser Source), và mép tóc còn điểm ảnh xanh ngọc, thành viền sáng.
  - Sửa: phông của cảnh `obs_layers` đổi thành xanh lá thuần (0,255,0); 0 và 255 là điểm cố định của gamma nên màu gần như giữ nguyên.
    Không sửa code app.
  - Chỉnh Chroma Key: trong khoảng cách CbCr của OBS, tóc tối và màu trung tính cách xanh lá ≈ 0,52, da ≈ 0,57. Vì vậy Spill cao (≥ 200)
    làm da xám đi mà không bỏ được viền. Chọn similarity 460, smoothness 40, spill 60: điểm ảnh mép pha xanh thành trong suốt, tóc và da
    vẫn đặc.
  - Đo bằng obs-websocket `GetSourceScreenshot`:
    - alpha nền của nguồn host = 0;
    - không còn bậc ở y=24;
    - điểm ảnh ngả xanh ở mép người giảm từ ≈ 4200 xuống ≈ 110;
    - độ bão hoà da giữ nguyên;
    - không thủng thân.
  - Nền để nét là ngoại lệ của FR-009a/ADR-100 mục 3, chỉ cho demo qua OBS: chữ và nhãn trên kệ (có nhãn giống bia của hãng khác) đọc
    được rõ hơn (RISKS P11). Ảnh này không bao giờ lên Shopee; trước Shopee phải đổi sang ảnh thật của shop hoặc làm mờ lại.
- **Sửa vệt đen viền tóc và phóng to thùng giữa (2026-11-28, người dùng: "vậy ảnh hiện tại thùng coca giữa phóng to lên gần sát
  tay host", "vệt đen xung quanh người host có làm cho nó không còn nữa được không"):**
  - Thùng 24 lon thật ở giữa: recipe `hero` đổi `feet` 1790 → 1815, `height` 250 → 330. Đỉnh thùng ở mép bàn (y ≈ 1485), ngay dưới
    tay host. Thùng hơi đè lên vỉ 6 chai bên trái, vì nó đứng trước.
  - Vệt đen: mép tóc trong khung của fork là điểm ảnh pha giữa tóc và phông xanh, như (31,74,16). Với 460/40/60, các điểm này chỉ trong
    suốt một nửa, rồi bị khử xanh thành xám đen. Đỉnh đầu còn vài chấm tóc rời.
  - Đo trên cùng một khung gốc (tắt Chroma Key, chụp nguồn), bằng bản numpy của shader `chroma_key_filter_v2` (YUV giới hạn):
    - màu trung tính (tóc, chữ nhãn AI) cách xanh lá ≈ 0,523, da ≥ 0,56; vì vậy similarity + smoothness phải ≤ ≈ 0,515;
    - chọn similarity 490, smoothness 15, spill 40: lượng xanh còn ở mép giảm từ 1,34 xuống 0,37, chấm rời từ 13 xuống 3;
    - độ bão hoà da giữ 0,98; nhãn "AI-GENERATED CONTENT" không đổi;
    - chỉ mất mép khe giữa tay và thân, chỗ chai nước đã che;
    - spill ≥ 70 làm da xám (độ bão hoà còn 0,67), nên loại.
  - Kiểm tra lại trong OBS thật bằng `GetSourceScreenshot`. Vẫn không sửa code app; làm sạch triệt để hơn cần co mặt nạ trong fork.
- **Mép cứng trong fork, bỏ bóng thùng, giữ nguyên chai (2026-11-28, người dùng: "vẫn còn vệt đen … fix hết giúp tôi", "chai coca
  chỗ này bị cắt một mảng nhỏ", "không cần đổ bóng chỗ thùng … nó như đang bay lên", "đặt thùng xuống bàn là được"):**
  - Nguyên nhân vệt đen còn lại: fork pha mép mềm của người (≈ 6 px, alpha 36→255) với phông xanh. Chroma Key cắt mép ấy giữa chừng
    (smoothness 15 gần như một ngưỡng), khử xanh thành xám đen, và nén màu 4:2:0 của video loang xanh thêm ≈ 2 px. Chỉnh Chroma Key
    không sửa hết được.
  - Sửa trong fork (`ailive_ext/background.py`, hợp đồng `specs/014-live-host-background/contracts/fork-protocol.md` §3): ảnh nền phẳng
    một màu (chênh từng kênh ≤ 2) là phông khoá màu. Khi đó mép người là mép cứng: điểm alpha ≥ 128 thêm 1 px viền lấy màu trung bình người
    đặc trong ô 9×9, còn lại là phông (đổi ở mục "Mép phải host bị nhoè" bên dưới). Ảnh nền thật (Meet) vẫn pha mép mềm. Test fork: 334 qua.
  - Đo bằng bản numpy của shader: sai số mép trung bình giảm từ 23,9 xuống ≈ 10 với 490/15/40. Trong OBS thật hết viền xám đen ở má,
    cằm, tóc và cổ áo; mép hơi răng cưa vì khung fork 480 px phóng lên 1080.
  - Thử Chroma Key 440/50/50 và 470/30/30: mép mượt hơn chút nhưng viền cam cổ áo lốm đốm tối, nên giữ 490/15/40.
  - Lớp bàn (`scripts/obs/photo_layers.py`): vùng bỏ thùng Gemini lấn vào mép trái chai Zero Sugar đầu tiên (thùng hết ở x ≈ 1095, chai
    bắt đầu ở x ≈ 1101 trong ảnh nguồn). Đổi mép phải `remove` và `remove_on_table` từ 1104/1106 về 1097. Thùng 24 lon thật không còn
    bóng đổ và phản chiếu (recipe `hero_shadow: null`; `draw_units(..., ground=False)`). Recipe có `hero_shadow` thì vẽ lại như cũ.
- **Mép phải host bị nhoè (2026-11-28, người dùng khi đang quay: "stop, bên phải host đang bị nhòe"):**
  - Nguyên nhân: dải mép mềm của mặt nạ bên phải host (má, tai, cổ) rộng 5–9 px. Bản mép cứng trên giữ mọi điểm alpha ≥ 128 rồi tô cả
    dải bằng trung bình người đặc ô 9×9, nên má/tai/cổ thành một mảng màu bệt, còn vệt xám xanh ở tai và chỗ cổ giáp cổ áo. Không phải
    lệch khung–mặt nạ: khung quay khớp khung nguồn và mặt nạ của nó.
  - Sửa (fork-protocol §3): ngưỡng giữ 128 → **200**, điểm được giữ **giữ màu thật**, chỉ 1 px viền ngoài lấy trung bình các điểm được giữ
    trong ô 3×3. Bỏ ô 9×9 và điểm người đặc gần nhất.
  - So bằng mô phỏng (phóng 2,25×, shader Chroma Key 490/15/40, lớp nền shop thật) ở khung 23 và 61: hết vệt xám, mép hàm mượt hơn, tai
    giữ chi tiết. Đã thử trừ màu phòng theo alpha (ngưỡng 128/160/200, kẹp ±30/40): tai và cổ áo ửng đỏ, viền tím, nên loại.
- **Bỏ Chroma Key, fork ghép host lên ảnh shop thật (2026-11-28, người dùng: "vệt phân giải quanh host không chỉnh tốt lên được à?",
  "bên trái host"):**
  - Nguyên nhân còn lại: khung fork 480×832 bị OBS phóng 2,25×, nên mép cứng sau Chroma Key thành bậc thang to, cộng viền tối ở hai bên.
    Chỉnh ngưỡng key không hết được vì mép bị cắt trước khi phóng.
  - Sửa (fork-protocol §3): với ảnh nền thật, fork pha mép bằng alpha kéo hẹp `clip((a − 120) · 255 / 110, 0, 255)` (≤ 120 là nền,
    ≥ 230 là người). Cảnh mới `assets/scenes/obs_layers_soft/` (không vào git): ảnh nền là `layers/background.png` cắt đúng vùng
    host trong khung OBS (0,24 → 1080,1896), `background.as_is: true` để gửi ảnh nguyên, không làm mờ, không chỉnh sáng (ngoại lệ
    FR-009a, luôn có cảnh báo `background_as_is`, không dùng cho Shopee). Tắt filter "Chroma Key" của nguồn "AI host" trong OBS.
  - Thử trên khung gốc (A hiện tại / B mép mềm gốc / B2 mép mềm hẹp): B2 hết bậc thang và viền tối ở cả hai bên. Ảnh nền app chuẩn
    (mờ 4 px, sáng theo phòng cũ) làm nền bạc màu và nhoè, nên dùng `as_is`.
  - Kiểm bằng ảnh chụp OBS thật: mép tóc, má, vai trái và phải mượt, không còn viền tối; dải 24 px trên cùng không có mối nối (chênh
    giữa hàng 23 và 24 ≈ 2,0, bằng chênh giữa hai hàng liền nhau bất kỳ); nhãn AI vẫn hiện. Đổi lại phần nền trong vùng host chỉ nét bằng
    khung fork phóng lên. Test fork 335 qua, test app 3620 qua.
- **Hoàn tác:** đóng OBS rồi trả `%APPDATA%\obs-studio\basic\scenes\AI_Live.json` từ `AI_Live.json.bak-adr102`; chạy app lại với
  `SCENE_DIR=assets/scenes/demo`. Chỉ hoàn tác bước bỏ Chroma Key: bật lại filter "Chroma Key" của "AI host" và chạy app với
  `SCENE_DIR=assets/scenes/obs_layers`.
