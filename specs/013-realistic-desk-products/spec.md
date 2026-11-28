# Đặc tả tính năng: Sản phẩm đứng trên bàn như đồ thật

- **Feature ID:** `013-realistic-desk-products` · **Branch:** `main` · **Ngày tạo:** 2026-11-22
- **Trạng thái:** In progress (2026-11-22) <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1d (tổng duyệt và demo); sửa cách bày bàn của M1b mục "Bố cục cảnh live quanh host" (009)
- **Mô tả gốc:** "để sản phẩm trên bàn như thật được không, như này nè [ảnh live Shopee mẫu: host ngồi sau bàn gỗ, sản phẩm thật
  đứng hai bên, hai tay host để giữa, không thẻ dưới từng món, chỉ một thẻ sản phẩm ghim]" (2026-11-22). Đề xuất kèm theo sau bản dựng
  thử: tự bỏ nền phẳng khi tải ảnh, bày hai bên tay có chiều sâu và bóng đổ, chọn chế độ thẻ, sửa vạch mép bàn của `demo_host_02`.

**Bối cảnh.** Cảnh live của 009 bày sản phẩm thành một hàng ô đều nhau ngay giữa khung, mỗi món có thẻ tên/giá bên dưới. Lần chạy thử
2026-11-22 với nhân vật `demo_host_02` (bàn gỗ đã có sẵn trong ảnh, 011) và một ảnh thùng Coca tải lên qua trang điều khiển (012) cho thấy
cảnh trông "dán lên" chứ không giống phiên live thật:
- ảnh có nền trắng hiện nguyên khung chữ nhật quanh sản phẩm (012 chỉ cảnh báo, không bỏ nền, vì chỉnh ảnh trong app nằm ngoài phạm vi
  của 009 và 012);
- sản phẩm lơ lửng phía trên mặt bàn vì vạch mép bàn khai cho nhân vật (78% chiều cao khung) cao hơn mép bàn thật trong ảnh (khoảng 87%);
- món chính ở giữa che đúng chỗ hai bàn tay của host;
- không có bóng đổ, cỡ như nhau, thẻ dưới mọi món nên trông như bảng giá.

Ảnh live Shopee người dùng gửi làm mẫu: sản phẩm thật đứng hai bên host trên mặt bàn, có món gần món xa, hai tay host ở giữa không bị
che, không có thẻ dưới từng món. Thẻ sản phẩm ghim và comment trong ảnh mẫu là giao diện của chính Shopee. Bản dựng thử bằng ảnh tĩnh
(2026-11-22, ngoài code chính) cho thấy làm được bằng cách bỏ nền phẳng, đặt đáy sản phẩm đúng mặt bàn, bày hai bên tay, món chính lớn hơn
ở phía trước, món phụ nhỏ hơn lùi về sau, thêm bóng đổ mềm.

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Sản phẩm đứng trên mặt bàn hai bên host, như đồ thật (Ưu tiên: P1)

Mình chọn cách bày "như thật" cho bộ cảnh của khách. Khi mở màn hình host, người xem thấy các sản phẩm đứng trên mặt bàn ở hai bên host:
đáy món nào cũng chạm mặt bàn, có bóng đổ mềm dưới đáy, món chính to hơn và ở phía trước, món phụ nhỏ hơn và lùi về sau. Hai bàn tay host ở
giữa, khuôn mặt, nhãn "AI" và watermark không bị món nào che. Không còn hàng thẻ tên/giá dưới từng món.

**Vì sao ưu tiên này:** đây là thứ khách nhìn thấy đầu tiên; cảnh giống phiên live thật làm buổi demo thuyết phục hơn. Story này một mình
đã đủ để demo với các ảnh sản phẩm đã có nền trong suốt.

**Kiểm thử độc lập:** dùng bộ cảnh demo có ảnh sản phẩm nền trong suốt (1 chính + 2–3 phụ), bật cách bày "như thật", mở màn hình host ở chế
độ nhân vật nhép miệng (`demo_host_02`, bàn có sẵn trong ảnh) và ở chế độ ảnh tĩnh, chụp ít nhất 20 ảnh ở thời điểm ngẫu nhiên; đo đáy từng
món so với mép bàn, kiểm tay, mặt, nhãn, watermark.

**Kịch bản chấp nhận:**
1. **Given** bộ cảnh có 1 sản phẩm chính + 2 sản phẩm phụ và cách bày "như thật", **When** mở màn hình host, **Then** cả 3 món đứng trên mặt
   bàn ở hai bên host, đáy món nào cũng nằm trên mặt bàn (không cao hơn mép bàn, không thò xuống dưới khung), có bóng đổ dưới đáy.
2. **Given** cảnh như #1, **Then** món chính hiện to hơn món phụ và ở phía trước (đáy thấp hơn trong khung); món phụ nhỏ hơn và lùi về sau
   (đáy cao hơn, gần mép bàn hơn); không món nào bị kéo méo tỷ lệ.
3. **Given** cảnh như #1, **When** host đang nói hoặc đang chờ, **Then** không món nào che vùng tay host, khuôn mặt, nhãn "AI" hay
   watermark, dù một phần.
4. **Given** nhân vật có mép bàn khai sai so với mép bàn thật trong ảnh, **When** người vận hành xem trước cảnh, **Then** thấy được vạch mép
   bàn đang dùng chồng lên ảnh nhân vật để phát hiện chỗ lệch, và sửa vạch đó trong hồ sơ nhân vật rồi mở lại phiên là đúng.
