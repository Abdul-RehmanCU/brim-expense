from __future__ import annotations

from typing import Any, Protocol

from app.schemas.review_queue import CitedPolicyClause, ReviewerBrief
from app.schemas.risk import RiskSignal

CONFIDENCE_BY_LEVEL = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class ReviewerBriefClient(Protocol):
    def compose_reviewer_brief(self, facts: dict[str, Any]) -> ReviewerBrief:
        ...


def compose_reviewer_brief(
    *,
    transaction: dict[str, Any],
    policy_check: dict[str, Any] | None,
    risk_score: dict[str, Any] | None,
    policy_flags: list[dict[str, Any]],
    risk_signals: list[RiskSignal],
    cited_policy_clauses: list[CitedPolicyClause] | None = None,
    fallback_next_action: str = "No action required.",
    client: ReviewerBriefClient | None = None,
) -> ReviewerBrief:
    facts = reviewer_brief_facts(
        transaction=transaction,
        policy_check=policy_check,
        risk_score=risk_score,
        policy_flags=policy_flags,
        risk_signals=risk_signals,
        cited_policy_clauses=cited_policy_clauses or [],
        fallback_next_action=fallback_next_action,
    )
    if client:
        try:
            return sanitize_ai_brief(client.compose_reviewer_brief(facts), facts)
        except Exception:
            pass
    return deterministic_reviewer_brief(facts)


def reviewer_brief_facts(
    *,
    transaction: dict[str, Any],
    policy_check: dict[str, Any] | None,
    risk_score: dict[str, Any] | None,
    policy_flags: list[dict[str, Any]],
    risk_signals: list[RiskSignal],
    cited_policy_clauses: list[CitedPolicyClause],
    fallback_next_action: str,
) -> dict[str, Any]:
    return {
        "transaction": {
            "id": str(transaction.get("id") or ""),
            "date": str(transaction.get("transaction_date") or ""),
            "merchant": transaction.get("normalized_merchant_name") or transaction.get("merchant_name") or "Unknown merchant",
            "amount_cad": float(transaction.get("amount_cad") or 0),
            "category": transaction.get("business_category")
            or transaction.get("policy_category")
            or transaction.get("normalized_category")
            or "Uncategorized",
        },
        "policy": {
            "status": (policy_check or {}).get("status"),
            "severity": (policy_check or {}).get("max_severity"),
            "missing_information": list((policy_check or {}).get("missing_information") or []),
            "flags": policy_flags,
        },
        "risk": {
            "score": int((risk_score or {}).get("risk_score") or 0),
            "level": (risk_score or {}).get("risk_level"),
            "signals": [signal.model_dump() for signal in risk_signals],
        },
        "data_quality_findings": data_quality_findings(transaction),
        "cited_policy_clauses": [clause.model_dump() for clause in cited_policy_clauses],
        "fallback_next_action": fallback_next_action,
    }


def deterministic_reviewer_brief(facts: dict[str, Any]) -> ReviewerBrief:
    transaction = facts["transaction"]
    policy = facts["policy"]
    risk = facts["risk"]
    policy_flags = list(policy.get("flags") or [])
    risk_signals = list(risk.get("signals") or [])
    cited_policy_clauses = [CitedPolicyClause(**clause) for clause in facts.get("cited_policy_clauses") or []]
    missing_context = normalized_strings([*(policy.get("missing_information") or []), *facts.get("data_quality_findings", [])])
    warnings = grounding_warnings(facts)

    key_reasons = []
    for flag in policy_flags[:3]:
        label = str(flag.get("rule_code") or "Policy finding")
        severity = str(flag.get("severity") or "unrated")
        explanation = str(flag.get("explanation") or "Deterministic policy rule matched.")
        key_reasons.append(f"{label} ({severity}): {explanation}")
    for signal in risk_signals[:3]:
        label = str(signal.get("type") or "risk_signal")
        severity = str(signal.get("severity") or "unrated")
        message = str(signal.get("message") or "Risk model flagged this transaction.")
        key_reasons.append(f"{format_label(label)} risk ({severity}): {message}")
    if not key_reasons:
        key_reasons.append("No blocking policy flag or material risk signal is attached to this review queue item.")

    summary = compose_summary(
        merchant=str(transaction.get("merchant") or "Unknown merchant"),
        amount_cad=float(transaction.get("amount_cad") or 0),
        policy_status=policy.get("status"),
        risk_level=risk.get("level"),
        policy_flags=policy_flags,
        risk_signals=risk_signals,
    )

    return ReviewerBrief(
        summary=summary,
        key_reasons=key_reasons,
        cited_policy_clauses=cited_policy_clauses,
        missing_context=missing_context,
        recommended_next_action=str(facts.get("fallback_next_action") or "No action required."),
        confidence=confidence_level(policy_flags, risk_signals, cited_policy_clauses, missing_context),
        grounding_warnings=warnings,
        generated_by="deterministic_fallback",
    )


