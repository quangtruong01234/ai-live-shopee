# Đặc tả tính năng: Đưa AI host vào OBS để phát live

- **Feature ID:** `006-obs-output` · **Branch:** `main` · **Ngày tạo:** 2026-11-13
- **Trạng thái:** Tasked <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M2 (mục "Output cho OBS"), làm sớm trong lúc chờ duyệt demo
- **Mô tả gốc:** "làm các task còn sót chạy song song với 006 gộp với output OBS" (2026-11-13). Trước đó người dùng nói: "Tại tôi không
  live trên youtube đâu", nên phần YouTube Unlisted của đề xuất `006-youtube-live` bị bỏ; 006 chỉ còn đường đưa hình và tiếng vào OBS.

## Bối cảnh

Ở giai đoạn sau, phiên live Shopee chạy qua OBS: OBS đẩy hình và tiếng lên Shopee bằng Stream Key do khách cấp (PRD giai đoạn 2). Hiện
AI host chỉ xem được trên trang host trong Chrome, mục đích là chia sẻ tab vào Google Meet. Trang này có nút "Bắt đầu" phải bấm, và chỉ
một trang được phát tiếng tại một thời điểm. Feature này làm cho người vận hành đưa được AI host (hình, tiếng, nhãn "AI", bố cục cảnh
của 009) vào OBS thành một nguồn hình duy nhất, chạy lâu không cần chạm vào, và hệ thống biết được khi đầu ra OBS bị mất.

Feature này không đẩy gì lên Shopee: việc đó do OBS làm, và chỉ sau khi khách được Shopee duyệt live AI. Khi kiểm thử, OBS ghi ra file
trên máy.

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Thêm AI host vào OBS thành một nguồn hình có tiếng (Ưu tiên: P1)

Người vận hành mở OBS trên máy chạy live, thêm một nguồn, dán một địa chỉ do hệ thống đưa ra. Trong OBS hiện ngay AI host đang nói, có
tiếng khớp miệng, nhãn "AI" nằm trong khung hình, đúng bố cục cảnh (bàn bày sản phẩm, thẻ tên/giá). Khung hình không có nút bấm, chữ
trạng thái hay phần giao diện điều khiển nào. Không cần bấm gì trong nguồn đó để có tiếng.

**Vì sao ưu tiên này:** đây là đường duy nhất để đưa AI host lên Shopee Live qua OBS. Không có story này thì các story sau vô nghĩa.

**Kiểm thử độc lập:** chạy show kịch bản (không gọi LLM: đọc nguyên văn hoặc engine giả), thêm nguồn vào OBS, cho OBS ghi 5 phút ra
file, rồi chấm bản ghi: nhãn "AI" có trong mọi khung lấy mẫu, không có phần giao diện điều khiển, tiếng khớp miệng.

**Kịch bản chấp nhận:**
1. **Given** show đang chạy với nhép miệng, **When** người vận hành thêm nguồn theo hướng dẫn, **Then** OBS hiện AI host có tiếng
   trong vòng 10 giây, không cần bấm "Bắt đầu" hay thao tác nào khác trong nguồn.
2. **Given** nguồn đã thêm, **When** OBS ghi ra file, **Then** mọi khung lấy mẫu có nhãn "AI" và không có nút, banner, chữ trạng thái
   hay phụ đề điều khiển nào.
3. **Given** nhép miệng đang lỗi và hệ thống về ảnh tĩnh (feature 005), **When** OBS đang nhận, **Then** OBS vẫn có ảnh tĩnh kèm nhãn
   "AI" và tiếng nói tiếp, không cần thao tác.
4. **Given** khung nguồn trong OBS có kích thước khác khung hình của host, **When** OBS co giãn nguồn, **Then** nhãn "AI" không bị cắt
   mất (khung được thu nhỏ, có viền, không bị cắt xén).
5. **Given** chưa có show nào chạy, **When** nguồn OBS đang mở, **Then** OBS hiện AI host ở trạng thái chờ có nhãn "AI", không hiện
   màn hình trống hay thông báo lỗi.

---

### User Story 2: Chạy lâu không cần chạm vào OBS (Ưu tiên: P2)

Trong một phiên dài, những sự cố thường gặp (khâu nhép miệng khởi động lại, app khởi động lại, mạng trong máy chập chờn) không làm OBS
kẹt màn hình đen hay mất tiếng vĩnh viễn: nguồn tự nối lại. Người vận hành xem thử trong cửa sổ preview của OBS; lỡ mở trang host trên Chrome thì trang đó
không cướp tiếng của OBS và không làm tiếng nói hai lần.