5. **Given** cách bày "như thật", **When** cảnh hiện, **Then** không có thẻ tên/giá dưới từng món; thẻ (nếu có) theo chế độ thẻ ở US3.
6. **Given** bộ cảnh chọn cách bày của 009, **When** mở màn hình host, **Then** cảnh giống hệt trước feature này.
7. **Given** cách bày "như thật" và nhân vật **không** có bàn trong ảnh, **When** mở màn hình host, **Then** cảnh vẽ mặt bàn như 009 và bày
   sản phẩm trên mặt bàn đó theo cùng luật #1–#3.

---

### User Story 2: Tự bỏ nền phẳng khi tải ảnh sản phẩm (Ưu tiên: P2)

Khách thường gửi ảnh sản phẩm chụp trên nền trắng hoặc nền một màu. Khi mình tải ảnh đó lên trang điều khiển (luồng 012), hệ thống tự bỏ
nền, cho mình xem ảnh trước và sau khi bỏ nền, rồi mình chọn dùng ảnh đã bỏ nền hay giữ nguyên ảnh gốc. Ảnh mình đã tự tách nền thì giữ
nguyên.

**Vì sao ưu tiên này:** US1 chỉ đẹp khi ảnh có nền trong suốt; hiện tách nền phải làm bằng tay ngoài app, không kịp khi khách đổi ảnh giữa
buổi. Cần US1 để thấy rõ giá trị, nhưng tự kiểm được riêng.

**Kiểm thử độc lập:** tải lên một bộ ít nhất 10 ảnh sản phẩm thật (nền trắng, nền một màu, nền phức tạp, ảnh đã trong suốt); xem trang xem
trước và ảnh trên live sau khi áp dụng; so ảnh tải lên với ảnh đã bỏ nền.

**Kịch bản chấp nhận:**
1. **Given** ảnh sản phẩm nền trắng hoặc một màu, **When** tải lên, **Then** trang xem trước hiện ảnh gốc và ảnh đã bỏ nền cạnh nhau, ảnh
   đã bỏ nền được chọn sẵn; áp dụng thì món trên bàn không còn khung chữ nhật.
2. **Given** ảnh đã có nền trong suốt, **When** tải lên, **Then** ảnh giữ nguyên, không bị bỏ nền lần nữa.
3. **Given** ảnh có nền phức tạp (cảnh thật, nhiều màu) mà hệ thống không tách chắc được, **When** tải lên, **Then** trang báo rõ "không tự
   bỏ được nền", vẫn cho dùng ảnh gốc, và gợi ý xin khách ảnh nền trơn hoặc ảnh đã tách nền.
4. **Given** sản phẩm có phần cùng màu với nền (hộp trắng trên nền trắng), **When** bỏ nền, **Then** phần sản phẩm không bị khoét mất;
   nếu hệ thống không chắc thì báo như #3 thay vì đưa ra ảnh bị khoét.
5. **Given** ảnh đã bỏ nền, **Then** chi tiết của sản phẩm (hình dáng, màu, chữ, nhãn) không đổi so với ảnh tải lên; chỉ nền bị bỏ.
6. **Given** mình chọn "giữ ảnh gốc", **When** áp dụng, **Then** món hiện đúng ảnh gốc như 012 hiện nay (kèm cảnh báo còn nền).

---

### User Story 3: Thẻ sản phẩm và làm nổi hợp với cảnh thật (Ưu tiên: P3)

Thay cho thẻ dưới mọi món, mình chọn một trong ba chế độ thẻ cho phiên: không thẻ (khi lên Shopee đã có thẻ ghim của Shopee), một thẻ cho
món đang được nói tới, hoặc thẻ dưới mọi món như 009. Khi host nói tới một món, món đó được làm nổi một cách tự nhiên (ánh sáng dịu quanh
món) thay vì phóng to hẳn.

**Vì sao ưu tiên này:** cảnh thật không có thẻ giá dưới từng món, nhưng ở buổi demo Meet người xem vẫn cần thấy tên và giá món đang nói.
Có cấu hình mặc định tạm ở Giả định nên US1 không phải chờ story này.

**Kiểm thử độc lập:** chạy show kịch bản một vòng đủ 3 sản phẩm ở mỗi chế độ thẻ, chụp ảnh lúc đổi phân đoạn; so thẻ với file dữ liệu và
sản phẩm nổi với log show.

**Kịch bản chấp nhận:**
1. **Given** chế độ "một thẻ", **When** câu đầu của phân đoạn về sản phẩm X bắt đầu phát, **Then** trong vòng 1 giây hiện một thẻ của X
   (tên, giá hoặc khoảng giá, dòng khuyến mãi đầu tiên nếu có, nguyên văn file) ở chỗ không che tay, mặt, nhãn, watermark và không che
   chính các sản phẩm; phân đoạn chung thì không có thẻ.
2. **Given** chế độ "không thẻ", **Then** không có thẻ nào trong khung ở mọi thời điểm.
3. **Given** chế độ "mọi món", **Then** mỗi món có thẻ như 009 và thẻ không đè lên món khác hay vùng tay.
4. **Given** X đang được nói tới, **Then** X được làm nổi bằng ánh sáng dịu, cỡ tăng không quá mức để vẫn đứng đúng mặt bàn, vẫn không che
   vùng cấm; các món khác vẫn rõ.
