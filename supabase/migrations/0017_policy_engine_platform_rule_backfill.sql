insert into public.policy_rules (
  rule_code,
  title,
  description,
  severity,
  deterministic,
  active,
  synthetic,
  name,
  enabled,
  status,
  rule_kind,
  config_schema_version,
  condition,
  outcome,
  scope,
  rule_metadata,
  source_type
)
values
  (
    'PREAPPROVAL_PENDING_REVIEW',
    'Pending preapproval requires review',
    'Transactions above the preapproval threshold stay in review while approval evidence is still pending.',
    'medium',
    true,
    true,
    true,
    'Pending preapproval requires review',
    true,
    'active',
    'json_config',
    1,
    '{
      "all": [
        {"field": "skips_normal_expense_rules", "operator": "is_false"},
        {"field": "requires_preapproval", "operator": "is_true"},
        {"field": "has_pending_preapproval", "operator": "is_true"}
      ]
    }'::jsonb,
    '{
      "status": "review_required",
      "violation": {
        "rule_code": "PREAPPROVAL_PENDING_REVIEW",
        "severity": "medium",
        "explanation": "This transaction still has pending preapproval evidence.",
        "required_action": "Follow up on the pending preapproval before approving reimbursement."
      }
    }'::jsonb,
    '{"department_ids": [], "employee_ids": []}'::jsonb,
    '{"source": "policy_engine_platform_refactor"}'::jsonb,
    'seeded'
  ),
  (
    'RECEIPT_EVIDENCE_REQUIRED',
    'Receipt evidence readiness required',
    'Receipt-sensitive expenses require receipt evidence to be present or collected before final reimbursement review.',
    'low',
    true,
    true,
    true,
    'Receipt evidence readiness required',
    true,
    'active',
    'json_config',
    1,
    '{
      "all": [
        {"field": "skips_normal_expense_rules", "operator": "is_false"},
        {"field": "receipt_sensitive_category", "operator": "is_true"},
        {"field": "receipt_evidence_unavailable", "operator": "is_true"},
        {"field": "receipt_explicitly_missing", "operator": "is_false"}
      ]
    }'::jsonb,
    '{
      "status": "review_required",
      "violation": {
        "rule_code": "RECEIPT_EVIDENCE_REQUIRED",
        "severity": "low",
        "explanation": "Receipt-sensitive spend is missing receipt evidence in the current dataset.",
        "required_action": "Collect the receipt evidence during reimbursement review."
      }
    }'::jsonb,
    '{"department_ids": [], "employee_ids": []}'::jsonb,
    '{"source": "policy_engine_platform_refactor"}'::jsonb,
    'seeded'
  )
on conflict (rule_code) do update
set
  title = excluded.title,
  description = excluded.description,
  severity = excluded.severity,
  deterministic = excluded.deterministic,
  active = excluded.active,
  synthetic = excluded.synthetic,
  name = excluded.name,
  enabled = excluded.enabled,
  status = excluded.status,
  rule_kind = excluded.rule_kind,
  config_schema_version = excluded.config_schema_version,
  condition = excluded.condition,
  outcome = excluded.outcome,
  scope = excluded.scope,
  rule_metadata = coalesce(public.policy_rules.rule_metadata, '{}'::jsonb) || excluded.rule_metadata,
  source_type = excluded.source_type,
  updated_at = now();

