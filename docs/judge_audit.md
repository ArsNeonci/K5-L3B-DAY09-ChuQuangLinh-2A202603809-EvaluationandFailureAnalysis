# Judge audit

Chạy (replay, không cần key; FAIL là lớp dương):
```
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5     # PASS floors, exit 0
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5  # FAIL floors, exit 1
```

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt cả 3** | **Dùng** (làm tín hiệu theo dõi, không thay code grader) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Trượt κ và recall** | **Loại** |

Ma trận nhầm lẫn (FAIL = dương): `tone_ok` tp 24 · fp 4 · fn 6 · tn 66; `helpful` tp 9 · fp 0 · fn 21 · tn 70.
Tỉ lệ lỗi quan sát → hiệu chỉnh Rogan-Gladen: `tone_ok` 0.28 → **0.30** (judge gần đúng, sửa rất ít); `helpful` 0.09 → **0.30** (judge báo thiếu 3.3 lần).

## Vì sao `helpful` không được làm gate
1. **Recall 0.30:** trong 30 reply người gán FAIL, judge chỉ bắt 9. Một gate dựa vào nó cho qua 70% reply hỏng, và precision 1.0 chỉ nói rằng khi nó hô FAIL thì đúng, không nói gì về những lần nó im lặng.
2. **Lý do nằm ở thông tin judge không có.** Trong 21 lần bỏ sót, 18 lần nhãn người là "sai tiền" (ví dụ HL-015: reply nói 55.000đ, ledger ghi 40.000đ) và 3 lần là "sai xưng hô". Judge chỉ nhìn reply, không nhìn ledger, nên một câu xin lỗi trôi chảy luôn qua mặt nó. Đáng chú ý: các reply có đoạn xin lỗi dài (HL-016, 028, 035, 041, 043, 053, 058, 070, 072, 074, 090, 096, 098) đều bị judge cho PASS dù sai tiền; sự lịch sự đã che mất lỗi.
3. **Sửa đúng chỗ:** "đúng số tiền" là việc của code đọc ledger (`ReplyMatchesLedger`, FM-08), không phải của judge. Phần "sai xưng hô" thuộc tiêu chí tone và nên chuyển sang `tone_ok` (nó đã đạt calibration).
4. Nếu vẫn dùng judge này làm gate, tỉ lệ lỗi báo cáo là 9% trong khi tỉ lệ thật khoảng 30%: một con số đẹp nhưng sai.

## Audit thủ công ≥5 bất đồng (`tone_ok`, 10 bất đồng trong CSV, dưới đây là 8)
Quy ước: "Người" và "Judge" là nhãn trong CSV. Cột *Ai đúng* là kết luận của tôi sau khi đọc reply và ghi chú.

| # | Case | Judge | Người | Ai đúng? | Hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | **Người.** Xưng "em" + "nha" suồng sã với khách khiếu nại. | Thêm: *bắt buộc mở bằng "Dạ" và xưng "LogiX … anh/chị"; không dùng "nha", "nhé"*. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ … rồi nha." | PASS | FAIL | **Người.** Gọi khách là "bạn" (không rõ tuổi) + "nha". | Cùng quy tắc xưng hô: chỉ "anh/chị"; liệt kê "bạn", "em", "nha" là FAIL. |
| 3 | H-029 "Dạ, vui lòng chờ. … không cần nhắn thêm." | PASS | FAIL | **Người.** Giọng ra lệnh; judge chỉ thấy "Dạ, vui lòng". | Thêm ví dụ FAIL: câu cấm/ra lệnh khách ("không cần nhắn thêm"); judge phải đọc cả câu, không dừng ở từ mở đầu. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người.** Ngắn nhưng đủ ý, lịch sự; judge phạt vì "thiếu xin lỗi". | Ghi rõ: *chỉ cần xin lỗi khi có lỗi của LogiX hoặc khách phản ánh; reply thông báo kết quả không cần*. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ …" | FAIL | PASS | **Người.** CS LogiX cho phép dùng "refund"; judge phạt vì tiếng Anh. | Thêm bảng thuật ngữ cho phép (refund, ship, order) vào rubric. |
| 6 | H-070 "… hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | **Người.** Emoji cười trong ngữ cảnh khiếu nại là thiếu tôn trọng. | Cấm emoji trong reply khiếu nại; liệt kê 😂 😅 là FAIL. |
| 7 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi …" | PASS | FAIL | **Người.** Mất dấu tiếng Việt (dịch máy), khó đọc, thiếu chuyên nghiệp. | Thêm điều kiện: *phải có dấu tiếng Việt đầy đủ*. Có thể kiểm bằng regex, không cần judge. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge.** Ghi chú trong CSV: người đã đọc nhầm ticket nên nhãn PASS sai; judge đúng. Tôi chỉ có reply và ghi chú, không có ticket, nên không tự xác minh được độc lập. | **Sửa nhãn người** (H-081 → FAIL) rồi tính lại; quy trình: mỗi nhãn người phải kèm ticket để người thứ hai kiểm. |

Còn lại 2 bất đồng chưa liệt kê: H-063 ("sẽ hoàn thêm", hứa ngoài kết quả hệ thống; người đúng, nhưng đây là lỗi *cam kết*, không phải *tone*, nên chuyển sang tiêu chí faithfulness/FM-08) và H-088 ("Dạ, dạ" lỗi gõ; người đúng, lỗi chính tả thuộc tiêu chí định dạng, không tính vào tone).

**Mẫu hình chung:** judge nhầm theo hai hướng. Nó **quá khoan** với xưng hô, emoji, giọng ra lệnh, mất dấu (6 FN trong tone: H-008, 017, 029, 063, 070, 094), và **quá khắt** với những thứ rubric chưa nói rõ (4 FP: H-042, 051, 081, 088). Cả hai hướng đều là rubric thiếu ví dụ, không phải lỗi ngẫu nhiên.

## Kết luận
- **Loại `helpful`** (κ 0.375, recall 0.30); "đúng số tiền" chuyển cho code grader FM-08.
- **Giữ `tone_ok`** với rubric đã bổ sung ở cột cuối bảng. Lần chạy lại cần nhãn người mới để đo xem κ có tăng không.
- **Rủi ro còn lại:** (1) judge chỉ được kiểm trên dữ liệu replay đã công khai, chưa có tập held-out mới; (2) n=100 nên κ có khoảng tin cậy rộng, 0.757 chưa chắc vượt 0.6 ổn định; (3) một nhãn người (H-081) đã sai, nghĩa là "nhãn vàng" cũng cần kiểm; (4) judge thật khác judge replay: kết quả không suy ra được cho model khác.