5. **Given** thay file dữ liệu sản phẩm giữa phiên, **Then** thẻ đổi theo file mới như 009 FR-013.

### Trường hợp biên

- **Nhiều sản phẩm hơn số chỗ hai bên bàn:** hiện món chính và các món phụ theo thứ tự trong file tới hết chỗ; mình được báo món nào không
  có chỗ (như 009).
- **Chỉ có 1 sản phẩm:** món đó đứng một bên tay (mặc định bên phải người xem; bên trái nếu ở đó món được vẽ to rõ hơn), bên kia trống.
- **Ảnh sản phẩm rất rộng hoặc rất dẹt** (hộp nằm ngang, ảnh băng rôn): thu cỡ cho vừa một bên bàn, không tràn vào vùng tay; quá rộng không
  đặt được thì báo như cảnh báo `too_wide` của 012.
- **Ảnh rất cao (chai dài):** thu cỡ để đỉnh không lên quá cằm host và không che mặt.
- **Hai món chồng lên nhau một phần** (món trước che chân món sau): chấp nhận, giống đồ thật; món trước luôn vẽ đè lên món sau, không món
  nào bị che quá nửa.
- **Mép bàn trong ảnh nhân vật nghiêng hoặc cong:** dùng một vạch mép bàn ngang; chấp nhận sai lệch nhỏ, mình kiểm bằng xem trước (US1 #4).
- **Nhân vật đưa tay ra ngoài vùng tay đã khai** trong clip nói: tay có thể bị món che một phần; chấp nhận nếu không xảy ra ở clip chờ và
  không che mặt (như 009 chấp nhận tay bị bàn che).
- **Bỏ nền lỗi hoặc quá chậm:** dùng ảnh gốc kèm cảnh báo, không chặn việc tải ảnh hay áp dụng; phiên live không dừng.
- **Tải ảnh nền phức tạp giữa show:** model tách nền tranh CPU với giọng nói (giọng live chạy trên CPU); chạy ở mức ưu tiên thấp, không
  để tiếng bị lặng hay giật (FR-016). Nếu không giữ được thì chỉ cho bỏ nền phức tạp ngoài show và báo người vận hành.
- **Shopee chỉ ghim món chính:** khi host nói món phụ, thẻ ghim vẫn là món chính; người xem mua món phụ qua giỏ hàng của phiên. Chấp nhận
  vì không có người trực đổi ghim.
- **Ảnh có bóng đổ sẵn trên nền trắng:** phần bóng có thể bị bỏ cùng nền hoặc còn lại mờ; chấp nhận, bóng của cảnh vẽ thêm vẫn có.
- **Ảnh bộ cảnh chuẩn bị trước phiên còn nền:** dùng nguyên như hiện nay, kiểm tra trước demo cảnh báo ảnh còn nền.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

**Cách bày "như thật"**

- **FR-001**: Bộ cảnh PHẢI chọn được cách bày: "như thật" (feature này) hoặc "hàng ô" (009). Đổi cách bày là sửa bộ cảnh rồi mở lại phiên,
  như các thay đổi bố cục khác của 009.
- **FR-002**: Ở cách bày "như thật", đáy của mỗi sản phẩm PHẢI nằm trên mặt bàn: không cao hơn mép bàn, không thấp quá đáy khung.
- **FR-003**: Sản phẩm PHẢI được bày ở hai bên host, chừa trống vùng tay của nhân vật. Mỗi nhân vật PHẢI có vùng tay khai trong hồ sơ nhân
  vật; nhân vật chưa khai vùng tay thì dùng một vùng mặc định ở giữa khung và kiểm tra trước demo cảnh báo.
- **FR-004**: Món chính PHẢI to hơn và ở phía trước (đáy thấp hơn) so với món phụ; món phụ nhỏ dần và lùi về sau theo thứ tự trong file.
  "To hơn" tính theo cỡ vẽ trên khung: món đứng sau không được vừa cao bằng vừa chiếm diện tích bằng món đứng trước nó (chai cao mảnh
  được đứng sau hộp dẹt, nhưng không lấn món trước cả hai chiều). Món chính đứng ở bên bàn cho nó cỡ vẽ to rõ hơn (làm rõ 2026-11-23).
  Cỡ của mọi món giữ đúng tỷ lệ ảnh, không kéo méo.
- **FR-005**: Mỗi sản phẩm PHẢI có bóng đổ mềm ngay dưới đáy, rộng theo cỡ món. Bóng không phủ lên vùng cấm.
- **FR-006**: Hệ thống ĐƯỢC chỉnh độ sáng đều của ảnh sản phẩm trong giới hạn nhỏ để hợp ánh sáng cảnh, nhưng KHÔNG được đổi màu (sắc độ),
  chữ, nhãn hay hình dáng sản phẩm.
- **FR-007**: Vùng cấm của 009 (khuôn mặt từ cằm trở lên, nhãn "AI", watermark) cộng thêm vùng tay PHẢI không bị ảnh sản phẩm, bóng, thẻ hay
  hiệu ứng làm nổi che, ở mọi thời điểm. Bố cục chồng lên vùng cấm PHẢI bị từ chối và báo lỗi như 009 FR-019.
- **FR-008**: Ở chế độ xem trước, người vận hành PHẢI thấy được vạch mép bàn và vùng tay đang dùng chồng lên ảnh nhân vật (không vào khung
  gửi đi), để phát hiện chỗ lệch với ảnh.
- **FR-009**: Với nhân vật không có bàn trong ảnh, cách bày "như thật" PHẢI vẽ mặt bàn như 009 rồi bày sản phẩm theo FR-002–FR-007.
- **FR-010**: Hồ sơ nhân vật `demo_host_02` PHẢI có vạch mép bàn khớp mép bàn thật trong ảnh (sai lệch không quá 1% chiều cao khung khi
  xem trước).

**Bỏ nền khi tải ảnh**

- **FR-011**: Khi tải ảnh sản phẩm không có nền trong suốt (luồng 012), hệ thống PHẢI thử bỏ nền ngay lúc tải lên và lưu bản đã bỏ nền
  cùng ảnh tải lên. Ảnh đã có nền trong suốt PHẢI giữ nguyên.
- **FR-012**: Trang xem trước PHẢI hiện ảnh tải lên và ảnh đã bỏ nền cạnh nhau (trên nền ca-rô để thấy chỗ trong suốt) và trên cảnh; mình
  chọn dùng bản nào trước khi áp dụng. Mặc định chọn bản đã bỏ nền khi bỏ được.
- **FR-013**: Hệ thống PHẢI bỏ được cả nền trơn/một màu lẫn nền phức tạp (cảnh thật, nhiều màu). Nền trơn bỏ bằng cách đơn giản, nhanh;
  ảnh nền phức tạp dùng một model AI tách nền chạy trên máy (không gọi dịch vụ trả phí). Chọn model, cài thư viện và tải model PHẢI có ADR
  và kiểm giấy phép thương mại (ràng buộc 5) trước khi cài.
- **FR-014**: Khi không bỏ nền chắc chắn được (kể cả sau khi dùng model, ví dụ sản phẩm cùng màu nền có nguy cơ bị khoét), hệ thống PHẢI
  báo "không tự bỏ được nền" kèm lý do thay vì đưa ra ảnh lỗi, và vẫn cho dùng ảnh gốc.
- **FR-015**: Bỏ nền PHẢI chỉ đổi phần nền thành trong suốt (kể cả làm mềm mép vài điểm ảnh); KHÔNG được vẽ thêm, xóa hay đổi chi tiết của
  sản phẩm (009 FR-002, ràng buộc 7 và 8).
- **FR-016**: Bỏ nền PHẢI làm một lần lúc tải lên, không làm lại mỗi khung hình, và không làm chậm phiên live đang chạy (tiếng, hình, khoảng
  lặng giữa câu giữ như khi không tải ảnh).
- **FR-017**: Bản đã bỏ nền PHẢI đi theo mọi thao tác của 012 (áp dụng, về ảnh trước, gỡ ảnh, bộ chuẩn bị, xác nhận quyền dùng), như một
  phiên bản ảnh của món đó.
- **FR-018**: Kiểm tra trước demo PHẢI cảnh báo (không phải lỗi) ảnh sản phẩm đang dùng còn nền khi cách bày là "như thật".

**Thẻ và làm nổi**

- **FR-019**: Phiên PHẢI chọn được chế độ thẻ: "không thẻ", "một thẻ cho món đang nói", "mọi món" (như 009). Mặc định là "không thẻ" ở
  mọi đầu ra (Meet và OBS), giống phiên live Shopee nơi thẻ sản phẩm là thẻ ghim của chính Shopee.
- **FR-020**: Mọi chữ trên thẻ PHẢI lấy nguyên văn từ file dữ liệu như 009 FR-011–FR-014; thẻ đổi theo file mới như 009 FR-013.
- **FR-021**: Ở chế độ "một thẻ", thẻ của món đang nói PHẢI hiện/ẩn theo câu đang phát như luật làm nổi 009 FR-015–FR-017 (trong vòng 1
  giây, không sớm hơn lúc câu đầu của phân đoạn phát).
- **FR-022**: Ở cách bày "như thật", món đang nói PHẢI được làm nổi bằng ánh sáng dịu quanh món; nếu tăng cỡ thì đáy vẫn đứng đúng mặt bàn và
  không chạm vùng cấm. (2026-11-25, ADR-093: ở `showcase` ánh sáng này nhẹ hơn, alpha 60 thay 230, vì món đứng trước áo tối của host.)

**Cách bày "trưng bày" (làm rõ 2026-11-23, ADR-079)**

- **FR-025**: Bộ cảnh PHẢI chọn được thêm cách bày "trưng bày": món chính đứng giữa, phía trước host, cao khoảng 0,26–0,30 chiều cao khung,
  tức gần cỡ thật so với đầu host (sửa 2026-11-23, ADR-082; trước đó 0,35–0,40) (nhỏ hơn khi không đủ chỗ); tối đa 3 món phụ đứng lùi sau, hai bên món chính. Không sản phẩm nào được che sản phẩm nào, kể cả lúc một
  món được làm nổi, và sticker giá không che món phụ (sửa 2026-11-23, ADR-081; trước đó món chính được che tới 40% món phụ). Thiếu chỗ
  hai bên thì món chính thu nhỏ trước (không thấp hơn 0,22 H) để món phụ giữ ít nhất 85% cỡ mục tiêu; vẫn thiếu thì món phụ thu nhỏ
  tiếp, rồi mới ẩn (`no_room`). Cụm sản phẩm ĐƯỢC che tay và ngực host (không dùng vùng tay của FR-003, FR-007), nhưng ảnh, bóng, bục, sticker và ánh
  sáng làm nổi KHÔNG được chạm vùng cấm của 009 (mặt từ cằm trở lên, nhãn AI, watermark) và không ra ngoài khung. Luật đáy, bóng, cỡ
  (FR-002, FR-004, FR-005), chỉnh sáng (FR-006), thẻ (FR-019–FR-021), làm nổi (FR-022) và cảnh báo ảnh còn nền (FR-018) áp dụng như
  "như thật".
- **FR-026**: Cách bày "trưng bày" ĐƯỢC bật bục tròn màu trắng dưới món chính (`riser`, mặc định tắt). Bục đứng trên mặt bàn, có bóng, và
  cũng không chạm vùng cấm.
- **FR-027**: Cách bày "trưng bày" ĐƯỢC bật sticker tròn ở góc trên món chính (`sticker`, mặc định tắt). Chữ trên sticker CHỈ là giá hoặc
  khoảng giá của món chính lấy nguyên văn từ file dữ liệu như 009 FR-011 (không có chữ khuyến mãi tự đặt, không có "giảm X%" tự tính).
  Món chính không có giá → không vẽ sticker + cảnh báo `sticker_no_price`; không có chỗ ngoài vùng cấm → không vẽ + cảnh báo
  `sticker_no_room`.
- **FR-028**: Khi ảnh sản phẩm nhỏ hơn cỡ vẽ trên khung quá mức (ảnh nguồn thấp hơn 1,5 lần chiều cao vẽ lúc món được làm nổi, ở mọi
  cách bày), kiểm tra cảnh và lúc tải ảnh lên (012) PHẢI cảnh báo "ảnh độ phân giải thấp, sẽ mờ trên hình" (`art_low_resolution`,
  mức cảnh báo, không chặn áp dụng). Bộ cảnh giữ ảnh sản phẩm tối đa 960 px cạnh dài (`ART_MAX_SIDE`, trước là 640 px, đủ cho món
  chính `showcase` nổi trên khung 720×1280); ảnh đã đạt mức này thì KHÔNG cảnh báo, vì tải ảnh to hơn cũng không nét hơn.
- **FR-029** (thêm 2026-11-23, ADR-082): Ở cách bày "như thật" và "trưng bày", ảnh sản phẩm PHẢI được làm mềm nhẹ cho hợp độ nét
  của hình host (mờ khoảng 0,7 px, mép mềm khoảng 0,8 px trên khung cao 832 px) để không trông như ảnh dán lên. Làm mềm không được đổi
  màu, chữ, nhãn hay hình dáng (FR-006): chữ trên sản phẩm vẫn đọc được. Cách bày hàng (009) không đổi.
- **FR-030** (thêm 2026-11-26, ADR-095): Ở "trưng bày", khi bật `stock`, mỗi món tách nền PHẢI hiện thành nhóm hàng dựng từ chính
  ảnh của món, chọn theo hình dáng: chai thành cụm hai hàng (đổi bởi ADR-098, FR-035; trước là hàng ba), lon thành tháp ba, lốc thành cặp, thùng rộng giữ một đơn vị. Chỉ được đổi độ
  sáng các đơn vị phía sau (FR-006); cỡ một đơn vị vẫn theo luật cỡ thật (ADR-082). Mặc định tắt.
- **FR-031** (thêm 2026-11-26, ADR-095): Khi bật `price_tags`, mỗi món PHẢI có tem giá dưới chân, chữ lấy nguyên từ giá trong file dữ
  liệu (ràng buộc 7); không có chỗ mà không che món khác thì không vẽ tem và báo lỗi cảnh. Mặc định tắt.
- **FR-032** (thêm 2026-11-26, ADR-095): Khi bật `promo_banner`, băng dưới cụm sản phẩm PHẢI liệt kê nguyên văn khuyến mãi trong file;
  thiếu chỗ thì thu chữ trước, sau đó bỏ nguyên khuyến mãi cuối, không cắt nửa câu; không còn chỗ thì không vẽ và báo lỗi cảnh. Mặc
  định tắt.
- **FR-033** (thêm 2026-11-26, ADR-096): Ở "trưng bày", món chính rộng (thùng, hộp quà) KHÔNG được rộng quá nửa khung, để món phụ còn
  chỗ đứng hai bên mà không món nào che món nào (FR-025).
- **FR-034** (thêm 2026-11-26, ADR-097): Ở "trưng bày", các món trên bàn PHẢI thành một cụm có bậc trước–sau: món chính thấp, rộng
  đứng trước ở giữa, gần mép trước bàn nhưng không sát mép; món phụ cao hơn đứng lùi sau ở hai bên, chân đứng cao hơn chân món chính
  và đỉnh cao hơn đỉnh món chính để hàng phía sau vẫn lộ ra. Món chính rộng (thùng, hộp quà) không rộng quá khoảng 0,38 bề rộng khung (đổi bởi ADR-098; trước là 0,42).
  Khi chiếu qua Meet (không có lớp app Shopee) cảnh demo tắt `avoid_app_overlay`; khi lên Shopee qua OBS thì bật lại (014 FR-019).
- **FR-035** (thêm 2026-11-26, ADR-098): Ở "trưng bày" khi bật `stock`, chai PHẢI đứng thành cụm hai hàng so le: 2 chai hàng trước
  đứng sát nhau, 3 chai hàng sau lệch nửa chai để mỗi chai sau lộ ra giữa hai chai trước, nhỏ hơn (0,85) và tối hơn (0,86) vì ở xa hơn;
  đỉnh hàng sau ngang đỉnh hàng trước để cả cụm chỉ cao một chai và luật cỡ thật (ADR-082) vẫn tính theo một chai. Không đổi màu, chữ
  hay hình dáng chai (FR-006); các nhóm hàng của các món khác nhau vẫn không che nhau (FR-025).

**An toàn và quan sát**

- **FR-023**: Lỗi ở cách bày "như thật" (ảnh lỗi, bố cục không đặt được) PHẢI không làm dừng phiên: món lỗi không hiện, các món khác vẫn
  hiện, trang điều khiển báo lỗi (như 009 FR-021).
- **FR-024**: Hệ thống PHẢI ghi thời gian ghép cảnh mỗi khung và số khung hình mỗi giây như 009 FR-022, và ghi mỗi lần bỏ nền (thời gian,
  kết quả: đã bỏ / không bỏ được / giữ nguyên, lý do).

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): cảnh vẫn ghép từ ảnh tĩnh ngay lúc phát, không có video dựng sẵn; nhãn "AI" và
  watermark nằm trong vùng cấm (FR-007); bộ cảnh và hồ sơ nhân vật vẫn gắn một khách.
