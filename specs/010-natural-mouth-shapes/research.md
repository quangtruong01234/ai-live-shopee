# Nghiên cứu: Khẩu hình miệng host AI giống người thật

- **Feature ID:** `010-natural-mouth-shapes` · **Ngày:** 2026-11-13 · **Plan:** [plan.md](./plan.md)
- Mọi số đo ở đây chạy trên laptop dev (GTX 1650 Ti 4 GB), nhân vật `demo_host_01`, clip nói `demo_host_01__talk_01`, model
  `wav2lip256` `models/wav2lip.pth` (ADR-041), bộ 24 câu `data/eval/mouth_sentences.json` đọc bằng VieNeu. Kết quả thô nằm ở
  `out/mouth/runs/<lần đo>/` (ngoài git).

## R1. Đo bằng gì (FR-006)

- **Quyết định:** điểm mốc khuôn mặt MediaPipe Face Landmarker (ADR-053) trên từng khung đã dán, và SyncNet (ADR-054) cho LSE-C/LSE-D.
  Không dùng bộ căn âm vị: mỗi câu thuộc một nhóm thiết kế sẵn (`vowel_a`, `vowel_i`, `vowel_u`, `vowel_o`, `bilabial`, `natural`), nên các
  chỉ số hình miệng là so sánh giữa nhóm:
  - `open_ratio` = độ mở trung vị nhóm `a` / nhóm `i`+`u` (SC-003 vế 1);
  - `spread_ratio` = tỷ lệ rộng/cao môi ngoài nhóm `i` / nhóm `u`+`o` (SC-003 vế 2);
  - `closure_recall` = số lần môi khép đếm được / số lần khép mong đợi ở câu `bilabial` (SC-002);
  - `corr_open_loud` = tương quan độ mở với độ to tiếng từng khung;
  - `sharp_ratio` = độ nét vùng miệng / độ nét cùng vùng trên khung clip gốc (FR-006e);
  - `silence_closed`, `render_fps`, `detected`.
- **Ngưỡng môi khép:** lấy từ chính clip đứng yên (`idle`) của nhân vật (phân vị 95 × 1,5, sàn 0,006). Với `demo_host_01` ra 0,006.
- **Lý do:** bộ căn âm vị tiếng Việt chạy offline không có sẵn, cài thêm là một model nữa. Câu theo nhóm cho tín hiệu đủ rõ để so cách
  này với cách kia (cùng tiếng, cùng clip, cùng con trỏ).
- **Phương án đã loại:** whisper căn từ (nặng, sai nhiều với tiếng Việt có dấu); chấm bằng mắt hoàn toàn (không lặp lại được).

## R2. "ph" không phải phụ âm môi

- "ph" tiếng Việt đọc là /f/ (răng chạm môi dưới), môi **không** khép. Bộ đếm khép môi chỉ tính b, m, p đầu âm tiết và p, m cuối âm
  tiết. Spec SC-002 và US1 đã sửa (Làm rõ 2026-11-13).

## R3. Độ nét: so với chính clip gốc, không so với mắt

- Bản đầu chia độ nét miệng cho độ nét vùng mắt, giả định mắt không bị vẽ lại. Sai: cách dán hộp cứng của upstream thay **cả hộp mặt**
  bằng ảnh model vẽ (256×256 phóng ra), mắt cũng mờ theo, nên tỷ số bị đẩy lên. Lần đo r1: cách dán mềm (giữ nửa trên của clip) bị chấm
  0,34, bằng một nửa w2l (0,72), ngược với điều mắt thấy.
- **Quyết định:** `sharp_ratio` = phương sai Laplacian vùng miệng trên khung ra / cùng vùng đó trên khung clip gốc mà nó được dán vào
  (1,0 = nét như miệng quay thật). Khi không có khung gốc mới dùng lại cách so với mắt.

## R4. Model khác: MuseTalk 1.5

- Thử MuseTalk 1.5 fp16 trên laptop: khoảng 0,7 khung/giây, xa ngưỡng 20 (SC-005). **Loại** cho laptop (ADR-055); ghi số để người dùng
  quyết khi có GPU mạnh hơn (spec, Làm rõ).
- Không thử LatentSync, SadTalker, các model khuếch tán khác: đều chậm hơn MuseTalk trên GPU 4 GB.

## R5. Ảnh tham chiếu cố định

