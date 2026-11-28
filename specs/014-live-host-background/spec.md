# Đặc tả tính năng: Nền sau người dẫn giống phòng live của shop

- **Feature ID:** `014-live-host-background` · **Branch:** `main` · **Ngày tạo:** 2026-11-23
- **Trạng thái:** In progress (2026-11-25; thêm FR-018, FR-019 cùng ngày; FR-019 thêm phần bày hàng né vùng che, ADR-087) <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1d (tổng duyệt và demo); bổ sung cho cảnh live của 009/013
- **Mô tả gốc:** "điều chỉnh background đằng sau sao giống buồi live", "đằng sau người nói", rồi sau bản dựng thử: "ý là kiểu nền làm theo
  ý tôi muốn chứ không phải 1 skill để triển khai cho nhiều cái sau này phải không?" và "ok làm cả hai, chạy /sdd.specify cho 014"
  (2026-11-23). "Cả hai" gồm: nền theo ý từng shop, dùng lại được cho khách sau; và công cụ đo độ thật của cảnh (013) đo thêm phần nền.

**Bối cảnh.** Sau 013, sản phẩm đã đứng trên mặt bàn như đồ thật, nhưng phía sau host vẫn là căn phòng có sẵn trong video gốc của nhân
vật: kệ trắng đầy mỹ phẩm, cây xanh và đèn LED vàng dưới kệ. Với shop bán Coca của demo, phòng này lạc chủ đề: người xem thấy shop mỹ phẩm
đang bán nước ngọt. Khung hình live là một đoạn video ngắn của nhân vật chạy lặp lại; host cử động trong đoạn đó (nghiêng đầu, đưa vai),
nên nền không thể thay bằng một khung cố định. Ảnh xem trước tĩnh của nhân vật là một cảnh quay khác với khung live.

Bản dựng thử bằng ảnh tĩnh (2026-11-23, ngoài code chính, hai khung 0 và 40 của đoạn lặp) thử bốn kiểu: làm mờ phòng cũ, kệ hàng bày sản
phẩm của chính shop, bảng màu shop có tên shop phía trên đầu host, và ảnh shop thật. Kết quả:
- thay được nền mà vẫn giữ host, mặt bàn và sản phẩm 013 phía trước;
- làm mờ phòng cũ trông tự nhiên nhất nhưng vẫn giữ màu phòng mỹ phẩm (bỏ khi làm rõ 2026-11-23); kệ hàng của shop hợp chủ đề nhất;
- cách tách người đơn giản dùng thử để lọt mảng kệ cũ cạnh vai, và ở khung host nghiêng đầu lọt cả dải đèn LED cũ trên đầu. Muốn sạch
  cần cách tách người tốt hơn, chuẩn bị một lần cho từng nhân vật.

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Thay phòng sau host bằng kệ hàng của shop, không lọt phòng cũ (Ưu tiên: P1)

Mình chọn kiểu nền "kệ hàng" cho bộ cảnh của khách: một dãy kệ đầy hàng có chiều sâu (kệ hai bên chạy vào trong, kệ cuối phía sau đầu
host), đèn sáng, màu rõ, bày kín chính sản phẩm của shop, hơi mềm cho hợp khung video của host; trông như kho hay shop thật đang có hàng,
không phải vài chai lẻ trên kệ trống (làm rõ 2026-11-25). Khi mở màn hình host, người xem thấy host nói và cử động như cũ trước nền mới; quanh tóc, vai, tay không còn mảng phòng cũ; mặt
bàn, sản phẩm trên bàn, nhãn "AI" vẫn như trước. Đổi sang khách khác chỉ cần đổi cấu hình nền của bộ cảnh, không sửa code.

**Vì sao ưu tiên này:** đây là phần người xem thấy ngay. Phòng mỹ phẩm sau lưng người bán Coca làm demo kém tin cậy. Kiểu này chỉ cần ảnh
sản phẩm đã bỏ nền mà shop đã có (012/013), không cần dữ liệu mới từ khách.