**Vì sao ưu tiên này:** live Shopee dự kiến khoảng 15 giờ/ngày; người vận hành không thể ngồi bấm lại OBS mỗi lần có sự cố.

**Kiểm thử độc lập:** trong lúc OBS đang ghi, tắt rồi bật lại khâu nhép miệng, khởi động lại app, mở/đóng trang host trên Chrome 5 lần; chấm
bản ghi OBS xem nguồn tự về lại hình và tiếng, không có đoạn nói đôi.

**Kịch bản chấp nhận:**
1. **Given** OBS đang nhận hình nhép miệng, **When** khâu nhép miệng tắt rồi bật lại, **Then** OBS chuyển sang ảnh tĩnh có tiếng, rồi
   tự về hình nhép miệng trong vòng 10 giây sau khi khâu đó sẵn sàng, không cần thao tác trong OBS.
2. **Given** OBS đang nhận, **When** app khởi động lại, **Then** nguồn OBS tự nối lại trong vòng 15 giây sau khi app sẵn sàng.
3. **Given** OBS là đầu ra đang phát, **When** người vận hành mở trang host trên Chrome, **Then** trang đó báo "đang phát qua OBS, xem
   trong cửa sổ OBS", không phát tiếng; OBS vẫn giữ tiếng, và không có câu nào bị nói hai lần hay bị mất.
4. **Given** người vận hành vô tình thêm nguồn AI host hai lần trong OBS, **When** show chạy, **Then** chỉ một nguồn phát tiếng, không
   có tiếng nói đôi.

---

### User Story 3: Biết được đầu ra OBS có đang nhận hay không (Ưu tiên: P3)

Bước kiểm tra trước demo (feature 007) và màn canh show cho biết đầu ra OBS đã nối chưa và còn đang nhận hình, tiếng không. Khi đầu ra
OBS đứt, trang điều khiển hiện cảnh báo rõ ràng.

**Vì sao ưu tiên này:** khi live thật, người vận hành nhìn trang điều khiển chứ không nhìn OBS liên tục; đầu ra đứt mà không ai biết là
mất khách.

**Kiểm thử độc lập:** chạy kiểm tra trước demo khi chưa mở OBS, rồi khi đã mở; trong show, đóng nguồn OBS và xem cảnh báo.

**Kịch bản chấp nhận:**
1. **Given** người vận hành chọn chế độ phát qua OBS và chưa mở nguồn OBS, **When** chạy kiểm tra trước demo, **Then** mục đầu ra OBS
   báo chưa đạt, kèm hướng dẫn cách thêm nguồn.
2. **Given** show đang chạy qua OBS, **When** nguồn OBS bị đóng hoặc ngừng nhận, **Then** trang điều khiển hiện cảnh báo trong vòng
   10 giây; khi nguồn nhận lại, cảnh báo tự tắt.

### Trường hợp biên

- OBS đặt nguồn ở chế độ "tắt khi không hiển thị" và người vận hành chuyển sang cảnh OBS khác: khi quay lại cảnh có AI host, nguồn tự
  nối lại; hướng dẫn khuyên tắt chế độ đó.
- OBS bật nghe thử (monitor) nguồn trên cùng loa với trang xem thử: tiếng có thể vọng; hướng dẫn nói rõ cách tránh.
- Cả trang host (dùng cho Meet) và nguồn OBS cùng mở: đầu ra OBS phát, trang host chỉ hiện thông báo (FR-006).
- Máy chạy live vào chế độ ngủ hoặc tắt màn hình: hướng dẫn trong runbook yêu cầu tắt chế độ ngủ trước phiên dài.
- App chạy với ảnh tĩnh (không có nhép miệng) ngay từ đầu: nguồn OBS vẫn có ảnh, nhãn và tiếng.
- Video dự phòng (feature 007) không bao giờ đi qua đầu ra OBS.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

- **FR-001**: Hệ thống PHẢI cung cấp một địa chỉ đầu ra riêng cho OBS, hiển thị AI host (hình nhép miệng hoặc ảnh tĩnh dự phòng, bố cục
  cảnh, nhãn "AI") và phát tiếng nói, không cần người dùng bấm hay thao tác trong trang đó.
- **FR-002**: Khung hình của đầu ra OBS KHÔNG ĐƯỢC chứa nút bấm, lớp phủ "Bắt đầu", chữ trạng thái, banner cảnh báo hay phần giao diện
  điều khiển nào; chỉ có nội dung dành cho người xem live.
