# src/lib/categorization/AGENTS.md

This folder owns deterministic transaction categorization.

## Responsibilities

- Categorize transactions using merchant name, MCC, description, and country/state.
- Return category labels with confidence scores.
- Keep merchant and MCC rules explicit and editable.

## Rules

- Do not call external APIs from this folder.
- Prefer deterministic matching before AI.
- Return `Uncategorized` with low confidence when uncertain.
- Store confidence and reason where useful.
- Prefer finance-facing category labels for `businessCategory`.
- Keep `normalizedCategory` aligned as a compatibility alias until the migration is complete.
- When a transaction could match both permits and fuel, permit/government-fee logic should win.
- When account-side credits or redemptions are clearly identifiable, prefer explicit excluded non-expense categories over generic `Uncategorized`.

## Example mappings

- FEDEX, UPS, DHL, MCC 4215 -> Shipping / Courier
- UBER, LYFT, TAXI -> Ground Transportation
- ENTERPRISE, HERTZ, AVIS, NATIONAL CAR -> Car / Truck Rental
- MNDOT, UDOT, DOT, DMV, DEPT OF TRANS, OSOW, PERMIT -> Permits / Government Fees
- CWB EFT PAYMENT -> Account Payment / Transfer
- POINT REDEMPTION -> Reward / Redemption
- LCBO, SAQ, LIQUOR, BEER, WINE -> Alcohol / Restricted
- CAT SCALE COMPANY -> Transportation / Fleet / Operations