**Kiểm thử độc lập:** chọn "kệ hàng" cho bộ cảnh demo, chạy live, chụp 20 khung rải đều trong đoạn lặp (có khung host nghiêng đầu);
so với khung gốc thì phòng cũ không còn lọt quanh người, miệng vẫn mấp máy theo tiếng.

**Kịch bản chấp nhận:**
1. **Given** bộ cảnh chọn kiểu "kệ hàng" và nhân vật đã được chuẩn bị nền, **When** host đang nói live, **Then** phía sau là kệ bày các sản
   phẩm đang có ảnh của shop, có đèn ấm; không còn mảng kệ mỹ phẩm hay dải đèn cũ nào lọt ra, kể cả khi host nghiêng đầu.
2. **Given** nền mới đang bật, **When** xem mặt bàn và sản phẩm 013 phía trước host, **Then** mặt bàn giữ nguyên, sản phẩm vẫn đứng trên
   bàn với bóng đổ, nhãn "AI" vẫn nằm trên cùng.
3. **Given** hai khách có hai bộ cảnh khác nhau, **When** chuyển sang bộ cảnh của khách thứ hai, **Then** nền đổi theo cấu hình của khách đó,
   không mang sản phẩm hay tên của khách trước.

---

### User Story 2: Nền an toàn khi thiếu dữ liệu, có xem trước trên trang điều khiển (Ưu tiên: P2)

Trước giờ live, mình xem trên trang điều khiển: bộ cảnh đang dùng kiểu nền nào, một ảnh xem trước của khung live với nền đó, và cảnh báo
nếu nhân vật chưa được chuẩn bị nền hoặc phần chuẩn bị không khớp. Khi thiếu hay hỏng, live vẫn chạy với khung gốc thay vì vỡ hình.
Bước kiểm tra sẵn sàng trước buổi demo báo rõ việc này.

**Vì sao ưu tiên này:** một khung nền lỗi giữa buổi demo (mảng đen, người bị khoét) tệ hơn phòng cũ. Mình cần biết trước, không phải đoán.

**Kiểm thử độc lập:** xoá hoặc làm hỏng phần chuẩn bị nền của nhân vật, chạy kiểm tra sẵn sàng và mở live: có cảnh báo, live hiện khung
gốc, không lỗi hình.

**Kịch bản chấp nhận:**
1. **Given** nhân vật chưa được chuẩn bị nền, **When** chạy live với kiểu nền khác "gốc", **Then** live hiện phòng gốc, trang điều khiển và
   kiểm tra sẵn sàng báo "nhân vật chưa có nền" cùng cách khắc phục.
2. **Given** phần chuẩn bị nền không khớp đoạn lặp hiện tại (số khung hay cỡ khung khác), **When** khởi động, **Then** hệ thống không dùng
   nó, rơi về phòng gốc và báo lỗi cụ thể.
3. **Given** kiểu "kệ hàng" nhưng shop chưa có ảnh sản phẩm nào đã bỏ nền, **When** khởi động, **Then** live hiện phòng gốc và báo lý do.
4. **Given** mọi thứ hợp lệ, **When** mở trang điều khiển, **Then** thấy kiểu nền đang dùng và ảnh xem trước khung live với nền đó.

---

### User Story 3: Nền mang nhận diện của shop: bảng màu tên shop, ảnh shop thật (Ưu tiên: P4, sau demo)

*Làm rõ 2026-11-23: demo chỉ cần "kệ hàng" (US1); story này giữ trong spec nhưng làm sau buổi demo, không chặn mốc M1d.*

Với khách muốn nền riêng, mình chọn "bảng shop" (một tấm bảng màu chủ đạo của shop sau lưng host, tên shop phía trên đầu, hai bên là kệ
hàng) hoặc "ảnh shop" (ảnh chụp cửa hàng thật của khách, đã xác nhận quyền dùng). Nền không có logo của bên thứ ba, tên shop lấy đúng từ
dữ liệu, không tự đặt.

**Vì sao ưu tiên này:** làm demo giống shop của khách hơn, nhưng cần dữ liệu khách đưa (tên shop, ảnh) và nhiều rủi ro quy định hơn nên
đứng sau US1.

