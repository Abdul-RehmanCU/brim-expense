alter table if exists public.approval_requests
  add column if not exists review_queue_item_id uuid references public.review_queue_items(id) on delete set null;

alter table if exists public.approval_requests
  add column if not exists context_snapshot jsonb not null default '{}'::jsonb;

alter table if exists public.approval_requests
  add column if not exists recommendation_source text not null default 'deterministic_fallback'
  check (recommendation_source in ('deterministic_fallback', 'openai_structured_output'));

alter table if exists public.approval_requests
  add column if not exists recommendation_generated_at timestamptz;

create index if not exists idx_approval_requests_status_created_at
  on public.approval_requests(status, created_at desc);

create index if not exists idx_approval_requests_review_queue_item_id
  on public.approval_requests(review_queue_item_id);

create index if not exists idx_approval_requests_context_snapshot_gin
  on public.approval_requests using gin (context_snapshot);
