# Đặc tả tính năng: AI host chuyển động tự nhiên, nhép miệng realtime trên laptop

- **Feature ID:** `005-lipsync-livetalking` · **Branch:** `main` (ADR-027) · **Ngày tạo:** 2026-10-31
- **Trạng thái:** In progress (2026-11-07) <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1b (chạy tạm trên GPU laptop theo ADR-023)
- **Mô tả gốc:** "005-lipsync-livetalking: AI host nhép miệng realtime theo giọng TTS, chạy trên GPU laptop GTX 1650 Ti 4GB (ADR-023).
  Ưu tiên làm ra nhân vật nhìn thấy được và nhép miệng đúng trước; tốc độ/FPS/độ trễ bàn sau (chấp nhận chậm). Vẫn sinh realtime,
  có nhãn AI trong frame, là adapter AvatarRenderer mới cắm vào pipeline 001."
- **Sửa phạm vi 2026-11-03:** người dùng muốn "người ảo sống động hơn" và "theo loại AI host đang dùng trên Shopee Live để làm nhanh".
  Loại phổ biến hiện nay là nhân vật 2D chạy trên **video nền có chuyển động tự nhiên**, miệng được tạo realtime theo giọng, có thư viện
  clip động tác. Người dùng chọn hướng **gương mặt tạo bằng AI** (không quay người thật). Clip nền tạo một lần từ ảnh gương mặt trên
  GPU cloud miễn phí, Kaggle trước rồi Colab (ADR-036). Thay câu trả lời "một ảnh chân dung, chỉ cử động miệng" của phiên làm rõ 2026-10-31.

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Nhân vật chuyển động tự nhiên và nhép miệng theo một đoạn tiếng nói (Ưu tiên: P1)

Mình tạo trước một **gương mặt bằng AI** (không phải người thật) và từ ảnh đó tạo một bộ **clip nền** ngắn, không tiếng: một clip chờ
(chớp mắt, thở, nghiêng đầu nhẹ) và một clip đang nói (đầu, vai và thân cử động như người đang nói, khung nửa người). Chuẩn bị nhân vật trên laptop từ ảnh và
bộ clip đó. Mở màn hình host: nhân vật hiện lên ở trạng thái chờ, có chuyển động nhẹ chứ không đứng im như ảnh, góc hình có nhãn "AI".
Đưa vào một đoạn tiếng nói tiếng Việt: nhân vật chuyển sang clip đang nói và mở miệng theo đúng đoạn tiếng đó, phần miệng được tạo ngay
lúc nói. Nói xong, nhân vật trở về trạng thái chờ.

**Vì sao ưu tiên này:** người dùng muốn nhân vật "sống động hơn" ảnh tĩnh và giống loại AI host đang chạy trên Shopee Live. Đây là lát cắt
nhỏ nhất cho thấy điều đó, không cần LLM, comment hay giọng thật.

**Kiểm thử độc lập:** chỉ cần nhân vật đã chuẩn bị, màn hình host và vài đoạn tiếng nói mẫu. Để nhân vật chờ vài phút, phát từng đoạn
tiếng, nhìn miệng có khớp tiếng không, chỗ lặp hoặc chuyển clip có giật không, và nhãn "AI" có nằm trong hình không.

**Kịch bản chấp nhận:**
1. **Given** nhân vật đã chuẩn bị xong và màn hình host đang mở, **When** chưa có tiếng nói nào, **Then** nhân vật ở trạng thái chờ,
   miệng khép, có chuyển động nhẹ của clip chờ, có nhãn "AI" trong hình.
2. **Given** màn hình host đang mở, **When** đưa vào một đoạn tiếng nói tiếng Việt khoảng 10 giây, **Then** nhân vật chuyển sang clip
   đang nói và nhép miệng theo đoạn đó từ đầu đến cuối, người xem nghe tiếng và thấy miệng khớp nhau, không có lúc tiếng đi trước hình rõ rệt.
