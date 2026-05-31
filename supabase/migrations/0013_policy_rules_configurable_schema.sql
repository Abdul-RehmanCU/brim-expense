alter table public.policy_rules
  add column if not exists rule_kind text not null default 'python_function',
  add column if not exists config_schema_version integer not null default 1,
  add column if not exists condition jsonb not null default '{}'::jsonb,
  add column if not exists outcome jsonb not null default '{}'::jsonb,
  add column if not exists scope jsonb not null default '{}'::jsonb,
  add column if not exists rule_metadata jsonb not null default '{}'::jsonb;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'policy_rules_rule_kind_check'
      and conrelid = 'public.policy_rules'::regclass
  ) then
    alter table public.policy_rules
      add constraint policy_rules_rule_kind_check
      check (rule_kind in ('python_function', 'json_config'));
  end if;
end $$;

create index if not exists idx_policy_rules_active_kind
  on public.policy_rules(active, rule_kind);

create index if not exists idx_policy_rules_condition_gin
  on public.policy_rules using gin (condition);

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
  rule_metadata = rule_metadata || '{"source": "milestone_3_6_configurable_rules_foundation"}'::jsonb,
  updated_at = now()
where rule_code in (
  'PREAPPROVAL_OVER_50',
  'ENTERTAINMENT_CONTEXT_REQUIRED',
  'ALCOHOL_RESTRICTED'
);