- [x] Điều II (đồng ý / bảo mật): ảnh tải lên và bản đã bỏ nền là dữ liệu của khách, lưu ngoài git như 012; giữ ô xác nhận quyền dùng của
  012 (FR-017).
- [x] Điều III (có căn cứ): chữ trên thẻ nguyên văn file (FR-020), sticker chỉ ghi giá từ file (FR-027); bỏ nền và chỉnh sáng không đổi chi tiết sản phẩm, không đổi màu
  (FR-006, FR-015), để không gây hiểu sai về sản phẩm (ràng buộc 7, 8).
- [x] Điều IV (adapter): cách bày mới là một lựa chọn của lớp cảnh, chọn bằng bộ cảnh; cách bày 009 giữ nguyên (FR-001).
- [x] Điều VI (độ trễ): bỏ nền chạy một lần lúc tải ảnh, ngoài đường câu → tiếng (FR-016); ghép cảnh mỗi khung không chậm hơn 009 quá
  giới hạn ở SC-005.
- [x] Điều VII (đơn giản): model tách nền cho ảnh nền phức tạp (FR-013) là thư viện và model mới, phải có ADR, kiểm giấy phép và người
  dùng duyệt trước khi cài; nền trơn vẫn bỏ bằng cách đơn giản không cần model.
