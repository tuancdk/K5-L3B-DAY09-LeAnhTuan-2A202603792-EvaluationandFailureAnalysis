# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: `swarm C-002@55` (baseline thật, không phải variant gài lỗi)

Output (rút gọn payload):

```
== swarm C-002@55  lab8 grader: FAIL (status resolved != denied)
   1 handoff            {"task": "check_applicable_policy", "claim_id": "C-002", "principal_scope": "owner_order_only", ...}
   2 investigator       {"lookup_order": {"visible": true, "order": {"order_id": "O-202", "status": "delivered",
                          "delay_days": 2, "shipping_fee_vnd": 20000, ...}}, "policy_count": 1}
   3 model_override     {"delay_days": 5}
   4 quote              {"amount_vnd": 20000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"], ...}
-- ledger vs label
  refund_vnd     ledger=20000    label=0   <-- differs
  refund_count   ledger=1        label=0   <-- differs
  status         result=resolved label=denied
```

| Trường | Nội dung |
|---|---|
| Trial | `swarm C-002@55`, trace run `R-swarm-C-002-s55`; trong report baseline `E-swarm-20261118-c319` (eval set `c319d666cd27`) đây là trial fail duy nhất trong 70 (`pass_rate` 0.9857 = 69/70) |
| Triệu chứng | `TrialPass` FAIL (`status resolved != denied`), `RefundAmountCorrect` FAIL (ledger 20.000đ, nhãn 0đ), `DbFactKept` FAIL (1 event `model_override`). Ticket: "Đơn giao trễ 5 ngày, hoàn phí ship giúp." Khách được hoàn 20.000đ phí ship cho một đơn **không đủ điều kiện**. |
| Bước sai đầu tiên | **Event 3 `model_override`** `{"delay_days": 5}`: agent đè `delay_days` của DB bằng số ngày khách tự khai trong ticket. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng contract (task, scope `owner_order_only`, tool read-only). Event 2 `investigator` đọc đúng sự thật từ DB: O-202 `delivered`, `delay_days: 2`, tức chưa tới ngưỡng trễ của SHIP-LATE-03. Đến hết event 2, agent có đủ dữ liệu đúng để từ chối. Event 4 `quote` 20.000đ chỉ là hệ quả: `compute_compensation` tính đúng trên input đã bị đè (5 ngày). |
| Failure mode | **FM-03 ticket_trust** (`docs/failure_taxonomy.md`). Layer model/prompt: trong `swarm_reference`, nhánh tin ticket bật khi `seed % 5 == 0`, nên với bộ seed 11/22/33/44/55 lỗi luôn rơi vào seed 55. |
| Đối chứng | `fixed C-002@55`: event 2 giống hệt (`delay_days: 2`), **không có** `model_override`; event 3 `quote` `{"amount_vnd": 0, "reason": "no_entitlement"}` → `denied`, ledger 0, PASS. Cùng claim trên `swarm` seed 11 cũng PASS, nên lỗi phụ thuộc seed chứ không phụ thuộc dữ liệu. |
| Regression test | `src/tests/test_lab9_trace_case.py` (marker `student`, chạy trong CI bằng `-k "lab9 and not advanced"`): `test_lab9_trace_case_ticket_trust_is_caught[swarm / seeded_regression]` assert event ngay sau `investigator` là `model_override`, ledger 20.000, và `db_fact_kept`, `refund_amount_correct`, `pass_rate` đều FAIL; `test_lab9_trace_case_fixed_is_clean` assert `fixed` không có override, ledger 0 và mọi grader sạch. **Đã chạy: 3/3 pass** (fail trên variant lỗi được phát hiện, pass trên `fixed`). Item tương ứng trong eval set: E-002 (`failure_modes: ["FM-03"]`). |
| Chưa chắc chắn | (1) Trace của `swarm` Lab 8 không có event `reply`, nên không biết khách được báo gì; FM-08 trên baseline không đo được. (2) MockLLM tất định: trên LLM thật, việc "tin ticket" không gắn với `seed % 5` mà là xác suất, có thể cao hơn 1/5 với ticket nói số ngày cụ thể. (3) Trace không cho biết vì sao model tin ticket (prompt hay ngữ cảnh); chỉ cho biết **là** nó đã tin. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