**Kiểm thử độc lập:** cấu hình "bảng shop" với tên shop mẫu, và "ảnh shop" với một ảnh có xác nhận quyền dùng; chụp khung live và kiểm tra
tên đúng, không bị đầu host che, ảnh phủ kín nền không méo.

**Kịch bản chấp nhận:**
1. **Given** kiểu "bảng shop" và có tên shop, **When** live, **Then** bảng màu chủ đạo của shop hiện sau host, tên shop đọc được phía trên
   đầu host, không bị đầu che ở mọi khung của đoạn lặp.
2. **Given** kiểu "bảng shop" nhưng chưa có tên shop, **When** khởi động, **Then** bảng hiện không chữ (không tự đặt tên) và có cảnh báo.
3. **Given** kiểu "ảnh shop" với ảnh đã xác nhận quyền dùng, **When** live, **Then** ảnh phủ kín vùng nền, giữ đúng tỷ lệ (cắt bớt chứ không
   kéo méo), mờ và chỉnh sáng nhẹ cho hợp với host.
4. **Given** ảnh shop chưa xác nhận quyền dùng, **When** áp dụng, **Then** không áp được, trang chỉ rõ còn thiếu xác nhận.
5. **Given** ảnh shop do AI tạo (ghi nguồn "AI tạo") đã được người vận hành xác nhận không còn logo hay chữ đọc được, **When** live,
   **Then** nền được làm mờ ít nhất mức tối thiểu cho ảnh AI (dù cấu hình độ mềm thấp hơn), nhãn AI vẫn hiện, sản phẩm trên bàn vẫn là
   ảnh thật của khách (làm rõ 2026-11-28, ADR-100).

---

### User Story 4: Công cụ đo độ thật của cảnh đo cả phần nền (Ưu tiên: P3)

Khi chỉnh cảnh cho khách mới, mình chạy công cụ đo độ thật (đang dùng cho sản phẩm trên bàn, 013) và nhận thêm các chỉ số phần nền: chỗ
lọt phòng cũ quanh người, độ mờ của nền so với người, độ sáng và màu ánh sáng của nền so với người, kèm ảnh so sánh các phương án đặt cạnh
nhau. Công cụ chỉ dựng ảnh thử, không sửa cấu hình hay code.

**Vì sao ưu tiên này:** giúp chỉnh nhanh cho khách sau, nhưng demo hiện tại vẫn chỉnh bằng mắt được.

**Kiểm thử độc lập:** chạy công cụ cho từng kiểu nền trên vài khung của đoạn lặp; báo cáo có các chỉ số nền, cờ cảnh báo khi cố ý làm sai
(nền sắc hơn người, nền sáng hơn người nhiều).

**Kịch bản chấp nhận:**
1. **Given** một kiểu nền và nhân vật đã chuẩn bị nền, **When** chạy công cụ trên các khung chọn, **Then** báo cáo cho mỗi khung số điểm ảnh
   phòng cũ còn lọt quanh người và đánh dấu vị trí trên ảnh.
2. **Given** nền sắc nét hơn người, **When** chạy công cụ, **Then** có cờ "nền sắc hơn người" với tỷ lệ đo được.
3. **Given** nền sáng hoặc ấm/lạnh khác hẳn người, **When** chạy công cụ, **Then** có cờ về độ sáng hoặc màu ánh sáng.

### Trường hợp biên

- Host giơ tay hoặc nghiêng người ra ngoài vùng thường thấy: phần người đó vẫn phải giữ nguyên, không bị nền mới đè lên.
- Tóc mảnh, viền vai mờ do chuyển động: chuyển tiếp mềm, không có viền cứng hay quầng sáng.
- Nhân vật mới hoặc đoạn lặp được làm lại: phần chuẩn bị nền cũ không còn khớp, phải bị từ chối (US2).
- Bộ cảnh tắt (cảnh live không bật): không đổi gì so với hiện nay.
- Ảnh xem trước tĩnh của nhân vật (khi chưa chạy lip-sync) là cảnh quay khác: nền chỉ áp khi ảnh đó cũng đã được chuẩn bị nền, nếu không thì
  giữ nguyên ảnh.