- [x] Điều VIII (quan sát, chịu lỗi): FR-014, FR-023, FR-024.

### Thực thể chính

- **Cách bày**: thuộc bộ cảnh; "hàng ô" (009) hoặc "như thật".
- **Mép bàn**: vạch ngang theo tỷ lệ chiều cao khung, khai trong hồ sơ nhân vật khi bàn có sẵn trong ảnh, hoặc theo bàn vẽ thêm (009).
- **Vùng tay**: hình chữ nhật trong khung, khai trong hồ sơ nhân vật; là một phần của vùng cấm ở cách bày "như thật".
- **Chỗ đứng**: vị trí một món trên mặt bàn: bên (trái/phải), độ sâu (trước/sau), cỡ; món chính ở chỗ trước và to nhất.
- **Phiên bản ảnh đã bỏ nền**: tạo từ một ảnh tải lên; có kết quả bỏ nền (đã bỏ / không bỏ được / giữ nguyên) và lý do; đi cùng ảnh tải lên
  trong các thao tác của 012.
- **Chế độ thẻ**: "không thẻ", "một thẻ", "mọi món"; chọn theo phiên.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Trong 100% của ít nhất 20 ảnh chụp màn hình host ở thời điểm ngẫu nhiên (lúc chờ, lúc nói, lúc đổi món nổi, chế độ nhép miệng
  và ảnh tĩnh), đáy mọi sản phẩm nằm trên mặt bàn và không món, bóng hay thẻ nào che khuôn mặt, vùng tay, nhãn "AI", watermark.
