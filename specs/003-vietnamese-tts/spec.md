# Đặc tả tính năng: Giọng tiếng Việt thật cho AI host

- **Feature ID:** `003-vietnamese-tts` · **Branch:** `main` (ADR-027) · **Ngày tạo:** 2026-10-31
- **Trạng thái:** Done (2026-11-12) <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1a
- **Mô tả gốc:** "003-vietnamese-tts: Giọng tiếng Việt thật cho AI host qua adapter TTSEngine, streaming theo câu, chuẩn hóa số/giá/đơn vị
  trước khi đọc, cắm vào pipeline 001 thay FakeTTS. Làm song song với 005 (lip-sync cần giọng thật để kiểm tra khớp miệng).
  Laptop GTX 1650 Ti 4GB dùng chung với lip-sync (ADR-023). Ưu tiên phương án miễn phí (ADR-019)."

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Host trả lời bằng giọng tiếng Việt thật (Ưu tiên: P1)

Người vận hành mở phiên như feature 001 nhưng chọn giọng thật thay cho giọng giả. Gõ một comment; host đọc câu trả lời bằng giọng
tiếng Việt tự nhiên, rõ ràng. Câu đầu tiên bắt đầu phát ngay khi sẵn sàng, không đợi cả câu trả lời; các câu sau nối tiếp liền mạch.

**Vì sao ưu tiên này:** giọng giả chỉ là âm "bíp"; không có giọng thật thì không demo được cho khách và không kiểm tra được khớp miệng ở feature 005.

**Kiểm thử độc lập:** mở phiên với giọng thật, gõ vài comment, nghe câu trả lời và xem bảng độ trễ.

**Kịch bản chấp nhận:**
1. **Given** phiên mở với giọng thật, **When** gửi comment hỏi giá, **Then** host đọc câu trả lời bằng tiếng Việt có dấu, đúng thanh điệu,
   nghe hiểu được, phụ đề hiện cùng lúc câu được đọc.
2. **Given** câu trả lời có 3 câu, **When** host đọc, **Then** câu đầu bắt đầu phát trước khi câu cuối được tạo xong, và giữa các câu
   không có khoảng lặng bất thường.
3. **Given** phiên mở với giọng giả, **When** chạy như feature 001, **Then** mọi thứ hoạt động như cũ (giọng giả vẫn dùng cho test).

---

### User Story 2: Đọc đúng số, giá, đơn vị và viết tắt (Ưu tiên: P2)

Câu trả lời thường có giá ("259.000đ", "250k"), phần trăm ("giảm 15%"), dung tích, khối lượng, kích thước ("1,5L", "500ml", "2kg"),
size ("size M"), khoảng giá ("259.000đ–439.000đ") và viết tắt ("SP", "KM"). Trước khi đọc, hệ thống chuyển các dạng này thành chữ
đọc tự nhiên theo cách nói miền Nam, để host không đọc từng ký tự hay đọc sai giá.

**Vì sao ưu tiên này:** đọc sai giá là lỗi nặng nhất trong live bán hàng (RISKS Q2); nhưng cần US1 trước mới nghe được.

**Kiểm thử độc lập:** cho một bộ câu mẫu chứa số, giá, đơn vị qua bước chuyển chữ, so với cách đọc kỳ vọng; rồi nghe vài câu.

**Kịch bản chấp nhận:**
1. **Given** câu "Giá chỉ 259.000đ", **When** chuyển chữ, **Then** thành "Giá chỉ hai trăm năm mươi chín ngàn đồng".
2. **Given** câu "Combo 250k, giảm 15%", **When** chuyển chữ, **Then** thành "Combo hai trăm năm mươi ngàn, giảm mười lăm phần trăm".
3. **Given** câu có khoảng giá "259.000đ–439.000đ", **When** chuyển chữ, **Then** đọc "từ ... đến ..." chứ không đọc dấu gạch.
4. **Given** câu có "1,5L" hoặc "500ml", **When** chuyển chữ, **Then** đọc "một phẩy năm lít", "năm trăm mi li lít".
5. **Given** phụ đề của câu, **When** host đọc, **Then** phụ đề vẫn hiện dạng gốc dễ nhìn ("259.000đ"), chỉ tiếng đọc là dạng chữ.

---

### User Story 3: Thử giọng riêng lẻ, đổi giọng bằng cấu hình và chịu lỗi (Ưu tiên: P3)