- Thử cho mọi khung dùng chung một ảnh tham chiếu (một khung miệng khép), dán hộp cứng: mắt và tư thế đầu lệch khỏi clip (model chép
  mắt và góc đầu từ ảnh tham chiếu), nhìn rất giả. **Loại.**
- Biến thể còn giữ: `ref=offset:N` lấy khung cách N bước trong cùng clip (giống lúc huấn luyện: tham chiếu là một lúc khác của clip).

## R6. Các núm chỉnh hậu kỳ (run r1, 24 câu, 2026-11-13)

| cách | open_ratio | spread_ratio | closure_recall | corr | LSE-C | fps |
|---|---|---|---|---|---|---|
| `w2l` | 1,230 | 0,985 | 0,677 | 0,220 | 6,39 | 28,7 |
| `feather` (dán mềm + chỉnh màu) | 1,246 | 0,984 | 0,677 | 0,220 | 5,74 | 26,4 |
| `ref12` (+ tham chiếu lệch 12) | 1,297 | 1,000 | 0,696 | 0,163 | 5,65 | 26,2 |
| `sharp` (+ làm nét 0,5) | 1,262 | 0,989 | 0,635 | 0,227 | 5,79 | 25,7 |
| `gain6` (+ tăng 6 dB cho model) | 1,111 | 0,990 | 0,659 | 0,212 | 5,99 | 25,9 |

(`sharp_ratio` r1 tính theo cách cũ ở R3 nên không đưa vào bảng.)

- Cách dán và chỉnh màu không đổi hình miệng (model vẽ gì thì vẫn thế), chỉ đổi đường viền. Không cách nào đạt SC-001 so với w2l.
- Tăng độ to cho model làm miệng mở **ít** hơn và khép kém hơn: bỏ.
- Chẩn đoán thêm (diag1, 8 câu): chỉ dán mềm LSE-C 6,24 so với 6,36; chỉ chỉnh màu 6,30. Hai núm này không làm hỏng khớp tiếng đáng kể.

## R7. Miệng đi trước tiếng: cửa sổ tiếng lệch so với lúc huấn luyện

- SyncNet báo lệch **−1 khung (hình đi trước tiếng)** ở **cả 24 câu** của mọi cách trong r1.
- Lý do (đọc mã): upstream lấy cửa sổ mel 16 bước (200 ms) của khung i **bắt đầu từ** khung i
  (`avatars/audio_features/mel.py`, `start_idx = left + i*3.2`), nên model thấy tiếng của 200 ms **sau** khung. Lúc huấn luyện Wav2Lip
  (`get_segmented_mels`) cửa sổ khung i bắt đầu từ khung **i − 2**, tức đặt giữa khung. Đã kiểm luồng live: `warm_up` đẩy 10 khung tiếng
  câm vào hàng phát, nên tiếng nghe được của khung hình k cũng bắt đầu đúng ở chỗ cửa sổ bắt đầu. Bộ đo tái hiện y hệt (đệm 200 ms im
  lặng trước câu như bộ đệm live).
- **Quyết định thử:** khóa `shift=N` trong `LIVETALKING_MOUTH_METHOD`, dời cửa sổ N khung (âm = sớm hơn). Bộ đệm live đã giữ 200 ms tiếng
  trước đó (`-l 10`), nên `shift=-2` **không tăng độ trễ**.
- **Kết quả r2** (24 câu, `out/mouth/runs/r2/`):

| cách | lệch SyncNet (khung, cả 24 câu) | open_ratio | closure_recall | corr | LSE-C | fps |
|---|---|---|---|---|---|---|
| `w2l` | −1 | 1,230 | 0,677 | 0,220 | 6,39 | 28,7 |
| `shift=-1` (`s1`) | **0** | 1,214 | 0,635 | 0,254 | 6,35 | 28,4 |
| `shift=-2` (`s2`) | +1 | 1,234 | 0,677 | 0,019 | 6,34 | 28,5 |
| `shift=-3` (`s3`) | +2 | 1,365 | 0,619 | −0,157 | 6,19 | 28,4 |
| `feather;color=1;shift=-2` | +1 | 1,170 | 0,677 | 0,020 | 5,87 | 26,6 |

