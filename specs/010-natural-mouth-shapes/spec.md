# Đặc tả tính năng: Khẩu hình miệng host AI giống người thật khi nói tiếng Việt

- **Feature ID:** `010-natural-mouth-shapes` · **Branch:** `main` · **Ngày tạo:** 2026-11-13
- **Trạng thái:** In progress <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1b
- **Mô tả gốc:** "010-natural-mouth-shapes: Khẩu hình miệng host AI giống người thật khi nói tiếng Việt (độ mở, độ tròn/dẹt theo nguyên
  âm, răng/môi rõ, khớp tiếng). Người dùng yêu cầu 2026-11-13, cho phép cài tool/repo cần thiết (mỗi thứ mới ghi ADR), vẫn realtime
  trên GTX 1650 Ti 4 GB (ADR-023), có đo khách quan và gói duyệt bằng mắt người."

## Bối cảnh

Feature 005 đã cho host nhép miệng realtime trên laptop (khoảng 25 khung/giây, miệng khớp tiếng ở mức "nhìn được"). Người dùng thấy khẩu
hình chưa giống người thật nói tiếng Việt: miệng chủ yếu đóng/mở, ít thay đổi hình dáng giữa các âm, có lúc mở chỉ khoảng một nửa (ghi
nhận ở 005 quickstart bước 8, nhất là ở đoạn clip nói đầu nghiêng), răng và môi chưa rõ. Feature này nâng chất lượng khẩu hình, đo được
bằng số và bằng mắt người, mà vẫn sinh miệng realtime trên laptop.

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Host nói với khẩu hình giống người hơn trong show (Ưu tiên: P1)

Mình mở phiên ở chế độ nhân vật nhép miệng như 005. Khi host nói, miệng mở rộng ở nguyên âm mở (a, á), tròn lại ở nguyên âm tròn (o, ô,
u), dẹt ra ở nguyên âm dẹt (i, e, ê), khép môi ở phụ âm môi (m, b, p), khép khi im lặng; răng và môi nhìn rõ, vùng miệng hòa vào mặt
không lộ đường viền. Người xem thấy giống người thật đang nói hơn bản 005.

**Vì sao ưu tiên này:** đây chính là điều người dùng cần cho buổi demo; khẩu hình máy móc làm khách mất niềm tin vào host AI.

**Kiểm thử độc lập:** chạy show kịch bản 10 phút ở chế độ nhép miệng với cách tạo miệng mới; chạy bộ đo (US2) trên cùng các câu; mở
bản ghi so sánh cạnh bản 005; đo số khung hình mỗi giây và khoảng lặng giữa câu.

**Kịch bản chấp nhận:**
1. **Given** phiên ở chế độ nhép miệng với cách tạo miệng mới, **When** host nói một câu có "a", "ô", "i" và "m/b/p", **Then** miệng
   mở rộng ở "a", tròn ở "ô", dẹt ở "i", khép môi ở "m/b/p", đúng lúc nghe thấy âm đó.
2. **Given** host đang nói, **When** nhìn gần vùng miệng, **Then** răng và môi rõ, không mờ hơn hẳn phần mặt xung quanh, không có viền
   hay đổi màu quanh miệng.
3. **Given** show kịch bản chạy 10 phút, **When** xem bảng độ trễ, **Then** số khung hình mỗi giây và khoảng lặng giữa câu nằm trong
   giới hạn SC-005.
4. **Given** cách tạo miệng mới không nạp được hoặc hết bộ nhớ GPU, **When** mở phiên hoặc giữa show, **Then** phiên tự dùng cách tạo
   miệng cũ (005) hoặc về ảnh tĩnh như ADR-046, show không dừng, trang điều khiển báo rõ lý do.

---

### User Story 2: Bộ đo khẩu hình khách quan và so sánh các cách tạo miệng (Ưu tiên: P2)

Mình chạy một lệnh trên laptop: hệ thống đọc một bộ câu tiếng Việt cố định bằng giọng của host, cho từng cách tạo miệng tạo hình realtime,
rồi chấm điểm (khớp tiếng, khép môi ở phụ âm môi, khác biệt hình miệng giữa các nhóm nguyên âm, độ nét vùng miệng, khung hình mỗi giây, bộ
nhớ GPU) và xuất video đặt cạnh nhau để người xem so.

**Vì sao ưu tiên này:** không có số đo thì không chọn được cách tạo miệng tốt nhất, cũng không biết lần chỉnh sau tốt lên hay tệ đi.

