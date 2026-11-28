# Đặc tả tính năng: Đổi ảnh sản phẩm ngay trên trang điều khiển giữa phiên live

- **Feature ID:** `012-product-image-upload` · **Branch:** `main` · **Ngày tạo:** 2026-11-20
- **Trạng thái:** Done <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1d (đổi sản phẩm khi tổng duyệt và demo); dùng lại ở M2 (live Shopee dài, đổi hàng trong ngày)
- **Mô tả gốc:** "Đổi ảnh sản phẩm ngay trên trang điều khiển (control page) giữa phiên live, không cần sửa file tay hay tạo video
  mới. Người vận hành chọn một sản phẩm trong file nội dung đang nạp, tải ảnh mới lên (png/webp/jpg), xem trước, và cảnh live (bàn bày
  sản phẩm + thẻ tên/giá của feature 009) đổi theo ảnh mới trong vài giây mà show không bị dừng. Phải ghi nguồn ảnh (provenance: ai
  gửi, ngày nhận, quyền dùng) vì quy định nội dung AI của Shopee (ADR-065, RISKS P9/P11) cấm logo bên thứ ba / ảnh không có quyền. Kèm
  luồng đổi sản phẩm nhanh: nạp file nội dung mới rồi gán ảnh cho các sản phẩm mới ngay trên trang điều khiển. Hiện 009 liệt kê 'sửa
  cảnh giữa phiên trên trang điều khiển' và 'chỉnh ảnh sản phẩm lúc live' là ngoài phạm vi; feature này mở phần tải/thay ảnh (không
  chỉnh sửa ảnh trong app)."

**Bối cảnh.** Feature 009 ghép bàn bày sản phẩm, ảnh sản phẩm và thẻ tên/giá vào khung hình ngay lúc phát, nên đổi ảnh **không cần
tạo lại video nhân vật**. Nhưng hiện muốn đổi ảnh phải chép file vào bộ cảnh của khách, sửa hồ sơ nguồn gốc bằng tay, rồi nạp lại file
nội dung để cảnh đọc lại. Việc này chậm và dễ sai giữa buổi live. Tên và giá đã đổi được trên trang điều khiển (nạp file nội dung mới,
FR-013 của 009); ảnh thì chưa. Người dùng muốn đổi sản phẩm kịp ngay trên trang điều khiển (yêu cầu 2026-11-20, lúc chạy demo2).

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Thay ảnh một sản phẩm đang bày trên bàn giữa phiên (Ưu tiên: P1)

Show đang chạy. Khách gửi ảnh mới cho kem chống nắng (ảnh đẹp hơn, hoặc bao bì mới). Người vận hành mở trang điều khiển, thấy danh sách
sản phẩm của file đang nạp với ảnh hiện tại của từng món. Họ chọn kem chống nắng, chọn file ảnh trên máy và đánh dấu xác nhận quyền dùng
(không phải điền nguồn ảnh). Trang hiện bản xem trước: món đó trên bàn với ảnh mới, cạnh ảnh đang live. Người vận hành bấm "Áp dụng";
vài giây sau người xem thấy ảnh mới trên bàn. Host vẫn nói liên tục, không có khoảng lặng lạ.

**Vì sao ưu tiên này:** đây là phần người dùng hỏi trực tiếp, và một mình nó đã đủ để demo việc "đổi ảnh không cần video mới". Story 2 và
3 dùng lại đúng thao tác này.

**Kiểm thử độc lập:** chạy show kịch bản ở chế độ nhân vật nhép miệng với file demo (3 sản phẩm, đủ ảnh). Giữa show thay ảnh của một
sản phẩm 10 lần (luân phiên các sản phẩm, có lần thay đúng sản phẩm đang được làm nổi). Mỗi lần ghi thời điểm bấm "Áp dụng" và thời điểm
ảnh mới xuất hiện trong khung hình gửi đi; so khoảng lặng giữa câu với một show không thay ảnh.

**Kịch bản chấp nhận:**
1. **Given** show đang chạy và bàn đang bày 3 sản phẩm, **When** người vận hành mở trang điều khiển, **Then** thấy đủ 3 sản phẩm theo
   thứ tự trong file, mỗi món kèm ảnh nhỏ đang live (hoặc ghi "chưa có ảnh").
