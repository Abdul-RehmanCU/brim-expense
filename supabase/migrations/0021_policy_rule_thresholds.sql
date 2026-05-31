alter table public.policy_rules
  add column if not exists thresholds_json jsonb not null default '{}'::jsonb;

update public.policy_rules
set
  thresholds_json = jsonb_build_object(
    'preapproval_threshold_cad',
    jsonb_build_object(
      'value', 50,
      'currency', 'CAD',
      'source', 'seed_policy_rule_threshold'
    )
  ),
  rule_json = coalesce(rule_json, '{}'::jsonb) || jsonb_build_object(
    'thresholds',
    jsonb_build_object(
      'preapproval_threshold_cad',
      jsonb_build_object(
        'value', 50,
        'currency', 'CAD',
        'source', 'seed_policy_rule_threshold'
      )
    )
  ),
  requires_json = coalesce(nullif(requires_json, '{}'::jsonb), '{"facts":[]}'::jsonb)
    || '{"evidence":["manager pre-authorization evidence"]}'::jsonb,
  rule_metadata = coalesce(rule_metadata, '{}'::jsonb) || jsonb_build_object(
    'thresholds',
    jsonb_build_object(
      'preapproval_threshold_cad',
      jsonb_build_object(
        'value', 50,
        'currency', 'CAD',
        'source', 'seed_policy_rule_threshold'
      )
    )
  ),
  updated_at = now()
where rule_code in ('PREAPPROVAL_OVER_50', 'PREAPPROVAL_PENDING_REVIEW');

update public.policy_rules
set
  thresholds_json = jsonb_build_object(
    'meal_context_threshold_cad',
    jsonb_build_object(
      'value', 50,
      'currency', 'CAD',
      'source', 'seed_policy_rule_threshold'
    )
  ),
  rule_json = coalesce(rule_json, '{}'::jsonb) || jsonb_build_object(
    'thresholds',
    jsonb_build_object(
      'meal_context_threshold_cad',
      jsonb_build_object(
        'value', 50,
        'currency', 'CAD',
        'source', 'seed_policy_rule_threshold'
      )
    )
  ),
  requires_json = coalesce(nullif(requires_json, '{}'::jsonb), '{"facts":[]}'::jsonb)
    || '{"evidence":["guest names","business purpose","customer context"]}'::jsonb,
  rule_metadata = coalesce(rule_metadata, '{}'::jsonb) || jsonb_build_object(
    'thresholds',
    jsonb_build_object(
      'meal_context_threshold_cad',
      jsonb_build_object(
        'value', 50,
        'currency', 'CAD',
        'source', 'seed_policy_rule_threshold'
      )
    )
  ),
  updated_at = now()
where rule_code = 'ENTERTAINMENT_CONTEXT_REQUIRED';