- **FR-003**: Nhãn "AI" PHẢI có trong mọi khung hình của đầu ra OBS, ở cả chế độ nhép miệng và ảnh tĩnh, và không có cấu hình nào tắt
  được nó ở đầu ra này.
- **FR-004**: Khung hình đầu ra OBS PHẢI giữ nguyên tỉ lệ khung của cảnh live; khi OBS co giãn nguồn, nội dung (kể cả nhãn "AI") không
  bị cắt.
- **FR-005**: Đầu ra OBS PHẢI tự nối lại hình và tiếng sau khi khâu nhép miệng hoặc app khởi động lại, không cần thao tác trong OBS
  (giới hạn thời gian ở SC-004).
- **FR-006**: Tại một thời điểm, chỉ một trang PHẢI phát tiếng và điều khiển nhịp phát của show. Đầu ra OBS luôn được ưu tiên hơn trang
  host dùng cho Meet: khi đầu ra OBS đang nối, trang host mở thêm không phát; khi đầu ra OBS nối vào, nó nhận quyền phát từ trang host.
- **FR-007**: Khi OBS đang là đầu ra phát, trang host mở trên trình duyệt PHẢI báo rõ "đang phát qua OBS" và không phát tiếng; việc mở hay
  đóng trang đó không được làm OBS mất tiếng hay làm câu nào bị nói hai lần hay bị bỏ. Người vận hành xem thử trong cửa sổ preview của OBS.
- **FR-008**: Khi nguồn AI host bị mở hai lần (hai nguồn OBS hoặc hai trang đầu ra), hệ thống PHẢI bảo đảm chỉ một nơi phát tiếng.
- **FR-009**: Bước kiểm tra trước demo PHẢI có mục đầu ra OBS: đạt khi chế độ phát qua OBS được chọn và đầu ra OBS đang nối và đang phát;
  chưa đạt thì kèm hướng dẫn.
- **FR-010**: Màn canh show PHẢI cảnh báo trên trang điều khiển khi đầu ra phát (OBS) ngừng gửi nhịp quá 10 giây, và tự tắt cảnh báo khi
  đầu ra nhận lại.
- **FR-011**: Hệ thống PHẢI có hướng dẫn từng bước thêm AI host vào OBS (loại nguồn, địa chỉ, kích thước, cài đặt tiếng, các cài đặt nên
  tắt), viết tiếng Việt, nằm trong runbook.
- **FR-012**: Đầu ra OBS KHÔNG ĐƯỢC phát bất kỳ hình hay tiếng ghi sẵn nào (kể cả video dự phòng của 007); chỉ phát nội dung sinh realtime.
- **FR-014**: Người vận hành PHẢI chọn được chế độ phát (Meet hay OBS) bằng một cài đặt lúc khởi động, mặc định là Meet; chế độ này quyết
  định bước kiểm tra trước demo và màn canh show đòi đầu ra nào.
- **FR-013**: Mọi khoảng lặng, khung hình đầu và lệch hình–tiếng của show khi phát qua OBS PHẢI đo được bằng các mốc log hiện có, như khi
  phát qua trang host.

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): đầu ra OBS là đường dẫn tới nền tảng live, nên chỉ phát nội dung sinh realtime
  (FR-012) và nhãn "AI" luôn nằm trong khung hình, không tắt được (FR-003). Một host vẫn gắn với một khách như hiện tại; feature không
  thêm cách dùng host cho tài khoản khác.
- [x] Điều II (đồng ý / bảo mật): feature không lưu và không nhận Stream Key hay phiên Shopee; Stream Key do người vận hành nhập trong OBS.
- [x] Điều VI (độ trễ): show kịch bản qua OBS giữ câu đầu ≤ 5 giây và khoảng lặng p95 ≤ 1,5 giây như khi phát qua trang host; feature
  không được thêm quá 0,2 giây vào khoảng lặng p95 so với trang host trên cùng máy (SC-005).
- [x] Điều VIII (quan sát): đầu ra OBS gửi nhịp trạng thái để canh show đo được (FR-010, FR-013).

### Thực thể chính

- **Đầu ra phát**: nơi đang phát tiếng và quyết định nhịp phát của show. Thuộc tính: loại (trang host cho Meet hoặc đầu ra OBS), đang nối
  hay không, lần gửi nhịp cuối, đang có hình nhép miệng hay ảnh tĩnh. Mỗi lúc chỉ có một.
- **Trang host bị nhường**: trang host mở khi đầu ra OBS đang phát; chỉ hiện thông báo, không phát tiếng, không ảnh hưởng nhịp show.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Người vận hành làm theo hướng dẫn, từ lúc OBS đang mở tới lúc AI host hiện trong OBS có tiếng mất ≤ 5 phút và ≤ 5 thao tác
  trong OBS.
