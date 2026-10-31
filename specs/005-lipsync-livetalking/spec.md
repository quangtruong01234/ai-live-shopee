# Đặc tả tính năng: AI host nhép miệng realtime trên laptop

- **Feature ID:** `005-lipsync-livetalking` · **Branch:** `005-lipsync-livetalking` (chưa tạo, chờ người dùng xác nhận, xem báo cáo) · **Ngày tạo:** 2026-10-31
- **Trạng thái:** Clarified <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1b (chạy tạm trên GPU laptop theo ADR-023)
- **Mô tả gốc:** "005-lipsync-livetalking: AI host nhép miệng realtime theo giọng TTS, chạy trên GPU laptop GTX 1650 Ti 4GB (ADR-023).
  Ưu tiên làm ra nhân vật nhìn thấy được và nhép miệng đúng trước; tốc độ/FPS/độ trễ bàn sau (chấp nhận chậm). Vẫn sinh realtime,
  có nhãn AI trong frame, là adapter AvatarRenderer mới cắm vào pipeline 001."

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Nhân vật hiện lên và nhép miệng theo một đoạn tiếng nói (Ưu tiên: P1)

Mình chuẩn bị nhân vật một lần từ tư liệu hình của một **gương mặt tạo bằng AI** (không phải người thật). Sau đó mở màn hình host trên laptop: nhân vật hiện lên,
góc hình có nhãn "AI". Mình đưa vào một đoạn tiếng nói tiếng Việt; nhân vật mở miệng nói theo đúng đoạn tiếng đó, hình được tạo ngay
lúc nói chứ không phải video dựng sẵn. Nói xong, nhân vật trở về trạng thái chờ.

**Vì sao ưu tiên này:** người dùng muốn "làm ra nhân vật trước". Đây là lát cắt nhỏ nhất cho thấy nhân vật thật sự nhép miệng,
không cần LLM, comment hay giọng thật.

**Kiểm thử độc lập:** chỉ cần nhân vật đã chuẩn bị, màn hình host và vài đoạn tiếng nói mẫu. Phát từng đoạn, nhìn miệng có khớp tiếng
không và nhãn "AI" có nằm trong hình không.

**Kịch bản chấp nhận:**
1. **Given** nhân vật đã chuẩn bị xong và màn hình host đang mở, **When** chưa có tiếng nói nào, **Then** nhân vật hiện ở trạng thái chờ,
   miệng khép, có nhãn "AI" trong hình.
2. **Given** màn hình host đang mở, **When** đưa vào một đoạn tiếng nói tiếng Việt khoảng 10 giây, **Then** nhân vật nhép miệng theo
   đoạn đó từ đầu đến cuối, người xem nghe tiếng và thấy miệng khớp nhau, không có lúc tiếng đi trước hình rõ rệt.
3. **Given** nhân vật đang nhép miệng, **When** đoạn tiếng kết thúc, **Then** nhân vật về trạng thái chờ, không bị đứng hình ở khung miệng mở.
4. **Given** tư liệu hình không có khuôn mặt rõ (che mặt, quay nghiêng, nhiều người), **When** chuẩn bị nhân vật, **Then** việc chuẩn bị
   bị từ chối kèm lý do, không tạo ra nhân vật hỏng.
5. **Given** tư liệu hình chưa có hồ sơ nguồn gốc (tạo bằng công cụ nào, ai tạo, điều khoản sử dụng, cam kết không cố ý giống người
   có thật), **When** chuẩn bị nhân vật, **Then** việc chuẩn bị bị từ chối.

---

### User Story 2: Nhân vật nhép miệng thay ảnh tĩnh trong pipeline trả lời comment (Ưu tiên: P2)

Mình chọn chế độ "nhân vật nhép miệng" thay cho "ảnh tĩnh" khi mở phiên. Mọi thứ của pipeline 001 giữ nguyên: gõ comment, host
trả lời đúng dữ liệu, phụ đề, hàng đợi, tạm dừng, bỏ qua. Khác biệt duy nhất là màn hình host giờ là nhân vật nhép miệng theo câu trả lời.