2. **Given** đã chọn một sản phẩm, **When** chọn một file ảnh hợp lệ, **Then** trang hiện bản xem trước món đó trên bàn với ảnh mới;
   khung hình live chưa đổi.
3. **Given** bản xem trước đang hiện và đã xác nhận quyền dùng, **When** bấm "Áp dụng", **Then** khung hình live đổi sang ảnh mới trong
   vòng 2 giây, thẻ tên/giá giữ nguyên, show không dừng, không câu nào bị cắt.
4. **Given** chưa đánh dấu xác nhận quyền dùng, **When** bấm "Áp dụng", **Then** không áp dụng được, trang chỉ rõ còn thiếu xác nhận.
5. **Given** file ảnh hỏng, sai định dạng hoặc quá lớn, **When** chọn file, **Then** trang từ chối kèm lý do tiếng Việt, ảnh đang live
   giữ nguyên.
6. **Given** sản phẩm đang được làm nổi (009 FR-015), **When** thay ảnh của nó, **Then** món đó vẫn nổi và dùng ảnh mới ở cỡ nổi.
7. **Given** đã áp ảnh mới, **When** dừng rồi mở lại phiên với cùng bộ cảnh của khách, **Then** ảnh mới vẫn được dùng.

---

### User Story 2: Đổi bộ sản phẩm nhanh: nạp file mới rồi gán ảnh cho món mới (Ưu tiên: P2)

Khách muốn chuyển sang bán nhóm hàng khác ngay trong buổi. Người vận hành mở phần "chuẩn bị bộ sản phẩm mới" trên trang điều khiển,
chọn file nội dung mới. Trang liệt kê các sản phẩm của file mới; món nào đã từng có ảnh trong bộ cảnh của khách (cùng sản phẩm) thì dùng
lại ảnh cũ, món chưa có ảnh thì người vận hành tải ảnh như Story 1. Trong lúc chuẩn bị, live vẫn chạy bộ sản phẩm cũ, không đổi gì. Khi
đủ, người vận hành bấm "Áp dụng bộ mới" một lần: file nội dung và mọi ảnh lên live cùng lúc.

**Vì sao ưu tiên này:** đổi hàng là lý do chính người dùng cần tính năng; nhưng cần Story 1 trước vì nó dùng lại thao tác tải ảnh.

**Kiểm thử độc lập:** đang show với file demo, chuẩn bị file mới có 3 sản phẩm chưa có ảnh trong bộ cảnh, gán ảnh cho cả 3 (kiểm live
không đổi trong lúc chuẩn bị), rồi áp dụng một lần; bấm giờ cả quá trình; rồi chuẩn bị lại file cũ và kiểm 3 ảnh cũ tự có, không cần tải.

**Kịch bản chấp nhận:**
1. **Given** show đang chạy, **When** chọn file nội dung mới trong phần chuẩn bị, **Then** trong vòng 2 giây trang liệt kê các sản phẩm
   của file mới, ghi rõ món nào đã có ảnh, món nào còn thiếu, mỗi món thiếu có chỗ tải ảnh; khung hình live và file đang nạp chưa đổi.
2. **Given** một sản phẩm của file mới đã có ảnh trong bộ cảnh từ trước, **When** chọn file, **Then** bộ chuẩn bị tự dùng lại ảnh đó.
3. **Given** bộ chuẩn bị đã đủ, **When** bấm "Áp dụng bộ mới", **Then** trong vòng 2 giây khung hình live đổi sang thẻ và ảnh của bộ mới
   cùng lúc; sản phẩm không còn trong file mới biến mất khỏi bàn (như 009) nhưng ảnh vẫn còn trong bộ cảnh để dùng lại sau.
4. **Given** bộ chuẩn bị còn món thiếu ảnh, **When** bấm "Áp dụng bộ mới", **Then** trang hỏi lại, nêu tên các món thiếu ảnh; người vận
   hành xác nhận thì áp, món thiếu chỉ hiện thẻ tên/giá; hủy thì live giữ bộ cũ.
5. **Given** đổi bộ sản phẩm giữa show, **Then** không lúc nào khung hình live hiện ảnh của sản phẩm này trên thẻ tên/giá của sản phẩm
   khác, và không có khung hình nào trộn thẻ của bộ cũ với bộ mới.
6. **Given** đang chuẩn bị, **When** bấm "Hủy chuẩn bị", **Then** bộ chuẩn bị bỏ đi; ảnh đã tải vẫn còn trong bộ cảnh để dùng lại.

