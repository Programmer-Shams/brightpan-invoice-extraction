# Manual review of mismatches

Run `20261021T110006Z` (`eval/results.csv`). Every field or line item that didn't match the answer key, with the
reviewer's verdict. The verdict is final; reported numbers follow it.

| Document | Field | Answer key | Read as | Verdict |
| --- | --- | --- | --- | --- |
| RCPT01 | line 1 | Bubble wrap roll 12in x 175ft, qty 2, 24.99, 49.98 | Bubble wrap roll 12in x 17, qty 2, 24.99, 49.98 | **Counted as a miss.** The receipt itself prints the name cut off at "12in x 17" (narrow till receipt); the system recorded it exactly as printed and quantity, unit price and amount are correct. Kept as a miss for strict reporting. |

Reviewed 2026-10-21 by the project owner. Reported result: 200/200 header fields, 79/80 line items.
