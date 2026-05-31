from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from math import isfinite
from typing import Any

import pandas as pd

from app.schemas.data_quality import (
    DataQualityFinding,
    DataQualitySummary,
    DataQualityValidationResponse,
    GreatExpectationsAudit,
)

ALLOWED_DEBIT_CREDIT = {"debit", "credit"}
BASE_REQUIRED_COLUMNS = {"transaction_date", "posting_date", "amount_cad", "debit_credit"}
HIGH_POSTING_DELAY_DAYS = 30
MEDIUM_POSTING_DELAY_DAYS = 10
WEAK_SOURCE_CATEGORY_CODES = {"1", "0001"}
WEAK_SOURCE_CATEGORY_PREVALENCE = 0.35
NON_EXPENSE_TYPES = {
    "account_payment",
    "cash_advance_reversal",
    "merchant_credit",
    "reward_redemption",
}
NON_EXPENSE_ELIGIBILITIES = {"excluded_non_expense"}
MISSING_VALUES = {"", "none", "null", "nan", "n/a", "na"}


def validate_transaction_dataset(
    rows: Sequence[Mapping[str, Any]] | pd.DataFrame,
    *,
    run_great_expectations: bool = True,
) -> DataQualityValidationResponse:
    dataframe = _coerce_dataframe(rows)
    records = _coerce_records(dataframe)
    findings: list[DataQualityFinding] = []

    findings.extend(_missing_column_findings(dataframe))

    weak_source_rows = 0
    for row_index, row in enumerate(records):
        context = _RowContext(row=row, row_index=row_index)
        findings.extend(_validate_row(context))
        if _is_weak_source_category(row.get("source_category")):
            weak_source_rows += 1

    findings.extend(_dataset_level_findings(len(records), weak_source_rows))

    return DataQualityValidationResponse(
        row_count=len(records),
        findings=findings,
        summary=_build_summary(len(records), findings),
        great_expectations=_run_great_expectations_audit(dataframe) if run_great_expectations else GreatExpectationsAudit(),
    )


