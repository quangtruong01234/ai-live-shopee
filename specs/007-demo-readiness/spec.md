# Đặc tả tính năng: Sẵn sàng cho buổi demo

- **Feature ID:** `007-demo-readiness` · **Branch:** `main` · **Ngày tạo:** 2026-11-13
- **Trạng thái:** In progress (2026-11-13) <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1d (Tổng duyệt và demo)
- **Mô tả gốc:** "007-demo-readiness: Chạy liên tục 30 phút, watchdog cơ bản, runbook, video dự phòng" (bảng "Đề xuất chưa tạo",
  `progress/FEATURES.md`). Người dùng 2026-11-13: "Tiếp tục feature mới mà không đụng đến LLM API Free."

## Bối cảnh

Các khâu của buổi demo đã chạy được (004 kịch bản, 005 nhép miệng, 008 chuỗi model, 009 cảnh, 010 khẩu hình). Thứ còn thiếu để qua M1
là **độ tin cậy trong đúng một buổi**: biết trước khi lên sóng là mọi thứ đã sẵn sàng, biết ngay khi show trục trặc, chứng minh được
phiên tổng duyệt 30 phút đạt tiêu chí PRD §3 (tiêu chí 3, 4), và có video dự phòng 2–3 phút (tiêu chí 5). Bản nháp quy trình đã có
ở `docs/RUNBOOK.md`; feature này biến các bước kiểm bằng tay trong đó thành bước máy kiểm được, và bổ sung phần còn thiếu.

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Kiểm tra sẵn sàng trước khi lên sóng (Ưu tiên: P1)

Một giờ trước buổi demo, người vận hành bật fork và app như runbook, rồi mở mục "Kiểm tra trước demo" (trên trang điều khiển, hoặc chạy
một lệnh). Hệ thống tự kiểm từng mục, mỗi mục ghi **Đạt / Cảnh báo / Lỗi** kèm một câu tiếng Việt nói phải làm gì. Cuối danh sách là
kết luận chung "Sẵn sàng" hay "Chưa sẵn sàng". Mục máy không kiểm được (văn bản đồng ý đã ký, Meet đã thử từ máy khác) được liệt kê
riêng thành "Việc tự xác nhận".

**Vì sao ưu tiên này:** phần lớn sự cố trong buổi demo đến từ cấu hình sai hoặc một thành phần chưa bật (tab host chưa mở, `.env` còn
giá trị thử, ảnh mẫu chưa thay, thiếu video dự phòng). Phát hiện trước khi chia sẻ màn hình rẻ hơn nhiều so với xử lý trước mặt khách.

**Kiểm thử độc lập:** chạy kiểm tra trong ba trạng thái: cấu hình giống ngày demo (kết luận "Sẵn sàng"), cấu hình còn giá trị thử
(`fake`, chế độ dev, bật ghi luồng) và thiếu thành phần (fork tắt, chưa mở tab host). Mỗi trạng thái cho đúng danh sách mục Lỗi/Cảnh
báo. Kiểm được hoàn toàn không cần GPU và không gọi dịch vụ LLM.

**Kịch bản chấp nhận:**
1. **Given** fork chạy, tab host đã mở và đã bấm "Bắt đầu", cấu hình đúng như runbook §6, có video dự phòng, **When** chạy kiểm tra,
   **Then** mọi mục máy kiểm đều Đạt và kết luận là "Sẵn sàng".
2. **Given** cấu hình còn bộ trả lời giả, chế độ dev hoặc đang bật ghi luồng, **When** chạy kiểm tra, **Then** mỗi giá trị đó là một
   mục Lỗi nêu đúng biến cần sửa và giá trị nên dùng, kết luận "Chưa sẵn sàng".
3. **Given** fork chưa bật hoặc tab host chưa mở, **When** chạy kiểm tra, **Then** mục tương ứng là Lỗi kèm việc cần làm (bật fork theo
   runbook bước 2; mở `/host` và bấm "Bắt đầu").
4. **Given** bộ cảnh còn ảnh mẫu, hoặc nội dung sản phẩm có lỗi kiểm tra, **When** chạy kiểm tra, **Then** mục đó là Lỗi và nêu sản phẩm
   hay ảnh nào.
