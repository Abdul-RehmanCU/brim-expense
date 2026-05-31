from __future__ import annotations

from typing import Any, Iterable, Protocol, TypeVar


class ReviewClusterItem(Protocol):
    review_group_key: str | None
    review_group_size: int
    review_group_total_amount_cad: float
    review_group_transaction_ids: list[str]

    def model_copy(self, *, update: dict[str, Any]) -> Any:
        ...


TReviewClusterItem = TypeVar("TReviewClusterItem", bound=ReviewClusterItem)


def review_group_key_from_transaction(transaction: dict[str, Any]) -> str:
    return review_group_key_from_values(
        transaction_id=str(transaction.get("id") or ""),
        employee_id=string_or_none(transaction.get("employee_id")),
        department_id=string_or_none(transaction.get("department_id")),
        merchant=string_or_none(transaction.get("normalized_merchant_name") or transaction.get("merchant_name")),
        transaction_date=string_or_none(transaction.get("transaction_date")),
        category=string_or_none(
            transaction.get("business_category")
            or transaction.get("policy_category")
            or transaction.get("normalized_category")
        ),
    )


def review_group_key_from_values(
    *,
    transaction_id: str,
    employee_id: str | None,
    department_id: str | None,
    merchant: str | None,
    transaction_date: str | None,
    category: str | None,
) -> str:
    if not merchant or not transaction_date or not employee_id:
        return f"transaction:{transaction_id}"

    return "|".join(
        [
            "review-context",
            normalize_group_value(employee_id),
            normalize_group_value(department_id),
            normalize_group_value(merchant),
            transaction_date,
            normalize_group_value(category),
        ]
    )


def annotate_review_clusters(items: Iterable[TReviewClusterItem]) -> list[TReviewClusterItem]:
    materialized = list(items)
    grouped: dict[str, list[TReviewClusterItem]] = {}
    for item in materialized:
        key = item.review_group_key or f"transaction:{item.review_group_transaction_ids[0] if item.review_group_transaction_ids else ''}"
        grouped.setdefault(key, []).append(item)

    annotated: list[TReviewClusterItem] = []
    for item in materialized:
        key = item.review_group_key or f"transaction:{item.review_group_transaction_ids[0] if item.review_group_transaction_ids else ''}"
        cluster = grouped.get(key, [item])
        transaction_ids = [
            transaction_id
            for cluster_item in cluster
            for transaction_id in cluster_item.review_group_transaction_ids
        ]
        annotated.append(
            item.model_copy(
                update={
                    "review_group_size": len(cluster),
                    "review_group_total_amount_cad": round(sum(cluster_item.review_group_total_amount_cad for cluster_item in cluster), 2),
                    "review_group_transaction_ids": dedupe_strings(transaction_ids),
                }
            )
        )
    return annotated


def normalize_group_value(value: Any) -> str:
    return " ".join(str(value or "unknown").strip().lower().split())


def string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        text = str(value).strip()
        if text:
            seen.setdefault(text, None)
    return list(seen)
