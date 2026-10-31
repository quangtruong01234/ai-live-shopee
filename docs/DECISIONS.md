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
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt
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
- **Ngày:** 2026-10-30 · **Trạng thái:** Đã chốt nhà cung cấp (người dùng quyết định); model cụ thể: Đề xuất (spec 001, research R5)
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
- **Ngày:** 2026-10-31 · **Trạng thái:** Đã chốt (người dùng yêu cầu). Thay một phần ADR-008.
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
    ghi ADR chọn model (ADR-004).
  - Laptop vừa chạy app, TTS vừa chạy lip-sync, nên có thể nóng máy và giật. Chạy thử 30 phút để xem.
  - Các điều kiện cũ vẫn áp dụng: văn bản đồng ý của người mẫu trước khi dùng ảnh và giọng; kiểm tra license LiveTalking và Wav2Lip
    (RISKS L1, L2); tải model hoặc thêm dependency cần ADR.
- **Phương án đã loại:** Thuê RunPod ngay (tốn tiền khi chưa có khách đồng ý); chờ mua GPU (vốn lớn).

## ADR-024: Hai nguồn giọng miễn phí: VieNeu-TTS (CPU, trên laptop) và Gemini TTS (free tier)
- **Ngày:** 2026-10-31 · **Trạng thái:** Đề xuất (spec 003, plan và research R1, R2, R7). Chờ người dùng duyệt dependency và việc tải model.
  Bổ sung ADR-006.
- **Quyết định:**
  - `TTS_PROVIDER` nhận `fake | vieneu | gemini`. Bỏ `elevenlabs` và `oss` khỏi cấu hình vì chưa có adapter. ElevenLabs vẫn là ứng viên
    trong `docs/VENDORS.md`.
  - `vieneu`: gói pip `vieneu` (Apache-2.0), model VieNeu-TTS v3 Turbo, backend ONNX trên **CPU** để không tranh 4 GB VRAM với lip-sync
    (ADR-023). Giọng nữ miền Nam có sẵn, không clone. **Dependency mới**, kéo theo `onnxruntime`, `numpy`. Model tải vào cache ngoài repo.
  - `gemini`: model Gemini TTS (mặc định `gemini-3.8-flash-tts`) qua SDK `google-genai` và `GEMINI_API_KEY` đã có (ADR-018).
    Không thêm dependency. Chỉ gửi chữ cần đọc.
  - Protocol `TTSEngine` thêm `async def warm_up()` để nạp model trước phiên.
  - Nguồn mặc định: chọn sau khi so sánh theo SC-006 của spec 003, ghi bổ sung vào ADR này.
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
- **TODO:** Dung lượng model VieNeu? Tốc độ CPU thật trên laptop? Giới hạn free tier Gemini TTS (xem AI Studio)?

## ADR-025: Tiếng TTS là PCM16 mono 16 kHz; chuẩn hóa chữ tự viết trước mọi nguồn giọng
- **Ngày:** 2026-10-31 · **Trạng thái:** Đề xuất (spec 003, research R3, R4, R5)
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