3. **Given** nhân vật đang nhép miệng, **When** đoạn tiếng kết thúc, **Then** nhân vật về clip chờ, không bị đứng hình ở khung miệng mở.
4. **Given** nhân vật ở trạng thái chờ lâu hơn độ dài clip chờ, **When** clip chờ lặp lại, **Then** chỗ lặp không có bước nhảy hình thấy rõ.
5. **Given** ảnh gương mặt hoặc một clip nền không có đúng một khuôn mặt rõ ở mọi khung hình (che mặt, quay nghiêng quá, nhiều người,
   mặt biến dạng), **When** chuẩn bị nhân vật, **Then** việc chuẩn bị bị từ chối kèm lý do (tên clip, vị trí khung hình), không tạo ra nhân vật hỏng.
6. **Given** ảnh gương mặt hoặc một clip nền chưa có hồ sơ nguồn gốc, **When** chuẩn bị nhân vật, **Then** việc chuẩn bị bị từ chối.

---

### User Story 2: Nhân vật thay ảnh tĩnh trong show kịch bản và đường trả lời comment (Ưu tiên: P2)

Mình chọn chế độ "nhân vật nhép miệng" thay cho "ảnh tĩnh" khi mở phiên. Mọi thứ của show kịch bản (004) và đường trả lời comment (001)
giữ nguyên: câu nói đúng dữ liệu, phụ đề, tạm dừng, bỏ qua. Khác biệt duy nhất là màn hình host giờ là nhân vật chuyển động và nhép miệng
theo từng câu.

**Vì sao ưu tiên này:** biến nhân vật ở US1 thành AI host thật cho buổi demo; cần US1 trước. Show kịch bản là nội dung chính (ADR-026);
đường comment giữ làm công cụ thử.

**Kiểm thử độc lập:** mở phiên ở chế độ nhân vật nhép miệng, chạy show kịch bản vài phân đoạn và gõ vài comment, bấm bỏ qua khi host
đang nói, xem màn hình host và trang điều khiển.

**Kịch bản chấp nhận:**
1. **Given** phiên mở ở chế độ nhân vật nhép miệng, **When** show kịch bản chạy một phân đoạn, **Then** nhân vật nói từng câu và nhép
   miệng theo từng câu, phụ đề hiện cùng lúc câu được nói, giữa hai câu của cùng phân đoạn không giật về clip chờ.
2. **Given** phiên mở ở chế độ nhân vật nhép miệng, **When** người vận hành gửi comment hỏi giá, **Then** nhân vật nói câu trả lời
   và nhép miệng theo từng câu như ở kịch bản 1.
3. **Given** nhân vật đang nói, **When** bấm bỏ qua lượt này, **Then** tiếng, miệng và phụ đề dừng, nhân vật về clip chờ và
   hệ thống chuyển sang lượt kế tiếp.
4. **Given** phần tạo hình nhép miệng bị lỗi hoặc không phản hồi trong một lượt, **When** lượt đó chạy, **Then** lượt được ghi lỗi ở bước
   tạo hình, trang điều khiển báo lỗi và lượt sau vẫn chạy.
5. **Given** phần tạo hình bị lỗi ở 2 lượt liền nhau, **When** lượt kế tiếp bắt đầu, **Then** phiên tự chuyển sang ảnh tĩnh của chính
   nhân vật đó (vẫn có tiếng, phụ đề và nhãn "AI"), trang điều khiển báo rõ đã chuyển và vì sao.
6. **Given** phiên đã tự chuyển sang ảnh tĩnh, **When** người vận hành bấm bật lại nhân vật nhép miệng trên trang điều khiển, **Then** từ
   lượt kế tiếp nhân vật nhép miệng chạy lại, không phải mở lại phiên; nếu phần tạo hình vẫn lỗi thì lượt đó ghi lỗi như kịch bản 4.
7. **Given** phiên mở ở chế độ ảnh tĩnh, **When** chạy như feature 001 và 004, **Then** mọi thứ hoạt động như cũ (chế độ mới không làm hỏng chế độ cũ).

---

### User Story 3: Xoay vòng nhiều clip chờ và clip nói (Ưu tiên: P3)

Bộ clip nền có thể có nhiều clip chờ và nhiều clip nói (ví dụ 2 clip chờ, 2–3 clip nói với cách nghiêng đầu khác nhau). Mỗi khi cần
clip nền mới, nhân vật chọn một clip đúng loại nhưng không lấy lại đúng clip vừa dùng, để người xem bớt thấy lặp. Cử chỉ đổi theo nội
dung (đưa tay giới thiệu, chỉ sang bên, gật đầu cảm ơn) để feature sau (làm rõ 2026-11-05).

