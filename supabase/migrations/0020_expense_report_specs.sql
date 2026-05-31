alter table if exists public.expense_reports
  add column if not exists report_name text;

alter table if exists public.expense_reports
  add column if not exists report_spec jsonb not null default '{}'::jsonb;