5. **Given** máy đang chạy pin hoặc ổ đĩa còn ít chỗ, **When** chạy kiểm tra, **Then** mục đó là Cảnh báo (vẫn có thể "Sẵn sàng" nếu
   không có Lỗi), nêu lý do.
6. **Given** bất kỳ trạng thái nào, **When** chạy kiểm tra, **Then** không có yêu cầu nào tới dịch vụ LLM và không có tiếng hay hình
   nào phát tới người xem.

---

### User Story 2: Canh show khi đang chạy (Ưu tiên: P2)

Trong lúc show chạy, hệ thống tự canh các dấu hiệu khách sẽ thấy ngay: host im lặng quá lâu, hình đứng, mất tiếng ở tab host, fork mất
kết nối, show tự rơi vào chế độ dự phòng. Khi có dấu hiệu, trang điều khiển hiện cảnh báo nổi bật kèm việc nên làm theo runbook §4,
và hệ thống tự gỡ những chỗ kẹt có cách gỡ an toàn. Mọi cảnh báo được ghi vào log phiên.

**Vì sao ưu tiên này:** người vận hành vừa nói chuyện với khách vừa canh máy; nếu chỉ nhìn bằng mắt thì một câu kẹt 10–20 giây dễ bị
bỏ sót. PRD tiêu chí 3 không cho khoảng lặng nào quá 5 giây.

**Kiểm thử độc lập:** chạy show bằng bộ trả lời giả và tiếng giả, giả lập từng lỗi (bước tạo tiếng treo, hình ngừng cập nhật, tab host
đóng, fork tắt). Mỗi lỗi sinh đúng một cảnh báo trong ngưỡng thời gian, được ghi log, tự hết khi lỗi hết. Không cần GPU, không gọi LLM.

**Kịch bản chấp nhận:**
1. **Given** show đang chạy, không tạm dừng, **When** không có câu nào bắt đầu phát trong quá 5 giây, **Then** trang điều khiển hiện
   cảnh báo "host im lặng" kèm số giây, và log phiên có một bản ghi cảnh báo.
2. **Given** cảnh báo "host im lặng" đang hiện, **When** khoảng im lặng kéo tới ngưỡng tự gỡ, **Then** hệ thống tự bỏ câu đang kẹt một
   lần (như bấm "Bỏ qua câu đang nói") và ghi lại việc đã làm. Ngưỡng tự gỡ mặc định 15 giây (Làm rõ 2026-11-13).
3. **Given** show đang chạy, **When** người vận hành bấm "Tạm dừng", **Then** không có cảnh báo im lặng nào trong lúc tạm dừng.
4. **Given** đang dùng nhân vật nhép miệng, **When** hình trên tab host không đổi trong quá 3 giây, **Then** có cảnh báo "hình đứng"
   kèm việc nên làm.
5. **Given** host đang nói, **When** tab host không báo đã phát tiếng cho câu đó trong thời gian câu đáng lẽ đã phát xong, **Then** có
   cảnh báo "có thể mất tiếng ở tab host" kèm gợi ý bấm "Bắt đầu" trên `/host` hoặc kiểm chia sẻ âm thanh của Meet.
6. **Given** một cảnh báo đang hiện, **When** dấu hiệu hết (câu kế tiếp phát, hình chạy lại, fork nối lại), **Then** cảnh báo tự tắt và
   log ghi thời điểm hết cùng tổng thời gian.
7. **Given** show không chạy, **When** máy ở trạng thái chờ, **Then** không có cảnh báo im lặng (chỉ canh khi có show).

---

### User Story 3: Báo cáo phiên tổng duyệt 30 phút (Ưu tiên: P3)

Sau khi chạy một show tổng duyệt, người vận hành mở báo cáo của show đó và thấy ngay show đạt hay không đạt PRD tiêu chí 3 và 4: thời
lượng, kết thúc bình thường hay bị gián đoạn, khoảng lặng p95 và lớn nhất, số câu lỗi tiếng/hình, số lần và tổng thời gian của từng
loại cảnh báo (US2), thời gian chạy chế độ dự phòng và ảnh tĩnh, tốc độ hình. Báo cáo được lưu cạnh log của phiên.

