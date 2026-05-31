insert into public.policy_rules (rule_code, title, description, severity, deterministic, active, synthetic)
values
  ('PREAPPROVAL_OVER_50', 'Expenses over $50 require manager pre-authorization', 'Expenses over CAD 50 require manager pre-authorization before reimbursement or approval.', 'high', true, true, true),
  ('RECEIPT_REQUIRED', 'Receipts are required before reimbursement', 'Receipts must be submitted before reimbursement can be completed.', 'high', true, true, true),
  ('RECEIPT_CURRENT_MONTH', 'Receipts should be submitted within the current month', 'Receipts should be submitted within the current month where possible.', 'medium', true, true, true),
  ('FALSIFICATION_PROHIBITED', 'Falsified expense reports are prohibited', 'Falsified, altered, or misleading expense reports are prohibited.', 'critical', true, true, true),
  ('ENTERTAINMENT_CONTEXT_REQUIRED', 'Customer entertainment requires context', 'Customer entertainment requires guest names and business purpose.', 'high', true, true, true),
  ('ALCOHOL_RESTRICTED', 'Alcohol is restricted', 'Alcohol is not permitted unless dining with a customer.', 'high', true, true, true),
  ('TIPS_SERVICE_15', 'Service tips capped at 15 percent', 'Tips for services or porterage may be expensed up to 15 percent.', 'medium', true, true, true),
  ('MEAL_TIPS_20', 'Meal tips capped at 20 percent', 'Meal tips are not reimbursed above 20 percent.', 'medium', true, true, true),
  ('PARKING_ALLOWED', 'Reasonable parking may be reimbursed', 'Reasonable parking expenses may be reimbursed.', 'low', true, true, true),
  ('TOLLS_ALLOWED', 'Tolls may be reimbursed', 'Toll expenses may be reimbursed.', 'low', true, true, true),
  ('TICKETS_NOT_REIMBURSABLE', 'Traffic and parking tickets are not reimbursable', 'Traffic tickets and parking tickets are not reimbursable.', 'high', true, true, true),
  ('CAR_RENTAL_RECEIPTS_REQUIRED', 'Vehicle-related receipts are required', 'Car rental, parking, and gasoline receipts are required.', 'high', true, true, true),
  ('CARD_NAMED_INDIVIDUAL_ONLY', 'Corporate cards are for named individuals only', 'Corporate cards may only be used by the named individual.', 'high', true, true, true),
  ('PERSONAL_CARD_USE_PROHIBITED', 'Personal corporate card use is prohibited', 'Personal expenses on corporate cards are prohibited.', 'critical', true, true, true),
  ('CONSISTENT_ABUSE_REVIEW', 'Consistent abuse can restrict cards', 'Consistent abuse can restrict or revoke corporate cards.', 'high', true, true, true)
on conflict (rule_code) do update set
  title = excluded.title,
  description = excluded.description,
  severity = excluded.severity,
  deterministic = excluded.deterministic,
  active = excluded.active,
  synthetic = true;

update public.policy_rules
set
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
    when 'ENTERTAINMENT_CONTEXT_REQUIRED' then
      '{
        "all": [
          {"field": "skips_normal_expense_rules", "operator": "is_false"},
          {"field": "category", "operator": "in", "value": ["Meals / Entertainment", "Meals"]},
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
          {"field": "category", "operator": "eq", "value": "Alcohol / Restricted"}
        ]
      }'::jsonb
    else condition
  end,
  outcome = case rule_code
    when 'PREAPPROVAL_OVER_50' then
      jsonb_build_object(
        'violation',
        jsonb_build_object(
          'rule_code', rule_code,
          'severity', 'high',
          'explanation', 'Transaction exceeds the configurable preauthorization threshold.',
          'required_action', 'Collect or document the required preapproval evidence before approval.'
        )
      )
    when 'ENTERTAINMENT_CONTEXT_REQUIRED' then
      jsonb_build_object(
        'violation',
        jsonb_build_object(
          'rule_code', rule_code,
          'severity', 'medium',
          'explanation', 'Meals or entertainment over the context threshold require guest names, business purpose, and customer context.',
          'required_action', 'Collect missing entertainment context before deciding compliance.'
        ),
        'missing_information',
        jsonb_build_array('customer context', 'guest names', 'business purpose')
      )
    when 'ALCOHOL_RESTRICTED' then
      jsonb_build_object(
        'violation',
        jsonb_build_object(
          'rule_code', rule_code,
          'severity', 'high',
          'explanation', 'Alcohol spend is restricted unless tied to dining with a customer.',
          'required_action', 'Collect customer dining context before approving reimbursement.'
        ),
        'missing_information',
        jsonb_build_array('customer dining context', 'guest names', 'business purpose')
      )
    else outcome
  end,
  scope = coalesce(nullif(scope, '{}'::jsonb), '{"department_ids": [], "employee_ids": []}'::jsonb),
  rule_metadata = rule_metadata || '{"source": "seed_configurable_rules_foundation"}'::jsonb,
  updated_at = now()
where rule_code in (
  'PREAPPROVAL_OVER_50',
  'ENTERTAINMENT_CONTEXT_REQUIRED',
  'ALCOHOL_RESTRICTED'
);

update public.policy_rules
set
  thresholds_json = jsonb_build_object(
    'preapproval_threshold_cad',
    jsonb_build_object('value', 50, 'currency', 'CAD', 'source', 'seed_policy_rule_threshold')
  ),
  rule_json = coalesce(rule_json, '{}'::jsonb) || jsonb_build_object(
    'thresholds',
    jsonb_build_object(
      'preapproval_threshold_cad',
      jsonb_build_object('value', 50, 'currency', 'CAD', 'source', 'seed_policy_rule_threshold')
    )
  ),
  requires_json = coalesce(nullif(requires_json, '{}'::jsonb), '{"facts":[]}'::jsonb)
    || '{"evidence":["manager pre-authorization evidence"]}'::jsonb,
  rule_metadata = coalesce(rule_metadata, '{}'::jsonb) || jsonb_build_object(
    'thresholds',
    jsonb_build_object(
      'preapproval_threshold_cad',
      jsonb_build_object('value', 50, 'currency', 'CAD', 'source', 'seed_policy_rule_threshold')
    )
  )
where rule_code = 'PREAPPROVAL_OVER_50';

update public.policy_rules
set
  thresholds_json = jsonb_build_object(
    'meal_context_threshold_cad',
    jsonb_build_object('value', 50, 'currency', 'CAD', 'source', 'seed_policy_rule_threshold')
  ),
  rule_json = coalesce(rule_json, '{}'::jsonb) || jsonb_build_object(
    'thresholds',
    jsonb_build_object(
      'meal_context_threshold_cad',
      jsonb_build_object('value', 50, 'currency', 'CAD', 'source', 'seed_policy_rule_threshold')
    )
  ),
  requires_json = coalesce(nullif(requires_json, '{}'::jsonb), '{"facts":[]}'::jsonb)
    || '{"evidence":["guest names","business purpose","customer context"]}'::jsonb,
  rule_metadata = coalesce(rule_metadata, '{}'::jsonb) || jsonb_build_object(
    'thresholds',
    jsonb_build_object(
      'meal_context_threshold_cad',
      jsonb_build_object('value', 50, 'currency', 'CAD', 'source', 'seed_policy_rule_threshold')
    )
  )
where rule_code = 'ENTERTAINMENT_CONTEXT_REQUIRED';
