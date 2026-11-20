# Đặc tả tính năng: Host AI nhép miệng bằng model riêng của nhân vật (Ultralight) trong show live

- **Feature ID:** `011-ultralight-live-lipsync` · **Branch:** `main` · **Ngày tạo:** 2026-11-19
- **Trạng thái:** In progress <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1b (mục "Khẩu hình giống người")
- **Mô tả gốc:** "011: Dùng Ultralight (model nhép miệng huấn luyện riêng cho nhân vật demo_host_02, thầy MuseTalk cho dev /
  InfiniteTalk cho prod, ADR-060/064) làm phương pháp nhép miệng trong show live realtime trên laptop, thay hoặc bên cạnh Wav2Lip;
  chọn bằng biến môi trường, so sánh chất lượng và tốc độ, giữ nhãn AI và các ràng buộc realtime"

## Bối cảnh

- Cách nhép miệng hiện tại (Wav2Lip, nhân vật `demo_host_01`) chạy ổn nhưng khẩu hình chưa giống người: spec 010 đã thử mọi cách chỉnh
  sau mà không đạt SC-001 của 010.
- Hướng đang thử (ADR-060, ADR-064): huấn luyện một model nhỏ **riêng cho nhân vật mới `demo_host_02`**, học khẩu hình từ video
  "thầy" tạo bằng AI. Có hai thầy: MuseTalk (dev, đã có video, model đang huấn luyện trên Kaggle) và InfiniteTalk (prod, miệng đẹp
  hơn nhưng cần GPU thuê để làm video đủ dài).
- Công cụ cài model lên laptop và bộ đo so sánh của 010 đã có. Còn thiếu: dùng model này **trong show live thật** và có số liệu để
  quyết định có đổi cấu hình demo hay không.
- ADR-062: buổi demo giữ Wav2Lip cho tới khi Ultralight đạt ngưỡng ở ADR-060 mục 5 và còn kịp tổng duyệt 30 phút. Feature này chính
  là "feature mới" mà ADR-060 mục 5 và ADR-062 nhắc tới.

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Chạy show kịch bản bằng model riêng của nhân vật (Ưu tiên: P1)

Người vận hành chọn nhân vật `demo_host_02` với cách nhép miệng "model riêng" bằng một thiết lập, bật hệ thống và chạy show kịch bản
như thường lệ. Host nói tiếng Việt, miệng do model riêng sinh ra theo thời gian thực trên laptop, có nhãn AI trong khung, cảnh live
vẫn hiện thẻ sản phẩm. Khi không thiết lập gì, hệ thống chạy đúng như hôm nay (Wav2Lip, nhân vật hiện tại).

**Vì sao ưu tiên này:** chưa chạy được trong show thật thì không có gì để so sánh hay quyết định. Đây là phần nhỏ nhất xem được bằng mắt.

**Kiểm thử độc lập:** cài model dev (thầy MuseTalk) lên laptop, chọn cách nhép miệng "model riêng", chạy show kịch bản 10 phút với
nội dung demo; xem trang host và bản ghi tự kiểm.

**Kịch bản chấp nhận:**
1. **Given** model riêng của `demo_host_02` đã cài, **When** người vận hành chọn cách nhép miệng "model riêng" rồi bật show,
   **Then** host nói từng câu kịch bản, miệng mở/khép theo tiếng, mọi khung hình đều có nhãn AI.
2. **Given** show đang chạy bằng model riêng, **When** giữa hai câu host im lặng, **Then** host vẫn chuyển động nhẹ, miệng khép, hình
   không đứng hay nhảy.
3. **Given** không thiết lập cách nhép miệng, **When** bật hệ thống, **Then** dùng Wav2Lip với nhân vật hiện tại, kết quả như trước
   feature này.
4. **Given** ảnh nền của `demo_host_02` đã có bàn, **When** bật cảnh live, **Then** cảnh không vẽ thêm lớp bàn đè lên, thẻ sản phẩm và
   nhãn AI vẫn hiện, không che mặt host.

---

### User Story 2: So sánh model riêng với Wav2Lip để quyết định (Ưu tiên: P2)