- Shop chỉ có một sản phẩm có ảnh: kệ hàng lặp lại món đó, không bịa thêm món khác.
- Ảnh shop có người, logo bên thứ ba hoặc chữ quảng cáo: người vận hành chịu trách nhiệm xác nhận quyền dùng (giống ảnh sản phẩm 012);
  hệ thống không tự nhận diện logo.
- Nền mới bị lỗi giữa buổi live (lọt phòng cũ, khoét người): không có công tắc tắt nhanh (làm rõ 2026-11-24). Lỗi ghép thì hệ thống tự
  về phòng gốc (FR-010); lỗi chỉ thấy bằng mắt thì người vận hành đổi bộ cảnh về "gốc" và khởi động lại. Vì vậy phần chuẩn bị nền phải
  được duyệt bằng mắt trước buổi live.
- Nền có sản phẩm (kệ hàng): không được hiểu nhầm là shop có thêm hàng hay số lượng tồn kho nào; chỉ bày những món có trong dữ liệu.
  Kệ kín bằng nhiều đơn vị của chính các món đó là trưng bày, không có chữ hay số lượng (FR-007).
- Vùng che của app Shopee đo từ một ảnh chụp màn hình điện thoại (máy dọc 9:20, 2026-11-25). Điện thoại khác tỷ lệ, hay app đổi giao diện
  thì vùng che xê dịch. TODO: kiểm lại bằng một buổi live thử trên Shopee hoặc trên điện thoại thật, xem app phủ kín (cắt hai bên) hay
  co khung (có viền đen) (FR-019).

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

- **FR-001**: Hệ thống PHẢI cho chọn kiểu nền sau host theo từng bộ cảnh: "gốc" (không đổi), "kệ hàng", "bảng shop", "ảnh shop".
  Mặc định là "gốc" để bộ cảnh cũ không đổi khi chưa cấu hình. Không có kiểu chỉ làm mờ phòng gốc (làm rõ 2026-11-23).
- **FR-002**: Hệ thống PHẢI thay vùng phòng phía sau host ở **mọi khung** của đoạn lặp, theo đúng dáng host ở từng khung (host cử động).
- **FR-003**: Phần tách người khỏi phòng PHẢI được chuẩn bị một lần cho mỗi nhân vật, trước giờ live, cho mọi khung của đoạn lặp; phần
  chuẩn bị này không chứa tiếng hay miệng. Miệng, hình và tiếng của host vẫn được sinh thời gian thực trong lúc live như hiện nay.
- **FR-004**: Vùng người PHẢI giữ nguyên điểm ảnh gốc; chỗ giáp người và nền PHẢI chuyển tiếp mềm (không viền cứng, không quầng phòng cũ).
- **FR-005**: Mặt bàn trong khung và mọi thứ của cảnh live phía trước host (sản phẩm, bóng đổ, thẻ, giá dán) PHẢI giữ như trước; nhãn "AI"
  PHẢI nằm trên cùng và không bị nền ảnh hưởng.
- **FR-006**: Nền mới PHẢI có độ sáng, màu ánh sáng gần với ánh sáng trên người host, và độ mềm (mờ) nhẹ chỉnh được theo bộ cảnh, mặc
  định nhẹ cho hợp độ mềm của khung video host, đặt 0 là tắt; để host không trông như bị dán lên.
- **FR-007**: Kiểu "kệ hàng" PHẢI chỉ bày ảnh sản phẩm đã bỏ nền của chính shop (theo dữ liệu đang nạp); không thêm sản phẩm, logo, giá
  hay chữ nào không có trong dữ liệu. Lặp lại nhiều đơn vị của chính các sản phẩm đó cho kín kệ là cách trưng bày, không phải thông tin
  tồn kho: nền không ghi số lượng hay chữ nào (làm rõ 2026-11-25).
- **FR-008**: Kiểu "bảng shop" PHẢI dùng màu chủ đạo của bộ cảnh và tên shop lấy từ một mục "tên shop" trong file dữ liệu sản phẩm khách
  đưa (cùng nguồn với tên, giá sản phẩm); file không có mục này thì không ghi chữ. Trang điều khiển không nhập hay sửa tên shop.