---

### User Story 3: Hoàn tác hoặc gỡ ảnh (Ưu tiên: P3)

Người vận hành lỡ áp ảnh sai (nhầm món, ảnh có logo của hãng khác). Họ bấm "Về ảnh trước" để quay lại ảnh vừa thay, hoặc "Gỡ ảnh" để
món đó chỉ còn thẻ tên/giá. Họ cũng xem được ảnh này áp lúc nào, đã xác nhận quyền dùng hay chưa.

**Vì sao ưu tiên này:** giảm hậu quả của thao tác nhầm giữa live. Không cần cho thao tác thay ảnh cơ bản.

**Kiểm thử độc lập:** thay ảnh một sản phẩm 2 lần, rồi hoàn tác 1 lần, rồi gỡ ảnh; mỗi bước kiểm khung hình live và thông tin ảnh hiện
trên trang.

**Kịch bản chấp nhận:**
1. **Given** sản phẩm đã được thay ảnh ít nhất một lần, **When** bấm "Về ảnh trước", **Then** ảnh trước đó quay lại live trong vòng 2 giây.
2. **Given** sản phẩm đang có ảnh, **When** bấm "Gỡ ảnh" và xác nhận, **Then** món đó chỉ còn thẻ tên/giá trên bàn trong vòng 2 giây;
   ảnh vẫn còn trong bộ cảnh để dùng lại.
3. **Given** một sản phẩm đang có ảnh, **When** mở chi tiết, **Then** thấy ảnh áp lúc nào và lúc xác nhận quyền dùng.

### User Story 4: Xem AI đang nói gì và dữ liệu sản phẩm đã nạp (Ưu tiên: P2)

Người vận hành đang theo dõi show trên trang điều khiển muốn biết AI vừa nói những câu gì (không chỉ câu đang nói), và muốn xem file nội
dung vừa nạp chứa gì cho từng sản phẩm (giá, phân loại, khuyến mãi, thông số, hỏi đáp, điều cấm nói) để đối chiếu với lời AI và kiểm
file trước khi áp bộ mới. Hiện trang chỉ hiện tên sản phẩm và một dòng câu đang nói, bị thay mỗi câu (người dùng hỏi 2026-11-20).

**Vì sao ưu tiên này:** người vận hành cần thấy AI có nói đúng dữ liệu không (Điều III) và file mới có đúng không trước khi áp (Story 2);
không phụ thuộc Story 1–3, làm được riêng.

**Kiểm thử độc lập:** chạy show kịch bản ở chế độ ảnh tĩnh với file demo; sau 2 phút kiểm danh sách câu đã nói khớp nhật ký phiên; mở chi
tiết từng sản phẩm, đối chiếu với file nội dung.

**Kịch bản chấp nhận:**
1. **Given** show đang chạy, **When** AI nói xong một câu, **Then** trong vòng 1 giây câu đó nằm đầu danh sách "AI vừa nói" trên trang
   điều khiển, kèm giờ và sản phẩm · chủ đề của đoạn; danh sách giữ ít nhất 50 câu gần nhất.
2. **Given** một câu bị guard chặn hay bị bỏ, **When** xem danh sách, **Then** câu đó không nằm trong "AI vừa nói" (nó vẫn ở mục câu bị
   chặn như hiện có).
3. **Given** file nội dung đã nạp, **When** mở một sản phẩm trong khung "Nội dung sản phẩm", **Then** thấy đúng dữ liệu của sản phẩm đó
   như hệ thống đã đọc từ file: giá hoặc bảng phân loại, khuyến mãi, thông số, hỏi đáp, điều cấm nói, mô tả, lời giới thiệu.
4. **Given** đang chuẩn bị bộ sản phẩm mới (Story 2), **When** mở một sản phẩm của bộ chuẩn bị, **Then** thấy dữ liệu của file mới, tách
   rõ với bộ đang live.
5. **Given** tải lại trang điều khiển giữa show, **When** trang mở xong, **Then** danh sách "AI vừa nói" vẫn có các câu gần nhất của show.

### Trường hợp biên