- **SC-002**: Ít nhất 2/3 người xem thử, xem hai đoạn 1 phút "hàng ô" (009) và "như thật" không biết đoạn nào là bản nào, chọn "như thật" là
  giống phiên live bán hàng hơn; và ít nhất 2/3 nói sản phẩm trông như đặt trên bàn (không lơ lửng, không khung nền, không méo).
- **SC-003**: Với bộ ít nhất 10 ảnh sản phẩm thật nền trắng hoặc một màu, ít nhất 8/10 ảnh bỏ nền sạch (ở cỡ hiện trên live không thấy viền
  nền, không mất phần nào của sản phẩm) theo người vận hành chấm; với bộ ít nhất 10 ảnh nền phức tạp, ít nhất 7/10 sạch; 100% ảnh bỏ nền
  không đạt được báo trước khi áp dụng, không ảnh lỗi nào lên live mà không có cảnh báo.
- **SC-004**: Đặt ảnh tải lên cạnh bản đã bỏ nền của 100% ảnh trong bộ SC-003, người dùng xác nhận chi tiết sản phẩm (hình, màu, chữ, nhãn)
  không đổi.
- **SC-005**: Trên laptop dev ở chế độ nhép miệng, số khung hình mỗi giây với cách bày "như thật" không thấp hơn quá 10% so với cách bày
  "hàng ô" cùng cấu hình, khoảng lặng giữa câu p95 không tăng quá 0,1 giây (show 10 phút mỗi bên); trong lúc tải và bỏ nền một ảnh giữa show,
  không có khoảng lặng nào vượt giới hạn của Điều VI.