Người dùng muốn biết model riêng có thật sự tốt hơn không trước khi đổi cấu hình demo. Hệ thống đo hai cách nhép miệng trên **cùng
nhân vật, cùng bộ câu, cùng máy**: chỉ số hình miệng, độ khớp hình–tiếng, tốc độ khung hình, bộ nhớ GPU, độ trễ show; tạo một gói xem
mù để người thật chấm; rồi ghi kết luận đạt/không đạt theo ngưỡng đã chốt ở ADR-060 mục 5.

**Vì sao ưu tiên này:** model dev học từ thầy miệng mở ít (ADR-064), nên chỉ chạy được (US1) chưa đủ để đổi cấu hình demo.

**Kiểm thử độc lập:** chạy lệnh so sánh trên model đã cài; nhận một báo cáo có đủ chỉ số của hai cách và một gói xem mù.

**Kịch bản chấp nhận:**
1. **Given** model riêng đã cài, **When** chạy so sánh, **Then** báo cáo có đủ các chỉ số của cả hai cách, cùng bộ câu, và dòng kết
   luận đạt/không đạt theo từng ngưỡng.
2. **Given** báo cáo đã có, **When** chạy lại cùng đầu vào, **Then** các chỉ số hình miệng ra cùng giá trị (sai khác chỉ do đo thời gian).
3. **Given** báo cáo đã có, **When** người dùng mở gói xem mù, **Then** thấy các cặp video có tiếng không ghi tên cách làm và phiếu chấm.

---

### User Story 3: Đổi model dev / prod và chặn model sai trước khi lên show (Ưu tiên: P3)

Khi có model prod, người vận hành đổi từ model dev (thầy MuseTalk) sang model prod (thầy InfiniteTalk) chỉ bằng một thiết lập, không
sửa code. Kiểm tra trước demo cho biết đang dùng cách nhép miệng nào, model của thầy nào, và chặn nếu model thiếu, hỏng hoặc thuộc
nhân vật khác.

**Vì sao ưu tiên này:** ADR-064 đã chọn hai thầy. Buổi demo dùng model dev nếu đạt (ADR-066), nhưng đường đổi sang prod phải
sẵn và không được nhầm model.

**Kiểm thử độc lập:** cài model dev; đặt thiết lập sang thầy prod chưa cài và chạy kiểm tra trước demo; rồi đặt lại thầy dev.

**Kịch bản chấp nhận:**
1. **Given** chỉ có model dev, **When** chọn thầy prod và chạy kiểm tra trước demo, **Then** kiểm tra báo lỗi bằng tiếng Việt, nói rõ
   thiếu model nào và cách cài, show không bắt đầu bằng model sai.
2. **Given** đã cài cả hai model, **When** đổi thiết lập thầy và bật lại, **Then** show dùng model mới, trang điều khiển và bản ghi phiên
   ghi đúng cách nhép miệng và thầy đang dùng.
3. **Given** model trên máy được huấn luyện cho nhân vật khác nhân vật đang chọn, **When** bật hệ thống, **Then** hệ thống từ chối chạy
   và báo lỗi, không tự đổi sang model khác.

### Trường hợp biên

- Model riêng chạy không kịp thời gian thực trên laptop (máy nóng, chạy pin): hệ thống báo chậm như đang làm với Wav2Lip (canh show 007);
  không tự đổi sang Wav2Lip giữa show, vì đổi model giữa chừng làm host đổi khẩu hình đột ngột.
- Model riêng hoặc bộ khung hình của nhân vật bị xóa/hỏng sau khi đã kiểm tra: lần bật tiếp theo báo lỗi rõ ràng, không treo.
- Fork nhép miệng tắt giữa show: hệ thống nối lại như 005 đang làm với Wav2Lip.
- Câu rất dài hoặc tiếng có đoạn im lặng giữa câu: miệng khép trong đoạn im.
- Câu có nhiều số (giá, dung tích): khẩu hình vẫn theo tiếng (bộ câu v2 của 010 có nhóm số).
- Người vận hành chọn "model riêng" cho nhân vật chưa có model (ví dụ `demo_host_01`): kiểm tra trước demo báo lỗi.
- Đổi thiết lập khi show đang chạy: chỉ có hiệu lực sau khi bật lại.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