- **Thay ảnh khi show chưa bắt đầu, đang tạm dừng hoặc đã kết thúc:** được; cảnh xem trước của màn hình host (009 FR-010) đổi theo.
- **Phiên đang ở chế độ ảnh tĩnh** (cấu hình, hoặc tự về ảnh tĩnh khi nhép miệng lỗi): ảnh tĩnh có cảnh cũng đổi theo ảnh mới.
- **Cảnh đang tắt bằng cấu hình** (009 FR-009): trang điều khiển vẫn cho xem và chuẩn bị ảnh nhưng ghi rõ "cảnh đang tắt, ảnh chưa
  hiện trên live".
- **File nội dung bị thay trong lúc đang xem trước ảnh:** nếu sản phẩm đang chọn không còn trong file mới thì bản xem trước bị hủy kèm
  thông báo; không áp ảnh cho sản phẩm không còn tồn tại.
- **Hai lần áp ảnh cho cùng một sản phẩm gần nhau:** lần áp sau cùng thắng; live không bao giờ dừng ở ảnh của lần áp cũ hơn.
- **Ảnh JPEG hay ảnh còn nền** (không trong suốt): vẫn nhận, hiện nguyên khung ảnh trên bàn, không kéo méo; trang ghi chú "ảnh còn
  nền, trên bàn sẽ thấy cả nền" để người vận hành biết trước khi áp.
- **Ảnh trong suốt hoàn toàn hoặc gần như trống:** từ chối, vì trên live sẽ không thấy gì.
- **Ảnh động** (nhiều khung): từ chối (009: không có ảnh động).
- **Ảnh chụp bằng điện thoại có thông tin xoay:** hiện đúng chiều như khi xem ảnh trên máy.
- **Ảnh rất cao hoặc rất rộng:** thu cho vừa chỗ trên bàn như 009, không vươn lên che mặt host, nhãn "AI-GENERATED CONTENT" hay
  watermark. Ảnh quá rộng so với ô của món (thu vừa ô thì thấp hơn mức tối thiểu của 009) thì live chỉ hiện thẻ của món: trang điều khiển
  báo trước khi áp và cả sau khi áp (FR-004a, thêm 2026-11-20 sau T068).
- **Lưu ảnh lỗi** (đầy ổ đĩa, không ghi được): báo lỗi trên trang điều khiển, live giữ ảnh cũ, show không dừng.
- **Hai tab trang điều khiển cùng mở:** cả hai thấy cùng một trạng thái ảnh sau khi áp; không cần khóa riêng.
- **Cùng một ảnh dùng cho hai sản phẩm:** được, mỗi sản phẩm có bản ghi riêng.
- **Thay ảnh một món giữa lúc đang chuẩn bị bộ mới:** thay ảnh (Story 1) áp cho bộ đang live; bộ chuẩn bị nếu có cùng sản phẩm thì dùng
  ảnh mới nhất lúc bấm "Áp dụng bộ mới".
- **Nạp file nội dung theo cách cũ (không qua phần chuẩn bị) giữa lúc đang chuẩn bị:** bộ đang live đổi như 009; bộ chuẩn bị giữ nguyên,
  trang ghi rõ bộ đang live đã đổi.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

**Xem và chọn**

- **FR-001**: Trang điều khiển PHẢI liệt kê mọi sản phẩm của file nội dung đang nạp, theo thứ tự trong file, ghi rõ sản phẩm chính,
  kèm ảnh nhỏ của ảnh đang dùng trên bàn (hoặc "chưa có ảnh").
- **FR-002**: Người vận hành PHẢI chọn được một sản phẩm trong danh sách đó và tải lên một file ảnh từ máy, định dạng PNG, WebP hoặc
  JPEG. Mỗi sản phẩm có tối đa một ảnh trên bàn (như 009).

**Kiểm ảnh**

- **FR-003**: Hệ thống PHẢI từ chối ảnh hỏng, sai định dạng, ảnh động, ảnh trong suốt gần như hoàn toàn, file lớn hơn 10 MB hoặc cạnh dài
  hơn 4000 điểm ảnh (cùng giới hạn với bộ cảnh 009), kèm lý do tiếng Việt; ảnh đang live không đổi khi bị từ chối.
- **FR-004**: Ảnh không có nền trong suốt PHẢI vẫn được nhận và hiện nguyên khung, không kéo méo tỷ lệ; trang điều khiển PHẢI cảnh báo
  điều đó trước khi áp dụng.