Mình gõ một câu và nghe ngay giọng đọc, không cần mở phiên; lưu được đoạn tiếng đó trên laptop để làm đoạn tiếng mẫu cho feature 005.
Đổi giữa các nguồn giọng chỉ bằng cấu hình. Khi nguồn giọng lỗi, chậm hoặc hết hạn mức, lượt đó báo lỗi rõ, phiên không dừng.

**Vì sao ưu tiên này:** cần để chọn giọng, cung cấp tiếng mẫu cho nhân vật nhép miệng và giữ phiên ổn định; không cần cho lát cắt đầu.

**Kiểm thử độc lập:** gõ câu thử và nghe; đổi cấu hình rồi mở lại phiên; giả lập lỗi ở bước tạo tiếng.

**Kịch bản chấp nhận:**
1. **Given** không mở phiên, **When** gõ một câu thử, **Then** nghe được giọng đọc và lưu được đoạn tiếng thành file trên laptop.
2. **Given** nguồn giọng trả lỗi hoặc quá thời gian trong một lượt, **When** lượt đó chạy, **Then** lượt ghi lỗi ở bước tạo tiếng,
   trang điều khiển báo lỗi, comment sau vẫn được trả lời.
3. **Given** nguồn giọng báo hết hạn mức, **When** có lượt mới, **Then** trang điều khiển báo rõ "hết hạn mức giọng nói", không thử lại
   liên tục làm treo phiên.

### Trường hợp biên

- **Câu có từ tiếng Anh hoặc tên thương hiệu** ("serum", "Vitamin C"): đọc được, chấp nhận giọng Việt hóa; không bỏ qua từ.
- **Số rất lớn, số thập phân, số có dấu chấm ngăn cách nghìn** ("1.250.000đ", "0,5%"): đọc đúng giá trị; không nhầm dấu chấm ngăn cách nghìn
  với dấu thập phân (quy ước Việt Nam: chấm ngăn nghìn, phẩy thập phân).
- **Số điện thoại, mã sản phẩm, mã giảm giá** (dãy số dài, chữ lẫn số): đọc từng ký tự, không đọc thành số lớn.
- **Emoji, ký tự đặc biệt, link** (lọt qua bước lọc): không đọc ra tiếng.
- **Câu rất ngắn** ("Dạ.") và **câu rất dài**: đều đọc được; câu dài không làm tràn thời gian chờ của một câu.
- **Laptop vừa chạy giọng vừa chạy nhân vật nhép miệng** (feature 005): giọng có thể chậm hơn; ghi số liệu, không làm dừng phiên.
- **Bỏ qua lượt đang nói:** tiếng dừng ngay như feature 001, phần tiếng đang tạo dở bị hủy.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

**Giọng đọc**
- **FR-001**: Hệ thống PHẢI đọc câu trả lời bằng giọng tiếng Việt thật, đúng thanh điệu, theo từng câu ngay khi câu đó sẵn sàng.
- **FR-002**: Giọng dùng cho phiên là **một giọng có sẵn** của nguồn giọng, không phải giọng clone của người thật cụ thể (hợp với
  nhân vật gương mặt AI ở feature 005). Giọng được chọn bằng cấu hình và gắn với đúng một khách; không dùng cùng giọng cho khách khác.
  Với nguồn (a), giọng có thể kèm **một đoạn tiếng mẫu ngắn do chính giọng có sẵn đó đọc** (không phải tiếng người thật) để giữ chất
  giọng ổn định; đoạn mẫu chọn bằng cấu hình, nằm ngoài git, thiếu hoặc hỏng thì báo lỗi cấu hình chứ không đọc bằng giọng khác.
- **FR-003**: Hệ thống PHẢI có **hai nguồn giọng thật, đều miễn phí**, chọn bằng cấu hình: (a) một nguồn chạy ngay trên laptop
  (dùng chung card đồ họa 4 GB với nhân vật nhép miệng); (b) một dịch vụ bên ngoài ở gói miễn phí (có hạn mức ký tự, cần mạng).
  Với nguồn (b), chỉ gửi đúng phần chữ cần đọc, không gửi thêm thông tin phiên hay người xem. Nguồn mặc định là (a), nguồn (b) giữ
  làm dự phòng (người dùng chọn 2026-11-07, ADR-024); người dùng xác nhận lại 2026-11-09 sau khi đo (T049, research bảng kết quả).