- `shift=-1` đưa độ lệch về **0 ở cả 24 câu** và tăng tương quan độ mở–độ to 16%. LSE-C gần như không đổi (−0,7%), closure_recall
  giảm 6%. `shift=-2` (giữa khung như lúc huấn luyện) lại làm miệng **trễ** 1 khung: phần lệch còn lại nằm ở đường đi của tiếng (bộ đệm
  10 khung và cách cắt khối 20 ms), không chỉ ở cửa sổ mel.
- Không cách nào đạt SC-001 (cần ≥ 2/4 chỉ số tốt hơn 15%). Theo ngưỡng cảm nhận thường dùng, miệng đi trước tiếng 40 ms là khó thấy
  (người xem dễ nhận ra tiếng đi trước hình hơn), nên lợi ích của `shift=-1` phải xác nhận bằng mắt: gói A/B r4 (R12).

## R8. Dự phòng và an toàn (FR-005, FR-013)

- Cách tạo miệng đọc một lần lúc fork khởi động. Giá trị sai thì ghi lỗi và dùng `w2l`. Dán lỗi ở một khung thì khung đó dùng hộp cứng
  và chỉ ghi log một lần. Mọi núm chỉ chạm vào vùng hộp mặt; nhãn "AI" và watermark vẽ sau cùng (ADR-044), không bị ảnh hưởng.
- Không tốn thêm bộ nhớ GPU: cùng model, cùng batch; `ref=offset` chỉ đổi ảnh đưa vào.

## R9. torchaudio trong venv fork

- `torchaudio` trong venv fork đã hỏng từ trước 010 (không liên quan). SyncNet dùng `python_speech_features` cho MFCC (ADR-054), không
  cần torchaudio.

## R10. Ảnh tham chiếu môi khép (run r3, `ref=closed:W`)

- Ý tưởng: nửa tham chiếu của model lấy từ khung có môi khép nhất trong ±W khung, để model "thấy" môi khép và vẽ khép rõ hơn ở b/m/p.

| cách | open_ratio | closure_recall | corr | sharp_ratio | LSE-C |
|---|---|---|---|---|---|
| `w2l` | 1,230 | 0,677 | 0,220 | 0,883 | 6,39 |
| `closed:3` | 1,284 | 0,682 | 0,226 | 0,906 | 6,36 |
| `closed:6` | 1,288 | 0,659 | 0,223 | 0,941 | 6,08 |
| `closed:12` | 1,294 | 0,635 | 0,222 | 0,966 | 6,22 |
| `closed:6;shift=-1` | 1,154 | 0,589 | 0,271 | 0,959 | 6,17 |

- Miệng mở rộng hơn 4–5% và nét hơn 3–9%, nhưng khép môi **không** tốt lên và LSE-C giảm. Không đạt SC-001. Clip nói của demo_host_01
  ít khung môi khép (R11), nên ảnh tham chiếu "khép nhất" trong cửa sổ vẫn hé.
- **Quyết định:** giữ `ref=closed:W` chỉ cho bộ đo; `prepare` không viết độ mở môi cho live (contracts/mouth-method.md §1).

## R11. Góc đầu trong clip nói (US3)

- Đo tư thế từng khung clip nói của demo_host_01 (MediaPipe, ADR-053) so với trung vị idle (pitch ≈ 11°, yaw ≈ −14°, roll ≈ 16°), rồi so
  với độ mở môi trung vị lúc tiếng to (`gap` p50) theo từng nhóm 10 khung (`out/mouth/pose_vs_mouth.json`):
  - talk_01: roll 16–19° → gap 0,015–0,023; khung 30–39 (đang xoay đầu) 0,0074; khung 80–109 (roll ~0°) **0,035–0,044**, vì môi ở clip
    gốc đang mở sẵn (gap gốc 0,017–0,037).
  - talk_02: roll −4° (lệch 20°) → 0,016–0,029; khung 60–69 0,043; khung 70–109 roll −16°, yaw −18° (lệch 32°, 4°) → 0,022–0,028;
    khung 110–120 0,007–0,011.
- **Kết luận:** độ mở miệng **không** phụ thuộc rõ vào góc đầu; nó theo trạng thái môi của khung gốc. Nhận xét của 005 "đầu nghiêng thì
  miệng hé" chỉ đúng một phần (talk_01 khung 30–39, talk_02 khung 110–120: lúc đầu đang chuyển động).