- **FR-004a** (thêm 2026-11-20 sau T068): Khi ảnh quá rộng so với ô của món trên bàn, theo bố cục của bộ mà ảnh sẽ lên (bộ đang live
  hoặc bộ chuẩn bị), đến mức cảnh chỉ hiện thẻ, trang điều khiển PHẢI cảnh báo ngay khi nhận ảnh, trước khi áp dụng, cùng chỗ cảnh báo
  ảnh còn nền; nếu ảnh chỉ hiện được lúc AI đang nói về món đó (ô to hơn) thì cảnh báo ghi rõ điều đó. Ảnh vẫn được nhận và áp được.
  Món đang live mà cảnh không vẽ được ảnh PHẢI có cảnh báo trong danh sách ảnh, ghi đúng lý do (ô quá hẹp so với ảnh, hay không đủ chỗ
  dưới vùng mặt).

**Quyền dùng**

- **FR-005**: Người vận hành KHÔNG phải điền nguồn ảnh (người gửi, ngày nhận, đã chỉnh gì) và KHÔNG phải tải kèm ảnh gốc (làm rõ
  2026-11-20). Hệ thống tự ghi cho mỗi ảnh: lúc tải lên, lúc áp dụng, lúc xác nhận quyền dùng. Ảnh tải lên từ trang điều khiển PHẢI được
  bước kiểm bộ cảnh (009 FR-003) chấp nhận khi mở lại phiên, dù không có hồ sơ nguồn đầy đủ như 009 FR-002.
- **FR-006**: Người vận hành PHẢI đánh dấu một ô xác nhận trước khi áp dụng, với nội dung: ảnh do khách cung cấp, là ảnh chụp thật của
  chính sản phẩm; không chứa logo, ảnh người hay tài sản của bên thứ ba khi chưa được phép; không phải ảnh do AI tạo. Thiếu xác nhận thì
  không áp dụng được. Hệ thống ghi lại lúc xác nhận.
- **FR-007**: Ảnh tải lên PHẢI thuộc bộ cảnh của đúng khách của phiên; không có thao tác nào gán ảnh vào bộ cảnh của khách khác.

**Xem trước và áp dụng**

- **FR-008**: Trước khi áp dụng, trang điều khiển PHẢI hiện bản xem trước sản phẩm đó trên bàn với ảnh mới (cùng cỡ và vị trí như sẽ
  hiện trên live), đặt cạnh ảnh đang live; xem trước không làm đổi khung hình live. Người vận hành áp dụng hoặc hủy.
- **FR-009**: Sau khi bấm "Áp dụng", khung hình gửi đi PHẢI dùng ảnh mới trong vòng 2 giây, ở cả chế độ nhân vật nhép miệng và chế độ ảnh
  tĩnh; thẻ tên/giá, sản phẩm đang nổi và phụ đề giữ nguyên.
- **FR-010**: Thay ảnh PHẢI không làm dừng show, không cắt câu đang nói, không làm khoảng lặng giữa câu dài thêm quá mức ở SC-001.
- **FR-011**: Lỗi khi lưu hoặc ghép ảnh mới PHẢI không làm dừng phiên: live giữ ảnh cũ, trang điều khiển báo lỗi kèm lý do.
- **FR-012**: Ảnh đã áp PHẢI được giữ lại trong bộ cảnh của khách: mở lại phiên với cùng bộ cảnh vẫn dùng ảnh đó.

**Đổi bộ sản phẩm**

- **FR-013**: Trang điều khiển PHẢI có phần "chuẩn bị bộ sản phẩm mới": chọn file nội dung mới, trong vòng 2 giây liệt kê các sản phẩm
  của file đó, ghi rõ món đã có ảnh và món còn thiếu, mỗi món có chỗ tải ảnh như FR-002 (cùng kiểm ảnh FR-003, FR-004 và xác nhận
  FR-006). Trong lúc chuẩn bị, file nội dung đang nạp và khung hình live PHẢI không đổi (làm rõ 2026-11-20).
- **FR-014**: Ảnh của sản phẩm không còn trong file mới PHẢI được giữ lại trong bộ cảnh (không hiện trên bàn); khi file sau có lại sản
  phẩm đó thì bộ chuẩn bị tự dùng lại ảnh đó.