**Vì sao ưu tiên này:** lặp một clip duy nhất suốt buổi là điểm yếu chung của AI host hiện nay và làm tăng rủi ro bị coi là "nội dung
quay sẵn" (RISKS P2). Xoay clip rẻ hơn nhiều so với cử chỉ theo chủ đề. Cần US1 và US2 trước.

**Kiểm thử độc lập:** chuẩn bị nhân vật có ít nhất 2 clip chờ và 2 clip nói, để chờ vài vòng và chạy show kịch bản vài phân đoạn, xem
clip nền có đổi và có lặp lại liền nhau không.

**Kịch bản chấp nhận:**
1. **Given** nhân vật có từ 2 clip nói trở lên, **When** cần clip nói mới (lượt nói mới bắt đầu sau khi nhân vật đã về clip chờ, hoặc clip
   nói đang dùng đã chạy hết một vòng đi tới rồi đi lùi và tới ranh giới câu), **Then** clip nói sau khác clip nói vừa dùng và miệng vẫn
   khớp tiếng. Câu đến trong khoảng giữ nói tiếp trên clip đang giữ, không đổi clip ở mỗi câu (sửa 2026-11-12, xem Làm rõ).
2. **Given** nhân vật có từ 2 clip chờ trở lên, **When** clip chờ chạy hết và cần clip chờ tiếp theo, **Then** không chọn lại đúng clip vừa dùng.
3. **Given** nhân vật chỉ có 1 clip của một loại, **When** cần clip loại đó, **Then** dùng lại clip đó, không coi là lỗi.

---

### User Story 4: Đo tốc độ nhân vật trên laptop (Ưu tiên: P4)

Sau khi nhân vật chạy được, mình xem số liệu thật trên laptop: số khung hình mỗi giây, thời gian từ lúc có tiếng đến lúc miệng bắt
đầu cử động, độ trễ cả lượt, và máy có chịu được 30 phút không. Feature này chỉ đo và ghi lại; đặt mục tiêu tốc độ là việc bàn sau.

**Vì sao ưu tiên này:** người dùng chấp nhận chậm và muốn bàn tốc độ sau, nhưng cần số liệu thật để bàn.

**Kiểm thử độc lập:** chạy một phiên có nhiều lượt nói, mở bảng độ trễ và ghi số liệu.

**Kịch bản chấp nhận:**
1. **Given** phiên ở chế độ nhân vật nhép miệng đã có ít nhất 20 lượt nói, **When** mở bảng độ trễ, **Then** thấy độ trễ cả lượt và
   riêng bước tạo hình, cùng số khung hình mỗi giây thực tế.
2. **Given** phiên chạy liên tục 30 phút, **When** kết thúc, **Then** có ghi nhận máy có bị dừng, đứng hình, mất tiếng
   hay hết bộ nhớ đồ họa không.

### Trường hợp biên

- **Laptop tạo hình không kịp tốc độ của tiếng:** không được để tiếng chạy trước hình rồi hình đuổi theo. Hệ thống giảm số khung hình
  hoặc độ nét để giữ tiếng và miệng khớp nhau (FR-007). Tốc độ thấp được chấp nhận (ADR-023).
