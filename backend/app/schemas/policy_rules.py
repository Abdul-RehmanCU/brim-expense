from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.policy import Severity

RuleOperator = Literal[
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "contains",
    "not_contains",
    "exists",
    "is_true",
    "is_false",
]


class PolicyRuleScope(BaseModel):
    department_ids: list[str] = Field(default_factory=list)
    employee_ids: list[str] = Field(default_factory=list)


class PolicyRuleViolationTemplate(BaseModel):
    rule_code: str | None = None
    severity: Severity | None = None
    explanation: str
    required_action: str


class PolicyRuleOutcomeTemplate(BaseModel):
    violation: PolicyRuleViolationTemplate | None = None
    missing_information: list[str] = Field(default_factory=list)


class ConfigurablePolicyRulePayload(BaseModel):
    rule_code: str
    name: str
    enabled: bool = True
    severity: Severity
    condition: dict[str, Any]
    outcome: PolicyRuleOutcomeTemplate
    scope: PolicyRuleScope = Field(default_factory=PolicyRuleScope)