- **FR-009**: Kiểu "ảnh shop" PHẢI chỉ dùng ảnh đã được người vận hành xác nhận quyền dùng, ghi lại ai xác nhận và lúc nào (như ảnh sản
  phẩm 012); ảnh phủ kín vùng nền, giữ tỷ lệ, cắt bớt chứ không kéo méo.
- **FR-009a**: Ảnh shop PHẢI ghi nguồn: "ảnh thật" hoặc "AI tạo". Ảnh "AI tạo" chỉ là cảnh cửa hàng chung (không người, không sản phẩm
  của khách, không logo bên thứ ba đọc được), người vận hành xác nhận điều đó khi đưa ảnh vào, và hệ thống PHẢI làm mờ ảnh này ít nhất một
  mức tối thiểu cố định để chữ và logo trên kệ không đọc được. Sản phẩm của khách trên bàn hay trên nền không bao giờ dùng ảnh AI tạo
  (ADR-100).
  Ngoại lệ duy nhất (2026-11-28, ADR-102): cảnh lớp OBS cho demo Meet/YouTube đặt `background.as_is: true`, ảnh nền là đúng ảnh shop
  OBS đã hiện nét dưới host, nên hệ thống gửi ảnh giữ nguyên (không làm mờ, không chỉnh sáng) và cảnh báo `background_as_is` ở mọi lần
  nạp cảnh. Cảnh có `as_is` không bao giờ dùng cho Shopee.
- **FR-010**: Khi phần chuẩn bị nền của nhân vật thiếu, hỏng hoặc không khớp đoạn lặp, hệ thống PHẢI hiện phòng gốc, không lỗi hình, và
  báo lý do cụ thể ở trang điều khiển và bước kiểm tra sẵn sàng.
- **FR-011**: Khi kiểu nền đã chọn thiếu dữ liệu (không có ảnh sản phẩm cho "kệ hàng", không có ảnh cho "ảnh shop"), hệ thống PHẢI hiện
  phòng gốc và báo lý do.
- **FR-012**: Trang điều khiển PHẢI hiện kiểu nền đang dùng, trạng thái phần chuẩn bị nền của nhân vật và một ảnh xem trước khung live với
  nền đó.
- **FR-013**: Nền PHẢI thuộc về bộ cảnh của đúng một khách; đổi bộ cảnh thì đổi nền, không mang sản phẩm, tên hay ảnh của khách khác.
- **FR-014**: Màn hình đưa vào OBS (006) PHẢI có cùng nền như màn hình host.
- **FR-015**: Mỗi lần khởi động, hệ thống PHẢI ghi lại kiểu nền đang dùng, có dùng phần chuẩn bị nền hay không và lý do rơi về nếu có.
- **FR-016**: Công cụ đo độ thật của cảnh PHẢI đo thêm cho phần nền: số điểm ảnh phòng cũ còn lọt quanh người (kèm ảnh đánh dấu), tỷ lệ
  độ sắc nét nền/người, chênh độ sáng và màu ánh sáng nền/người; và dựng được ảnh so sánh các kiểu nền. Công cụ không sửa cấu hình hay code.
- **FR-018**: Kiểu "kệ hàng" PHẢI trông như dãy kệ đầy hàng: các tầng kệ bày sát nhau kín bề ngang, có chiều sâu (kệ hai bên chạy vào trong
  và kệ cuối nhỏ hơn, tối hơn), độ tương phản và màu đủ rõ, không bạc màu khi chỉnh theo độ sáng của phòng cũ. Độ mềm mặc định vẫn không
  được làm nền sắc hơn người (FR-006, công cụ đo FR-016). Vẫn vẽ một lần lúc khởi động, cùng kết quả mỗi lần (làm rõ 2026-11-25).
