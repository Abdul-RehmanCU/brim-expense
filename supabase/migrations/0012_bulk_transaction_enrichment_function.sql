create or replace function public.bulk_update_transaction_enrichment(payload jsonb)
returns integer
language plpgsql
as $$
declare
  updated_count integer := 0;
begin
  with updates as (
    select *
    from jsonb_to_recordset(payload) as item(
      id uuid,
      transaction_type text,
      transaction_eligibility text,
      network_category_code text,
      business_category text,
      policy_category text,
      category_source text,
      normalized_merchant_family text,
      mcc_description text,
      amount_bucket text,
      posting_delay_days integer,
      is_account_activity boolean,
      is_credit_or_refund boolean,
      is_foreign_transaction boolean
    )
  ),
  updated as (
    update public.transactions as transaction
    set
      transaction_type = updates.transaction_type,
      transaction_eligibility = updates.transaction_eligibility,
      network_category_code = updates.network_category_code,
      business_category = updates.business_category,
      policy_category = updates.policy_category,
      category_source = updates.category_source,
      normalized_merchant_family = updates.normalized_merchant_family,
      mcc_description = updates.mcc_description,
      amount_bucket = updates.amount_bucket,
      posting_delay_days = updates.posting_delay_days,
      is_account_activity = updates.is_account_activity,
      is_credit_or_refund = updates.is_credit_or_refund,
      is_foreign_transaction = updates.is_foreign_transaction,
      updated_at = now()
    from updates
    where transaction.id = updates.id
    returning 1
  )
  select count(*) into updated_count
  from updated;

  return coalesce(updated_count, 0);
end;
$$;