- **SC-006**: Từ lúc chọn ảnh tải lên tới lúc trang xem trước hiện cả ảnh gốc và bản đã bỏ nền không quá 5 giây cho ảnh nền trơn và không
  quá 20 giây cho ảnh nền phức tạp (ảnh tới 2000 điểm ảnh mỗi cạnh, laptop dev); áp dụng vẫn lên live trong 2 giây như 012.
- **SC-007**: 100% tên, giá, khuyến mãi trên thẻ trong một phiên 30 phút (mỗi chế độ thẻ có thẻ) khớp nguyên văn file đang nạp.

## Giả định

- **Cách bày "như thật" là lựa chọn của bộ cảnh, không thay hẳn 009**: bộ cảnh cũ không đổi gì vẫn chạy như trước (FR-001); bộ cảnh demo
  sẽ chuyển sang "như thật" khi feature xong.
- **Món chính đứng phía trước bên phải người xem, món phụ chia hai bên theo thứ tự file**, theo bản dựng thử 2026-11-22; vị trí cụ thể do plan
  chọn, người dùng duyệt bằng ảnh chụp. Nếu bên trái cho món chính cỡ vẽ to rõ hơn (ví dụ hộp dẹt, bên phải hẹp) thì cả bố cục lật sang
  trái; món đang nói không làm lật bố cục (làm rõ 2026-11-23).
- **Vùng tay khai tay trong hồ sơ nhân vật** (như mép bàn của 011), không tự dò tay trong ảnh; nhân vật mới đo một lần khi làm nhân vật.
- **Bóng đổ là bóng mềm chung dưới đáy**, không tính theo hướng đèn thật trong ảnh.
- **Chỉnh sáng trong giới hạn nhỏ** (FR-006), không đổi sắc độ, vì đổi màu có thể làm khách hiểu sai màu sản phẩm.
- **Ảnh tải lên vẫn được giữ** cùng bản đã bỏ nền để chọn lại và để kiểm SC-004; đây là ảnh mình tải lên, không phải hồ sơ nguồn mà 012 đã
  bỏ (làm rõ 012 ngày 2026-11-20).
- **Làm nổi ở cách bày "như thật" không phóng to như 009** (cỡ tăng nhỏ hoặc không tăng), vì đồ thật trên bàn không to lên; cỡ cụ thể
  do plan chọn, người dùng duyệt bằng ảnh chụp.
- **Thẻ ở chế độ "một thẻ" nằm ở góc dưới khung**, giống thẻ ghim của Shopee trong ảnh mẫu, không che sản phẩm; plan chốt vị trí. Mặc định
  là "không thẻ" (FR-019); "một thẻ" vẫn bật được khi demo Meet cần hiện giá trên hình.
- **Ghim sản phẩm trên Shopee là thao tác tay** của người bán trong ứng dụng Shopee Live (theo các bài hướng dẫn bên thứ ba tra 2026-11-22,
  chưa có tài liệu chính thức nói có ghim tự động). Không có người trực nên chỉ ghim món chính một lần khi mở phiên (bước trong runbook M2);
  các món khác người xem mua qua giỏ hàng. Hệ thống không thao tác gì trên tài khoản Shopee. TODO: kiểm lại trong Kênh Người bán khi có tài
  khoản thử của khách.
- Ảnh sản phẩm của khách vẫn là ảnh chụp thật; hệ thống không tạo ảnh sản phẩm bằng AI (009, 012).

## Ngoài phạm vi

- Tách host khỏi nền hay đặt sản phẩm phía sau host (hướng C của 009).
- Tự dò tay, dò mép bàn trong ảnh nhân vật; bóng đổ theo hướng đèn thật; phản chiếu trên mặt bàn.
- Kéo thả vị trí sản phẩm trên trang điều khiển giữa phiên.
- Host cầm sản phẩm hay chỉ tay vào sản phẩm.
- Chỉnh ảnh khác ngoài bỏ nền và chỉnh sáng (cắt khung, xoay, chỉnh màu, làm nét) trong app.
- Tạo ảnh sản phẩm bằng AI hoặc làm sản phẩm trông khác ảnh thật.
- Thẻ ghim, comment hay nút mua kiểu Shopee (Shopee tự hiện).
- Thêm dữ liệu sản phẩm mới (ví dụ thùng Coca dùng thử 2026-11-22): tên và giá vẫn chỉ đến từ file dữ liệu khách gửi.

## Làm rõ

<!-- /sdd.clarify writes here. One subsection per session. -->

