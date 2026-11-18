# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (trong `src/`, backend replay, FAIL là lớp dương: việc của judge là **tìm** lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (exit 0) | **dùng** (non-blocking, theo dõi) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** κ và R (exit 1) | **loại**, không dùng làm gate |

Ma trận nhầm lẫn (FAIL = dương):

| Tiêu chí | TP | FP | FN | TN | Tỉ lệ FAIL quan sát | Sau Rogan-Gladen |
|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 |

Specificity: tone = 66/70 = 0.943; helpful = 70/70 = 1.0.

## ≥5 case audit thủ công

Tone: 10 bất đồng (6 FN, 4 FP). Helpful: 21 bất đồng, **tất cả là FN** (người FAIL, judge PASS).

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | tone H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em", "nha" quá suồng sã. Rubric thêm: *xưng hô phải là "LogiX" / "anh/chị"; "em/bạn/nha/nhé" ⇒ FAIL*. Cùng lỗi: H-017 ("bạn ơi … rồi nha"). |
| 2 | tone H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge bám từ khoá lịch sự ("Dạ, vui lòng") mà bỏ qua giọng ra lệnh. Rubric: *mọi mệnh lệnh cấm khách liên hệ ⇒ FAIL bất kể có "Dạ"*. |
| 3 | tone H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa hẹn ngoài kết quả hệ thống. Đây không hẳn là lỗi giọng điệu mà là lỗi nội dung, nên **chuyển sang grader code** (reply không được hứa khoản chưa có trong ledger), đừng nhồi vào rubric tone. |
| 4 | tone H-070 "…ạ 😂😂" | PASS | FAIL | Người | Emoji cười trong ngữ cảnh khiếu nại. Rubric: *không emoji trong phản hồi khiếu nại*. Thêm 2–3 ví dụ emoji vào few-shot. |
| 5 | tone H-094 "Da, LogiX da hoan…" (mất dấu) | PASS | FAIL | Người | Tiếng Việt không dấu, dịch máy. Rubric: *văn bản phải có dấu đầy đủ*. Có thể bắt bằng code (tỉ lệ ký tự có dấu) rẻ hơn judge. |
| 6 | tone H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric phải nói rõ: *xin lỗi không bắt buộc khi kết quả có lợi cho khách; ngắn gọn ≠ thô lỗ*. |
| 7 | tone H-051 "…đã refund 90.000đ…" | FAIL | PASS | Người | CS LogiX cho phép từ "refund". Thêm vào rubric danh sách từ mượn được phép (refund, ship, voucher). |
| 8 | tone H-088 "Dạ, dạ, LogiX đã hoàn…" | FAIL | PASS | Chưa rõ, nghiêng về người | Lỗi gõ lặp "Dạ" không làm mất lịch sự. Rubric: *lỗi chính tả nhỏ không phải lỗi tone*. |
| 9 | tone H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Ghi chú dữ liệu: nhãn người sai (đọc nhầm ticket). **Sửa nhãn người** trong bộ held-out, không sửa rubric. Cho thấy nhãn người cũng cần kiểm tra chéo (2 người gán, đo κ giữa người với người). |
| 10 | helpful HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL | Người | Ledger ghi 40.000đ. Judge chỉ thấy reply, **không thấy ledger**, nên không thể biết số sai. Cùng kiểu: HL-020, 062, 087, 100. |
| 11 | helpful HL-016 / HL-028 / HL-043 … (13 ca xin lỗi lặp 2 lần + số tiền sai) | PASS | FAIL | Người | Verbosity / sycophancy bias: câu xin lỗi dài làm judge chấm "hữu ích" dù số tiền sai so với ledger (vd. HL-043 nói 35.000đ, ledger 20.000đ). |
| 12 | helpful HL-047 / 091 / 097 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả, số tiền hay bước tiếp theo. Rubric: *reply phải nêu trạng thái (đã hoàn X đ / bị từ chối vì … / cần thêm thông tin gì)*. |

Phân loại 21 FN của helpful: 18/21 là **số tiền trong reply ≠ ledger** (13 ca có xin lỗi lặp, 5 ca ngắn), 3/21 là reply rỗng nội dung ("Ok bạn … xử lý rồi nhé").

## Kết luận

- **tone_ok dùng được**: κ = 0.757, P = 0.857, R = 0.80, cả ba đều trên sàn. Bất đồng chủ yếu do rubric chưa nói rõ xưng hô, emoji, mệnh lệnh và từ mượn được phép; sửa rubric theo bảng trên rồi đo lại. Chỉ dùng làm metric **non-blocking**: nó vẫn bỏ sót 6/30 reply có giọng điệu tệ (R = 0.8). Tỉ lệ FAIL thật ước lượng bằng Rogan-Gladen là 0.30 so với 0.28 quan sát được.
- **helpful bị loại, không được dùng làm gate.** Precision 1.0 trông đẹp nhưng sai cách đọc: judge gần như không bao giờ nói FAIL (9/100). Recall chỉ 0.30, tức bỏ sót 21/30 reply không hữu ích; κ = 0.375 < 0.6. Một gate dùng judge này sẽ báo "chỉ 9% lỗi" trong khi tỉ lệ thật (Rogan-Gladen) là **30%**, gấp hơn 3 lần.
- **Nguyên nhân gốc:** 18/21 lỗi bị bỏ sót là FM-08 (reply nói số tiền khác ledger). Judge chỉ đọc reply, không có ledger, nên **về nguyên tắc không thể** chấm được lỗi này. Đúng quy tắc của bài: *tiền luôn chấm bằng code*. Thay judge helpful bằng grader code so số tiền trong reply với `snapshot.refund_vnd` (metric FM-08 ở M3); phần còn lại (reply thiếu trạng thái) xử lý bằng rubric mới cho judge và đo lại.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí); sửa rubric theo chính các ca này rồi đo lại trên cùng tập sẽ overfit. Cần nhãn người mới để có tập held-out thật, và cần ≥2 người gán nhãn để đo κ giữa người với người (H-081 cho thấy nhãn người cũng có thể sai).