**Vì sao ưu tiên này:** ROADMAP M1d cần "phiên chạy liên tục 30 phút không lỗi (ghi lại log)". Hiện số liệu nằm rải ở nhiều file log;
mỗi lần tổng duyệt phải tự đối chiếu bằng tay.

**Kiểm thử độc lập:** dựng log của một show giả (đạt, và các kiểu không đạt) rồi xuất báo cáo; mỗi kiểu cho đúng kết luận. Đo thật:
một show 30 phút bằng bộ trả lời giả trên GPU laptop (không gọi LLM) cho báo cáo đầy đủ.

**Kịch bản chấp nhận:**
1. **Given** một show chạy đủ 30 phút, kết thúc bằng nút "Kết thúc", khoảng lặng p95 ≤ 1,5 giây, không khoảng nào quá 5 giây, không
   cảnh báo hình đứng / mất tiếng, **When** xuất báo cáo, **Then** kết luận "Đạt" cho cả tiêu chí 3 và 4.
2. **Given** một show ngắn hơn 30 phút, **When** xuất báo cáo, **Then** tiêu chí 4 là "Chưa đủ thời lượng", không phải "Đạt".
3. **Given** một show có một khoảng lặng 7 giây, **When** xuất báo cáo, **Then** tiêu chí 3 "Không đạt" và báo cáo chỉ ra thời điểm và
   câu liền trước khoảng lặng đó.
4. **Given** show có đoạn tạm dừng hoặc lỗi giả lập, **When** xuất báo cáo, **Then** các đoạn đó không tính vào khoảng lặng (như PRD §3).
5. **Given** show chạy bằng bộ trả lời giả, **When** xuất báo cáo, **Then** báo cáo ghi rõ "chạy với bộ trả lời giả, chưa phải tổng
   duyệt thật" và không đánh dấu tiêu chí 2.
6. **Given** app bị tắt giữa show (sập), **When** xuất báo cáo từ log còn lại, **Then** tiêu chí 4 "Không đạt: show không kết thúc
   bình thường".

---

### User Story 4: Làm video dự phòng 2–3 phút (Ưu tiên: P4)

Người vận hành chạy một lệnh để làm video dự phòng: hệ thống chạy một show thật (hình, tiếng tạo realtime như live) trong khoảng 2–3
phút, ghi lại đúng khung hình và tiếng người xem thấy (có nhãn "AI", watermark, cảnh), rồi kiểm file: độ dài, có tiếng, có nhãn "AI".
File lưu ngoài git, tên ghi rõ là video dự phòng.

**Vì sao ưu tiên này:** PRD tiêu chí 5 bắt buộc có video dự phòng; hiện chưa có file và chưa có cách làm lặp lại được khi nhân vật,
sản phẩm hay cảnh thay đổi.

**Kiểm thử độc lập:** phần chạy show và kiểm file kiểm bằng nguồn hình/tiếng giả không cần GPU; một lần làm thật trên GPU laptop với
nhân vật mẫu cho file thật.

**Kịch bản chấp nhận:**
1. **Given** fork và app chạy, **When** chạy lệnh làm video dự phòng, **Then** sau khoảng 2–3 phút có một file video 120–180 giây, có
   tiếng, nhãn "AI" có trong mọi khung đã kiểm, kèm một tờ ghi nhân vật, sản phẩm, nguồn nội dung, ngày làm.
2. **Given** dịch vụ LLM không dùng được (hết hạn mức), **When** làm video dự phòng, **Then** video vẫn làm được với nội dung lấy nguyên
   văn từ phần giới thiệu và mô tả trong file sản phẩm (mặc định, Làm rõ 2026-11-13). Khi LLM dùng được, người vận hành có thể chọn
   làm bằng kịch bản LLM như show thật.
3. **Given** video làm xong, **When** kiểm tra trước demo (US1) chạy, **Then** mục "video dự phòng" Đạt; nếu file thiếu, ngắn hơn 2
   phút, dài hơn 3 phút hay không có tiếng thì là Lỗi.
