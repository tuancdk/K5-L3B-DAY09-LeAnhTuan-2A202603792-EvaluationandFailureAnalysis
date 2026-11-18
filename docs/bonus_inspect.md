# Bonus: port 3 grader sang Inspect AI và so khớp

```bash
cd src
python -m pip install -r requirements-bonus.txt     # inspect_ai==0.3.291, tách khỏi requirements của CI
python -m bonus.inspect_port                        # 7 shape × eval set v2 (28 item × 5 seed)
```

Code: `src/bonus/inspect_port.py`. Kết quả do script ghi: `src/reports/bonus_inspect_compare.json`.

## Cách port

| lab9 (pydantic-evals) | Inspect AI | Ghi chú |
|---|---|---|
| `Dataset` / `Case` = item@seed | `Task` với 1 `Sample` cho mỗi item@seed; nhãn nằm trong `Sample.metadata["label"]` | Nhãn vẫn đọc từ `labels_v2.json`, không inline trong item |
| task `run_one` (lab9.eval) | `@solver run_shape`: chạy shape trên SQLite tạm qua host Lab 8, lưu Trial vào `state.store` | Model `mockllm/model` có sẵn của Inspect: chạy offline, solver không gọi model |
| `ApprovalBypass` | `@scorer approval_bypass` (1 = vi phạm) | |
| `RefundAmountCorrect` | `@scorer refund_amount_correct` | So ledger với nhãn, không đọc reply |
| `ReplyMatchesLedger` (FM-08) | `@scorer reply_matches_ledger` | Regex số tiền viết lại riêng trong file port |

Ba scorer được **viết lại độc lập**, không import `lab9.graders`. Nếu chỉ gọi lại grader cũ thì việc so khớp không chứng minh được gì. `max_samples=1` giữ các lần chạy tuần tự như `lab9.eval` (`max_concurrency=1`), vì các shape ghi chung thư mục trace.

## Kết quả (eval set v2 `52023ce92e20`, 140 trial mỗi shape)

| Shape | approval_bypass (đếm) | refund_amount_correct | reply_matches_ledger | Khớp |
|---|---|---|---|---|
| swarm (baseline) | 0 / 0 | 0.9786 / 0.9786 | 1.0 / 1.0 | 420/420 |
| fixed | 0 / 0 | 1.0 / 1.0 | 1.0 / 1.0 | 420/420 |
| seeded_regression | 0 / 0 | 0.7857 / 0.7857 | 0.7143 / 0.7143 | 420/420 |
| honest_refactor | 0 / 0 | 1.0 / 1.0 | 1.0 / 1.0 | 420/420 |
| slice_regression | 0 / 0 | 0.9357 / 0.9357 | 1.0 / 1.0 | 420/420 |
| flaky_regression | 0 / 0 | 0.9643 / 0.9643 | 1.0 / 1.0 | 420/420 |
| sibling_regression* | 55 / 55 | 0.6071 / 0.6071 | 1.0 / 1.0 | 420/420 |

Mỗi ô ghi giá trị pydantic-evals / Inspect AI. **Tổng 2.940/2.940 kết quả chấm khớp từng dòng** (theo item, seed, metric); script trả exit 0.

\* `sibling_regression` = `fixed` + công tắc `sibling_refund` (FM-07), chỉ dùng cho bonus. Không variant công khai nào làm `approval_bypass` > 0, nên cần thêm variant này để so khớp có cả trường hợp vi phạm, không chỉ toàn số 0.

## Nhận xét

- Việc so khớp có ý nghĩa vì dữ liệu chứa cả dòng đạt lẫn dòng lỗi ở mỗi metric: 55 vi phạm approval, `refund_amount_correct` thấp tới 0.6071, `reply_matches_ledger` 0.7143.
- Hai framework khác nhau ở phần hạ tầng (Inspect có log `.eval`, `store`, metric `mean()`), nhưng với grader code tất định thì phần quyết định chỉ là logic chấm. Khớp 100% cho thấy logic không phụ thuộc framework và bản port không sai lệch.
- Giới hạn: chỉ port 3 grader code; `pass_rate` (grader của Lab 8) và các judge LLM chưa được port. Chưa so trên model thật, nơi Inspect có thêm `epochs` để đo pass^k trực tiếp.
