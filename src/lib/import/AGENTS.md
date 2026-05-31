# src/lib/import/AGENTS.md

This folder owns CSV parsing and transaction import orchestration.

## Responsibilities

- Validate the provided CSV columns.
- Parse rows with PapaParse.
- Preserve raw transaction data.
- Call normalization, categorization, and synthetic assignment flows needed for the current import path.

## Required CSV columns

- Transaction Code
- Transaction Description
- Transaction Category
- Posting date of transaction
- Transaction Date
- Merchant Info DBA Name
- Transaction Amount
- Debit or Credit
- Merchant Category Code
- Merchant City
- Merchant Country
- Merchant Postal Code
- Merchant State/Province
- Conversion Rate

## Rules

- Do not silently ignore missing required columns.
- Report row-level import errors clearly.
- Preserve original raw values in `raw_transactions`.
- Convert to normalized transactions only after validation.
- Keep imports deterministic so re-importing the same file gives stable synthetic employee assignments.
- Write `businessCategory` as the finance-facing category and keep `normalizedCategory` populated for compatibility.
- Do not create receipt or preapproval records here unless the user explicitly asks to migrate that workflow into import.
- Do not silently trigger policy or risk scans from import unless the product change explicitly requires it.