**Kiểm thử độc lập:** chạy bộ đo với cách tạo miệng 005 hiện tại: ra bảng điểm cho từng câu, điểm tổng, và video so sánh; chạy lại lần
hai cho kết quả gần như nhau.

**Kịch bản chấp nhận:**
1. **Given** bộ câu mẫu và một cách tạo miệng, **When** chạy bộ đo, **Then** có bảng điểm từng câu và điểm tổng cho các chỉ số ở
   FR-006, kèm khung hình mỗi giây và bộ nhớ GPU lớn nhất.
2. **Given** hai cách tạo miệng, **When** chạy bộ đo cho cả hai, **Then** có video đặt cạnh nhau cùng tiếng và bảng so sánh, đánh dấu cách
   tốt hơn ở từng chỉ số.
3. **Given** cùng một cách tạo miệng, **When** chạy bộ đo hai lần, **Then** điểm tổng lệch nhau không quá 5%.
4. **Given** bộ đo đã chạy, **When** tạo gói xem mù, **Then** có các cặp đoạn A/B xáo thứ tự để người xem chọn mà không biết bản nào mới.

---

### User Story 3: Clip nói chỉ dùng đoạn mặt nhìn thẳng (Ưu tiên: P3)

Đoạn clip nói có đầu ngửa hoặc nghiêng làm miệng dán vào bị méo hoặc chỉ mở một nửa. Host chỉ dùng các đoạn mặt nhìn thẳng (hoặc nghiêng
nhẹ trong ngưỡng) khi nói, nên khẩu hình ở mọi câu đều đầy đủ.

**Vì sao ưu tiên này:** sửa được phần lỗi lớn nhất đã thấy ở 005, nhưng chỉ có giá trị đầy đủ khi cách tạo miệng (US1) đã tốt.

**Kiểm thử độc lập:** quét các clip nói, xem danh sách đoạn bị loại vì đầu nghiêng; chạy show 10 phút và kiểm không có khung nói nào nằm
trong đoạn bị loại.

**Kịch bản chấp nhận:**
1. **Given** clip nói có đoạn đầu nghiêng quá ngưỡng, **When** chuẩn bị nhân vật, **Then** đoạn đó được đánh dấu không dùng khi nói và
   có báo cáo khung nào bị loại, vì sao.
2. **Given** show đang chạy, **When** host nói, **Then** mọi khung nói lấy từ đoạn mặt nhìn thẳng, chuyển đoạn không giật (giữ tiêu chí
   SC-007 của 005).
3. **Given** sau khi loại, phần clip nói còn lại quá ngắn để xoay vòng không lặp lộ, **When** chuẩn bị nhân vật, **Then** báo cho người
   vận hành, không tự tạo lại clip.

### Trường hợp biên

- Nói nhanh, nhiều âm tiết liền nhau (đọc giá "hai trăm năm mươi chín nghìn đồng"): miệng phải theo kịp, không đứng ở một hình.
- Im lặng giữa câu hoặc ngắt hơi: miệng khép, không rung lặt vặt.
- Âm môi cuối từ ("cơm", "đẹp"): môi khép ngắn rồi mở lại đúng lúc.
- Bộ nhớ GPU gần đầy (4 GB) giữa show: không treo máy, chuyển về cách cũ hoặc ảnh tĩnh (US1 kịch bản 4).
- Máy chậm, không kịp mỗi khung: giảm chất lượng có kiểm soát (ví dụ suy luận mỗi khung thứ hai như 005) thay vì để tiếng đi trước hình.
- Đổi clip giữa một từ: hình miệng liền mạch, không nhảy.
- Ánh sáng/màu da khác nhau giữa các clip: vùng miệng vẫn khớp màu với mặt.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

- **FR-001**: Hệ thống PHẢI sinh hình miệng theo tiếng nói **ngay khi phát** cho từng khung hình; không dựng trước video hay khung miệng
  cho câu, kể cả câu kịch bản đã biết trước (Điều I).
- **FR-002**: Hình miệng PHẢI thay đổi theo âm tiếng Việt: mở rộng ở nguyên âm mở, tròn ở nguyên âm tròn, dẹt ở nguyên âm dẹt, khép môi ở
  phụ âm môi, khép khi im lặng; mức đạt được đo bằng FR-006 và giới hạn ở SC-002, SC-003.
- **FR-003**: Vùng miệng PHẢI rõ răng và môi, hòa vào mặt (không viền, không lệch màu, không nhòe hơn hẳn mặt xung quanh).
- **FR-004**: Người vận hành PHẢI chọn được cách tạo miệng bằng cấu hình; cách của 005 vẫn dùng được và là phương án dự phòng.
- **FR-005**: Khi cách tạo miệng đang chọn không nạp được, hết bộ nhớ GPU hay lỗi giữa show, hệ thống PHẢI tự dùng cách dự phòng (hoặc về
  ảnh tĩnh theo ADR-046), ghi log, báo trên trang điều khiển; show không dừng.