update public.policy_rules
set
  name = coalesce(name, title),
  active = true,
  enabled = true,
  status = 'active',
  rule_kind = 'json_config',
  config_schema_version = 1,
  condition = case rule_code
    when 'PREAPPROVAL_OVER_50' then
      '{
        "all": [
          {"field": "skips_normal_expense_rules", "operator": "is_false"},
          {"field": "amount_cad", "operator": "gt", "value": {"threshold": "preapproval_threshold_cad"}},
          {"field": "missing_preapproval", "operator": "is_true"}
        ]
      }'::jsonb
    when 'RECEIPT_REQUIRED' then
      '{
        "all": [
          {"field": "skips_normal_expense_rules", "operator": "is_false"},
          {"field": "receipt_explicitly_missing", "operator": "is_true"}
        ]
      }'::jsonb
    when 'RECEIPT_CURRENT_MONTH' then
      '{
        "all": [
          {"field": "skips_normal_expense_rules", "operator": "is_false"},
          {"field": "has_receipt_evidence", "operator": "is_true"},
          {"field": "receipt_submitted_current_month", "operator": "is_false"}
        ]
      }'::jsonb
    when 'ENTERTAINMENT_CONTEXT_REQUIRED' then
      '{
        "all": [
          {"field": "skips_normal_expense_rules", "operator": "is_false"},
          {"field": "is_meal_or_entertainment", "operator": "is_true"},
          {"field": "amount_cad", "operator": "gt", "value": {"threshold": "meal_context_threshold_cad"}},
          {
            "any": [
              {"field": "has_guest_names", "operator": "is_false"},
              {"field": "has_business_purpose", "operator": "is_false"}
            ]
          }
        ]
      }'::jsonb
    when 'ALCOHOL_RESTRICTED' then
      '{
        "all": [
          {"field": "skips_normal_expense_rules", "operator": "is_false"},
          {"field": "is_alcohol_category", "operator": "is_true"}
        ]
      }'::jsonb
    when 'TICKETS_NOT_REIMBURSABLE' then
      '{
        "all": [
          {"field": "skips_normal_expense_rules", "operator": "is_false"},
          {"field": "is_ticket_or_fine", "operator": "is_true"}
        ]
      }'::jsonb
    when 'PERSONAL_CARD_USE_PROHIBITED' then
      '{
        "all": [
          {"field": "skips_normal_expense_rules", "operator": "is_false"},
          {"field": "is_personal_expense", "operator": "is_true"}
        ]
      }'::jsonb
    else condition
  end,
  outcome = case rule_code
    when 'PREAPPROVAL_OVER_50' then
      '{
        "status": "approval_evidence_needed",
        "violation": {
          "rule_code": "PREAPPROVAL_OVER_50",
          "severity": "high",
          "explanation": "This transaction exceeds the active preapproval threshold and is missing approval evidence.",
          "required_action": "Collect or document the required preapproval evidence before approval."
        }
      }'::jsonb
    when 'RECEIPT_REQUIRED' then
      '{
        "status": "approval_evidence_needed",
        "violation": {
          "rule_code": "RECEIPT_REQUIRED",
          "severity": "medium",
          "explanation": "This transaction is explicitly missing required receipt evidence.",
          "required_action": "Collect and attach the required receipt evidence before approval."
        }
      }'::jsonb
    when 'RECEIPT_CURRENT_MONTH' then
      '{
        "status": "review_required",
        "violation": {
          "rule_code": "RECEIPT_CURRENT_MONTH",
          "severity": "low",
          "explanation": "Receipt evidence was submitted outside the transaction month.",
          "required_action": "Review whether the delayed receipt submission is acceptable."
        }
      }'::jsonb
    when 'ENTERTAINMENT_CONTEXT_REQUIRED' then
      '{
        "status": "context_needed",
        "missing_information": ["customer context", "guest names", "business purpose"],
        "violation": {
          "rule_code": "ENTERTAINMENT_CONTEXT_REQUIRED",
          "severity": "medium",
          "explanation": "Entertainment spend over the configured threshold is missing required context.",
          "required_action": "Collect the missing entertainment context before deciding compliance."
        }
      }'::jsonb
    when 'ALCOHOL_RESTRICTED' then
      '{
        "status": "context_needed",
        "missing_information": ["customer dining context", "guest names", "business purpose"],
        "violation": {
          "rule_code": "ALCOHOL_RESTRICTED",
          "severity": "high",
          "explanation": "Alcohol spend requires supporting customer dining context.",
          "required_action": "Collect the customer dining context before approving reimbursement."
        }
      }'::jsonb
    when 'TICKETS_NOT_REIMBURSABLE' then
      '{
        "status": "policy_violation",
        "violation": {
          "rule_code": "TICKETS_NOT_REIMBURSABLE",
          "severity": "high",
          "explanation": "This transaction matches a non-reimbursable ticket or fine rule.",
          "required_action": "Do not reimburse this transaction."
        }
      }'::jsonb
    when 'PERSONAL_CARD_USE_PROHIBITED' then
      '{
        "status": "policy_violation",
        "violation": {
          "rule_code": "PERSONAL_CARD_USE_PROHIBITED",
          "severity": "critical",
          "explanation": "This transaction matches a personal-spend prohibition rule.",
          "required_action": "Review the charge and recover funds if it is personal spend."
        }
      }'::jsonb
    else outcome
  end,
  scope = coalesce(nullif(scope, '{}'::jsonb), '{"department_ids": [], "employee_ids": []}'::jsonb),
  rule_metadata = coalesce(rule_metadata, '{}'::jsonb) || '{"source": "policy_engine_platform_refactor"}'::jsonb,
  source_type = coalesce(source_type, 'seeded'),
  updated_at = now()
where rule_code in (
  'PREAPPROVAL_OVER_50',
  'RECEIPT_REQUIRED',
  'RECEIPT_CURRENT_MONTH',
  'ENTERTAINMENT_CONTEXT_REQUIRED',
  'ALCOHOL_RESTRICTED',
  'TICKETS_NOT_REIMBURSABLE',
  'PERSONAL_CARD_USE_PROHIBITED'
);