- **Câu dài hơn clip nói:** clip nền lặp lại hoặc nối sang clip nói khác trong lúc nói, chỗ nối không giật rõ, miệng vẫn khớp tiếng.
- **Câu ngắn hơn clip nói:** nhân vật về clip chờ khi hết lượt (im lặng quá một khoảng giữ ngắn sau câu cuối, cấu hình được, mặc định 2,5 s), không chạy nốt clip nói với miệng khép lâu. Giữa hai câu sát nhau (của cùng lượt, hoặc hai câu kịch bản liền nhau) nhân vật giữ clip nói với miệng khép (US2 #1).
- **Hết bộ nhớ đồ họa hoặc phần tạo hình bị treo giữa phiên:** lượt đó ghi lỗi, phiên không dừng; lỗi 2 lượt liền thì phiên tự chuyển sang
  ảnh tĩnh của chính nhân vật (FR-022) để show không bị câm, trang điều khiển báo rõ; người vận hành khởi động lại phần tạo hình rồi bấm
  bật lại nhân vật.
- **Lỗi xen kẽ (một lượt lỗi, lượt sau chạy được):** bộ đếm lỗi liền nhau về 0, không tự chuyển sang ảnh tĩnh.
- **Đóng màn hình host giữa lúc nói:** như feature 001, lỗi "chưa mở màn hình host", mở lại thì chạy tiếp.
- **Đoạn tiếng toàn im lặng hoặc chỉ là âm báo của giọng giả:** miệng gần như khép; không coi là lỗi.
- **Câu rất dài (trên 30 giây tiếng):** nhân vật vẫn nhép miệng hết câu, không tràn bộ nhớ.
- **Hai lượt nối tiếp nhau sát nhau:** nhân vật không giật về trạng thái chờ giữa hai câu của cùng một lượt.
- **Clip nền có miệng tự cử động (model tạo video tự thêm động tác nói):** trong lúc chờ miệng vẫn phải khép (FR-008); clip chờ như vậy bị
  từ chối khi chuẩn bị hoặc phải tạo lại.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

**Chuẩn bị nhân vật**
- **FR-001**: Mình PHẢI chuẩn bị được một nhân vật trên laptop bằng một thao tác, trước phiên live, từ **một ảnh gương mặt tạo bằng AI**
  (không phải người thật) và **một bộ clip nền** tạo từ chính ảnh đó. Việc tạo clip nền là bước làm một lần cho mỗi nhân vật, chạy
  ngoài laptop (ADR-036); bước chuẩn bị trên laptop chỉ nhận ảnh và clip đã có.
- **FR-002**: Bộ clip nền PHẢI có ít nhất một clip chờ và một clip nói; clip không có tiếng, cùng nhân vật, cùng trang phục, bối cảnh
  và khung hình với ảnh gốc. Clip nền chỉ là phần chuyển động của đầu và thân; **phần miệng lúc nói luôn được tạo ngay lúc nói** theo tiếng.
- **FR-003**: Việc chuẩn bị PHẢI từ chối ảnh hoặc clip không có đúng một khuôn mặt rõ ở mọi khung hình, và báo lý do (tên clip, vị trí khung hình).
- **FR-004**: Mỗi nhân vật PHẢI gắn với đúng một khách/tài khoản. Ảnh gốc và từng clip nền PHẢI có hồ sơ nguồn gốc. Hệ thống PHẢI từ chối
  chuẩn bị khi thiếu hồ sơ nguồn gốc, và từ chối mở phiên khi nhân vật thuộc khách khác với khách của phiên.
- **FR-005**: Gương mặt PHẢI trông là người trưởng thành và không cố ý giống người có thật hay người nổi tiếng (luật AI live của Shopee).
  Người vận hành xác nhận điều này trong hồ sơ nguồn gốc khi chuẩn bị.

**Nhép miệng và chuyển động**
- **FR-006**: Nhân vật PHẢI nhép miệng theo tiếng nói đưa vào, phần miệng được tạo ngay trong lúc nói trên nền clip đang chạy. Không có
  đường nào phát một video có sẵn tiếng, hay một video nhân vật nói dựng sẵn.
- **FR-007**: Tiếng và miệng PHẢI khớp nhau trong suốt câu. Khi máy không tạo hình kịp, hệ thống PHẢI giảm số khung hình hoặc độ nét
  thay vì để tiếng đi trước hình.
- **FR-008**: Khi không nói, nhân vật PHẢI chạy lặp clip chờ với miệng khép, không đứng hình ở khung miệng mở.
- **FR-009**: Chuyển giữa clip chờ và clip nói chỉ xảy ra khi bắt đầu hoặc kết thúc lượt, hoặc ở ranh giới câu. Chỗ lặp clip
  và chỗ chuyển clip PHẢI không có bước nhảy hình thấy rõ.
- **FR-010**: Nhãn "AI" PHẢI nằm trong chính khung hình của nhân vật (không phải lớp phủ của trang web), luôn hiện, không tắt được.
- **FR-011**: Mình PHẢI thử được nhân vật riêng lẻ bằng cách đưa vào một đoạn tiếng nói có sẵn, không cần mở phiên
  (chỉ để kiểm tra trên laptop, không dùng làm nội dung live).

**Xoay vòng clip nền** (US3)
- **FR-012**: Mỗi clip nền PHẢI có loại (chờ hoặc nói). Một nhân vật có thể có nhiều clip mỗi loại.
- **FR-013**: Khi cần một clip nền mới (bắt đầu lượt sau khi đã về clip chờ, clip nói chạy hết một vòng và tới ranh giới câu, nối clip
  trong câu dài, hết clip chờ), hệ thống PHẢI chọn clip đúng loại và không chọn lại đúng clip vừa dùng của loại đó, trừ khi loại đó chỉ có
  một clip.

**Cắm vào pipeline**
- **FR-014**: Người vận hành PHẢI chọn được chế độ "ảnh tĩnh" hoặc "nhân vật nhép miệng" bằng cấu hình khi mở phiên; chế độ ảnh tĩnh giữ
  nguyên hành vi feature 001 và 004. Đổi chế độ giữa phiên chỉ có ở FR-022 (tự về ảnh tĩnh khi lỗi, người vận hành bật lại).
- **FR-015**: Ở chế độ nhân vật nhép miệng, show kịch bản (004) và đường trả lời comment (001) PHẢI chạy như cũ: phụ đề, tạm dừng, tiếp tục,
  bỏ qua, chịu lỗi từng lượt và ghi log.
- **FR-016**: Bỏ qua lượt đang nói PHẢI dừng tiếng, miệng và phụ đề; nhân vật về clip chờ.
- **FR-017**: Lỗi hoặc quá thời gian ở bước tạo hình PHẢI làm lượt đó kết thúc với lỗi ở bước tạo hình, không làm dừng phiên.
- **FR-022**: Khi bước tạo hình lỗi ở 2 lượt liền nhau, phiên PHẢI tự chuyển sang ảnh tĩnh của chính nhân vật đó từ lượt kế tiếp (tiếng,
  phụ đề, nhãn "AI", tạm dừng, bỏ qua vẫn như chế độ ảnh tĩnh) và trang điều khiển PHẢI báo đã chuyển kèm lý do. Người vận hành PHẢI bật
  lại được nhân vật nhép miệng ngay trên trang điều khiển, có hiệu lực từ lượt kế tiếp, không phải mở lại phiên. Việc tự chuyển và bật lại
  PHẢI được ghi log.
- **FR-018**: Màn hình host PHẢI xem được trên Chrome của laptop có cả hình và tiếng, để chia sẻ tab vào Google Meet như feature 001.

**Đo đạc**
- **FR-019**: Mốc "frame đầu tiên" của mỗi lượt PHẢI là lúc khung hình nhép miệng đầu tiên của câu đầu được hiển thị, ghi kèm mã lượt.
  Bản demo đo mốc này bằng tin xác nhận "bắt đầu phát" của phần tạo hình (`playback_started`, ADR-047); độ lệch giữa xác nhận và lúc hiển thị thật được đo một lần ở US4 (research R6) và ghi kèm số đo.
- **FR-020**: Hệ thống PHẢI ghi số khung hình mỗi giây thực tế và thời gian riêng của bước tạo hình cho mỗi lượt, hiện trong bảng độ trễ.
- **FR-021**: Hệ thống PHẢI ghi lại khi phần tạo hình gặp lỗi bộ nhớ đồ họa hoặc bị khởi động lại.

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): miệng được tạo ngay lúc nói theo tiếng (FR-006); clip nền không có tiếng, không có
  đường phát video dựng sẵn làm nội dung; nhãn "AI" ghép vào khung hình (FR-010); nhân vật gắn với đúng một khách (FR-004). Đoạn tiếng mẫu
  ở FR-011 chỉ để kiểm tra trên laptop. **Còn mở:** Shopee có coi clip nền lặp (miệng tạo realtime) là "nội dung quay sẵn" không; chỉ ảnh
  hưởng giai đoạn Shopee, không ảnh hưởng demo Meet/YouTube (RISKS P2). Giảm rủi ro bằng nhiều clip và không lặp lại đúng clip vừa dùng (FR-013).
