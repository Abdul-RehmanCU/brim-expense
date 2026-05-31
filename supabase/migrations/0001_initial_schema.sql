create extension if not exists pgcrypto;
create extension if not exists vector;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.departments (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  manager_name text not null,
  monthly_budget_cad numeric(12,2) not null check (monthly_budget_cad >= 0),
  quarterly_budget_cad numeric(12,2) not null check (quarterly_budget_cad >= 0),
  synthetic boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.employees (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments(id) on delete restrict,
  manager_employee_id uuid references public.employees(id) on delete set null,
  full_name text not null,
  email text not null unique,
  role text not null,
  synthetic boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.raw_transactions (
  id uuid primary key default gen_random_uuid(),
  source_file_name text,
  source_row_number integer not null check (source_row_number > 0),
  source_fingerprint text not null unique,
  raw_payload jsonb not null,
  import_batch_id uuid,
  synthetic_context_assigned boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.transactions (
  id uuid primary key default gen_random_uuid(),
  raw_transaction_id uuid references public.raw_transactions(id) on delete set null,
  employee_id uuid references public.employees(id) on delete set null,
  department_id uuid references public.departments(id) on delete set null,
  transaction_code text,
  description text,
  source_category text,
  normalized_category text not null default 'Uncategorized',
  category_confidence numeric(4,2) not null default 0.40 check (category_confidence >= 0 and category_confidence <= 1),
  posting_date date,
  transaction_date date,
  merchant_name text,
  normalized_merchant_name text,
  amount_original numeric(12,2) not null,
  amount_cad numeric(12,2) not null,
  debit_credit text not null check (debit_credit in ('debit', 'credit')),
  merchant_category_code text,
  merchant_city text,
  merchant_country text,
  merchant_postal_code text,
  merchant_region text,
  conversion_rate numeric(12,6),
  synthetic_assignment boolean not null default true,
  business_purpose text,
  guest_names text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.receipts (
  id uuid primary key default gen_random_uuid(),
  transaction_id uuid not null references public.transactions(id) on delete cascade,
  storage_path text,
  file_name text,
  receipt_date date,
  submitted_at timestamptz,
  status text not null default 'missing' check (status in ('missing', 'submitted', 'approved', 'rejected')),
  synthetic boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.preapprovals (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null references public.employees(id) on delete cascade,
  transaction_id uuid references public.transactions(id) on delete set null,
  department_id uuid references public.departments(id) on delete set null,
  requested_amount_cad numeric(12,2) not null check (requested_amount_cad >= 0),
  status text not null default 'missing' check (status in ('not_required', 'missing', 'requested', 'approved', 'denied')),
  requested_at timestamptz,
  approved_at timestamptz,
  approver_employee_id uuid references public.employees(id) on delete set null,
  approver_name text,
  business_purpose text,
  synthetic boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.policy_rules (
  id uuid primary key default gen_random_uuid(),
  rule_code text not null unique,
  title text not null,
  description text not null,
  severity text not null check (severity in ('low', 'medium', 'high', 'critical')),
  deterministic boolean not null default true,
  active boolean not null default true,
  effective_date date,
  synthetic boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.policy_checks (
  id uuid primary key default gen_random_uuid(),
  transaction_id uuid not null references public.transactions(id) on delete cascade,
  status text not null check (status in ('compliant', 'needs_receipt', 'needs_preapproval', 'needs_context', 'violation', 'review_required')),
  max_severity text not null check (max_severity in ('low', 'medium', 'high', 'critical')),
  missing_information text[] not null default '{}',
  recommended_next_action text not null,
  checked_at timestamptz not null default now(),
  engine_version text not null default 'policy-engine-v0',
  created_at timestamptz not null default now()
);

create table if not exists public.violations (
  id uuid primary key default gen_random_uuid(),
  policy_check_id uuid not null references public.policy_checks(id) on delete cascade,
  transaction_id uuid not null references public.transactions(id) on delete cascade,
  policy_rule_id uuid references public.policy_rules(id) on delete set null,
  rule_code text not null,
  severity text not null check (severity in ('low', 'medium', 'high', 'critical')),
  explanation text not null,
  required_action text not null,
  status text not null default 'open' check (status in ('open', 'resolved', 'dismissed')),
  created_at timestamptz not null default now()
);

create table if not exists public.risk_scores (
  id uuid primary key default gen_random_uuid(),
  transaction_id uuid not null references public.transactions(id) on delete cascade,
  risk_score integer not null check (risk_score >= 0 and risk_score <= 100),
  risk_level text not null check (risk_level in ('low', 'medium', 'high', 'critical')),
  signals jsonb not null default '[]'::jsonb,
  scored_at timestamptz not null default now(),
  engine_version text not null default 'risk-engine-v0',
  created_at timestamptz not null default now()
);

create table if not exists public.approval_requests (
  id uuid primary key default gen_random_uuid(),
  transaction_id uuid not null references public.transactions(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete restrict,
  department_id uuid not null references public.departments(id) on delete restrict,
  status text not null default 'draft' check (status in ('draft', 'requested', 'approved', 'denied', 'cancelled')),
  requested_amount_cad numeric(12,2) not null check (requested_amount_cad >= 0),
  policy_check_id uuid references public.policy_checks(id) on delete set null,
  risk_score_id uuid references public.risk_scores(id) on delete set null,
  ai_recommendation jsonb,
  requester_note text,
  decision_note text,
  decided_by text,
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.expense_reports (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null references public.employees(id) on delete restrict,
  department_id uuid not null references public.departments(id) on delete restrict,
  period_start date not null,
  period_end date not null,
  status text not null default 'draft' check (status in ('draft', 'generated', 'exported', 'archived')),
  total_amount_cad numeric(12,2) not null default 0,
  missing_receipt_count integer not null default 0,
  policy_flag_count integer not null default 0,
  risk_flag_count integer not null default 0,
  ai_summary text,
  synthetic boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (period_end >= period_start)
);

create table if not exists public.expense_report_items (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references public.expense_reports(id) on delete cascade,
  transaction_id uuid not null references public.transactions(id) on delete restrict,
  amount_cad numeric(12,2) not null,
  category text not null,
  policy_status text,
  risk_level text,
  created_at timestamptz not null default now(),
  unique (report_id, transaction_id)
);

create table if not exists public.policy_documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  version text not null,
  source_type text not null default 'seed',
  content text not null,
  synthetic boolean not null default true,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (title, version)
);

create table if not exists public.policy_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.policy_documents(id) on delete cascade,
  rule_code text references public.policy_rules(rule_code) on delete set null,
  chunk_index integer not null check (chunk_index >= 0),
  content text not null,
  embedding vector(1536),
  metadata jsonb not null default '{}'::jsonb,
  synthetic boolean not null default true,
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index)
);

create table if not exists public.audit_log (
  id uuid primary key default gen_random_uuid(),
  actor_employee_id uuid references public.employees(id) on delete set null,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  title text not null default 'Untitled session',
  created_by_employee_id uuid references public.employees(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system', 'tool')),
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_employees_department_id on public.employees(department_id);
create index if not exists idx_transactions_employee_id on public.transactions(employee_id);
create index if not exists idx_transactions_department_id on public.transactions(department_id);
create index if not exists idx_transactions_transaction_date on public.transactions(transaction_date);
create index if not exists idx_transactions_normalized_category on public.transactions(normalized_category);
create index if not exists idx_policy_checks_transaction_id on public.policy_checks(transaction_id);
create index if not exists idx_violations_transaction_id on public.violations(transaction_id);
create index if not exists idx_risk_scores_transaction_id on public.risk_scores(transaction_id);
create index if not exists idx_policy_chunks_rule_code on public.policy_chunks(rule_code);
create index if not exists idx_policy_chunks_embedding on public.policy_chunks using hnsw (embedding vector_cosine_ops);

drop trigger if exists set_departments_updated_at on public.departments;
create trigger set_departments_updated_at
before update on public.departments
for each row execute function public.set_updated_at();

drop trigger if exists set_employees_updated_at on public.employees;
create trigger set_employees_updated_at
before update on public.employees
for each row execute function public.set_updated_at();

drop trigger if exists set_transactions_updated_at on public.transactions;
create trigger set_transactions_updated_at
before update on public.transactions
for each row execute function public.set_updated_at();

drop trigger if exists set_receipts_updated_at on public.receipts;
create trigger set_receipts_updated_at
before update on public.receipts
for each row execute function public.set_updated_at();

drop trigger if exists set_preapprovals_updated_at on public.preapprovals;
create trigger set_preapprovals_updated_at
before update on public.preapprovals
for each row execute function public.set_updated_at();

drop trigger if exists set_policy_rules_updated_at on public.policy_rules;
create trigger set_policy_rules_updated_at
before update on public.policy_rules
for each row execute function public.set_updated_at();

drop trigger if exists set_approval_requests_updated_at on public.approval_requests;
create trigger set_approval_requests_updated_at
before update on public.approval_requests
for each row execute function public.set_updated_at();

drop trigger if exists set_expense_reports_updated_at on public.expense_reports;
create trigger set_expense_reports_updated_at
before update on public.expense_reports
for each row execute function public.set_updated_at();

drop trigger if exists set_policy_documents_updated_at on public.policy_documents;
create trigger set_policy_documents_updated_at
before update on public.policy_documents
for each row execute function public.set_updated_at();

drop trigger if exists set_chat_sessions_updated_at on public.chat_sessions;
create trigger set_chat_sessions_updated_at
before update on public.chat_sessions
for each row execute function public.set_updated_at();

create or replace function public.match_policy_chunks(
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
returns table (
  id uuid,
  document_id uuid,
  rule_code text,
  content text,
  similarity float
)
language sql
stable
as $$
  select
    policy_chunks.id,
    policy_chunks.document_id,
    policy_chunks.rule_code,
    policy_chunks.content,
    1 - (policy_chunks.embedding <=> query_embedding) as similarity
  from public.policy_chunks
  where policy_chunks.embedding is not null
    and 1 - (policy_chunks.embedding <=> query_embedding) >= match_threshold
  order by policy_chunks.embedding <=> query_embedding
  limit match_count;
$$;