4. **Given** mọi trạng thái, **When** dùng app, **Then** không có đường nào trong app phát video dự phòng ra luồng hình (video chỉ được
   người vận hành mở bằng trình phát riêng khi demo Meet/YouTube, runbook §5).

### Trường hợp biên

- Kiểm tra trước demo chạy lúc show đang chạy: chỉ đọc trạng thái, không làm gián đoạn show, không phát tiếng thử.
- Fork bật nhưng chưa nạp xong nhân vật: mục fork là Cảnh báo "đang khởi động", chạy lại sau vài giây.
- Không đọc được trạng thái nguồn điện hoặc ổ đĩa (máy khác hệ điều hành): mục đó là "Không kiểm được", không phải Lỗi.
- Cấu hình cố ý dùng ảnh tĩnh (`static`): các mục fork/hình đứng không áp dụng, không báo Lỗi.
- Nhiều dấu hiệu cùng lúc (fork mất kết nối kéo theo hình đứng): hiện một cảnh báo gốc (fork), không chồng nhiều cảnh báo cùng gốc.
- Câu rất dài: "host im lặng" chỉ tính khoảng giữa hai câu, không tính lúc câu đang phát.
- Show kết thúc giữa lúc cảnh báo đang hiện: cảnh báo đóng lại cùng show và ghi thời điểm.
- Tự bỏ câu kẹt không thành công (bước tạo tiếng vẫn treo): không lặp vô hạn; cảnh báo chuyển sang mức "cần người vận hành" và gợi ý
  video dự phòng theo runbook.
- Video dự phòng: nhân vật hoặc sản phẩm đổi sau khi làm video → kiểm tra trước demo cảnh báo video cũ (khác nhân vật/khách/bản nội
  dung đang nạp).
- Làm video dự phòng khi cấu hình nhân vật thuộc khách khác: từ chối như lúc khởi động app (ràng buộc 3).

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

**Kiểm tra trước demo (US1)**

- **FR-001**: Hệ thống PHẢI có một bước "kiểm tra trước demo" chạy được từ trang điều khiển và từ dòng lệnh, cho cùng kết quả.
- **FR-002**: Mỗi mục kiểm PHẢI có trạng thái Đạt / Cảnh báo / Lỗi / Không kiểm được, một câu tiếng Việt nêu lý do và việc cần làm;
  kết luận chung là "Sẵn sàng" khi không có mục Lỗi.
- **FR-003**: Các mục máy kiểm PHẢI gồm ít nhất: cấu hình đúng giá trị ngày demo (runbook §6: chế độ chạy, bộ trả lời, giọng, chế độ
  nhân vật, ghi luồng tắt); fork kết nối được và báo khỏe; nhân vật khớp khách; tab host đã mở và đã mở khóa âm thanh; nội dung sản
  phẩm đã nạp không lỗi; bộ cảnh không còn ảnh mẫu (khi bật cảnh); nhãn "AI" được bật; video dự phòng có mặt và hợp lệ; chuỗi model
  LLM đã cấu hình và trạng thái gần nhất đã biết; nguồn điện; chỗ trống ổ đĩa.
- **FR-004**: Kiểm tra trước demo KHÔNG ĐƯỢC gọi dịch vụ LLM, không phát tiếng hay hình tới người xem và không đổi trạng thái show.
- **FR-005**: Kết quả PHẢI kèm danh sách "Việc tự xác nhận" mà máy không kiểm được (văn bản đồng ý đã ký, đã thử Meet từ máy khác,
  không có RunPod đang bật), lấy theo runbook §2–§3.
- **FR-006**: Mỗi lần kiểm PHẢI được ghi vào log phiên (thời điểm, từng mục, kết luận).

**Canh show (US2)**

- **FR-007**: Khi show đang chạy và không tạm dừng, hệ thống PHẢI phát hiện: host im lặng quá 5 giây giữa hai câu; hình trên tab host
  không đổi quá 3 giây (khi dùng nhân vật nhép miệng); tab host không báo đã phát tiếng cho một câu; fork mất kết nối; tab host đóng;
  show chuyển sang chế độ dự phòng hoặc ảnh tĩnh.
