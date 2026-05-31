alter table public.policy_documents
  add column if not exists file_name text,
  add column if not exists storage_path text,
  add column if not exists raw_text text,
  add column if not exists extracted_text text,
  add column if not exists extraction_status text not null default 'pending',
  add column if not exists extraction_error text;

update public.policy_documents
set
  raw_text = coalesce(raw_text, content),
  extracted_text = coalesce(extracted_text, content),
  extraction_status = case
    when coalesce(nullif(trim(coalesce(extracted_text, '')), ''), nullif(trim(coalesce(content, '')), '')) is not null
      then 'extracted'
    else coalesce(extraction_status, 'pending')
  end
where raw_text is null
   or extracted_text is null
   or extraction_status = 'pending';

create table if not exists public.policy_extraction_runs (
  id uuid primary key default gen_random_uuid(),
  policy_document_id uuid not null references public.policy_documents(id) on delete cascade,
  model_used text,
  status text not null default 'pending',
  summary text,
  ambiguities jsonb not null default '[]'::jsonb,
  unsupported_or_missing_fields jsonb not null default '[]'::jsonb,
  suggested_feature_engineering jsonb not null default '[]'::jsonb,
  draft_rule_count integer not null default 0 check (draft_rule_count >= 0),
  error text,
  created_at timestamptz not null default now()
);

alter table public.policy_extraction_runs enable row level security;

alter table public.policy_rules
  add column if not exists policy_document_id uuid references public.policy_documents(id) on delete set null,
  add column if not exists policy_extraction_run_id uuid references public.policy_extraction_runs(id) on delete set null;

create index if not exists idx_policy_documents_source_type
  on public.policy_documents(source_type);

create index if not exists idx_policy_documents_extraction_status
  on public.policy_documents(extraction_status);

create index if not exists idx_policy_extraction_runs_policy_document_id_created_at
  on public.policy_extraction_runs(policy_document_id, created_at desc);

create index if not exists idx_policy_rules_policy_document_id
  on public.policy_rules(policy_document_id);

create index if not exists idx_policy_rules_policy_extraction_run_id
  on public.policy_rules(policy_extraction_run_id);
