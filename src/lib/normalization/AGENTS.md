# src/lib/normalization/AGENTS.md

This folder owns transaction normalization.

## Responsibilities

- Parse dates.
- Normalize merchant names.
- Compute CAD amounts.
- Interpret debit/credit direction.
- Clean unreliable fields without destroying raw data.

## Rules

- Raw values must remain preserved in `raw_transactions`.
- `Conversion Rate` of 0, null, empty, or missing means no conversion; `amountCad = transactionAmount`.
- Otherwise `amountCad = transactionAmount * conversionRate`.
- Debit means expense.
- Credit means refund or reversal.
- Merchant city may contain phone numbers or bad values; do not rely on it heavily.
- Merchant normalization should be conservative and explainable.

## Examples

- `FEDEX268575826` should normalize toward `FEDEX`.
- `CAT SCALE COMPANY` should remain `CAT SCALE COMPANY`.