**Vì sao ưu tiên này:** biến nhân vật ở US1 thành AI host thật cho buổi demo; cần US1 trước.

**Kiểm thử độc lập:** mở phiên ở chế độ nhân vật nhép miệng, gõ vài comment, bấm bỏ qua khi host đang nói, xem màn hình host và trang điều khiển.

**Kịch bản chấp nhận:**
1. **Given** phiên mở ở chế độ nhân vật nhép miệng, **When** người vận hành gửi comment hỏi giá, **Then** nhân vật nói câu trả lời
   và nhép miệng theo từng câu, phụ đề hiện cùng lúc câu được nói.
2. **Given** nhân vật đang nói, **When** bấm bỏ qua lượt này, **Then** tiếng, miệng và phụ đề dừng, nhân vật về trạng thái chờ và
   hệ thống chuyển sang comment kế tiếp.
3. **Given** phần tạo hình nhép miệng bị lỗi hoặc không phản hồi trong một lượt, **When** lượt đó chạy, **Then** lượt được ghi lỗi ở bước
   tạo hình, trang điều khiển báo lỗi và comment sau vẫn được trả lời.
4. **Given** phiên mở ở chế độ ảnh tĩnh, **When** chạy như feature 001, **Then** mọi thứ hoạt động như cũ (chế độ mới không làm hỏng chế độ cũ).

---

### User Story 3: Đo tốc độ nhân vật trên laptop (Ưu tiên: P3)

Sau khi nhân vật chạy được, mình xem số liệu thật trên laptop: số khung hình mỗi giây, thời gian từ lúc có tiếng đến lúc miệng bắt
đầu cử động, độ trễ cả lượt, và máy có chịu được 30 phút không. Feature này chỉ đo và ghi lại; đặt mục tiêu tốc độ là việc bàn sau.

**Vì sao ưu tiên này:** người dùng chấp nhận chậm và muốn bàn tốc độ sau, nhưng cần số liệu thật để bàn.

**Kiểm thử độc lập:** chạy một phiên có nhiều lượt nói, mở bảng độ trễ và ghi số liệu.

**Kịch bản chấp nhận:**
1. **Given** phiên ở chế độ nhân vật nhép miệng đã có ít nhất 20 lượt trả lời, **When** mở bảng độ trễ, **Then** thấy độ trễ cả lượt và
   riêng bước tạo hình, cùng số khung hình mỗi giây thực tế.
2. **Given** phiên chạy liên tục 30 phút có comment định kỳ, **When** kết thúc, **Then** có ghi nhận máy có bị dừng, đứng hình, mất tiếng
   hay hết bộ nhớ đồ họa không.

### Trường hợp biên

- **Laptop tạo hình không kịp tốc độ của tiếng:** không được để tiếng chạy trước hình rồi hình đuổi theo. Hệ thống giảm số khung hình
  hoặc độ nét để giữ tiếng và miệng khớp nhau (FR-006). Tốc độ thấp được chấp nhận (ADR-023).
- **Hết bộ nhớ đồ họa hoặc phần tạo hình bị treo giữa phiên:** lượt đó ghi lỗi, phiên không dừng; trang điều khiển báo rõ để người vận hành
  khởi động lại phần tạo hình hoặc chuyển về chế độ ảnh tĩnh.
- **Đóng màn hình host giữa lúc nói:** như feature 001, lỗi "chưa mở màn hình host", mở lại thì chạy tiếp.
- **Đoạn tiếng toàn im lặng hoặc chỉ là âm báo của giọng giả:** miệng gần như khép; không coi là lỗi.
- **Câu rất dài (trên 30 giây tiếng):** nhân vật vẫn nhép miệng hết câu, không tràn bộ nhớ.
- **Hai lượt nối tiếp nhau sát nhau:** nhân vật không giật về trạng thái chờ giữa hai câu của cùng một lượt.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