- **FR-015**: "Áp dụng bộ mới" PHẢI đổi file nội dung và mọi ảnh của bộ chuẩn bị lên live trong một lần, trong vòng 2 giây; không có khung
  hình nào ghép ảnh của sản phẩm này với thẻ tên/giá của sản phẩm khác, hay trộn thẻ bộ cũ với bộ mới. Còn món thiếu ảnh thì PHẢI hỏi lại
  trước khi áp. Lỗi khi áp thì live giữ nguyên bộ cũ (không áp nửa chừng).
- **FR-015a**: Người vận hành PHẢI hủy được bộ chuẩn bị; ảnh đã tải vẫn còn trong bộ cảnh.

**Hoàn tác và gỡ**

- **FR-016**: Người vận hành PHẢI quay lại được ảnh trước đó của một sản phẩm bằng một thao tác; ảnh trước hiện trên live trong vòng
  2 giây.
- **FR-017**: Người vận hành PHẢI gỡ được ảnh của một sản phẩm (có bước xác nhận) để món đó chỉ còn thẻ tên/giá; ảnh vẫn còn trong bộ cảnh.
- **FR-018**: Trang điều khiển PHẢI hiện cho ảnh đang dùng: lúc tải lên, lúc áp dụng, lúc xác nhận quyền dùng.

**Quan sát**

- **FR-019**: Hệ thống PHẢI ghi lại mỗi lần thay, hoàn tác, gỡ ảnh: thời điểm, sản phẩm, thao tác, kết quả, thời gian từ lúc bấm đến lúc
  ảnh lên khung hình; lần áp bộ mới ghi thêm số sản phẩm, số món thiếu ảnh. Kiểm tra trước demo (007) báo ảnh đang dùng mà thiếu xác
  nhận quyền dùng.

**Xem lời AI và dữ liệu sản phẩm** (Story 4, ghép vào 012 theo yêu cầu 2026-11-20)

- **FR-020**: Trang điều khiển PHẢI có danh sách "AI vừa nói": mỗi câu kịch bản đã gửi đi phát (không gồm câu bị guard chặn hay bị bỏ),
  mới nhất ở trên, kèm giờ và sản phẩm · chủ đề của đoạn; câu mới hiện trong vòng 1 giây; giữ ít nhất 50 câu gần nhất của show đang chạy
  hoặc vừa kết thúc.
- **FR-021**: Tải lại trang điều khiển PHẢI vẫn thấy các câu gần nhất của FR-020 (không chỉ câu đến sau lúc mở trang).
- **FR-022**: Khung "Nội dung sản phẩm" PHẢI cho mở từng sản phẩm để xem đúng dữ liệu hệ thống đã đọc từ file: giá hoặc bảng phân loại,
  khuyến mãi, thông số, hỏi đáp, điều cấm nói, mô tả, lời giới thiệu; hiện nguyên văn, không qua LLM. Đường link sản phẩm không cần hiện.
- **FR-023**: Phần chuẩn bị bộ sản phẩm mới (FR-013) PHẢI cho xem dữ liệu sản phẩm của file mới theo cùng cách FR-022, ghi rõ là bộ chuẩn
  bị, chưa lên live.

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): ảnh sản phẩm vẫn là ảnh tĩnh ghép vào khung hình ngay lúc phát (như 009),
  không tạo hay phát video dựng sẵn; nhãn "AI-GENERATED CONTENT", watermark và mặt host không bị che sau khi thay ảnh (vùng cấm 009
  FR-019 vẫn áp dụng); ảnh thuộc bộ cảnh của đúng một khách (FR-007).
- [x] Điều II (đồng ý / bảo mật): ảnh sản phẩm tải lên là dữ liệu của khách, lưu ngoài git; không có ảnh người thật nào được thêm vào
  cảnh (xác nhận ở FR-006, RISKS P14); trang điều khiển không hiện hay ghi bí mật nào.
- [x] Điều III (có căn cứ): ảnh là ảnh chụp thật của sản phẩm do khách gửi, không phải ảnh do AI tạo, người vận hành xác nhận ở FR-006
  (ràng buộc 7 và 8, RISKS P15 "gây hiểu nhầm"); không bắt ghi nguồn chi tiết (làm rõ 2026-11-20), nên khi có tranh chấp chỉ còn lúc xác
  nhận và file ảnh để đối chiếu. Tên, giá vẫn lấy nguyên văn từ file nội dung, feature này không sửa chữ trên thẻ.
