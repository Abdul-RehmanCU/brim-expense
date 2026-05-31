alter table if exists public.expense_reports
  add column if not exists workflow_status text not null default 'action_required'
  check (workflow_status in ('scan_incomplete', 'action_required', 'pending_cfo_review', 'ready_for_cfo'));

alter table if exists public.expense_reports
  add column if not exists workflow_snapshot jsonb not null default '{}'::jsonb;

alter table if exists public.expense_report_items
  add column if not exists review_queue_item_id uuid references public.review_queue_items(id) on delete set null;

alter table if exists public.expense_report_items
  add column if not exists approval_request_id uuid references public.approval_requests(id) on delete set null;

alter table if exists public.expense_report_items
  add column if not exists approval_recommendation jsonb;

alter table if exists public.expense_report_items
  add column if not exists reviewer_next_action text;

create index if not exists idx_expense_reports_workflow_status
  on public.expense_reports(workflow_status, created_at desc);

create index if not exists idx_expense_report_items_approval_request_id
  on public.expense_report_items(approval_request_id);

create index if not exists idx_expense_report_items_review_queue_item_id
  on public.expense_report_items(review_queue_item_id);