- **FR-019**: Khi phát lên Shopee (OBS), nhãn "AI" PHẢI nằm ở chỗ giao diện app Shopee không che khi xem live trên điện thoại dọc: vị trí `shopee-top` ở giữa, ngay dưới dải
  tiêu đề và tên shop của app, phía trên đầu host, xuống hai dòng khi một dòng không vừa dải trống đó. Các vùng app che (tiêu đề và tên
  shop, nhãn và thẻ sản phẩm ghim bên trái, ô quà thưởng bên phải, bình luận và ô chat phía dưới) PHẢI được ghi thành một bảng theo tỷ lệ
  màn hình, có giả định cách app cắt khung; công cụ đo độ thật PHẢI báo khi nhãn AI hoặc sản phẩm trên bàn nằm trong các vùng đó, và vẽ
  các vùng lên ảnh vùng. Vị trí nhãn vẫn chọn được bằng cấu hình như trước (làm rõ 2026-11-25). Buổi demo qua Meet không có giao diện app nên
  mặc định là `top-center`, một dòng (ADR-090, sửa 2026-11-25: người dùng thấy nhãn hai dòng nhỏ và mờ). Khi bộ cảnh bật khóa
  `layout.avoid_app_overlay` (cách bày `showcase`), sản phẩm trên bàn PHẢI đứng lùi vào trong bàn để ảnh sản phẩm không nằm dưới
  bình luận và ô chat của app: cả cụm co chiều sâu theo cùng một tỷ lệ nên món chính vẫn đứng trước các món sau; bục và bóng được nằm
  dưới vùng che; mọi món vẫn đứng trên mặt bàn (bổ sung 2026-11-25, ADR-087).

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): hình và tiếng host vẫn sinh thời gian thực; phần chuẩn bị một lần cho nhân vật chỉ
  là vùng người trong đoạn lặp, giống bước chuẩn bị nhân vật đang có, không phải video quay sẵn. Nhãn "AI" ghép trong khung, nằm trên nền.
  Nền thuộc một khách (FR-013).
- [x] Điều II (đồng ý / bảo mật): ảnh shop chỉ dùng khi có xác nhận quyền dùng (FR-009); không logo bên thứ ba; ảnh shop, tên shop là dữ
  liệu khách, không đưa vào git. Không đổi gì về khuôn mặt, giọng của host đã có đồng ý.
- [x] Điều III (trả lời có căn cứ): nền không được gợi ý thông tin sai về hàng (FR-007): chỉ bày món có trong dữ liệu, không thêm giá, khuyến
  mãi hay số lượng.
- [x] Điều IV (adapter trước): mỗi kiểu nền là một lựa chọn cấu hình; thêm kiểu mới không sửa phần lõi của pipeline.
- [x] Điều V (test trước): logic chọn kiểu, rơi về và ghép nền kiểm thử được không cần GPU, trên khung mẫu.
- [x] Điều VI (độ trễ): không thêm độ trễ vào câu đầu (≤ 5 giây) hay khoảng lặng (p95 ≤ 1,5 giây); tốc độ khung hình live không được giảm
  đáng kể (SC-003).
- [x] Điều VII (đơn giản trước): nếu cách tách người tốt hơn cần thêm thư viện hay tải mô hình thì phải có ADR và kiểm tra giấy phép dùng
  thương mại trước.
- [x] Điều VIII (quan sát được): ghi log kiểu nền, trạng thái chuẩn bị và lý do rơi về (FR-015).

### Thực thể chính

- **Cấu hình nền**: thuộc một bộ cảnh; gồm kiểu nền, độ mờ, độ sáng, và tuỳ kiểu: danh sách món bày trên kệ (lấy từ dữ liệu), tên shop,
  ảnh shop kèm xác nhận quyền dùng. Tên shop không nằm trong cấu hình nền mà đọc từ file dữ liệu sản phẩm (mục "tên shop").
- **Phần chuẩn bị nền của nhân vật**: vùng người cho từng khung của đoạn lặp, gắn với đúng một nhân vật và đúng đoạn lặp đó (số khung, cỡ
  khung); có trạng thái hợp lệ / thiếu / không khớp.
- **Ảnh shop**: ảnh do khách đưa hoặc do AI tạo (nguồn), người xác nhận quyền dùng, thời điểm xác nhận.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Trên 20 khung chọn ngẫu nhiên của đoạn lặp (có cả khung host nghiêng đầu), không khung nào còn mảng phòng cũ quanh người mà
  người xem nhận ra ở cỡ màn hình điện thoại; công cụ đo (US4) báo không có mảng lọt lớn hơn một ngưỡng chốt ở bước plan.