- **FR-006**: Bộ đo PHẢI chấm, cho mỗi câu của bộ câu mẫu và cho tổng: (a) độ khớp tiếng–miệng tự động; (b) tỷ lệ khép môi ở phụ âm
  môi; (c) độ khác biệt hình miệng giữa nhóm nguyên âm mở / tròn / dẹt; (d) độ mở miệng theo độ to của tiếng; (e) độ nét vùng miệng so
  với mặt; (f) khung hình mỗi giây, thời gian tới khung đầu, bộ nhớ GPU lớn nhất.
- **FR-007**: Bộ câu mẫu PHẢI cố định, có ít nhất 20 câu tiếng Việt phủ mọi nhóm nguyên âm, các phụ âm môi, số và giá, đọc bằng giọng
  TTS đang dùng cho host; mỗi lần đo dùng cùng tiếng để so được.
- **FR-008**: Bộ đo PHẢI xuất video đặt cạnh nhau (cùng tiếng) và gói xem mù A/B xáo thứ tự cho người xem chấm.
- **FR-009**: Kết quả đo PHẢI lưu lại kèm tên cách tạo miệng, cấu hình và ngày giờ, để so lần sau; không đưa ảnh/video nhân vật vào git.
- **FR-010**: Bảng độ trễ (005) PHẢI ghi cách tạo miệng của từng lượt cùng các số đo render hiện có.
- **FR-011**: Khi chuẩn bị nhân vật, hệ thống PHẢI đánh dấu các đoạn clip nói có đầu nghiêng/ngửa quá ngưỡng là không dùng khi nói, báo
  cáo khung bị loại, và cảnh báo khi phần còn lại quá ngắn (US3).
- **FR-012**: Mỗi công cụ, mã nguồn hay model mới dùng cho feature này PHẢI có ADR (nguồn, license, dung lượng, chạy offline được
  không) trước khi cài; trọng số model không vào git; license ghi vào danh sách rủi ro trước khi thương mại.
- **FR-013**: Nhãn "AI" và watermark license yêu cầu PHẢI vẫn nằm trên cùng khung hình, không bị phần miệng hay hậu xử lý che hay làm mờ
  (Điều I, ADR-044).
- **FR-014**: Nếu cần tinh chỉnh model trên video của chính nhân vật, việc đó PHẢI chạy ở chỗ không tốn tiền (máy laptop hoặc GPU cloud
  miễn phí theo ADR-036) và chỉ dùng clip của nhân vật thuộc khách đó; trọng số tinh chỉnh gắn với nhân vật đó, không dùng cho khách khác.

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): miệng sinh realtime theo từng khung (FR-001); nhãn và watermark trên cùng
  (FR-013); model tinh chỉnh trên nhân vật nào chỉ dùng cho nhân vật đó (FR-014).
- [x] Điều II (đồng ý / bảo mật): chỉ dùng clip của nhân vật đã có đồng ý (hoặc nhân vật AI của khách, ADR-036); ảnh/video nhân vật và
  trọng số ngoài git (FR-009, FR-012).
- [x] Điều VI (độ trễ): không làm khung đầu chậm thêm quá 0,3 s, không làm khoảng lặng p95 tăng quá 0,1 s so với 005 (SC-005); đo bằng
  mốc `utterance_id` hiện có.
- [x] Điều VII (đơn giản): mỗi phụ thuộc/model mới cần ADR và người dùng duyệt (người dùng đã cho phép trước 2026-11-13, ghi trong ADR).

### Thực thể chính

- **Cách tạo miệng**: tên, model và cấu hình đi kèm, có phải dự phòng không; một phiên dùng đúng một cách tại một thời điểm.
- **Bộ câu mẫu**: danh sách câu tiếng Việt, nhóm âm mỗi câu phủ, file tiếng đã đọc sẵn bằng giọng host (chỉ là đầu vào đo, không phát
  ra live).
- **Lần đo**: cách tạo miệng, cấu hình, ngày giờ, điểm từng câu và điểm tổng theo FR-006, video so sánh.
- **Đoạn clip nói dùng được**: clip, khoảng khung, lý do loại các khung còn lại.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Trên bộ câu mẫu, điểm khớp tiếng–miệng tự động của cách mới không thấp hơn cách 005, và ít nhất 2 trong 4 chỉ số hình miệng
  (khép môi, khác biệt nguyên âm, độ mở theo tiếng, độ nét) tốt hơn cách 005 ít nhất 15%.