- **FR-008**: Mỗi dấu hiệu PHẢI hiện thành cảnh báo trên trang điều khiển trong vòng 1 giây kể từ khi vượt ngưỡng, kèm việc nên làm
  lấy từ runbook §4, và tự tắt khi dấu hiệu hết.
- **FR-009**: Mỗi cảnh báo PHẢI được ghi vào log phiên với loại, thời điểm bắt đầu, thời điểm hết, show và câu liên quan.
- **FR-010**: Hệ thống PHẢI tự bỏ câu đang kẹt khi host im lặng tới ngưỡng tự gỡ, tối đa một lần cho mỗi khoảng im lặng; nếu vẫn kẹt
  thì nâng cảnh báo lên mức "cần người vận hành". Ngưỡng tự gỡ mặc định 15 giây.
- **FR-011**: Các ngưỡng (im lặng, hình đứng, tự gỡ) PHẢI đổi được bằng cấu hình mà không sửa code; mặc định theo PRD §3 (5 giây).
- **FR-012**: Canh show KHÔNG ĐƯỢC làm chậm show: khoảng lặng và câu đầu không tăng quá sai số đo so với khi tắt canh (đo theo
  SC-004, mốc so sánh là show 30 phút của 005 T073 chạy khi chưa có canh show).

**Báo cáo tổng duyệt (US3)**

- **FR-013**: Người vận hành PHẢI xuất được báo cáo của một show bất kỳ trong phiên, khi show đã kết thúc hoặc từ log còn lại sau khi
  app tắt đột ngột.
- **FR-014**: Báo cáo PHẢI nêu kết luận cho PRD tiêu chí 3 (khoảng lặng p95 ≤ 1,5 giây, không khoảng nào quá 5 giây, không tính lúc
  tạm dừng và lỗi giả lập) và tiêu chí 4 (≥ 30 phút, kết thúc bình thường, không hình đứng, không mất tiếng), kèm số liệu dẫn tới kết
  luận.
- **FR-015**: Báo cáo PHẢI liệt kê mọi khoảng lặng quá 5 giây và mọi cảnh báo (US2) theo thời điểm, cùng câu liền trước.
- **FR-016**: Báo cáo PHẢI ghi rõ điều kiện chạy (bộ trả lời thật hay giả, chế độ nhân vật, cách tạo miệng, nguồn điện nếu biết) để
  không nhầm một lần chạy thử với tổng duyệt thật.
- **FR-017**: Báo cáo PHẢI lưu thành file đọc được bằng mắt và file máy đọc được, cạnh log của phiên, ngoài git.

**Video dự phòng (US4)**

- **FR-018**: Hệ thống PHẢI có một lệnh làm video dự phòng bằng cách chạy show thật trong thời lượng đặt trước (mặc định 150 giây,
  trong khoảng 120–180) và ghi đúng hình, tiếng tab host phát ra.
- **FR-019**: Lệnh PHẢI kiểm file làm ra (độ dài trong 120–180 giây, có tiếng, nhãn "AI" có mặt ở các khung lấy mẫu) và ghi một tờ mô
  tả (nhân vật, khách, bản nội dung, nguồn nội dung, ngày làm, kết quả kiểm).
- **FR-020**: Video dự phòng PHẢI làm được khi dịch vụ LLM không dùng được: mặc định nội dung là nguyên văn phần giới thiệu và mô tả
  trong file sản phẩm, đọc lần lượt sản phẩm chính rồi sản phẩm phụ; người vận hành có thể chọn nguồn "kịch bản LLM" khi có hạn mức.
  Tờ mô tả ghi nguồn đã dùng.
- **FR-021**: App KHÔNG ĐƯỢC có đường phát video dự phòng ra luồng hình hay tab host (Hiến pháp Điều I). Video chỉ được lưu thành file
  để người vận hành mở bằng trình phát riêng khi demo ngoài Shopee.

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): video dự phòng được tạo bằng chính đường realtime rồi ghi lại, không dựng hậu
  kỳ; app không có đường phát video có sẵn ra luồng (FR-021); video chỉ dùng cho demo ngoài Shopee. Nhãn "AI" phải có trong video
  (FR-019) và kiểm tra trước demo báo Lỗi nếu nhãn bị tắt. Làm video bằng nhân vật thuộc khách khác bị từ chối.