- **Ngưỡng mặc định:** roll 35°, pitch 20°, yaw 30° so với idle: chỉ loại khung quay hẳn (model vẽ sai hướng), **không loại khung nào** của
  demo_host_01. Siết roll xuống 20° thì talk_02 bị loại hết (`talk_too_short`), mất nửa số clip nói mà miệng không đẹp hơn. Có thể siết
  bằng cờ `--max-roll` nếu khách khác có clip nói lắc đầu mạnh.

## R12. Lần đo lặp lại và gói A/B (r4)

- r4 (2026-11-13 08:43) đo lại `w2l` và `s1` (`shift=-1`) trên 24 câu bộ v1. Mọi chỉ số hình miệng và LSE-C/LSE-D **trùng khớp
  từng chữ số** với r2/r3 (`w2l`: open 1.230, closure 0.677, corr 0.220, LSE-C 6.394; `s1`: 1.214, 0.635, 0.254, 6.349).
  Chỉ `render_fps` dao động (28.8 / 28.2), vẫn ≥ 20. Kết luận: phép đo tất định với cùng model và cùng tiếng → **SC-007 đạt** (lệch 0%).
- Gói A/B cho SC-004: `out/mouth/runs/r4/ab/` gồm 4 đoạn (`moi`, `nguyen_am_1`, `nguyen_am_2`, `tu_nhien`), mỗi đoạn 2 clip X/Y
  xáo ngẫu nhiên, phiếu chấm `PHIEU.md`; khóa ở `out/mouth/runs/r4/ab_key.json` (chỉ mở sau khi chấm). Cần ≥ 3 người xem.
  Clip ghép cạnh nhau (đã biết đâu là đâu, để kỹ thuật soi) ở `out/mouth/runs/r4/side_by_side/`.
- Quy tắc quyết định: nếu ≥ 2/3 người chọn `s1` ở đa số đoạn thì đổi mặc định sang `shift=-1` (ghi ADR mới thay ADR-055);
  nếu không thì giữ `w2l`. Bộ câu v2 (thêm nhóm số đếm/giá/ngày giờ) chỉ dùng cho lần đo sau, không so trực tiếp với r2–r4.
- r5 (2026-11-13 08:48, `out/mouth/runs/r5_v2/`): đo nền bộ câu **v2** (27 câu, thêm nhóm `number` m1–m3) cho `w2l` và `s1`. Các chỉ số
  hình miệng gần như không đổi so với v1 (`w2l` closure 0,677, open 1,230; `s1` 0,635, 1,214). LSE-C tổng: `w2l` 6,399, `s1` 6,465 (với
  bộ v2 `s1` **không thấp hơn**), nhưng vẫn chỉ 1/4 chỉ số hình miệng tốt hơn ≥ 15% (corr +18%) nên SC-001 vẫn chưa đạt. Nhóm số: `w2l`
  lệch −1 khung ở cả 3 câu, `s1` về 0; LSE-C m1/m2/m3 = 8,68/7,21/6,36 (`w2l`) và 8,88/7,03/6,61 (`s1`). Từ giờ so trên bộ v2 dùng r5 làm
  baseline. Một vòng 27 câu × 2 cách có SyncNet mất khoảng 6 phút trên GTX 1650 Ti.

## R13. Repo nhép miệng khác: vì sao demo LiveTalking trông giống người (tra cứu 2026-11-16)

Người dùng hỏi (2026-11-16): demo của LiveTalking trông rất giống người, có repo nào làm được như vậy không, ưu tiên repo người Việt
dùng nhiều. Chỉ tra cứu, **chưa cài, chưa tải gì** (cần ADR và người dùng duyệt).

- **Vì sao demo LiveTalking đẹp hơn bản mình chạy:**
  - Video demo trên Bilibili dùng MuseTalk, ER-NeRF hoặc Wav2Lip, chạy trên GPU lớn: README ghi wav2lip256 cần RTX 3060 trở lên (60 khung/giây),
    MuseTalk cần RTX 3080 Ti trở lên (42–72 khung/giây).
  - Tác giả bán **bản thương mại** có model `wav2lipls` 192/384 px: tiếng đi qua HuBERT, thêm LSTM nối các khung trước và sau nên miệng ít giật.
    Không công bố giá; liên hệ qua WeChat, email hoặc Telegram, có trang thử `livetalking.top`. Bản mã nguồn mở không có model này.
  - Clip nền trong demo là người thật quay thẳng mặt, ánh sáng tốt và đang nói thật. Theo R6 và R10, chất lượng đầu vào quyết định nhiều.
