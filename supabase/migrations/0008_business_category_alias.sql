alter table public.transactions
  add column if not exists business_category text;

update public.transactions
set business_category = normalized_category
where business_category is null;

alter table public.transactions
  alter column business_category set default 'Uncategorized / Needs Review';

create index if not exists idx_transactions_business_category
  on public.transactions(business_category);
