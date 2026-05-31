alter table public.raw_transactions
add column if not exists source_fingerprint text;

update public.raw_transactions
set source_fingerprint = encode(
  digest(
    coalesce(source_file_name, '') || ':' || source_row_number::text || ':' || raw_payload::text,
    'sha256'
  ),
  'hex'
)
where source_fingerprint is null;

alter table public.raw_transactions
alter column source_fingerprint set not null;

create unique index if not exists raw_transactions_source_fingerprint_key
on public.raw_transactions(source_fingerprint);