- **SC-002**: Không khung nào trong 20 khung đó bị khoét mất phần người (tóc, tai, vai, tay) thấy được bằng mắt.
- **SC-003**: Tốc độ khung hình live khi bật nền giảm không quá 10% so với khi tắt, đo trên cùng máy và cùng nhân vật.
- **SC-004**: Câu đầu tiên và khoảng lặng giữa các câu của show kịch bản vẫn đạt ngân sách của Hiến pháp (≤ 5 giây; p95 ≤ 1,5 giây).
- **SC-005**: Khi xem ảnh trước/sau ở cỡ điện thoại, người dùng (chủ dự án) đánh giá nền "kệ hàng" hợp shop của khách hơn phòng gốc.
- **SC-006**: Thiếu hoặc hỏng phần chuẩn bị nền thì 100% lần khởi động vẫn hiện phòng gốc và có cảnh báo, không lần nào lỗi hình.
- **SC-007**: Đổi sang bộ cảnh của khách khác chỉ cần đổi cấu hình, không sửa code, và xong trong dưới 10 phút khi nhân vật đã được chuẩn bị
  nền.
- **SC-008**: Với bảng vùng che của app Shopee (FR-019), hộp nhãn AI ở `shopee-top` không giao vùng che nào và không che mặt host; khi bật `avoid_app_overlay`, hộp ảnh của mọi sản phẩm
  trên bàn không giao vùng bình luận và ô chat (ADR-087); ảnh
  trước/sau của kệ hàng ở cỡ điện thoại được người dùng đánh giá gần mức live AI thật trên Shopee mà họ đưa làm chuẩn (2026-11-25).

## Giả định

- Phần chuẩn bị nền làm trên laptop dev (hoặc máy chạy live), miễn phí, một lần cho mỗi nhân vật; mất vài phút là chấp nhận được.
- Cách tách người đơn giản đã thử trong bản dựng thử không đủ sạch; bước plan sẽ chọn cách tách người tốt hơn, kiểm tra giấy phép dùng
  thương mại và ghi ADR trước khi tải hay cài gì thêm (CLAUDE.md, Điều VII). Mô hình chỉ dùng cho nghiên cứu (như bộ dữ liệu của bộ bỏ nền
  013, RISKS L15) không được chọn.
- Mặt bàn trong khung gốc luôn giữ nguyên; nền chỉ thay phần phía trên mép bàn.
- Phòng gốc là chỗ rơi về duy nhất khi thiếu dữ liệu hay phần chuẩn bị nền: đúng như live đang chạy, không có gì mới để lỗi.
- Độ mềm, độ sáng của nền có giá trị mặc định hợp khung demo, chỉnh được theo bộ cảnh; giá trị cụ thể chốt ở plan bằng công cụ đo (US4).
- Nền mới khác hẳn phòng cũ nên chỗ tách người chưa sạch lộ rõ hơn so với khi chỉ làm mờ; chất lượng tách người là điều kiện của SC-001/SC-002.
- Ảnh xem trước trên trang điều khiển là ảnh tĩnh dựng từ một khung của đoạn lặp, không cần chạy lip-sync.
- Chọn kiểu nền (kể cả "gốc") làm trước giờ live rồi khởi động lại; trong lúc live không đổi hay bật/tắt nền (làm rõ 2026-11-24).

## Ngoài phạm vi

- Thay đổi chính người host (quần áo, ánh sáng trên mặt, dáng ngồi) hay mặt bàn.
- Nền động (video, đèn nhấp nháy, chữ chạy) và nhiều lớp chiều sâu chuyển động theo đầu host.
- Tự nhận diện logo bên thứ ba hay người lạ trong ảnh shop (người vận hành xác nhận quyền dùng).
- Tự sinh ảnh shop bằng AI tạo ảnh ngay trong hệ thống (người vận hành tự tạo ngoài hệ thống rồi đưa vào như FR-009a; làm rõ 2026-11-28).
- Thay nền cho nhân vật chưa được chuẩn bị nền (rơi về phòng gốc).
- Kiểu nền chỉ làm mờ phòng gốc: giữ màu và ánh sáng của phòng mỹ phẩm nên không đạt mục tiêu nền hợp shop (làm rõ 2026-11-23).