- **Repo người Việt:** không tìm thấy repo người Việt nào được dùng nhiều.
  - Các repo tiếng Việt tìm được là fork của LiveTalking. Ví dụ `Vietvie/ai_livestream` có 0 sao và hướng dẫn tiếng Việt, vẫn dùng đúng
    các model trên.
  - Dịch vụ livestream AI ở Việt Nam (ví dụ DeepCore) không công bố mã nguồn.
  - Cộng đồng Việt đang dùng chính LiveTalking, tức là repo mình đang dùng.
- **Ứng viên** (chạy realtime được, không render trước):

| Ứng viên | Cách chạy | Laptop 4 GB? | License | Nhận xét |
|---|---|---|---|---|
| Ultralight-Digital-Human / FeatherTalk (anliyuan, 2,7k sao) | Huấn luyện riêng cho từng người từ 3–5 phút video có tiếng; UNet nhẹ | **Có thể**: tác giả nói chạy realtime trên điện thoại, < 10 ms/khung trên RTX 2080 | Apache-2.0 | LiveTalking đã có sẵn chế độ `ultralight`, nên fork không phải thêm đường mới. Model học đúng miệng và răng của người mẫu. Rủi ro: chất lượng phụ thuộc video huấn luyện và tiếng; có issue "cằm to nhỏ thất thường" ở FeatherTalk. Cần GPU để huấn luyện (Kaggle/Colab miễn phí như ADR-036?). License rõ hơn wav2lip256 (RISKS L2, L11) |
| Bản thương mại LiveTalking (`wav2lipls`) | Thay model trong fork | Chưa rõ | Thương mại, trả tiền | Nhiều khả năng là thứ làm demo đẹp. Không có giá, phải hỏi tác giả. Có thể giải luôn câu hỏi license L11 |
| MuseTalk 1.5 (Tencent) | Đã có trong LiveTalking | Không: ~0,7 khung/giây (R4) | Mã MIT, model dùng thương mại được; thành phần phụ (whisper, VAE, DWPose, S3FD, face-parsing) theo license riêng | Chạy realtime cần RTX 3080 Ti/3090/4090, tức là RunPod tốn tiền theo giờ |
| Ditto (Ant Group) | Một ảnh chân dung + tiếng phát trực tiếp, cả đầu chuyển động, TensorRT | Không: thử trên A100, RTX 3090 | Apache-2.0 | Phải viết adapter mới (đầu vào là ảnh, không phải clip). Chỉ hợp khi có GPU thuê |
| HeyGem / Duix.Heygem | Render file video offline | — | — | **Loại**: render sẵn rồi phát, trái ràng buộc số 1 (chỉ sinh realtime) |
| LatentSync, LivePortrait | Khuếch tán chậm / chỉ chuyển động khuôn mặt | — | — | **Loại**: không chạy realtime trên GPU 4 GB, hoặc không nhép theo tiếng |

- **Đề xuất theo thứ tự chi phí:**
  1. Miễn phí, không cài gì: quay clip nói mới (mặt thẳng, môi khép rõ ở b/m/p) và chấm gói A/B r4.
  2. Miễn phí, cần ADR: thử Ultralight trong fork trên laptop, huấn luyện từ 3–5 phút video có tiếng của người mẫu đã ký đồng ý.
     Cần tải mã Ultralight/FeatherTalk và encoder tiếng (HuBERT hoặc WeNet). Sau đó so bằng bộ đo 010 (r5 làm baseline).
  3. Tốn tiền, hỏi trước: hỏi giá bản thương mại LiveTalking, hoặc thuê RunPod chạy MuseTalk 1.5 trong ngày demo.
- **Người dùng chọn hướng 2 (2026-11-17):** kế hoạch thử ở ADR-060.
- **Nguồn:**
  - <https://github.com/lipku/LiveTalking>
  - <https://livetalking-doc.readthedocs.io/zh-cn/latest/service.html>
  - <https://github.com/Vietvie/ai_livestream>
  - <https://github.com/anliyuan/Ultralight-Digital-Human>
  - <https://github.com/Born-Digital-AI/FeatherTalk>
  - <https://github.com/TMElyralab/MuseTalk>
  - <https://github.com/antgroup/ditto-talkinghead>
  - <https://askaillex.com/guides/duix-heygem-local-heygen-alternative/>
