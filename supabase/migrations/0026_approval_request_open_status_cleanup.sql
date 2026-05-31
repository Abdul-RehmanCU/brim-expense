-- Remove the retired approval request status and enforce one open approval per transaction.

update public.approval_requests
set status = 'requested'
where status = 'needs_information';

update public.approval_requests
set ai_recommendation = jsonb_set(
  jsonb_set(
    ai_recommendation::jsonb,
    '{recommendation}',
    '"deny"'::jsonb
  ),
  '{rationale}',
  to_jsonb('The packet shows missing approval evidence, business context, or policy support, so the approver should not approve it as-is.'::text)
)
where ai_recommendation is not null
  and ai_recommendation::jsonb ->> 'recommendation' = 'request_information';

with ranked_open_approvals as (
  select
    id,
    row_number() over (
      partition by transaction_id
      order by updated_at desc, created_at desc, id desc
    ) as open_rank
  from public.approval_requests
  where status in ('draft', 'requested')
)
update public.approval_requests approval_request
set
  status = 'cancelled',
  decision_note = concat_ws(
    E'\n',
    nullif(approval_request.decision_note, ''),
    'Cancelled by migration 0026 because another open approval exists for this transaction.'
  )
from ranked_open_approvals
where approval_request.id = ranked_open_approvals.id
  and ranked_open_approvals.open_rank > 1;

do $$
declare
  constraint_record record;
begin
  for constraint_record in
    select conname
    from pg_constraint
    where conrelid = 'public.approval_requests'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%status%'
      and pg_get_constraintdef(oid) ilike '%needs_information%'
  loop
    execute format(
      'alter table public.approval_requests drop constraint %I',
      constraint_record.conname
    );
  end loop;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.approval_requests'::regclass
      and conname = 'approval_requests_status_check'
  ) then
    alter table public.approval_requests
      add constraint approval_requests_status_check
      check (status in ('draft', 'requested', 'approved', 'denied', 'cancelled'));
  end if;
end $$;

create unique index if not exists idx_approval_requests_one_open_per_transaction
  on public.approval_requests(transaction_id)
  where status in ('draft', 'requested');