- **FR-001**: Người vận hành PHẢI chọn được cách nhép miệng (Wav2Lip hoặc model riêng của nhân vật) bằng một thiết lập cấu hình, không
  sửa code.
- **FR-002**: Khi không thiết lập, hệ thống PHẢI dùng Wav2Lip với nhân vật hiện tại, giữ nguyên hành vi trước feature này (ADR-062).
- **FR-003**: Với cách nhép miệng "model riêng", hệ thống PHẢI sinh hình miệng theo thời gian thực từ tiếng TTS của từng câu, không phát
  video đã dựng sẵn (Hiến pháp Điều I).
- **FR-004**: Mọi khung hình ra trang host và trang OBS PHẢI có nhãn AI giống cách hiện tại (chữ mặc định theo ADR-065), dù dùng cách
  nhép miệng nào.
- **FR-005**: Khi host không nói, hình PHẢI chuyển động nhẹ với miệng khép, không đứng hình, không nhảy hình ở chỗ nối vòng khung.
- **FR-006**: Người vận hành PHẢI chọn được model của thầy nào (dev hoặc prod) bằng một thiết lập; hai model cài song song, không ghi đè
  nhau (ADR-064).
- **FR-007**: Kiểm tra trước demo PHẢI báo lỗi (không chỉ cảnh báo) khi cách nhép miệng là "model riêng" mà model của nhân vật và thầy
  đã chọn bị thiếu, không khớp bằng chứng cài đặt, hoặc thuộc nhân vật khác; thông báo bằng tiếng Việt nói rõ cách sửa.
- **FR-008**: Hệ thống PHẢI từ chối chạy model riêng của một nhân vật cho nhân vật khác (Hiến pháp Điều I, một host một tài khoản).
- **FR-009**: Trang điều khiển, kết quả kiểm tra trước demo và bản ghi phiên PHẢI ghi cách nhép miệng, nhân vật và thầy đang dùng.
- **FR-010**: Các mốc đo độ trễ hiện có (câu đầu, khung hình đầu, khoảng lặng giữa câu, tốc độ khung hình) PHẢI có cho cả hai cách
  nhép miệng, để so sánh được.
- **FR-011**: Cảnh live (009) PHẢI hỗ trợ nhân vật có sẵn bàn trong ảnh nền: không vẽ lớp bàn, vẫn vẽ thẻ sản phẩm, nhãn AI và vùng
  làm nổi sản phẩm, không che mặt host.
- **FR-012**: Hệ thống PHẢI có lệnh so sánh hai cách nhép miệng trên cùng nhân vật, cùng bộ câu, cùng máy, cho ra báo cáo gồm chỉ số
  hình miệng, độ khớp hình–tiếng, tốc độ khung hình, bộ nhớ GPU đỉnh và dòng kết luận theo ngưỡng ADR-060 mục 5.
- **FR-013**: Luồng so sánh PHẢI có gói xem mù (cặp video có tiếng, không ghi tên cách làm, kèm phiếu chấm) như gói của 010; báo cáo
  so sánh chỉ ra đường dẫn gói (sửa 2026-11-19 sau analyze: gói do bộ đo khẩu hình tạo, không phải do lệnh so sánh).
- **FR-014**: Hệ thống KHÔNG ĐƯỢC tự đổi cách nhép miệng giữa show; khi model riêng chạy chậm hoặc lỗi thì báo qua canh show (007).
- **FR-015**: Đổi cấu hình demo mặc định sang model riêng CHỈ ĐƯỢC làm khi kết quả US2 đạt ngưỡng và người dùng đồng ý, có ADR ghi lại
  (ADR-062). Việc đánh giá này làm ngay khi model dev từ Kaggle xong (sửa 2026-11-19, ADR-066 mục 2); nếu đạt, buổi demo dùng model dev (thầy MuseTalk), không
  bắt buộc model prod (ADR-066).