- **SC-002**: Trong bản ghi OBS 30 phút của show kịch bản, 100% khung lấy mẫu (≥ 60 khung, rải đều) có nhãn "AI" và 0 khung có phần giao
  diện điều khiển.
- **SC-003**: Trong bản ghi OBS, lệch hình–tiếng không tệ hơn quá 1 khung hình (40 ms) so với bản ghi do khâu nhép miệng tự ghi trong
  cùng phiên.
- **SC-004**: Khi khâu nhép miệng bật lại, OBS về hình nhép miệng trong ≤ 10 giây; khi app khởi động lại, OBS có lại hình và tiếng trong
  ≤ 15 giây sau khi app sẵn sàng; cả hai không cần thao tác trong OBS (5/5 lần thử mỗi loại).
- **SC-005**: Show 30 phút qua OBS: khoảng lặng p95 không cao hơn quá 0,2 giây so với cùng show phát qua trang host trên cùng máy, và
  không có câu nào bị nói hai lần hay bị bỏ.
- **SC-006**: Mở/đóng trang host trên Chrome 5 lần trong show qua OBS: OBS không mất tiếng lần nào, 0 câu nói đôi, trang host báo
  "đang phát qua OBS" cả 5 lần.
- **SC-007**: Kiểm tra trước demo báo đúng trạng thái đầu ra OBS 3/3 lần (chưa mở, đã mở, đã đóng); cảnh báo ngừng nhận hiện trong
  ≤ 10 giây và tự tắt khi nhận lại.

## Giả định

- OBS chạy trên cùng máy với app và khâu nhép miệng (laptop demo hoặc máy vận hành sau này). Nối OBS từ máy khác qua mạng để sau.
- Người vận hành dùng OBS Studio bản miễn phí, mới nhất trên Windows. Khi kiểm thử, OBS ghi ra file trên máy, không đẩy lên nền tảng nào.
- Khung hình giữ đúng bố cục và tỉ lệ dọc của cảnh 009. Yêu cầu kích thước, tỉ lệ và bitrate cụ thể của Shopee Live qua OBS chưa rõ, nên
  ghi `TODO:` trong runbook; chỉnh trong OBS khi khách được whitelist, không đổi khung hình của pipeline.
- Chế độ mặc định vẫn là trang host cho Meet (demo hiện tại không đổi); người vận hành chọn đầu ra OBS khi cần.
- Kiểm thử feature này không gọi LLM: show dùng chế độ đọc nguyên văn hoặc engine giả.

## Ngoài phạm vi

- Đẩy thẳng lên YouTube, Shopee hay bất kỳ địa chỉ RTMP nào mà không qua OBS. Phần YouTube Unlisted của đề xuất cũ bị bỏ vì người dùng
  không live trên YouTube.
- Nhập, lưu hay quản lý Stream Key; tự động điều khiển OBS (bật/tắt stream, đổi cảnh).
- Đọc comment Shopee (tạm hoãn theo ADR-026).
- Chạy 15 giờ liên tục và tự khởi động lại toàn hệ thống (mục riêng ở M2); feature này chỉ lo đầu ra OBS tự nối lại.
- Nối OBS từ máy khác qua mạng.

## Làm rõ

### Phiên 2026-11-13

Tự chọn khuyến nghị theo ủy quyền làm liên tục; người dùng xem lại ở gói duyệt.

- Q: Khi OBS đang phát, người vận hành xem thử ở đâu? (Trên laptop, khâu nhép miệng chỉ chạy được một phiên hình, nên trang thứ hai không
  có hình nhép miệng riêng.) → A: Xem trong cửa sổ preview của OBS. Trang host mở thêm chỉ báo "đang phát qua OBS", không phát tiếng
  (FR-006, FR-007, US2 #3, SC-006 sửa theo).
- Q: Chọn đầu ra phát bằng cách nào? → A: Một cài đặt lúc khởi động, mặc định Meet (FR-014). Thứ tự ưu tiên phát luôn là đầu ra OBS trước
  trang host, bất kể chế độ; chế độ chỉ quyết định kiểm tra trước demo và canh show đòi đầu ra nào.
- Q: Đầu ra OBS có hiện phụ đề câu đang nói không? → A: Không. Khung hình chỉ có nội dung pipeline sinh ra (cảnh, host, nhãn "AI"); phụ đề
  để sau nếu khách muốn (FR-002).

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại)