## Làm rõ

### Phiên 2026-11-23
- Q: Có giữ kiểu nền "làm mờ" (giữ phòng gốc, làm mờ) không? → A: Bỏ, vì đang làm nền mới; thiếu dữ liệu thì rơi về phòng gốc. Nền mới vẫn
  có độ mềm nhẹ chỉnh được, đặt 0 là tắt (FR-001, FR-006, FR-011, US1, US2).
- Q: Demo cần những kiểu nền nào? → A: Chỉ "kệ hàng" (US1). "Bảng shop" và "ảnh shop" (US3, FR-008, FR-009) giữ trong spec, làm sau demo
  (US3 hạ xuống P4).
- Q: Tên shop cho "bảng shop" lấy từ đâu? → A: Một mục "tên shop" trong file dữ liệu sản phẩm khách đưa; không nhập trên trang điều khiển
  (FR-008, thực thể Cấu hình nền).
- Q: Có cần đổi kiểu nền ngay lúc đang live? → A: Bật/tắt nền khi đang live: trên trang điều khiển chuyển giữa "gốc" và kiểu đã cấu hình,
  áp ngay không dừng show, để cứu nhanh khi nền lỗi giữa buổi. Đổi sang kiểu khác vẫn chọn trước và khởi động lại (FR-017, US2 kịch bản 5,
  Trường hợp biên, Giả định). *Thay bởi phiên 2026-11-24.*

### Phiên 2026-11-24
- Q: Có cần bật/tắt nền khi đang live (hỏi lại lúc duyệt plan, ADR-084)? → A: Không. Bỏ FR-017 và US2 kịch bản 5; kiểu nền (kể cả "gốc")
  chỉ chọn trước giờ live rồi khởi động lại. Lỗi ghép thì hệ thống tự về phòng gốc (FR-010) (Trường hợp biên, Giả định).

### Phiên 2026-11-25
- Người dùng đưa ảnh chụp một live AI thật trên Shopee và nhận xét cảnh mình "hơi kém hơn"; chọn làm trước hai điểm: nền sau host và
  vùng app Shopee che khung.
- Q: Kệ hàng sau host cần trông thế nào? → A: Như kho hay shop thật đầy hàng: kệ kín, có chiều sâu, đèn sáng, màu rõ; không sao chép bảng
  hiệu hay logo của hãng khác trong ảnh tham khảo (US1, FR-007, FR-018, Điều II).
- Q: Lặp lại sản phẩm của shop cho kín kệ có bị coi là nói sai tồn kho? → A: Không, đó là trưng bày; nền không có chữ hay số lượng (FR-007,
  Trường hợp biên).
- Q: Nhãn AI ở giữa trên (ADR-076) bị dải tiêu đề của app Shopee đè lên thì sao? → A: Dời mặc định xuống dải trống giữa tiêu đề app và đầu
  host, hai dòng nếu cần; ghi bảng vùng che và cho công cụ đo báo khi nhãn hay sản phẩm nằm trong vùng che (FR-019, SC-008).
- Q: Nhãn hai dòng ở `shopee-top` trông nhỏ và mờ trên Meet; để một dòng được không? → A: Được: demo Meet mặc định `top-center` một dòng;
  `shopee-top` để dành cho lúc phát lên Shopee qua OBS (ADR-090, 2026-11-25).

### Phiên 2026-11-28
- Người dùng xem bản ghép thử (nền cửa hàng do Gemini tạo sau host, sản phẩm thật cắt nền đặt trên bàn) và chọn làm "ảnh shop" trước, kể cả
  cho demo.
- Q: Ảnh shop do AI tạo có dùng được không (trước đây ngoài phạm vi)? → A: Được, với điều kiện: ghi nguồn "AI tạo", chỉ là cảnh cửa hàng
  chung, người vận hành xác nhận không còn logo hay chữ đọc được, hệ thống làm mờ tối thiểu; sản phẩm của khách luôn là ảnh thật
  (FR-009a, US3 kịch bản 5, ADR-100).

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại)