def sanitize_ai_brief(brief: ReviewerBrief, facts: dict[str, Any]) -> ReviewerBrief:
    fallback = deterministic_reviewer_brief(facts)
    allowed_reasons = set(fallback.key_reasons)
    allowed_clauses = {
        (clause.rule_code, clause.clause_id, clause.text)
        for clause in fallback.cited_policy_clauses
    }
    grounded_clauses = [
        clause
        for clause in brief.cited_policy_clauses
        if (clause.rule_code, clause.clause_id, clause.text) in allowed_clauses
    ]
    missing_context = normalized_strings([*fallback.missing_context, *brief.missing_context])
    grounding_warnings = normalized_strings([*fallback.grounding_warnings, *brief.grounding_warnings])

    if not set(brief.key_reasons).issubset(allowed_reasons):
        grounding_warnings.append("AI-generated reasons were constrained to deterministic policy/risk facts.")

    return ReviewerBrief(
        summary=brief.summary or fallback.summary,
        key_reasons=[reason for reason in brief.key_reasons if reason in allowed_reasons] or fallback.key_reasons,
        cited_policy_clauses=grounded_clauses or fallback.cited_policy_clauses,
        missing_context=missing_context,
        recommended_next_action=fallback.recommended_next_action,
        confidence=brief.confidence if brief.confidence in {"low", "medium", "high"} else fallback.confidence,
        grounding_warnings=grounding_warnings,
        advisory_notice=fallback.advisory_notice,
        generated_by="openai_structured_output",
    )


def compose_summary(
    *,
    merchant: str,
    amount_cad: float,
    policy_status: str | None,
    risk_level: str | None,
    policy_flags: list[dict[str, Any]],
    risk_signals: list[dict[str, Any]],
) -> str:
    amount = f"CAD {amount_cad:,.2f}"
    status = format_label(policy_status or "compliant")
    risk = format_label(risk_level or "low")
    if policy_flags and risk_signals:
        return (
            f"Advisory brief: {merchant} for {amount} has deterministic policy status {status} and {risk} "
            "risk signals. Review the listed rule findings and anomaly drivers before taking action."
        )
    if policy_flags:
        return (
            f"Advisory brief: {merchant} for {amount} is grounded in deterministic policy status {status}. "
            "Resolve the policy finding or collect the required evidence before proceeding."
        )
    if risk_signals:
        return (
            f"Advisory brief: {merchant} for {amount} has no blocking policy flag in the queue, but carries "
            f"{risk} risk signals that should be checked before approval."
        )
    return (
        f"Advisory brief: {merchant} for {amount} has no blocking policy flag or material risk signal recorded "
        "in the merged review queue."
    )


def grounding_warnings(facts: dict[str, Any]) -> list[str]:
    warnings = [
        "This brief is grounded only in deterministic policy checks, risk signals, and stored policy citations."
    ]
    if not facts["cited_policy_clauses"]:
        warnings.append("No policy RAG citation is attached; rely on rule codes and deterministic finding text.")
    if not facts["risk"]["signals"]:
        warnings.append("No detailed risk signal is attached to this queue item.")
    if not facts["policy"]["flags"]:
        warnings.append("No deterministic policy flag is attached to this queue item.")
    if facts.get("data_quality_findings"):
        warnings.append("Data-quality findings are included as missing context, not as policy violations.")
    return warnings


def data_quality_findings(transaction: dict[str, Any]) -> list[str]:
    findings = []
    if not transaction.get("employee_id") and not transaction.get("employee_name"):
        findings.append("employee assignment unavailable")
    if not transaction.get("department_id") and not transaction.get("department_name"):
        findings.append("department assignment unavailable")
    if not transaction.get("transaction_date"):
        findings.append("transaction date unavailable")
    if not (transaction.get("normalized_merchant_name") or transaction.get("merchant_name")):
        findings.append("merchant name unavailable")
    return findings


def confidence_level(
    policy_flags: list[dict[str, Any]],
    risk_signals: list[dict[str, Any]],
    cited_policy_clauses: list[CitedPolicyClause],
    missing_context: list[str],
) -> str:
    if missing_context:
        return "low"
    if cited_policy_clauses and (policy_flags or risk_signals):
        return "high"
    if policy_flags or risk_signals:
        return "medium"
    return "low"


def normalized_strings(values: list[Any]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        text = str(value).strip()
        if text:
            seen.setdefault(text, None)
    return list(seen.keys())


def format_label(value: str) -> str:
    return value.replace("_", " ").title()
