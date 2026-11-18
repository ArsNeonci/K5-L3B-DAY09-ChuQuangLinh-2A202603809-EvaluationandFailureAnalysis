# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55   # cùng lỗi, có thật ở baseline
```

## Case của tôi: `seeded_regression C-002@11` (FM-03 ticket_trust)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, trong report `E-seeded_regression-20261118-c333` (`src/reports/eval_seeded_regression.json`), eval set `c3335ff5e34b`. |
| Triệu chứng | Grader Lab 8 FAIL (`status resolved != denied`). Reply: "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." Ledger ghi `refund_vnd=20000`, `refund_count=1`; nhãn là `denied`, 0đ, 0 lần hoàn. Reply trôi chảy và khớp ledger, nên `ReplyMatchesLedger` vẫn PASS: **lỗi nằm ở quyết định, không ở lời văn**. |
| Bước sai đầu tiên | **Event 3 `model_override {"delay_days": 5}`.** Ticket C-002 nói "trễ 5 ngày" còn `lookup_order` (event 2) trả `delay_days=2`; agent ghi đè số của DB bằng số trong ticket. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng hợp đồng (`allowed_tools` chỉ đọc). Event 2 `investigator` đọc đơn O-202 đúng: `visible=true`, `delay_days=2`. Event 3 là nơi giá trị sai xuất hiện lần đầu; event 4 `quote 20000` (clause `SHIP-LATE-03`) và event 6 `reply` chỉ là hệ quả (quote tính trên 5 ngày; với 2 ngày chính sách cho 0đ). |
| Failure mode | **FM-03** `ticket_trust` (`docs/failure_taxonomy.md`). |
| Đối chứng | `fixed C-002@11`: không có event `model_override`; event 3 `quote 0, reason no_entitlement`; reply "chưa đủ điều kiện hoàn"; ledger 0; Lab 8 grader PASS. Khác biệt duy nhất là event 3. |
| Regression test | `tests/test_lab9_trace_case.py`: (1) `test_first_wrong_step_is_the_model_override` khẳng định event 3 là `model_override {"delay_days": 5}` trên variant lỗi và không có event đó trên `fixed`; (2) `test_graders_catch_the_bug_and_pass_fixed`: `DbFactKept`, `RefundAmountCorrect`, `TrialPass` đều **fail** trên `seeded_regression` và **pass** trên `fixed`. Đã chạy: 2 test xanh (`pytest -m student -k "lab9 and not advanced"`). Case này cũng là item `E-002` trong eval set (`provenance.from_trace`). |
| Chưa chắc chắn | (1) Trace không cho biết *vì sao* MockLLM ưu tiên ticket; MockLLM chỉ mô phỏng, model thật có thể fail theo cách khác. (2) `seeded_regression` bật lỗi này ở mọi seed, còn ở `swarm` lỗi chỉ xuất hiện khi seed chia hết 5, nên tỉ lệ lỗi ngoài đời không suy ra được từ đây. (3) Test dùng đúng event `model_override`: một agent ghi đè mà **không** để lại event (`quiet_override`) sẽ không bị `DbFactKept` bắt, chỉ bị `RefundAmountCorrect` / `ProposalMatchesPolicy` / slice bắt. |

## Vì sao case này đáng giữ
Lỗi cùng loại **có thật ở baseline** chứ không chỉ ở variant cố tình gài: `swarm C-002@55` ra đúng chuỗi `model_override {"delay_days": 5}` → `quote 20000` → hoàn 20.000đ. Đó là trial duy nhất fail của baseline (1/70 trial ở v1, `pass_rate` 0.9857), và nó fail vì seed 55 chia hết 5, điểm yếu cố ý của `swarm_reference`. Vì vậy `fixed` (không bao giờ tin ticket) cho `pass_rate` 1.0 và `Δ +0.014`, CI [0.000, +0.043] khi so với baseline.

## Quy tắc đã áp dụng
- Đọc **ledger trước reply**: ở case này reply và ledger khớp nhau mà vẫn sai so với nhãn.
- "Bước sai đầu tiên" dẫn số event cụ thể (event 3), không phải "agent bị nhầm".
- Case hoàn thành vì có regression test chạy được (`tests/test_lab9_trace_case.py`) và là item trong eval set.