- [x] Điều IV (adapter): mở rộng cảnh 009 và trang điều khiển; không sửa lõi show kịch bản hay đường câu → tiếng.
- [x] Điều VI (độ trễ): thay ảnh không nằm trên đường câu → tiếng; câu đầu (≤ 5 giây) không bị ảnh hưởng; khoảng lặng p95 không tăng
  quá 0,1 giây khi thay ảnh (SC-001). Ảnh lên live ≤ 2 giây sau khi áp dụng (FR-009).
- [x] Điều VII (đơn giản): không thêm dịch vụ, cơ sở dữ liệu hay phụ thuộc mới cho việc này; nếu plan thấy cần thì phải có ADR.
- [x] Điều VIII (quan sát được, chịu lỗi): FR-011, FR-019.

### Thực thể chính

- **Ảnh sản phẩm** (từ 009): ảnh tĩnh của một sản phẩm trong bộ cảnh của một khách; một sản phẩm có tối đa một ảnh đang dùng.
- **Phiên bản ảnh**: mỗi lần áp ảnh tạo một phiên bản mới cho sản phẩm; giữ các phiên bản trước để hoàn tác (FR-016) và dùng lại (FR-014).
- **Bản ghi ảnh**: gắn với từng phiên bản, hệ thống tự ghi: lúc tải lên, lúc áp dụng, lúc xác nhận quyền dùng.
- **Bản xem trước**: ảnh mới đặt vào chỗ của sản phẩm trên bàn, chỉ hiện trên trang điều khiển cho tới khi áp dụng hoặc hủy.
- **Bộ chuẩn bị**: file nội dung mới + ảnh gán cho từng sản phẩm của nó, chưa lên live cho tới khi "Áp dụng bộ mới" hoặc hủy.
- **Nhật ký đổi ảnh**: các lần thay, hoàn tác, gỡ với thời điểm và kết quả (FR-019).
- **Câu đã nói**: một câu kịch bản đã gửi đi phát, với giờ, đoạn (sản phẩm · chủ đề) (FR-020).

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Trong một show kịch bản 10 phút ở chế độ nhân vật nhép miệng có 10 lần thay ảnh, 100% lần ảnh mới xuất hiện trong khung hình
  gửi đi trong vòng 2 giây sau khi bấm "Áp dụng"; show không dừng lần nào; khoảng lặng giữa câu p95 không tăng quá 0,1 giây so với show
  10 phút không thay ảnh cùng cấu hình.
- **SC-002**: Với ảnh đã có sẵn trên máy, người vận hành thay xong ảnh một sản phẩm (chọn món, chọn file, xác nhận, xem trước, áp dụng)
  trong vòng 30 giây.
- **SC-003**: 100% ảnh từng xuất hiện trên live có lúc xác nhận quyền dùng; 0 ảnh áp dụng được khi thiếu xác nhận.
- **SC-004**: Với bộ file thử gồm ít nhất 6 loại file sai (hỏng, không phải ảnh, ảnh động, trong suốt hoàn toàn, quá 10 MB, cạnh quá 4000
  điểm ảnh), 100% bị từ chối kèm lý do và ảnh đang live không đổi.
- **SC-005**: Chuẩn bị file nội dung có 3 sản phẩm mới, gán ảnh cho cả 3 và áp dụng xong trong vòng 3 phút; trong lúc chuẩn bị khung
  hình live không đổi; sau khi áp, thẻ và ảnh của cả 3 món lên live trong cùng một lần đổi (≤ 2 giây); mở lại phiên thì cả 3 ảnh vẫn còn;
  chuẩn bị lại file cũ thì ảnh cũ tự có mà không phải tải lại.
- **SC-006**: Trong ít nhất 20 ảnh chụp khung hình live quanh các lần thay ảnh (cả ảnh rất cao, rất rộng, ảnh còn nền), 100% ảnh: nhãn
  "AI-GENERATED CONTENT", watermark và mặt host không bị che phần nào, và không ảnh nào ghép ảnh sản phẩm này với thẻ của sản phẩm khác.
- **SC-007**: Trong một show kịch bản 10 phút, 100% câu có trong nhật ký phiên là đã phát cũng có trong danh sách "AI vừa nói" (trong
  phạm vi 50 câu gần nhất), đúng thứ tự, chậm không quá 1 giây; 0 câu bị guard chặn lọt vào danh sách. Với file demo, dữ liệu mở xem của
  từng sản phẩm khớp 100% các mục trong file.