- **FR-004**: Tiếng phải nối liền giữa các câu của cùng một lượt; câu đầu phát trước khi câu cuối được tạo xong.
- **FR-005**: Tiếng tạo ra PHẢI dùng được trực tiếp cho màn hình host ảnh tĩnh (feature 001) và nhân vật nhép miệng (feature 005),
  không cần chuyển đổi bằng tay.

**Chuyển chữ trước khi đọc**
- **FR-006**: Trước khi đọc, hệ thống PHẢI chuyển thành chữ: số nguyên, số thập phân, giá tiền ("đ", "đồng", "k", "VND"), khoảng giá,
  phần trăm, đơn vị đo phổ biến (ml, l, g, kg, cm, m), và danh sách viết tắt cố định có thể mở rộng.
- **FR-007**: Cách đọc PHẢI theo giọng miền Nam như cách xưng hô đã chốt ở feature 001 (ví dụ "ngàn" thay "nghìn").
- **FR-008**: Dãy số dài (số điện thoại, mã) PHẢI đọc từng chữ số; ký tự đặc biệt, emoji, link PHẢI bị bỏ khỏi phần đọc.
- **FR-009**: Phụ đề PHẢI giữ dạng chữ gốc; chỉ phần đọc dùng dạng đã chuyển.
- **FR-010**: Bước chuyển chữ PHẢI chạy và kiểm thử được riêng, không cần nguồn giọng.

**Vận hành và chịu lỗi**
- **FR-011**: Đổi giữa giọng giả và các nguồn giọng thật PHẢI chỉ cần sửa cấu hình, không sửa lõi pipeline.
- **FR-012**: Mình PHẢI thử được giọng bằng một câu gõ tay ngoài phiên và lưu được đoạn tiếng thành file trên laptop.
- **FR-013**: Lỗi, quá thời gian hoặc hết hạn mức ở bước tạo tiếng PHẢI làm lượt đó kết thúc với lỗi ở bước tạo tiếng, không dừng phiên;
  hết hạn mức PHẢI được báo rõ trên trang điều khiển và không thử lại liên tục.
- **FR-014**: Bỏ qua lượt đang nói PHẢI hủy cả phần tiếng đang tạo dở.
- **FR-015**: Mốc "chunk tiếng đầu tiên" của mỗi lượt PHẢI được ghi kèm mã lượt như feature 001; nếu nguồn giọng có hạn mức thì hệ thống
  PHẢI ghi số ký tự đã dùng trong phiên.
- **FR-016**: Khóa dịch vụ của nguồn giọng (nếu có) PHẢI chỉ đọc từ cấu hình bí mật, không ghi vào log.

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / 1 host 1 tài khoản): tiếng được tạo ngay lúc trả lời, không phát đoạn tiếng dựng sẵn trên nền tảng live.
  Đoạn tiếng lưu ở FR-012 chỉ dùng để thử trên laptop. Giọng có sẵn đã chọn gắn với đúng một khách (FR-002).
- [x] Điều II (đồng ý / bảo mật): dùng giọng có sẵn nên không clone giọng ai, không cần văn bản đồng ý về giọng. Nếu sau này đổi
  sang giọng clone thì bắt buộc văn bản đồng ý của người đọc mẫu; không bao giờ clone giọng người nổi tiếng.
  Khóa dịch vụ không vào log (FR-016). Mẫu giọng và tiếng ghi âm không đưa vào kho mã.
- [x] Điều III (trả lời có căn cứ): chuyển chữ không được đổi giá trị (giá, phần trăm, số lượng): US2 là ca kiểm thử bắt buộc.
- [x] Điều IV (adapter): mỗi nguồn giọng là một adapter, chọn bằng cấu hình (FR-011).
- [x] Điều V (test trước): chuyển chữ và chịu lỗi kiểm thử tự động không cần mạng hay khóa; ca gọi nguồn giọng thật tách riêng.
- [x] Điều VI (độ trễ): bước này có ngân sách 1,0 s đến chunk tiếng đầu tiên (p95) trong tổng < 5 giây.
- [x] Điều VIII (quan sát được, chịu lỗi): FR-013, FR-015.

### Thực thể chính

- **Nguồn giọng**: nơi tạo tiếng (giọng giả cho test, hoặc một nguồn giọng thật). Thuộc tính: tên, giọng được chọn, có hạn mức hay không,
  số ký tự đã dùng trong phiên.
