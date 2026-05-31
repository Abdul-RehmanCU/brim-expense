alter table public.transactions
  add column if not exists transaction_type text,
  add column if not exists transaction_eligibility text,
  add column if not exists network_category_code text,
  add column if not exists policy_category text,
  add column if not exists category_source text,
  add column if not exists normalized_merchant_family text,
  add column if not exists mcc_description text,
  add column if not exists amount_bucket text,
  add column if not exists posting_delay_days integer,
  add column if not exists is_account_activity boolean not null default false,
  add column if not exists is_credit_or_refund boolean not null default false,
  add column if not exists is_foreign_transaction boolean not null default false;

create index if not exists idx_transactions_transaction_eligibility
  on public.transactions(transaction_eligibility);

create index if not exists idx_transactions_policy_category
  on public.transactions(policy_category);

create index if not exists idx_transactions_transaction_type
  on public.transactions(transaction_type);

delete from public.policy_checks
where ctid in (
  select ctid
  from (
    select
      ctid,
      row_number() over (
        partition by transaction_id
        order by created_at desc, checked_at desc, id desc
      ) as row_number
    from public.policy_checks
  ) ranked
  where ranked.row_number > 1
);

create unique index if not exists idx_policy_checks_transaction_id_unique
  on public.policy_checks(transaction_id);
