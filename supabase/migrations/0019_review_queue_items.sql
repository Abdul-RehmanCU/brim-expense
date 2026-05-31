create table if not exists public.review_queue_items (
  id uuid primary key default gen_random_uuid(),
  transaction_id uuid not null references public.transactions(id) on delete cascade,
  employee_id uuid references public.employees(id) on delete set null,
  department_id uuid references public.departments(id) on delete set null,
  transaction_date date,
  merchant text,
  amount_cad numeric(12,2) not null default 0,
  category text not null default 'Uncategorized',
  queue_status text not null default 'open' check (queue_status in ('open', 'in_approval', 'resolved', 'ignored')),
  review_priority integer not null default 0 check (review_priority >= 0 and review_priority <= 100),
  review_level text not null default 'low' check (review_level in ('low', 'medium', 'high', 'critical')),
  policy_check_id uuid references public.policy_checks(id) on delete set null,
  policy_status text,
  policy_severity text check (policy_severity is null or policy_severity in ('low', 'medium', 'high', 'critical')),
  policy_flags jsonb not null default '[]'::jsonb,
  risk_score_id uuid references public.risk_scores(id) on delete set null,
  risk_score integer not null default 0 check (risk_score >= 0 and risk_score <= 100),
  risk_level text check (risk_level is null or risk_level in ('low', 'medium', 'high', 'critical')),
  risk_signals jsonb not null default '[]'::jsonb,
  ai_context text,
  next_action text not null default 'No action required.',
  generated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_review_queue_items_transaction_id_unique
  on public.review_queue_items(transaction_id);

create index if not exists idx_review_queue_items_open_priority
  on public.review_queue_items(queue_status, review_priority desc);

create index if not exists idx_review_queue_items_policy_check_id
  on public.review_queue_items(policy_check_id);

create index if not exists idx_review_queue_items_risk_score_id
  on public.review_queue_items(risk_score_id);

drop trigger if exists set_review_queue_items_updated_at on public.review_queue_items;
create trigger set_review_queue_items_updated_at
before update on public.review_queue_items
for each row execute function public.set_updated_at();

alter table public.review_queue_items enable row level security;
grant select, insert, update, delete on public.review_queue_items to anon, authenticated;

drop policy if exists "demo manage review queue items" on public.review_queue_items;
create policy "demo manage review queue items" on public.review_queue_items
for all using (true) with check (true);
