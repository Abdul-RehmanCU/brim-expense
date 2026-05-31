alter table public.policy_rules
  add column if not exists name text,
  add column if not exists enabled boolean not null default false,
  add column if not exists status text not null default 'draft',
  add column if not exists priority integer not null default 100,
  add column if not exists scope_json jsonb not null default '{}'::jsonb,
  add column if not exists applies_to_json jsonb not null default '{}'::jsonb,
  add column if not exists conditions_json jsonb not null default '{}'::jsonb,
  add column if not exists context_requirements_json jsonb not null default '[]'::jsonb,
  add column if not exists requires_json jsonb not null default '{}'::jsonb,
  add column if not exists outcome_json jsonb not null default '{}'::jsonb,
  add column if not exists rule_json jsonb not null default '{}'::jsonb,
  add column if not exists source_type text not null default 'seeded',
  add column if not exists source_text text,
  add column if not exists created_by text,
  add column if not exists editable boolean not null default true,
  add column if not exists version integer not null default 1,
  add column if not exists extraction_confidence numeric(5,4),
  add column if not exists needs_human_review boolean not null default false,
  add column if not exists validation_errors jsonb not null default '[]'::jsonb;

update public.policy_rules
set
  name = coalesce(name, title),
  enabled = active,
  status = case
    when active then 'active'
    when synthetic is false then 'draft'
    else 'disabled'
  end,
  source_type = case
    when synthetic then 'seeded'
    else source_type
  end
where name is null
   or status = 'draft'
   or source_type = 'seeded';

create index if not exists idx_policy_rules_status
  on public.policy_rules(status);

create index if not exists idx_policy_rules_source_type
  on public.policy_rules(source_type);