**Chuẩn bị nhân vật**
- **FR-001**: Mình PHẢI chuẩn bị được một nhân vật từ tư liệu hình của một gương mặt tạo bằng AI (không phải người thật) bằng một
  thao tác, chạy trên laptop, trước phiên live.
- **FR-002**: Tư liệu hình đầu vào là **một ảnh chân dung** của gương mặt AI (đầu và vai, nhìn thẳng, mặt rõ). Mọi khung hình
  của nhân vật được tạo từ ảnh này ngay trong lúc nói; không dùng video quay hay dựng sẵn làm nền.
- **FR-003**: Việc chuẩn bị PHẢI từ chối tư liệu không có đúng một khuôn mặt rõ, và báo lý do.
- **FR-004**: Mỗi nhân vật PHẢI gắn với đúng một khách/tài khoản và một hồ sơ nguồn gốc. Hệ thống PHẢI từ chối chuẩn bị khi thiếu hồ sơ
  nguồn gốc, và từ chối mở phiên khi nhân vật thuộc khách khác với khách của phiên.

**Nhép miệng**
- **FR-005**: Nhân vật PHẢI nhép miệng theo tiếng nói đưa vào, hình được tạo ngay trong lúc nói. Không có đường nào phát một video dựng sẵn.
- **FR-006**: Tiếng và miệng PHẢI khớp nhau trong suốt câu. Khi máy không tạo hình kịp, hệ thống PHẢI giảm số khung hình hoặc độ nét
  thay vì để tiếng đi trước hình.
- **FR-007**: Khi không nói, nhân vật PHẢI ở trạng thái chờ (miệng khép), không đứng hình ở khung miệng mở.
- **FR-008**: Nhãn "AI" PHẢI nằm trong chính khung hình của nhân vật (không phải lớp phủ của trang web), luôn hiện, không tắt được.
- **FR-009**: Mình PHẢI thử được nhân vật riêng lẻ bằng cách đưa vào một đoạn tiếng nói có sẵn, không cần mở phiên trả lời comment
  (chỉ để kiểm tra trên laptop, không dùng làm nội dung live).

**Cắm vào pipeline 001**
- **FR-010**: Người vận hành PHẢI chọn được chế độ "ảnh tĩnh" hoặc "nhân vật nhép miệng" bằng cấu hình khi mở phiên; chế độ ảnh tĩnh giữ nguyên hành vi feature 001.
- **FR-011**: Ở chế độ nhân vật nhép miệng, phụ đề, tạm dừng, tiếp tục, bỏ qua, chịu lỗi từng lượt và ghi log PHẢI hoạt động như feature 001.
- **FR-012**: Bỏ qua lượt đang nói PHẢI dừng tiếng, miệng và phụ đề; nhân vật về trạng thái chờ.
- **FR-013**: Lỗi hoặc quá thời gian ở bước tạo hình PHẢI làm lượt đó kết thúc với lỗi ở bước tạo hình, không làm dừng phiên.
- **FR-014**: Màn hình host PHẢI xem được trên Chrome của laptop có cả hình và tiếng, để chia sẻ tab vào Google Meet như feature 001.

**Đo đạc**
- **FR-015**: Mốc "frame đầu tiên" của mỗi lượt PHẢI là lúc khung hình nhép miệng đầu tiên của câu đầu được hiển thị, ghi kèm mã lượt.
- **FR-016**: Hệ thống PHẢI ghi số khung hình mỗi giây thực tế và thời gian riêng của bước tạo hình cho mỗi lượt, hiện trong bảng độ trễ.
- **FR-017**: Hệ thống PHẢI ghi lại khi phần tạo hình gặp lỗi bộ nhớ đồ họa hoặc bị khởi động lại.

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): hình nhép miệng sinh ngay lúc nói (FR-005); nhãn "AI" ghép vào khung hình
  (FR-008); nhân vật gắn với đúng một khách (FR-004). Đoạn tiếng mẫu ở FR-009 chỉ để kiểm tra trên laptop, không phát lên nền tảng live.