### Phiên 2026-11-22

- H: Bỏ nền chỉ cho nền trơn, hay bỏ cả nền phức tạp bằng model AI tách nền? → Đ: ảnh nền phức tạp thì dùng thêm model (FR-013; cần ADR
  và kiểm giấy phép trước khi cài; nền trơn vẫn dùng cách đơn giản).
- H: Chế độ thẻ mặc định? → Đ: "không thẻ", như phiên live Shopee có thẻ ghim (FR-019). Người dùng hỏi thêm: ghim trên Shopee là bấm tay hay
  tự động? → Theo các hướng dẫn tra được là bấm tay; hệ thống không được thao tác trên tài khoản Shopee. Bản nháp có thêm nhắc ghim trên trang
  điều khiển (FR-019a), người dùng bỏ vì sẽ không có người trực: chỉ ghim món chính một lần khi mở phiên (Giả định).

### Phiên 2026-11-23

- Bối cảnh: dựng thử trên khung live thật của `demo_host_02` với ảnh Coca (thùng lon làm món chính, hai chai làm món phụ) thì sản phẩm
  quá nhỏ so với tay host, và thùng dẹt ở bên phải hẹp bị vẽ nhỏ hơn chai món phụ. Người dùng: "demo thì sản phẩm nào cũng được, cứ làm
  để đúng yêu cầu cái đã".
- H: "To hơn" ở FR-004 so theo chiều cao hay diện tích? → Đ: món sau không được lấn món trước cả hai chiều (vừa cao bằng vừa diện tích
  bằng); chai cao mảnh đứng sau hộp dẹt là được (FR-004).
- H: Người dùng xem live: "đổ bóng dưới như đang bay ở trên bàn" → Đ: bóng bám theo đường đáy thật của ảnh (thùng chụp xéo có đáy
  nghiêng), chỉ lộ một dải ngắn trước đáy; viền trắng sót lại sau khi bỏ nền được tô bằng màu món lúc vẽ (FR-005, research R3).
- H: Món chính luôn ở bên phải? → Đ: bên phải là mặc định; lật sang trái khi ở đó món chính được vẽ to rõ hơn; món đang nói không làm
  lật bố cục (Giả định, trường hợp biên 1 sản phẩm).
- H: Làm nổi có đủ rõ? → Đ: ánh sáng ấm gần như không thấy trên bàn gỗ sáng, nên món nổi to hơn (mặc định 1,08) và món khác tối hơn
  (0,85) để tách hẳn (FR-022, research R3).
- H: Người dùng so với ảnh một phiên live thật: món chính to, đặt giữa trước host, món phụ xếp chồng sau, có bục và sticker giá. Giữ
  cách bày "như thật" hay đổi? → Đ: thêm cách bày thứ ba "trưng bày" (FR-025), bục và sticker tùy chọn (FR-026, FR-027); cụm sản phẩm
  được che tay và ngực, không che mặt, miệng, nhãn AI. Sticker chỉ ghi giá từ file dữ liệu, không bịa khuyến mãi (ràng buộc 7). Thêm
  cảnh báo ảnh độ phân giải thấp lúc tải (thùng Coca bị mờ khi phóng to) (FR-028). Người dùng: "ok triển khai cả 2 đi" (ADR-079).
- H: Người dùng xem live `showcase`: "đổi 1 thùng thành 1 lốc đi và các sản phẩm không bị che nhau" → Đ: món chính demo đổi thành lốc 6
  lon Coca-Cola 320ml; không món nào che món nào, món chính nhường chỗ (thu nhỏ tới 0,22 H) cho món phụ đứng hai bên (FR-025, ADR-081).
- H: Người dùng: "trình bày sản phẩm như 1 buổi hot live" → Đ: nhóm hàng, tem giá, băng khuyến mãi (FR-030–FR-032, ADR-095). Sau khi
  xem live: "không hiện giá trên này hoặc khuyến mãi chỉ có sản phẩm trên bàn thôi ... ví dụ dùng hộp quà hoặc sản phẩm nổi bật hiện
  nay nếu có" → Đ: tắt tem và băng trong cảnh demo; món chính là thùng quà Tết có trong file, rộng tối đa nửa khung (FR-033, ADR-096).
- H: Người dùng: "cái góc để đồ á nó hơi xấu, bạn research cách chưng bày sản phẩm để thu hút người xem và áp dụng vào trong này
  đi" → Đ: bày theo bậc (món thấp trước, món cao sau), cụm tam giác quanh món chính, gom gọn một chỗ; món chính ra trước, thu còn
  0,42 khung; cảnh Meet tắt `avoid_app_overlay` (FR-034, ADR-097).
- H: Người dùng gửi ảnh mẫu (bàn Coca-Cola Tết dày hàng, ảnh tạo bằng Gemini): "bạn học cách triển khai như hình này được không" →
  Đ: học phần làm được trong luật: chai thành cụm hai hàng so le (5 chai mỗi bên thay vì 3), thùng quà thu còn 0,38 khung (FR-035,
  ADR-098). Phần cần ảnh thật hoặc phải nới luật (lon rời, ly đá, hoa mai đào, lì xì, thùng chồng đôi, món chồng lên nhau) chờ
  người dùng quyết (`progress/OPEN.md`).

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại): FR-013, FR-019 đã làm rõ 2026-11-22