- **SC-002**: Ở ít nhất 80% vị trí phụ âm môi (b, m, p đầu âm tiết; p, m cuối âm tiết) trong bộ câu mẫu, môi khép (độ mở dưới ngưỡng im lặng của chính nhân vật đó).
- **SC-003**: Độ mở trung bình ở nguyên âm mở lớn hơn ở nguyên âm khép ít nhất 1,5 lần, và tỷ lệ rộng/cao miệng ở nguyên âm dẹt lớn hơn ở
  nguyên âm tròn ít nhất 1,2 lần.
- **SC-004**: Trong gói xem mù (ít nhất 3 cặp đoạn 20 giây), ít nhất 2/3 người xem chọn bản mới là "giống người thật nói hơn", và người
  dùng xác nhận bằng mắt.
- **SC-005**: Show kịch bản 10 phút trên laptop dev với cách mới: khung hình mỗi giây trung vị ≥ 20 (cách nào không đạt trên
  laptop thì không làm mặc định, xem Làm rõ), khung đầu chậm thêm ≤ 0,3 s, khoảng lặng p95 tăng ≤ 0,1 s so với 005; show 30 phút không hết bộ nhớ
  GPU, không lỗi.
- **SC-006**: Không có khung nói nào lấy từ đoạn clip bị loại vì đầu nghiêng trong show 10 phút (US3).
- **SC-007**: Chạy bộ đo hai lần cùng cấu hình, điểm tổng lệch nhau ≤ 5%.

## Giả định

- Nhân vật là `demo_host_01` (clip tạo bằng AI theo ADR-036); khi có người mẫu thật thì đo lại bằng bộ đo này.
- Người dùng đã cho phép cài công cụ, mã nguồn, model cần thiết (2026-11-13); vẫn ghi ADR cho từng thứ, không dùng dịch vụ tốn tiền,
  không bật RunPod nếu chưa hỏi (CLAUDE.md).
- Người xem mù dùng chung 3 người với 005 T068 nếu được; người dùng là người duyệt cuối.
- Ngưỡng "đầu nghiêng" lấy theo góc đầu đo được, chốt ở plan sau khi xem phân bố góc trong các clip hiện có.
- Ngưỡng 15% / 1,5 lần / 1,2 lần / 80% là mức khởi đầu; plan đo cách 005 trước, nếu cách 005 đã gần ngưỡng thì nâng ngưỡng, ghi vào
  phần Làm rõ.
- Biểu cảm, nháy mắt, cử động đầu giữ như 005; feature này chỉ đổi vùng miệng (và chọn đoạn clip ở US3).

## Ngoài phạm vi

- Biểu cảm khuôn mặt, ánh mắt, cử động đầu, cử chỉ tay.
- Huấn luyện model nhép miệng mới từ đầu (chỉ được tinh chỉnh model có sẵn theo FR-014).
- Tạo lại clip nền hay clip nói (nếu US3 cho thấy cần làm lại clip thì là việc riêng, báo người dùng).
- Đổi giọng hay TTS; đổi bố cục cảnh (009).
- Chạy trên GPU thuê (tốn tiền); cách cần GPU mạnh hơn chỉ được ghi lại số đo để người dùng quyết sau.

## Làm rõ

### Phiên 2026-11-13

> Tự chọn khuyến nghị theo ủy quyền "làm liên tục" của người dùng (2026-11-13 05:44); người dùng xem lại trong gói duyệt cuối.

- Q: Nếu cách cho khẩu hình tốt nhất chỉ đạt dưới 20 khung/giây trên laptop thì sao? → A: Không hạ ngưỡng và không dùng GPU thuê.
  Mặc định là cách tốt nhất **đạt ngưỡng 20 khung/giây** trên laptop (có thể kèm suy luận cách khung như 005); cách tốt hơn nhưng chậm
  hơn vẫn được đo và ghi số để người dùng quyết (ví dụ khi có GPU mạnh hơn). Nếu không cách mới nào đạt SC-001 trong ngưỡng tốc độ thì
  giữ cách 005 và báo rõ.
- Q: "ph" có tính là phụ âm môi (SC-002) không? → A: Không. "ph" tiếng Việt đọc là /f/ (răng chạm môi dưới), môi không khép; chỉ tính
  b, m, p đầu âm tiết và p, m cuối âm tiết (research R2). Sửa US1 và SC-002.

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại)