- [x] Điều II (đồng ý / bảo mật): video dự phòng chứa mặt và giọng người mẫu, chỉ lưu trên máy demo, ngoài git; kiểm tra trước demo
  nhắc xác nhận văn bản đồng ý; log và báo cáo không ghi khóa hay bí mật (chỉ ghi biến có giá trị hay không).
- [x] Điều III (trả lời có căn cứ): không đổi cách sinh câu; video dự phòng mặc định đọc nguyên văn nội dung có sẵn trong file sản
  phẩm nên không thêm rủi ro bịa; nếu chọn kịch bản LLM thì đi qua đúng bộ chặn như show thật.
- [x] Điều VI (độ trễ): canh show chỉ quan sát, không nằm trên đường sinh câu; ngưỡng cảnh báo lấy đúng ngân sách (5 giây). FR-012.
- [x] Điều VIII (quan sát được): mọi lần kiểm, cảnh báo, tự gỡ đều có trong log phiên.

### Thực thể chính

- **Kết quả kiểm tra trước demo**: thời điểm, danh sách mục (mã mục, trạng thái, lời nhắn, việc cần làm), kết luận, danh sách việc tự
  xác nhận.
- **Cảnh báo canh show**: loại (im lặng, hình đứng, mất tiếng, fork mất, host đóng, chế độ dự phòng, ảnh tĩnh), mức (cảnh báo / cần
  người vận hành), bắt đầu, kết thúc, show, câu liên quan, việc hệ thống đã tự làm.
- **Báo cáo tổng duyệt**: show, điều kiện chạy, thời lượng, cách kết thúc, số liệu khoảng lặng, lỗi câu, cảnh báo, kết luận từng tiêu
  chí.
- **Video dự phòng**: file video, tờ mô tả đi kèm (nhân vật, khách, bản nội dung, nguồn nội dung, ngày làm, kết quả kiểm).

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Với 6 tình huống cấu hình/thành phần sai đặt trước (bộ trả lời giả, chế độ dev, ghi luồng bật, fork tắt, tab host chưa
  mở, cảnh còn ảnh mẫu), kiểm tra trước demo báo đúng 6/6 mục Lỗi, và cấu hình đúng cho "Sẵn sàng"; mỗi lần kiểm xong trong ≤ 5 giây.
- **SC-002**: Với các lỗi giả lập (bước tạo tiếng treo, hình ngừng, tab host đóng, fork tắt), mỗi lỗi có cảnh báo trong ≤ 1 giây sau
  ngưỡng, tự tắt ≤ 1 giây sau khi hết; show dài 10 phút không lỗi có 0 cảnh báo sai.
- **SC-003**: Khi bước tạo tiếng treo giữa show, khoảng im lặng người xem nghe thấy không vượt ngưỡng tự gỡ (15 giây) cộng 2 giây.
- **SC-004**: Show 30 phút bằng bộ trả lời giả trên GPU laptop với canh show bật: khoảng lặng p95 và câu đầu không tệ hơn số đo 005
  T073 quá 0,1 giây; báo cáo tổng duyệt xuất ra đầy đủ và kết luận khớp với đối chiếu bằng tay từ log.
- **SC-005**: Báo cáo của 5 bộ log mẫu (đạt, thiếu thời lượng, có khoảng lặng 7 giây, có đoạn tạm dừng dài, app tắt giữa chừng) cho
  đúng 5/5 kết luận.
- **SC-006**: Video dự phòng làm ra dài 120–180 giây, có tiếng, nhãn "AI" có ở 100% khung lấy mẫu, tiếng khớp miệng khi người vận hành
  xem lại (mắt người), và đã thử phát qua Meet có tiếng (người dùng làm).
- **SC-007**: Toàn bộ feature làm và kiểm được mà không có yêu cầu nào tới dịch vụ LLM free (đếm trong log chuỗi model: 0 lượt gọi).