def _coerce_dataframe(rows: Sequence[Mapping[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(rows, pd.DataFrame):
        return rows.copy()
    return pd.DataFrame([dict(row) for row in rows])


def _coerce_records(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {column: _json_safe_value(value) for column, value in row.items()}
        for row in dataframe.to_dict(orient="records")
    ]


def _missing_column_findings(dataframe: pd.DataFrame) -> list[DataQualityFinding]:
    missing_columns = sorted(BASE_REQUIRED_COLUMNS - set(dataframe.columns))
    return [
        DataQualityFinding(
            rule_id="required_column_missing",
            severity="high",
            field=column,
            explanation=f"Required transaction field `{column}` is absent from the dataset.",
            remediation=f"Map the import source to `{column}` before persisting or validating transactions.",
        )
        for column in missing_columns
    ]


def _validate_row(context: _RowContext) -> list[DataQualityFinding]:
    row = context.row
    findings: list[DataQualityFinding] = []

    transaction_date = _parse_date(row.get("transaction_date"))
    posting_date = _parse_date(row.get("posting_date"))
    amount = _parse_amount(_first_present(row, ["amount_cad", "amount", "transaction_amount"]))
    debit_credit = _normalized_text(row.get("debit_credit"))
    is_expense = _is_expense_like(row, debit_credit, amount)

    if not transaction_date:
        findings.append(
            context.finding(
                "transaction_date_parseable",
                "high",
                "transaction_date",
                "Transaction date is missing or cannot be parsed as a calendar date.",
                "Correct the source date value and re-import the row.",
                row.get("transaction_date"),
            )
        )

    if not posting_date:
        findings.append(
            context.finding(
                "posting_date_parseable",
                "medium",
                "posting_date",
                "Posting date is missing or cannot be parsed as a calendar date.",
                "Correct the source posting date or mark the row for import review.",
                row.get("posting_date"),
            )
        )

    if amount is None:
        findings.append(
            context.finding(
                "amount_numeric",
                "high",
                "amount_cad",
                "Transaction amount is missing or not numeric.",
                "Normalize the amount to a numeric CAD value before downstream analysis.",
                _first_present(row, ["amount_cad", "amount", "transaction_amount"]),
            )
        )

    if debit_credit not in ALLOWED_DEBIT_CREDIT:
        findings.append(
            context.finding(
                "debit_credit_allowed",
                "high",
                "debit_credit",
                "Debit/credit indicator is outside the allowed set.",
                "Map the value to `debit` or `credit` before persistence.",
                row.get("debit_credit"),
            )
        )

    if is_expense and _is_blank(_merchant_value(row)):
        findings.append(
            context.finding(
                "merchant_required_for_expense",
                "high",
                "merchant_name",
                "Expense-like transaction has no merchant name.",
                "Recover merchant details from the source row or queue the row for manual review.",
                _merchant_value(row),
            )
        )

    if is_expense:
        findings.extend(_metadata_completeness_findings(context))
        findings.extend(_category_quality_findings(context))

    findings.extend(_conversion_rate_findings(context, amount))
    findings.extend(_posting_delay_findings(context, transaction_date, posting_date))
    findings.extend(_source_category_findings(context))

    return findings


def _metadata_completeness_findings(context: _RowContext) -> list[DataQualityFinding]:
    checks = [
        ("merchant_category_code", "medium", "Merchant category code is missing for an expense-like row."),
        ("merchant_country", "medium", "Merchant country is missing for an expense-like row."),
        ("merchant_region", "low", "Merchant region/state is missing for an expense-like row."),
    ]
    findings: list[DataQualityFinding] = []
    for field, severity, explanation in checks:
        if _is_blank(context.row.get(field)):
            findings.append(
                context.finding(
                    "merchant_metadata_complete",
                    severity,
                    field,
                    explanation,
                    f"Populate `{field}` from the import source or enrichment step.",
                    context.row.get(field),
                )
            )
    return findings


def _category_quality_findings(context: _RowContext) -> list[DataQualityFinding]:
    row = context.row
    category = _first_present(row, ["business_category", "normalized_category"])
    category_source = _normalized_text(row.get("category_source"))
    confidence = _parse_amount(row.get("category_confidence"))
    findings: list[DataQualityFinding] = []

    if _is_blank(category):
        findings.append(
            context.finding(
                "category_present",
                "medium",
                "business_category",
                "Expense-like row has no business or normalized category.",
                "Run deterministic categorization or queue the merchant for category mapping.",
                category,
            )
        )
    elif _normalized_text(category) in {"uncategorized", "unknown", "other"}:
        findings.append(
            context.finding(
                "category_specificity",
                "medium",
                "business_category",
                "Category is too generic for reliable spend analysis.",
                "Add a merchant, MCC, or source-category mapping to assign a finance-facing category.",
                category,
            )
        )

    if category_source in {"fallback", "unknown", "unmapped"}:
        findings.append(
            context.finding(
                "category_source_strength",
                "low",
                "category_source",
                "Category was assigned by a weak fallback source.",
                "Prefer deterministic merchant, MCC, or source-code rules for this row.",
                row.get("category_source"),
            )
        )
    if confidence is not None and confidence < 0.5:
        findings.append(
            context.finding(
                "category_confidence_low",
                "low",
                "category_confidence",
                "Category confidence is below the quality threshold.",
                "Review or enrich the category assignment before using it for reporting.",
                row.get("category_confidence"),
            )
        )

    return findings


def _conversion_rate_findings(context: _RowContext, amount_cad: float | None) -> list[DataQualityFinding]:
    row = context.row
    findings: list[DataQualityFinding] = []
    conversion_rate = _parse_amount(row.get("conversion_rate"))
    amount_original = _parse_amount(row.get("amount_original"))
    foreign = _is_foreign_merchant(row)

    if foreign and (conversion_rate is None or conversion_rate <= 0):
        findings.append(
            context.finding(
                "foreign_transaction_conversion_rate",
                "high",
                "conversion_rate",
                "Foreign merchant row has a zero, missing, or invalid conversion rate.",
                "Verify the source FX rate and recompute `amount_cad` if a conversion applies.",
                row.get("conversion_rate"),
            )
        )
    elif conversion_rate is not None and (conversion_rate < 0 or conversion_rate > 5):
        findings.append(
            context.finding(
                "conversion_rate_range",
                "medium",
                "conversion_rate",
                "Conversion rate is outside the expected deterministic validation range.",
                "Confirm the rate was parsed as a multiplier, not a percentage or malformed value.",
                row.get("conversion_rate"),
            )
        )

    if (
        conversion_rate is not None
        and conversion_rate > 0
        and amount_original is not None
        and amount_cad is not None
        and abs(round(amount_original * conversion_rate, 2) - round(amount_cad, 2)) > 0.02
    ):
        findings.append(
            context.finding(
                "amount_conversion_consistency",
                "medium",
                "amount_cad",
                "CAD amount does not match original amount multiplied by conversion rate.",
                "Recalculate `amount_cad` from `amount_original` and `conversion_rate`.",
                amount_cad,
            )
        )

    return findings


def _posting_delay_findings(
    context: _RowContext,
    transaction_date: date | None,
    posting_date: date | None,
) -> list[DataQualityFinding]:
    delay = _parse_int(context.row.get("posting_delay_days"))
    if delay is None and transaction_date and posting_date:
        delay = (posting_date - transaction_date).days
    if delay is None:
        return []
    if delay < 0:
        return [
            context.finding(
                "posting_delay_negative",
                "high",
                "posting_delay_days",
                "Posting date is earlier than transaction date.",
                "Correct one of the transaction/posting dates before using the row.",
                delay,
            )
        ]
    if delay > HIGH_POSTING_DELAY_DAYS:
        severity = "high"
    elif delay > MEDIUM_POSTING_DELAY_DAYS:
        severity = "medium"
    else:
        return []

    return [
        context.finding(
            "posting_delay_outlier",
            severity,
            "posting_delay_days",
            f"Posting delay of {delay} days is outside normal import expectations.",
            "Verify dates and confirm this delayed posting should remain in the dataset.",
            delay,
        )
    ]


def _source_category_findings(context: _RowContext) -> list[DataQualityFinding]:
    if not _is_weak_source_category(context.row.get("source_category")):
        return []
    return [
        context.finding(
            "weak_source_category_0001",
            "low",
            "source_category",
            "Source category `0001` is weak because it usually only identifies a broad purchase rail.",
            "Use merchant, MCC, and deterministic category enrichment rather than relying on `0001`.",
            context.row.get("source_category"),
        )
    ]


def _dataset_level_findings(row_count: int, weak_source_rows: int) -> list[DataQualityFinding]:
    if row_count == 0:
        return []
    prevalence = weak_source_rows / row_count
    if prevalence < WEAK_SOURCE_CATEGORY_PREVALENCE:
        return []
    return [
        DataQualityFinding(
            rule_id="weak_source_category_0001_prevalence",
            severity="medium",
            field="source_category",
            observed_value=round(prevalence, 4),
            explanation=f"{weak_source_rows} of {row_count} rows use weak source category `0001`.",
            remediation="Prioritize merchant, MCC, and category enrichment before reporting on source categories.",
        )
    ]


def _run_great_expectations_audit(dataframe: pd.DataFrame) -> GreatExpectationsAudit:
    try:
        import great_expectations as gx
        from great_expectations.core.expectation_suite import ExpectationSuite
    except ImportError:
        return GreatExpectationsAudit(available=False, error="great_expectations is not installed")

    try:
        context = gx.get_context(mode="ephemeral")
        context.variables.progress_bars = {"globally": False, "metric_calculations": False}
        datasource = context.data_sources.add_pandas("brim_data_quality")
        asset = datasource.add_dataframe_asset("transactions")
        batch_definition = asset.add_batch_definition_whole_dataframe("whole_dataframe")
        batch = batch_definition.get_batch(batch_parameters={"dataframe": dataframe})
        suite = ExpectationSuite(name="brim_transaction_data_quality")
        context.suites.add(suite)
        validator = context.get_validator(batch=batch, expectation_suite=suite)

        results = []
        for column in sorted(BASE_REQUIRED_COLUMNS & set(dataframe.columns)):
            results.append(validator.expect_column_values_to_not_be_null(column))
        if "debit_credit" in dataframe.columns:
            results.append(validator.expect_column_values_to_be_in_set("debit_credit", sorted(ALLOWED_DEBIT_CREDIT)))

        return GreatExpectationsAudit(
            available=True,
            evaluated_expectations=len(results),
            failed_expectations=sum(1 for result in results if not result.success),
        )
    except Exception as error:  # pragma: no cover - Great Expectations internals vary by version.
        return GreatExpectationsAudit(available=True, error=str(error))


def _build_summary(row_count: int, findings: list[DataQualityFinding]) -> DataQualitySummary:
    counts = Counter(finding.severity for finding in findings)
    rows_with_findings = {
        finding.row_index
        for finding in findings
        if finding.row_index is not None
    }
    return DataQualitySummary(
        row_count=row_count,
        finding_count=len(findings),
        critical_count=counts["critical"],
        high_count=counts["high"],
        medium_count=counts["medium"],
        low_count=counts["low"],
        rows_with_findings=len(rows_with_findings),
    )


def _first_present(row: Mapping[str, Any], fields: Iterable[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if not _is_blank(value):
            return value
    return None


def _is_expense_like(row: Mapping[str, Any], debit_credit: str, amount: float | None) -> bool:
    transaction_type = _normalized_text(row.get("transaction_type"))
    eligibility = _normalized_text(row.get("transaction_eligibility"))
    if transaction_type in NON_EXPENSE_TYPES or eligibility in NON_EXPENSE_ELIGIBILITIES:
        return False
    if bool(row.get("is_account_activity")) or bool(row.get("is_credit_or_refund")):
        return False
    if debit_credit == "credit":
        return False
    return debit_credit == "debit" and (amount is None or amount > 0)


def _metadata_source(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw_transactions = row.get("raw_transactions")
    return raw_transactions if isinstance(raw_transactions, Mapping) else {}


def _merchant_value(row: Mapping[str, Any]) -> Any:
    return _first_present(row, ["normalized_merchant_name", "merchant_name"])


def _is_foreign_merchant(row: Mapping[str, Any]) -> bool:
    country = _normalized_text(row.get("merchant_country")).upper()
    if bool(row.get("is_foreign_transaction")):
        return True
    return bool(country) and country not in {"CA", "CAN", "CANADA"}


def _is_weak_source_category(value: Any) -> bool:
    normalized = str(value or "").strip()
    if normalized.isdigit():
        normalized = str(int(normalized))
    return normalized in WEAK_SOURCE_CATEGORY_CODES


def _parse_date(value: Any) -> date | None:
    if _is_blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _parse_amount(value: Any) -> float | None:
    if _is_blank(value):
        return None
    try:
        parsed = float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _parse_int(value: Any) -> int | None:
    parsed = _parse_amount(value)
    return int(parsed) if parsed is not None else None


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in MISSING_VALUES


def _normalized_text(value: Any) -> str:
    return "" if _is_blank(value) else str(value).strip().lower()


def _json_safe_value(value: Any) -> Any:
    if _is_blank(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return value


class _RowContext:
    def __init__(self, row: Mapping[str, Any], row_index: int):
        self.row = row
        self.row_index = row_index

    def finding(
        self,
        rule_id: str,
        severity: str,
        field: str,
        explanation: str,
        remediation: str,
        observed_value: Any,
    ) -> DataQualityFinding:
        raw = _metadata_source(self.row)
        return DataQualityFinding(
            rule_id=rule_id,
            severity=severity,  # type: ignore[arg-type]
            field=field,
            transaction_id=_string_or_none(self.row.get("id") or self.row.get("transaction_id")),
            source_row=_parse_int(self.row.get("source_row") or self.row.get("source_row_number") or raw.get("source_row_number")),
            source_fingerprint=_string_or_none(self.row.get("source_fingerprint") or raw.get("source_fingerprint")),
            row_index=self.row_index,
            observed_value=_json_safe_value(observed_value),
            explanation=explanation,
            remediation=remediation,
        )


def _string_or_none(value: Any) -> str | None:
    return None if _is_blank(value) else str(value)