- **FR-016**: Nhân vật `demo_host_02` PHẢI gắn với đúng một khách và một tài khoản như mọi nhân vật khác (Hiến pháp Điều I, CLAUDE.md
  ràng buộc 3). `demo_host_02` là host của khách demo hiện tại (khách duy nhất); khi đạt, nó thay `demo_host_01`. Trên một tài khoản
  chỉ một trong hai nhân vật lên live (ADR-066).

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): mọi khung hình miệng sinh khi show chạy, video thầy chỉ là dữ liệu huấn luyện,
  không bao giờ phát ra; nhãn AI ở mọi khung với mọi cách nhép miệng; model riêng chỉ chạy cho đúng nhân vật của nó, nhân vật gắn
  một khách (FR-016). Nhân vật mặt AI, không giống người thật hay người nổi tiếng, trông rõ là người trưởng thành (ràng buộc 8, RISKS P14).
- [x] Điều II (đồng ý / bảo mật): `demo_host_02` là gương mặt AI và giọng VieNeu sẵn có, không có người mẫu nên không cần văn bản đồng ý
  (ADR-060). Model, khung hình nhân vật, video thầy là file ngoài git.
- [x] Điều IV (adapter trước): cách nhép miệng mới là một lựa chọn chọn bằng cấu hình, không đổi luồng chính của show.
- [x] Điều V (test trước): logic chọn cách nhép miệng, kiểm tra trước demo và từ chối model sai phải có test chạy không cần GPU.
- [x] Điều VI (độ trễ): show kịch bản câu đầu ≤ 5 giây; khoảng lặng giữa câu p95 ≤ 1,5 giây là mục tiêu chung; feature này không được
  làm khoảng lặng tệ hơn Wav2Lip đo cùng máy, cùng kịch bản (SC-002).
- [x] Điều VIII (quan sát được): cách nhép miệng, nhân vật, thầy ghi trong bản ghi phiên và bảng độ trễ (FR-009, FR-010).

### Thực thể chính

- **Cách nhép miệng**: Wav2Lip (mặc định) hoặc model riêng của nhân vật. Chọn một lần lúc bật hệ thống.
- **Model riêng của nhân vật**: thuộc đúng một nhân vật, học từ đúng một thầy (dev MuseTalk / prod InfiniteTalk); có bằng chứng cài đặt
  (nguồn gốc, mã kiểm tra file, nhân vật, thầy) và bộ khung hình nền dựng từ video thầy.
- **Nhân vật**: gương mặt + giọng của host, gắn một khách; có thể có sẵn bàn trong ảnh nền.
- **Báo cáo so sánh**: các chỉ số của hai cách trên cùng nhân vật, bộ câu, máy; kết luận theo từng ngưỡng; gói xem mù kèm theo.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Show kịch bản 10 phút bằng model riêng trên laptop dev: 0 lỗi dừng show, tốc độ khung hình đưa ra màn hình p50 ≥ 20 khung/giây
  (không phải tốc độ suy luận của model; sửa 2026-11-19 sau analyze), bộ nhớ
  GPU đỉnh ≤ 3,5 GB (ngưỡng ADR-060 mục 5).
- **SC-002**: Trong cùng show đó: câu đầu ≤ 5 giây; khoảng lặng giữa câu p95 không lớn hơn số của Wav2Lip đo cùng máy, cùng kịch bản
  quá 10%.
- **SC-003**: 100% trong ≥ 10 ảnh chụp trang host ở thời điểm ngẫu nhiên (lúc chờ và lúc nói) có nhãn AI; 0 ảnh có thẻ sản phẩm hay
  lớp cảnh che mặt host.
- **SC-004**: Báo cáo so sánh có đủ chỉ số của hai cách trên ≥ 27 câu (bộ câu v2 của 010) và chạy lại cho cùng giá trị chỉ số hình miệng.
  Kết luận ghi rõ đạt hay chưa đạt ngưỡng chất lượng ADR-060 mục 5 (≥ 2/4 chỉ số hình miệng tốt hơn 15%, độ khớp hình–tiếng không giảm);
  chưa đạt thì ghi số, không hạ ngưỡng.