## Giả định

- Ngưỡng hình đứng 3 giây: clip chờ và clip nói luôn chuyển động nhẹ, nên 3 giây hình không đổi là bất thường. Có thể chỉnh (FR-011).
- Phát hiện "hình đứng" và "mất tiếng" dựa vào tín hiệu tab host gửi về (khung đã hiện, tiếng đã phát), không phân tích hình ảnh.
- "Thời gian câu đáng lẽ đã phát" (kịch bản 5 của US2) khác nhau theo đường hình: ảnh tĩnh phát gần như ngay (3 giây), nhép miệng
  vốn bắt đầu câu sau khoảng 3 giây nên dùng 6 giây. Lý do: tổng duyệt 30 phút ngày 2026-11-13 (T054) có 2 cảnh báo mất tiếng báo sai,
  mỗi cái mở rồi tắt trong 3 ms vì câu được nghe sau 3,03 s và 3,16 s. Hai ngưỡng đều chỉnh được (FR-011).
- Trang điều khiển chỉ cảnh báo bằng hình (banner), không phát âm thanh, để không lẫn tiếng vào buổi demo.
- Ngưỡng chỗ trống ổ đĩa: Cảnh báo dưới 5 GB (log phiên, bản ghi tự kiểm và video dự phòng là thứ chiếm chỗ).
- Kiểm nguồn điện chỉ là Cảnh báo vì số đo đã có chạy pin vẫn đạt; runbook vẫn yêu cầu cắm sạc.
- "Trạng thái gần nhất" của chuỗi model lấy từ những gì app đã biết (lượt gọi trước, thời điểm hết hạn mức), không gọi thử.
- Phiên tổng duyệt thật (bộ trả lời thật, cắm sạc, ngày riêng) vẫn do người dùng chạy; feature cung cấp công cụ và một lần đo bằng bộ
  trả lời giả.
- Tự khởi động lại fork hoặc app khi chết thuộc M2 (chạy nhiều giờ), không thuộc feature này; ở đây chỉ cảnh báo và chỉ dẫn.
- Runbook (`docs/RUNBOOK.md`) được cập nhật theo feature này (mục kiểm tra trước demo, cảnh báo, cách làm video dự phòng).

## Ngoài phạm vi

- Tự khởi động lại fork/app, chạy nhiều giờ, cảnh báo qua điện thoại hay tin nhắn (M2).
- Phát video dự phòng từ trong app hay chuyển luồng sang video (cấm theo Điều I, FR-021).
- Phân tích hình ảnh để chấm khẩu hình hay chất lượng trong lúc live (đã có bộ đo 010 riêng).
- Chạy tổng duyệt thật với LLM thật và chấm tiêu chí 2 (người dùng, 004 T079).
- Đẩy RTMP lên YouTube (006).

## Làm rõ

<!-- /sdd.clarify writes here. One subsection per session. -->
### Phiên 2026-11-13

Tự chọn phương án khuyến nghị theo ủy quyền làm liên tục của người dùng (2026-11-13); người dùng xem lại trong gói duyệt cuối.

- Q: Host im lặng kẹt: chỉ cảnh báo, hay cảnh báo rồi tự bỏ câu kẹt? → A: Cảnh báo ở 5 giây, tự bỏ câu kẹt một lần ở 15 giây, vẫn
  kẹt thì nâng lên "cần người vận hành". Lý do: Hiến pháp Điều VIII (một lượt lỗi không được làm kẹt cả show); người vận hành đang nói
  chuyện với khách, khó phản ứng kịp; bỏ một câu ít hại hơn im lặng dài. Ngưỡng đổi được (FR-011).
- Q: Video dự phòng lấy nội dung từ đâu? → A: Mặc định đọc nguyên văn giới thiệu + mô tả trong file sản phẩm (không cần LLM, 0 rủi ro
  bịa, làm được ngay khi LLM free hết hạn mức); tùy chọn kịch bản LLM khi có hạn mức. Lý do: video dự phòng phải luôn làm được và an
  toàn khi trình chiếu cho khách; nội dung là chữ của chính khách.

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại)