- [x] Điều II (đồng ý / bảo mật): nhân vật là gương mặt tạo bằng AI, không phải người thật, nên không cần văn bản đồng ý về hình;
  thay vào đó bắt buộc hồ sơ nguồn gốc cho ảnh và từng clip (FR-004, US1 #6), không cố ý giống người có thật hay người nổi tiếng,
  trông là người trưởng thành (FR-005). Nếu sau này đổi sang người thật thì quay lại yêu cầu văn bản đồng ý. Đoạn tiếng mẫu dùng giọng
  của người đã đồng ý. Ảnh, clip và dữ liệu nhân vật không đưa vào kho mã.
- [x] Điều IV (adapter): nhân vật nhép miệng là một cách hiển thị mới thay được cho ảnh tĩnh, không sửa lõi pipeline (FR-014). Xoay vòng
  clip (FR-013) nằm trong cách hiển thị mới, không cần thêm thông tin gì từ 004.
- [x] Điều V (test trước): logic chọn chế độ, chọn clip, chịu lỗi, bỏ qua, ghi mốc phải kiểm thử tự động không cần card đồ họa (dùng phần
  tạo hình giả). Phần nhép miệng thật kiểm chứng bằng kịch bản tay trong quickstart. Điều V (hiến pháp 1.2.0, ADR-029) cho chạy GPU laptop
  trước theo ADR-023, RunPod là dự phòng. Tạo clip nền là bước chuẩn bị ngoài pipeline, chạy trên GPU cloud miễn phí (ADR-036).
- [x] Điều VI (độ trễ): feature này chiếm phần "lip-sync đến frame đầu tiên" (0,8 s) và "truyền hình" (0,5 s) trong ngân sách < 5 giây.
  Trên laptop người dùng chấp nhận vượt ngân sách (ADR-023); feature chỉ bắt buộc đo và ghi (FR-019, FR-020), không đặt ngưỡng.
- [x] Điều VIII (quan sát được, chịu lỗi): FR-017, FR-019 đến FR-022.

### Thực thể chính

- **Nhân vật (avatar)**: một AI host đã chuẩn bị. Thuộc tính: mã nhân vật, khách/tài khoản sở hữu (đúng một), ảnh gốc, bộ clip nền,
  hồ sơ nguồn gốc, ngày chuẩn bị, trạng thái (sẵn sàng / lỗi chuẩn bị kèm lý do).
- **Clip nền**: một đoạn video ngắn không tiếng của nhân vật, tạo từ ảnh gốc. Thuộc tính: mã clip, nhân vật, loại (chờ / nói),
  thời lượng, hồ sơ nguồn gốc.
- **Hồ sơ nguồn gốc**: cho ảnh gốc và từng clip. Ghi công cụ và model đã dùng, prompt, seed, ai tạo, ngày tạo, nơi chạy (dịch vụ GPU nào),
  điều khoản sử dụng của model và của nơi chạy (có cho dùng thương mại không), cam kết không cố ý giống người có thật và trông là người
  trưởng thành. Lưu cùng nhân vật, ngoài git.
- **Lượt nói** (đã có ở feature 001): thêm số khung hình mỗi giây thực tế, thời gian bước tạo hình và các clip nền đã dùng.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Với 10 đoạn tiếng nói mẫu tiếng Việt, người vận hành đánh giá miệng khớp tiếng ở ít nhất 8/10 đoạn khi xem bằng mắt.
- **SC-002**: Trong 100% ảnh chụp màn hình host ở thời điểm ngẫu nhiên (ít nhất 10 ảnh), nhãn "AI" nằm trong khung hình nhân vật.
- **SC-003**: Trong một phiên có ít nhất 20 lượt ở chế độ nhân vật nhép miệng, không lượt nào để tiếng chạy xong trước khi hình bắt đầu nhép miệng.
- **SC-004**: Bỏ qua lượt đang nói làm tiếng và miệng dừng trong vòng 1 giây, như feature 001.
- **SC-005**: Lỗi giả lập ở bước tạo hình không làm dừng phiên: lượt kế tiếp vẫn chạy trong 100% lần thử; lỗi giả lập 2 lượt liền thì
  lượt thứ ba chạy ở ảnh tĩnh có tiếng trong 100% lần thử, và bật lại nhân vật từ trang điều khiển có hiệu lực ngay lượt sau.
- **SC-006**: Có số liệu thật trên laptop (số khung hình mỗi giây, độ trễ bước tạo hình, độ trễ cả lượt p50/p95, kết quả chạy 30 phút)
  ghi vào tài liệu để bàn mục tiêu tốc độ sau. Không có ngưỡng đạt/trượt cho các số này.
- **SC-007**: Trong 3 phút ở trạng thái chờ cộng 10 lượt nói, người vận hành thấy rõ không quá 1 lần giật hình ở chỗ lặp hoặc chuyển clip.
- **SC-008**: Ít nhất 2/3 người xem thử (tối thiểu 3 người, không phải người làm dự án) đánh giá nhân vật ở chế độ chờ "trông như đang sống",
  không phải ảnh đứng im, sau khi xem 1 phút.

## Giả định

- Gương mặt AI và clip nền tạo bằng công cụ và model miễn phí, chạy trên GPU cloud miễn phí (ADR-019, ADR-036). Laptop 4 GB không đủ để
  tạo video. Chạy bằng notebook `scripts/avatar_clips/make_avatar_clips.ipynb` trên Kaggle trước, rồi Google Colab bản miễn phí
  (không qua giao diện web vì Colab bản miễn phí cấm). Điều khoản Kaggle chỉ cho dùng phi thương mại; người dùng chấp nhận dùng cho
  giai đoạn demo (2026-11-03), trước khi khách trả tiền phải đọc lại điều khoản. Không đủ thì thuê RunPod, báo chi phí trước.
- Phải kiểm tra điều khoản của model tạo ảnh, model tạo video và nơi chạy có cho dùng kết quả vào mục đích thương mại không trước khi thu
  tiền khách (ADR-036).
- Mỗi nhân vật có khoảng 3–6 clip nền, mỗi clip vài giây; độ dài và độ phân giải cụ thể do plan chọn theo model tạo video và khả năng laptop.
- Chạy nhép miệng trên laptop của người vận hành (card đồ họa 4 GB) theo ADR-023; chấp nhận chậm. RunPod là dự phòng, bật thì báo chi phí trước.
- Giọng thật tiếng Việt thuộc feature 003, chưa có. Giọng giả hiện tại chỉ phát âm báo nên không dùng để chấm độ khớp miệng.
  US1 và SC-001 dùng **đoạn tiếng nói ghi âm có sẵn** của người đã đồng ý (ví dụ người vận hành tự đọc), chỉ để thử trên laptop.
  Khi có feature 003, nhân vật dùng giọng thật mà không phải sửa gì thêm.
  Sửa 2026-11-10 (người dùng chọn): 003 đã có giọng VieNeu `Thùy Dung` dùng khi chạy phiên, nên SC-001 chấm trên 10 đoạn do VieNeu
  `Thùy Dung` đọc (giọng tổng hợp, không cần đồng ý của người thật) thay cho đoạn người vận hành tự đọc; sát giọng chạy live hơn.
- Ngưỡng 8/10 ở SC-001 lấy theo tinh thần tiêu chí demo trong PRD; chấm bằng mắt, không dùng thang điểm 1–5 (PRD còn TODO).
- Khung hình nhân vật: **nửa người tới ngang bụng**, thấy tay và thân, giống AI host trên Shopee Live và sẵn cho cử chỉ ở feature sau mà
  không phải tạo lại nhân vật (làm rõ 2026-11-05). Đánh đổi đã chấp nhận: mặt nhỏ hơn trong khung nên miệng kém rõ hơn, và tay trong clip
  do model tạo video dễ bị biến dạng (clip như vậy phải tạo lại, FR-003).
- Màn hình host tiếp tục là trang web mở trên Chrome của laptop như feature 001; chưa đẩy lên YouTube hay Shopee.
- Kích thước khung hình, số khung hình mỗi giây và độ nét do plan chọn theo khả năng laptop, ưu tiên khớp miệng hơn độ mượt.
- Chưa bàn license thương mại của phần nhép miệng: feature này chỉ dùng nội bộ và cho buổi demo. Phải xác minh license (RISKS L1, L2, L10)
  trước khi thu tiền khách.

## Ngoài phạm vi

- Đặt và đạt mục tiêu tốc độ (số khung hình mỗi giây, độ trễ < 5 giây): bàn sau khi có số liệu US4.
- Giọng thật tiếng Việt (feature 003) và kịch bản show (feature 004).
- Thuê GPU RunPod để chạy nhép miệng, đẩy RTMP lên YouTube hoặc Shopee, OBS (feature 006 trở đi).
- Quay người thật hay nhân bản người mẫu.
- Tạo chuyển động hoặc biểu cảm ngay lúc nói bằng model (ví dụ điều khiển đầu và nét mặt theo tiếng): cần GPU mạnh, để sau.
- Cử chỉ theo nội dung: clip cử chỉ (đưa tay giới thiệu, chỉ sang bên, gật đầu cảm ơn) chọn theo chủ đề phân đoạn (làm rõ
  2026-11-05, để feature sau).
- Nhiều nhân vật trong một phiên, đổi nhân vật giữa phiên, cử chỉ toàn thân phức tạp (PRD), biểu cảm theo cảm xúc của câu.
- Video dự phòng 2–3 phút (feature 007).

## Làm rõ

<!-- /sdd.clarify writes here. One subsection per session. -->
### Phiên 2026-10-31
- Q: Nhân vật AI host là ai (người thật đã ký đồng ý hay gương mặt tạo bằng AI)? → A: Gương mặt tạo bằng AI, không phải người thật.
  Bỏ yêu cầu văn bản đồng ý về hình, thay bằng hồ sơ nguồn gốc (FR-001, FR-004, US1 #5, Điều II, Thực thể chính, Giả định).
- Q: Tư liệu hình đầu vào là ảnh chân dung hay video ngắn lặp làm nền? → A: Một ảnh chân dung gương mặt AI, rồi nhép miệng
  theo tiếng; không mua thêm gì. Bản đầu chỉ cử động miệng; chớp mắt / chuyển động đầu để sau (FR-002, Giả định, Ngoài phạm vi).
  **Đổi ngày 2026-11-03** (sửa phạm vi ở đầu file): thêm bộ clip nền có chuyển động tự nhiên tạo từ ảnh gương mặt AI (ADR-036).

### Phiên 2026-11-05
- Q: Cử chỉ theo nội dung (US3) làm trong feature này hay để feature sau? → A: Để feature sau. Bản đầu chỉ có clip chờ và clip nói,
  nhưng cho nhiều clip mỗi loại và xoay vòng, không chọn lại đúng clip vừa dùng (US3 viết lại, FR-009, FR-012, FR-013, Điều IV,
  Thực thể chính, Ngoài phạm vi).
- Q: Khung hình nhân vật là đầu và vai hay nửa người? → A: Nửa người tới ngang bụng, thấy tay và thân; chấp nhận mặt nhỏ hơn và rủi ro
  tay biến dạng trong clip (Giả định; notebook `scripts/avatar_clips/` đổi mặc định sang `half_body`, thay clip cử chỉ bằng clip chờ thứ hai).
- Q: Phần tạo hình lỗi giữa buổi thì người xem thấy gì? → A: Lỗi 2 lượt liền thì phiên tự chuyển sang ảnh tĩnh của chính nhân vật (vẫn có
  tiếng, phụ đề, nhãn "AI"), trang điều khiển báo; người vận hành bấm bật lại nhân vật giữa phiên (US2 #5, #6, FR-022, Trường hợp biên,
  SC-005, Điều VIII).

### Phiên 2026-11-12 (sửa khi làm T067, theo đề xuất của agent; người dùng duyệt 2026-11-16)
- Q: Fork không biết đâu là "lượt": mỗi câu kịch bản của 004 là một `utterance_id` riêng (`seq 0`), nên đổi clip nói ở mỗi `seq 0` làm
  show kịch bản đổi clip ở mọi câu (44 lần trong 7 phút) và luôn chạy lại từ khung 0, người xem chỉ thấy ~3 s đầu của hai clip lặp lại. Đổi
  clip nói khi nào? → A: Câu đến trong khoảng giữ (kể cả `seq 0`) nói tiếp trên clip nói đang giữ. Chọn clip nói mới khi bắt đầu nói từ
  clip chờ, hoặc khi clip nói đang dùng đã chạy hết một vòng đi tới rồi đi lùi: đổi ở khoảng im lặng giữa hai câu hoặc ở đầu câu mới
  (ranh giới câu, FR-009). Khoảng giữ mặc định đổi 1,5 s → 2,5 s vì khoảng nghỉ giữa hai câu kịch bản p95 ~2,9 s (T067) (US3 #1, FR-013,
  Trường hợp biên).

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (giải xong 2026-11-05)