- **SC-005**: Trong gói xem mù, ≥ 3 người chấm; ghi tỉ lệ chọn model riêng là tự nhiên hơn (mục tiêu: đa số).
- **SC-006**: Đổi giữa Wav2Lip ↔ model riêng, hoặc thầy dev ↔ prod, mất ≤ 2 phút: đổi một thiết lập, bật lại, không sửa code.
  Phần thầy dev ↔ prod chỉ đo được khi có model thầy prod (ADR-066); trước đó đo chiều Wav2Lip ↔ model riêng và kiểm việc chặn
  thầy chưa cài (sửa 2026-11-19 sau analyze).
- **SC-007**: Kiểm tra trước demo bắt được 100% các trường hợp sai đã liệt kê (model thiếu, sai bằng chứng, sai nhân vật, thầy chưa cài)
  trong bộ test, và không báo lỗi nhầm với cấu hình đúng.
- **SC-008**: Cấu hình demo mặc định (Wav2Lip, `demo_host_01`) không đổi hành vi: toàn bộ test hiện có đạt, show 2 phút cho kết quả như
  trước feature.

## Giả định

- Model dùng để làm và kiểm feature là model dev (thầy MuseTalk) đang huấn luyện trên Kaggle; model prod chưa có, nên đường đổi sang prod
  được kiểm bằng test và bằng trường hợp "chưa cài" (US3 #1). Làm video thầy prod cần GPU thuê, nằm ngoài feature này và phải hỏi giá.
- Ngưỡng quyết định lấy nguyên từ ADR-060 mục 5 (người dùng đã duyệt); bộ đo, bộ câu v2 và cách làm gói xem mù dùng lại của 010.
- Hình nền của model riêng là vòng khung hình ngắn dựng từ video thầy (chạy tới rồi lùi), không dùng thư viện clip chờ/nói nhiều clip của
  005. Lúc im lặng, hình là các khung gốc của vòng này (miệng khép, vì đầu video thầy là đoạn im lặng).
- Laptop dev (GTX 1650 Ti 4 GB) là máy đo; số trên máy chạy live thật có thể khác.
- Giọng vẫn là VieNeu như hiện tại; không đổi tốc độ nói (ADR-064 mục 5).
- Kết quả chấm xem mù cần người thật; Claude chuẩn bị gói, người dùng tìm người chấm.

## Ngoài phạm vi

- Huấn luyện model, làm video thầy (notebook Kaggle đã có; video thầy prod cần GPU thuê).
- Thư viện nhiều clip chờ/nói, xoay vòng clip, loại đoạn đầu nghiêng (005/010) cho model riêng.
- Dùng model riêng cho `demo_host_01` hoặc nhân vật khác.
- Đổi mặc định khi chưa đạt ngưỡng hoặc chưa có đồng ý của người dùng.
- Chạy trên GPU thuê (RunPod) và chạy trên Shopee.
- Kiểm license mã Ultralight và trọng số liên quan (theo dõi ở RISKS, phải xong trước M2).

## Làm rõ

<!-- /sdd.clarify writes here. One subsection per session. -->

### Phiên 2026-11-19

- Q: Nếu model dev (thầy MuseTalk) đạt ngưỡng, có dùng nó cho buổi demo được không, hay bắt buộc model prod (thầy InfiniteTalk, cần GPU
  thuê)? → A: Đánh giá sau khi project làm xong hết; nếu ổn thì buổi demo dùng model thầy MuseTalk. Ghi vào FR-015, ADR-066.
  **Sửa 2026-11-19 (sau plan):** người dùng muốn xong sớm, demo luôn chạy trên laptop, miễn phí, share qua Meet → đánh giá ngay khi
  model Kaggle xong ("ok run đi"). FR-015 và ADR-066 mục 2 đã sửa theo.
- Q: `demo_host_02` dành cho khách demo hiện tại hay khách khác? → A: Dùng cho một khách, lấy `demo_host_02` (nhân vật mới nhất) cho
  khách demo hiện tại. Ghi vào FR-016, ADR-066.

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại)