- [x] Điều II (đồng ý / bảo mật): nhân vật là gương mặt tạo bằng AI, không phải người thật, nên không cần văn bản đồng ý về hình;
  thay vào đó bắt buộc hồ sơ nguồn gốc (FR-004, US1 #5) và không được cố ý tạo giống người có thật hay người nổi tiếng. Nếu sau này
  đổi sang người thật thì quay lại yêu cầu văn bản đồng ý. Đoạn tiếng mẫu dùng giọng của người đã đồng ý. Tư liệu hình và dữ liệu
  nhân vật không đưa vào kho mã.
- [x] Điều IV (adapter): nhân vật nhép miệng là một cách hiển thị mới thay được cho ảnh tĩnh, không sửa lõi pipeline (FR-010).
- [x] Điều V (test trước): logic chọn chế độ, chịu lỗi, bỏ qua, ghi mốc phải kiểm thử tự động không cần card đồ họa (dùng phần tạo hình
  giả). Phần nhép miệng thật kiểm chứng bằng kịch bản tay trong quickstart. **Lưu ý:** Điều V hiện ghi "gom chạy trên RunPod", trái với
  ADR-023 (chạy trên laptop). Cần sửa Hiến pháp bằng `/sdd.constitution` trước `/sdd.plan`.
- [x] Điều VI (độ trễ): feature này chiếm phần "lip-sync đến frame đầu tiên" (0,8 s) và "truyền hình" (0,5 s) trong ngân sách < 5 giây.
  Trên laptop người dùng chấp nhận vượt ngân sách (ADR-023); feature chỉ bắt buộc đo và ghi (FR-015, FR-016), không đặt ngưỡng.
- [x] Điều VIII (quan sát được, chịu lỗi): FR-013, FR-015 đến FR-017.

### Thực thể chính

- **Nhân vật (avatar)**: một AI host đã chuẩn bị. Thuộc tính: mã nhân vật, khách/tài khoản sở hữu (đúng một), hồ sơ nguồn gốc,
  loại tư liệu gốc (ảnh hoặc video), ngày chuẩn bị, trạng thái (sẵn sàng / lỗi chuẩn bị kèm lý do).
- **Hồ sơ nguồn gốc**: ghi gương mặt được tạo bằng công cụ nào, ai tạo, ngày tạo, điều khoản sử dụng của công cụ (có cho dùng thương mại
  không), và cam kết không cố ý giống người có thật. Lưu cùng nhân vật, ngoài git.
- **Lượt nói** (đã có ở feature 001): thêm số khung hình mỗi giây thực tế và thời gian bước tạo hình.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Với 10 đoạn tiếng nói mẫu tiếng Việt, người vận hành đánh giá miệng khớp tiếng ở ít nhất 8/10 đoạn khi xem bằng mắt.
- **SC-002**: Trong 100% ảnh chụp màn hình host ở thời điểm ngẫu nhiên (ít nhất 10 ảnh), nhãn "AI" nằm trong khung hình nhân vật.
- **SC-003**: Trong một phiên có ít nhất 20 lượt ở chế độ nhân vật nhép miệng, không lượt nào để tiếng chạy xong trước khi hình bắt đầu nhép miệng.
- **SC-004**: Bỏ qua lượt đang nói làm tiếng và miệng dừng trong vòng 1 giây, như feature 001.
- **SC-005**: Lỗi giả lập ở bước tạo hình không làm dừng phiên: comment kế tiếp vẫn được trả lời trong 100% lần thử.
- **SC-006**: Có số liệu thật trên laptop (số khung hình mỗi giây, độ trễ bước tạo hình, độ trễ cả lượt p50/p95, kết quả chạy 30 phút)
  ghi vào tài liệu để bàn mục tiêu tốc độ sau. Không có ngưỡng đạt/trượt cho các số này.

## Giả định

- Gương mặt AI do mình tạo bằng công cụ miễn phí nếu được (ADR-019); công cụ cụ thể chọn ở plan. Phải kiểm tra điều khoản công cụ
  có cho dùng ảnh tạo ra vào mục đích thương mại không trước khi thu tiền khách.
- Chạy trên laptop của người vận hành (card đồ họa 4 GB) theo ADR-023; chấp nhận chậm. RunPod là dự phòng, bật thì báo chi phí trước.
- Giọng thật tiếng Việt thuộc feature 003, chưa có. Giọng giả hiện tại chỉ phát âm báo nên không dùng để chấm độ khớp miệng.
  US1 và SC-001 dùng **đoạn tiếng nói ghi âm có sẵn** của người đã đồng ý (ví dụ người vận hành tự đọc), chỉ để thử trên laptop.
  Khi có feature 003, nhân vật dùng giọng thật mà không phải sửa gì thêm.
- Ngưỡng 8/10 ở SC-001 lấy theo tinh thần tiêu chí demo trong PRD; chấm bằng mắt, không dùng thang điểm 1–5 (PRD còn TODO).
- Nhân vật chỉ có đầu và vai, nhìn thẳng; không có cử chỉ tay hay chuyển động thân (PRD mục 5).
- Bản đầu chỉ cử động vùng miệng theo tiếng; phần còn lại của ảnh gần như đứng yên. Chớp mắt, gật hay nghiêng đầu nhẹ sinh từ ảnh
  là nâng cấp sau, khi đã có số đo trên laptop (cần thêm model nên cần ADR).
- Màn hình host tiếp tục là trang web mở trên Chrome của laptop như feature 001; chưa đẩy lên YouTube hay Shopee.
- Kích thước khung hình, số khung hình mỗi giây và độ nét do plan chọn theo khả năng laptop, ưu tiên khớp miệng hơn độ mượt.
- Chưa bàn license thương mại của phần nhép miệng: feature này chỉ dùng nội bộ và cho buổi demo. Phải xác minh license (RISKS L1, L2)
  trước khi thu tiền khách.

## Ngoài phạm vi

- Đặt và đạt mục tiêu tốc độ (số khung hình mỗi giây, độ trễ < 5 giây): bàn sau khi có số liệu US3.
- Giọng thật tiếng Việt (feature 003) và kịch bản khi rảnh (feature 004).
- Thuê GPU RunPod, đẩy RTMP lên YouTube hoặc Shopee, OBS (feature 006 trở đi).
- Nhiều nhân vật trong một phiên, đổi nhân vật giữa phiên, cử chỉ toàn thân, biểu cảm theo nội dung.
- Chớp mắt, chuyển động đầu tự nhiên; video nền lặp lại.
- Video dự phòng 2–3 phút (feature 007).

## Làm rõ

<!-- /sdd.clarify writes here. One subsection per session. -->
### Phiên 2026-10-31
- Q: Nhân vật AI host là ai (người thật đã ký đồng ý hay gương mặt tạo bằng AI)? → A: Gương mặt tạo bằng AI, không phải người thật.
  Bỏ yêu cầu văn bản đồng ý về hình, thay bằng hồ sơ nguồn gốc (FR-001, FR-004, US1 #5, Điều II, Thực thể chính, Giả định).
- Q: Tư liệu hình đầu vào là ảnh chân dung hay video ngắn lặp làm nền? → A: Một ảnh chân dung gương mặt AI, rồi nhép miệng
  theo tiếng; không mua thêm gì. Bản đầu chỉ cử động miệng; chớp mắt / chuyển động đầu để sau (FR-002, Giả định, Ngoài phạm vi).

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]`