- **Giọng của AI host**: giọng có sẵn được chọn cho một khách. Thuộc tính: nguồn giọng, tên giọng, khách sở hữu (đúng một).
- **Quy tắc chuyển chữ**: danh sách cách đọc số, tiền, đơn vị, viết tắt; mở rộng được khi gặp từ mới.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Bộ ít nhất 40 câu mẫu chứa giá, khoảng giá, phần trăm, đơn vị, viết tắt và dãy số: 100% được chuyển chữ đúng cách đọc kỳ vọng.
- **SC-002**: Nghe 10 câu trả lời mẫu, người vận hành đánh giá ít nhất 8/10 câu "nghe rõ, đúng dấu, không đọc sai số".
- **SC-003**: Khi chạy riêng (không có nhân vật nhép miệng cùng lúc), thời gian từ lúc có câu đầu tiên đến chunk tiếng đầu tiên ≤ 1,0 s (p95)
  trên ít nhất 20 lượt. Khi chạy cùng nhân vật nhép miệng: chỉ ghi số liệu, không đặt ngưỡng (ADR-023).
- **SC-004**: Lỗi giả lập ở bước tạo tiếng không làm dừng phiên: comment kế tiếp vẫn được trả lời trong 100% lần thử.
- **SC-006**: Cùng 10 câu trả lời mẫu được đọc bằng cả hai nguồn giọng (FR-003). Ghi cho mỗi nguồn: điểm nghe theo SC-002, thời gian
  đến chunk tiếng đầu tiên khi chạy riêng và khi chạy cùng nhân vật nhép miệng, số ký tự hạn mức đã dùng. Kết quả đủ để chốt ADR
  chọn nguồn mặc định.
- **SC-005**: Một phiên 30 phút có comment định kỳ với giọng thật chạy hết không bị dừng vì nguồn giọng (trừ khi hết hạn mức, khi đó
  trang điều khiển phải báo rõ).

## Giả định

- Dùng phương án miễn phí trước (ADR-019). Bất kỳ bước nào cần trả tiền (gói trả phí) phải báo người dùng kèm
  chi phí ước tính trước khi làm.
- Giọng nữ, giọng miền Nam, cho hợp với cách xưng hô "em" và từ ngữ miền Nam đã chốt ở feature 001. Đổi được bằng cấu hình.
- Bộ câu mẫu chuyển chữ (SC-001) do mình soạn từ file nội dung demo và các dạng thường gặp; khách không cần duyệt.
- Viết tắt ban đầu chỉ gồm vài dạng hay gặp trong live bán hàng; thêm dần khi gặp.
- Chuyển chữ áp dụng cho phần đọc của mọi câu host nói (trả lời, từ chối, câu đệm sau này).
- Chưa kiểm tra license thương mại của nguồn giọng (RISKS L6, L7): làm trước khi thu tiền khách, không chặn feature này.

## Ngoài phạm vi

- Nhân vật nhép miệng (feature 005), kịch bản khi rảnh (feature 004).
- Clone giọng người thật (để sau, khi khách đã đồng ý trả tiền và có người đọc mẫu ký đồng ý).
- Biểu cảm giọng theo nội dung (vui, nhấn mạnh), đổi giọng giữa phiên, nhiều giọng trong một phiên.
- Giọng các vùng miền khác, ngôn ngữ khác ngoài tiếng Việt.
- Tự động chọn nguồn giọng dự phòng khi nguồn chính lỗi (chỉ báo lỗi và bỏ lượt).

## Làm rõ

<!-- /sdd.clarify writes here. One subsection per session. -->
### Phiên 2026-10-31
- Q: Giọng của AI host là giọng có sẵn hay giọng clone người thật? → A: Giọng có sẵn của nguồn giọng (FR-002, Điều I, Điều II,
  Thực thể chính, Giả định, Ngoài phạm vi).
- Q: Nguồn giọng chạy trên laptop hay dịch vụ ngoài gói miễn phí? → A: Thử cả hai (đều miễn phí), so sánh rồi chốt nguồn mặc định
  bằng ADR (FR-003, SC-006).

### Phiên 2026-11-09 (lúc `/sdd.implement` T049)
- Q: Giọng có sẵn `Thục Đoan` đọc "nắng" thành "nứng"; giữ giọng có sẵn hay dùng đoạn mẫu? → A: Chọn `Thùy Dung`, kèm đoạn mẫu
  `D_ThuyDung_lan2` (một lần đọc của chính giọng `Thùy Dung`) làm chất giọng cố định; người dùng nghe 10 câu: ổn (FR-002).

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]`