## Giả định

- **Ảnh tải lên là ảnh đã chỉnh xong ngoài app** (cắt nền, chỉnh cỡ… theo 009 FR-002). App không cắt nền, không chỉnh ảnh, không tạo ảnh.
  Ảnh chưa cắt nền vẫn dùng được nhưng sẽ hiện cả nền (FR-004).
- **Ảnh được lưu lâu dài vào bộ cảnh của khách** (FR-012), không chỉ cho phiên hiện tại: đổi hàng thường kéo dài sang phiên sau. File
  nội dung thì vẫn theo cách hiện có (nạp lại từ file mỗi phiên).
- **Giữ mọi phiên bản ảnh cũ** để hoàn tác và dùng lại; số phiên bản giữ và cách dọn do plan chọn (ảnh nhỏ, vài sản phẩm, không đáng
  lo về dung lượng ở giai đoạn demo).
- **Trang điều khiển chỉ người vận hành dùng trên máy chạy live**, không có đăng nhập, như các thao tác hiện có (nạp file nội dung).
- **Chỉ đổi ảnh sản phẩm.** Ảnh mặt bàn và bố cục giữ nguyên như 009 (sửa bộ cảnh rồi mở lại phiên).
- **Giới hạn file** theo đúng giới hạn bộ cảnh 009 (10 MB, cạnh dài 4000 điểm ảnh) để ảnh nào tải lên được cũng nạp được khi mở lại phiên.
- **Thời gian ảnh lên live ≤ 2 giây**, cùng mức với đổi thẻ khi nạp file nội dung (009 FR-013).

## Ngoài phạm vi

- Chỉnh ảnh trong app: cắt nền, cắt khung, xoay, chỉnh màu, thêm bóng (vẫn làm ngoài app như 009).
- Tạo ảnh sản phẩm bằng AI, hay tìm ảnh trên mạng.
- Nhiều ảnh cho một sản phẩm, ảnh xoay vòng, ảnh động, video sản phẩm.
- Đổi ảnh mặt bàn, kéo thả hay đổi bố cục bàn giữa phiên.
- Sửa tên, giá, khuyến mãi trên trang điều khiển (vẫn nạp file nội dung).
- Tải ảnh từ điện thoại hay máy khác qua mạng, hay cho khách tự tải ảnh.
- Kiểm tự động logo hay khuôn mặt trong ảnh (người vận hành xác nhận ở FR-006).
- Ghi nguồn ảnh chi tiết (người gửi, ngày nhận, đã chỉnh gì) và lưu ảnh gốc của khách (làm rõ 2026-11-20).

## Làm rõ

<!-- /sdd.clarify writes here. One subsection per session. -->

### Phiên 2026-11-20

- Q: Có bắt buộc ghi nguồn ảnh / tải kèm ảnh gốc khi thay ảnh giữa live không? → A: Không cần nguồn. Bỏ form nguồn ảnh (người gửi,
  ngày nhận, đã chỉnh gì, ảnh gốc); giữ một ô xác nhận quyền dùng vì quy định nội dung AI của Shopee (ADR-065, ràng buộc 8), hệ thống tự
  ghi lúc tải lên, áp dụng, xác nhận. Sửa US1, US3, FR-001, FR-005, FR-006, FR-018, FR-019, SC-002, SC-003, thực thể.
- Q: Đổi bộ sản phẩm giữa live: áp file mới ngay rồi gán ảnh dần, hay chuẩn bị đủ rồi áp một lần? → A: Chuẩn bị đủ file + ảnh rồi áp và
  hiển thị một lần. Sửa US2, FR-013–FR-015a, SC-005, trường hợp biên.
- Q: Trên trang điều khiển không thấy AI nói gì và file nội dung chứa gì; thêm vào 012 hay tách feature? → A: Ghép vào 012. Thêm US4,
  FR-020–FR-023, SC-007.
- Q (sau T068 trên GPU laptop): ảnh 1600×300 ở ô món phụ không hiện, live chỉ còn thẻ mà trang vẫn báo áp thành công; xử lý thế nào?
  → A: người dùng "sửa 071": cảnh báo người vận hành, giữ cách thu ảnh của 009. Thêm FR-004a, sửa trường hợp biên "Ảnh rất cao hoặc rất
  rộng", T071.

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại): đã trả lời cả 2 ngày 2026-11-20
