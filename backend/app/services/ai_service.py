from __future__ import annotations

import json
from typing import Any, Protocol

from anthropic import Anthropic
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.schemas.approvals import ApprovalRecommendation
from app.schemas.common import PlaceholderResponse
from app.schemas.policy import PolicyRuleExtractionRequest
from app.schemas.reports import ReportNarrative
from app.schemas.review_queue import ReviewerBrief

RULE_EXTRACTION_MAX_TOKENS = 6000
REVIEWER_BRIEF_MAX_TOKENS = 1200
APPROVAL_RECOMMENDATION_MAX_TOKENS = 1200
REPORT_NARRATIVE_MAX_TOKENS = 1000
INSIGHT_RESPONSE_MAX_TOKENS = 700
OPENAI_REQUEST_TIMEOUT_SECONDS = 90.0


def get_ai_status() -> PlaceholderResponse:
    return PlaceholderResponse(
        status="placeholder",
        service="ai",
        implemented=False,
        message="Claude/OpenAI calls are intentionally not implemented in Milestone 2.5.",
    )


class JsonCompletionClient(Protocol):
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        ...


class InsightResponseClient(Protocol):
    def compose_answer(self, facts: dict[str, Any]) -> str:
        ...


class AnthropicJsonClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.anthropic_model
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for policy rule extraction.")
        self.client = Anthropic(api_key=self.api_key)

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=RULE_EXTRACTION_MAX_TOKENS,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(
            block.text if hasattr(block, "text") else str(getattr(block, "content", ""))
            for block in response.content
        )
        return parse_strict_json(text)


JsonPrimitive = str | int | float | bool | None
JsonConditionValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


class StructuredRuleCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    field: str | None = None
    operator: str | None = None
    value: JsonConditionValue = None
    all: list["StructuredRuleCondition"] | None = None
    any: list["StructuredRuleCondition"] | None = None
    not_: "StructuredRuleCondition | None" = Field(default=None, alias="not")


class StructuredRuleScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_ids: list[str] = Field(default_factory=list)
    employee_ids: list[str] = Field(default_factory=list)


class StructuredAppliesTo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_categories: list[str] = Field(default_factory=list)
    merchant_families: list[str] = Field(default_factory=list)
    eligibility_tags: list[str] = Field(default_factory=list)
    workflow_tags: list[str] = Field(default_factory=list)
    department_ids: list[str] = Field(default_factory=list)
    employee_ids: list[str] = Field(default_factory=list)
    employee_roles: list[str] = Field(default_factory=list)


class StructuredThresholdOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: float


class StructuredThresholdPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str | None = None
    end: str | None = None
    value: float


class StructuredThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    currency: str | None = None
    source_text: str | None = None
    by_department: list[StructuredThresholdOverride] = Field(default_factory=list)
    by_employee: list[StructuredThresholdOverride] = Field(default_factory=list)
    by_role: list[StructuredThresholdOverride] = Field(default_factory=list)
    by_period: list[StructuredThresholdPeriod] = Field(default_factory=list)


class StructuredRuleOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    message: str | None = None
    required_action: str | None = None
    missing_information: list[str] = Field(default_factory=list)


class StructuredRuleJson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: StructuredRuleCondition
    outcome: StructuredRuleOutcome
    scope: StructuredRuleScope = Field(default_factory=StructuredRuleScope)
    applies_to: StructuredAppliesTo = Field(default_factory=StructuredAppliesTo)
    thresholds: list[StructuredThreshold] = Field(default_factory=list)
    context_requirements: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    requires_facts: list[str] = Field(default_factory=list)
    period_start: str | None = None
    period_end: str | None = None


class StructuredDraftRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_code: str
    name: str
    description: str
    severity: str
    rule_json: StructuredRuleJson
    source_text: str
    extraction_confidence: float
    needs_human_review: bool


class StructuredPolicyExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    ambiguities: list[str] = Field(default_factory=list)
    unsupported_or_missing_fields: list[str] = Field(default_factory=list)
    suggested_feature_engineering: list[str] = Field(default_factory=list)
    draft_rules: list[StructuredDraftRule] = Field(default_factory=list)


StructuredRuleCondition.model_rebuild()


class OpenAIStructuredJsonClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.ai_rule_extraction_model or settings.openai_rule_extraction_model
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI policy rule extraction.")
        self.client = OpenAI(api_key=self.api_key, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS)

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_output_tokens=RULE_EXTRACTION_MAX_TOKENS,
                temperature=0,
                text_format=StructuredPolicyExtractionResponse,
            )
        except Exception as error:
            raise ValueError(f"OpenAI structured policy rule extraction failed: {error}") from error

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ValueError("OpenAI rule extraction response did not include parsed structured output.")
        return parsed.model_dump(mode="json", by_alias=True, exclude_none=True)


class OpenAIReviewerBriefClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_reviewer_brief_model
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI reviewer briefs.")
        self.client = OpenAI(api_key=self.api_key, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS)

    def compose_reviewer_brief(self, facts: dict[str, Any]) -> ReviewerBrief:
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": reviewer_brief_system_prompt()},
                    {"role": "user", "content": json.dumps(facts, ensure_ascii=True)},
                ],
                max_output_tokens=REVIEWER_BRIEF_MAX_TOKENS,
                temperature=0,
                text_format=ReviewerBrief,
            )
        except Exception as error:
            raise ValueError(f"OpenAI reviewer brief generation failed: {error}") from error

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ValueError("OpenAI reviewer brief response did not include parsed structured output.")
        return parsed


class OpenAIApprovalRecommendationClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_approval_recommendation_model
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI approval recommendations.")
        self.client = OpenAI(api_key=self.api_key, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS)

    def compose_approval_recommendation(self, facts: dict[str, Any]) -> ApprovalRecommendation:
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": approval_recommendation_system_prompt()},
                    {"role": "user", "content": json.dumps(facts, ensure_ascii=True)},
                ],
                max_output_tokens=APPROVAL_RECOMMENDATION_MAX_TOKENS,
                temperature=0,
                text_format=ApprovalRecommendation,
            )
        except Exception as error:
            raise ValueError(f"OpenAI approval recommendation generation failed: {error}") from error

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ValueError("OpenAI approval recommendation response did not include parsed structured output.")
        return parsed


class OpenAIReportNarrativeClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_reviewer_brief_model
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI report narratives.")
        self.client = OpenAI(api_key=self.api_key, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS)

    def compose_report_narrative(self, facts: dict[str, Any]) -> ReportNarrative:
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": report_narrative_system_prompt()},
                    {"role": "user", "content": json.dumps(facts, ensure_ascii=True)},
                ],
                max_output_tokens=REPORT_NARRATIVE_MAX_TOKENS,
                temperature=0,
                text_format=ReportNarrative,
            )
        except Exception as error:
            raise ValueError(f"OpenAI report narrative generation failed: {error}") from error

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ValueError("OpenAI report narrative response did not include parsed structured output.")
        return parsed


class OpenAIInsightResponseClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_insight_response_model
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for conversational insight responses.")
        self.client = OpenAI(api_key=self.api_key, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS)

    def compose_answer(self, facts: dict[str, Any]) -> str:
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": insight_response_system_prompt()},
                    {"role": "user", "content": json.dumps(facts, ensure_ascii=True)},
                ],
                max_output_tokens=INSIGHT_RESPONSE_MAX_TOKENS,
            )
        except Exception as error:
            raise ValueError(f"OpenAI conversational insight response failed: {error}") from error

        text = getattr(response, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                chunk = getattr(content, "text", None)
                if isinstance(chunk, str) and chunk.strip():
                    parts.append(chunk.strip())

        combined = "\n\n".join(part for part in parts if part)
        if combined:
            return combined
        raise ValueError("OpenAI conversational insight response did not include any text output.")


def reviewer_brief_system_prompt() -> str:
    return (
        "Create a concise finance reviewer brief from the supplied JSON facts only. The brief is advisory. "
        "Never change or override deterministic policy status, policy flags, risk score, risk level, missing context, "
        "or recommended_next_action. Do not invent policy citations or missing facts. If citations are absent, say so "
        "in grounding_warnings. Return the requested structured object only."
    )


def approval_recommendation_system_prompt() -> str:
    return (
        "Create a concise finance approval recommendation from the supplied JSON facts only. The recommendation is "
        "advisory and must be one of approve or deny. Ground the rationale only in supplied "
        "transaction, policy, risk, budget, spend history, and deterministic fallback facts. Do not invent policy "
        "citations, missing documents, manager names, budgets, or employee history. Never recommend approve when the "
        "deterministic fallback reports deny. Return the requested structured object only."
    )


def report_narrative_system_prompt() -> str:
    return (
        "Create a concise finance-facing expense report narrative from the supplied JSON facts only. "
        "The summary is advisory and must stay grounded in the supplied totals, grouping reason, workflow metrics, "
        "top categories, top merchants, and cited policy clauses. Do not invent receipts, approvals, policy clauses, "
        "budgets, travel purpose, or counts. Keep it short and specific. Return the requested structured object only."
    )


def insight_response_system_prompt() -> str:
    return (
        "You are a grounded finance operations copilot. Answer conversationally, but only from the supplied facts. "
        "Use the current page context when the user is asking what they are looking at, what this page shows, or how "
        "to interpret the screen. Never invent totals, counts, employees, merchants, policy outcomes, risk scores, "
        "or documents. Never contradict deterministic policy or risk outputs. If the supplied facts are incomplete, "
        "say what is known and what is not shown. Prefer short, natural prose over rigid labels. Do not use markdown "
        "tables or bullet lists unless the facts explicitly require a list."
    )


def default_approval_recommendation_client() -> OpenAIApprovalRecommendationClient | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return OpenAIApprovalRecommendationClient()


def default_report_narrative_client() -> OpenAIReportNarrativeClient | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return OpenAIReportNarrativeClient()


def default_insight_response_client() -> OpenAIInsightResponseClient | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return OpenAIInsightResponseClient()


def default_rule_extraction_client() -> JsonCompletionClient:
    settings = get_settings()
    provider = (settings.ai_rule_extraction_provider or "").strip().lower()
    if not provider:
        provider = "openai" if settings.openai_api_key else "anthropic"
    model = settings.ai_rule_extraction_model
    if provider == "openai":
        return OpenAIStructuredJsonClient(model=model)
    if provider in {"anthropic", "claude"}:
        return AnthropicJsonClient(model=model)
    raise RuntimeError("AI_RULE_EXTRACTION_PROVIDER must be either 'anthropic' or 'openai'.")


def extract_policy_rules_json(
    request: PolicyRuleExtractionRequest,
    client: JsonCompletionClient | None = None,
) -> dict[str, Any]:
    completion_client = client or default_rule_extraction_client()
    return completion_client.complete_json(
        system_prompt=rule_extraction_system_prompt(),
        user_prompt=rule_extraction_user_prompt(request),
    )


def rule_extraction_system_prompt() -> str:
    return (
        "You translate policy and compliance source text into draft declarative rules for a general-purpose rules "
        "platform. Return strict JSON only. Do not include Markdown. Do not decide compliance for specific records. "
        "Use the source text to infer reusable rules, thresholds, scope, and required evidence. Each rule must be "
        "expressed as rule_json with condition, outcome, and scope, plus optional applies_to, thresholds, "
        "period/date scope, context_requirements, evidence_requirements, and requires sections. Prefer preserving a "
        "policy intent as a draft rule, even if it needs human review or supporting data, instead of omitting it. "
        "Mark uncertain or partially supported rules with needs_human_review=true and explain data gaps in "
        "unsupported_or_missing_fields. Never turn one policy sentence into multiple duplicate rules with the same "
        "intent. Never create rules that are triggered only by card direction, debit activity, or account activity; "
        "those are routing facts, not proof of a policy issue."
    )


def rule_extraction_user_prompt(request: PolicyRuleExtractionRequest) -> str:
    available_fields = request.available_fields or []
    payload = {
        "policy_text": request.policy_text,
        "company_context": request.company_context or "",
        "available_fields": available_fields,
        "allowed_condition_operators": [
            "equals",
            "not_equals",
            "in",
            "not_in",
            "greater_than",
            "greater_than_or_equal",
            "less_than",
            "less_than_or_equal",
            "contains",
            "not_contains",
            "exists",
            "missing",
            "between",
        ],
        "instructions": [
            "Use only the fields listed in available_fields when writing rule_json.condition.",
            "Represent rules in a domain-neutral declarative format. Do not assume expense-only or Brim-specific workflows unless the source text says so.",
            "Create at most one draft rule for each distinct compliance intent. Prefer one scoped rule with applies_to over several near-duplicate rules.",
            "Do not write a rule whose only condition fields are debit_or_credit, is_account_activity, transaction_type, or transaction_status. Those fields may narrow a rule, but they cannot be the whole proof.",
            "Do not auto-convert guidance-only or conduct-only statements into active enforcement logic, but you may still emit them as draft rules with needs_human_review=true when they are important policy intents.",
            "For receipt, approval, attendee, business-purpose, budget, or attachment policies, prefer creating a draft rule plus missing data notes instead of dropping the policy intent entirely.",
            "For broad universal requirements, such as all expenses require receipts, emit a scoped draft rule when possible and list any missing evidence facts in unsupported_or_missing_fields.",
            "Use applies_to.business_categories, applies_to.merchant_families, applies_to.eligibility_tags, and applies_to.workflow_tags to narrow where a rule applies when the source text gives a category or workflow.",
            "When a policy uses an amount threshold, put that threshold in rule_json.thresholds and reference it from conditions as {'threshold': '<name>'}; do not invent a default amount.",
            "Represent department, employee, role, or time-period-specific thresholds in rule_json.thresholds using by_department, by_employee, by_role, and by_period overrides.",
            "Represent date or period scope in rule_json.period or rule_json.requires when the policy source gives an effective window.",
            "Represent receipt, approval, attendee, or business-purpose proof in rule_json.evidence_requirements and rule_json.requires.facts.",
            "If the policy depends on unavailable data such as approval artifacts, attachment timestamps, attendee lists, budgets, or human judgment signals, report that in unsupported_or_missing_fields.",
            "If the policy language is vague, such as reasonable, excessive, unusual, or manager discretion, report that in ambiguities.",
            "Use source text to infer scope or applies_to only when it is explicit.",
            "Keep outcome.required_action focused on a reviewer or operator next step, not hardcoded finance-only actions unless the source text requires that role.",
            "Set needs_human_review to true whenever a rule depends on missing data, human judgment, or approximate field mapping. Set it to false only when the rule is cleanly deterministic from available fields.",
            "Keep source_text to a short supporting excerpt from the policy, not the whole document.",
        ],
        "required_output_shape": {
            "summary": "Short summary of what was extracted and what still needs human judgment.",
            "ambiguities": ["List vague or judgment-heavy policy phrases that cannot be enforced deterministically."],
            "unsupported_or_missing_fields": [
                "List required data elements that are not present in available_fields or not safely enforceable yet."
            ],
            "suggested_feature_engineering": ["Optional future feature ideas such as approval_evidence_available."],
            "draft_rules": [
                {
                    "rule_code": "UPPERCASE_UNIQUE_CODE",
                    "name": "Human readable rule name",
                    "description": "What the rule enforces or asks a human reviewer to assess",
                    "severity": "low|medium|high|critical",
                    "rule_json": {
                        "condition": {
                            "all": [
                                {
                                    "field": "amount_cad",
                                    "operator": "greater_than",
                                    "value": {"threshold": "threshold_name_from_policy"},
                                }
                            ]
                        },
                        "outcome": {
                            "status": "policy_violation|approval_evidence_needed|context_needed|review_required|excluded_non_expense",
                            "message": "Finding explanation template",
                            "required_action": "Human reviewer next action",
                        },
                        "scope": {"department_ids": [], "employee_ids": []},
                        "applies_to": {
                            "business_categories": [],
                            "merchant_families": [],
                            "eligibility_tags": [],
                            "workflow_tags": [],
                        },
                        "thresholds": {
                            "threshold_name_from_policy": {
                                "value": "Numeric amount copied from source policy text.",
                                "currency": "CAD if specified, otherwise null",
                                "by_department": {},
                                "by_employee": {},
                                "by_role": {},
                                "by_period": [],
                            }
                        },
                        "context_requirements": [],
                        "evidence_requirements": [],
                        "period": {"start": None, "end": None},
                        "requires": {"facts": ["amount_cad"], "evidence": [], "period": {}},
                    },
                    "source_text": "Short excerpt from the policy source",
                    "extraction_confidence": 0.0,
                    "needs_human_review": False,
                }
            ],
        },
    }
    return json.dumps(payload, ensure_ascii=True)


def parse_strict_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError("Claude returned invalid JSON for policy rule extraction.") from error

    if not isinstance(value, dict):
        raise ValueError("Claude rule extraction response must be a JSON object.")
    return value
