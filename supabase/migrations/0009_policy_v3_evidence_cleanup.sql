delete from public.violations as violation
using public.receipts as receipt
where violation.transaction_id = receipt.transaction_id
  and violation.rule_code = 'RECEIPT_REQUIRED'
  and receipt.synthetic is true
  and receipt.status = 'unavailable';

insert into public.violations (
  policy_check_id,
  transaction_id,
  policy_rule_id,
  rule_code,
  severity,
  explanation,
  required_action,
  status
)
select
  policy_check.id,
  transaction.id,
  null,
  'RECEIPT_EVIDENCE_REQUIRED',
  'low',
  'Receipt evidence unavailable in transaction dataset. ' || coalesce(transaction.business_category, transaction.normalized_category, 'This category') || ' expenses require receipt evidence under the travel policy, but the provided CSV does not include attachments.',
  'Treat this as evidence-readiness metadata and collect the document during report assembly if reimbursement proceeds.',
  'open'
from public.transactions as transaction
join public.policy_checks as policy_check
  on policy_check.transaction_id = transaction.id
join public.receipts as receipt
  on receipt.transaction_id = transaction.id
where receipt.synthetic is true
  and receipt.status = 'unavailable'
  and coalesce(transaction.business_category, transaction.normalized_category) in (
    'Fuel',
    'Car Rental',
    'Car / Truck Rental',
    'Vehicle Maintenance',
    'Transportation / Fleet / Operations',
    'Parking / Tolls',
    'Parking',
    'Tolls / Road Fees',
    'Ground Transportation'
  )
  and not exists (
    select 1
    from public.violations as existing
    where existing.transaction_id = transaction.id
      and existing.rule_code = 'RECEIPT_EVIDENCE_REQUIRED'
  );

with latest_preapproval as (
  select distinct on (transaction_id)
    transaction_id,
    status
  from public.preapprovals
  where transaction_id is not null
  order by transaction_id, created_at desc
),
violation_rollup as (
  select
    transaction_id,
    count(*) as violation_count,
    max(case severity when 'critical' then 4 when 'high' then 3 when 'medium' then 2 else 1 end) as max_severity_rank,
    bool_or(rule_code in ('TICKETS_NOT_REIMBURSABLE', 'PERSONAL_CARD_USE_PROHIBITED')) as has_policy_violation,
    bool_or(rule_code = 'PREAPPROVAL_OVER_50') as has_preapproval_rule,
    bool_or(rule_code in ('RECEIPT_EVIDENCE_REQUIRED', 'RECEIPT_CURRENT_MONTH')) as has_evidence_readiness_rule
  from public.violations
  where status = 'open'
  group by transaction_id
)
update public.policy_checks as policy_check
set
  status = case
    when coalesce(violation_rollup.has_policy_violation, false) then 'policy_violation'
    when transaction.debit_credit = 'credit' or transaction.amount_cad <= 0 then 'excluded_non_expense'
    when coalesce(violation_rollup.has_preapproval_rule, false)
      and coalesce(latest_preapproval.status, 'missing') in ('missing', 'denied') then 'approval_evidence_needed'
    when cardinality(coalesce(policy_check.missing_information, array[]::text[])) > 0 then 'context_needed'
    when latest_preapproval.status = 'requested' then 'review_required'
    when coalesce(violation_rollup.violation_count, 0) > 0 then 'review_required'
    else 'compliant'
  end,
  max_severity = case coalesce(violation_rollup.max_severity_rank, 0)
    when 4 then 'critical'
    when 3 then 'high'
    when 2 then 'medium'
    when 1 then 'low'
    else 'low'
  end,
  severity_score = case coalesce(violation_rollup.max_severity_rank, 0)
    when 4 then 90
    when 3 then 60
    when 2 then 30
    when 1 then 10
    else 0
  end
  + case when transaction.amount_cad >= 500 then 10 else 0 end
  + case when transaction.amount_cad >= 1000 then 10 else 0 end,
  scan_version = 'python-policy-engine-v3-evidence-cleanup',
  engine_version = 'python-policy-engine-v3',
  recommended_next_action = case
    when coalesce(violation_rollup.has_policy_violation, false) then 'Do not reimburse until finance reviews and resolves the violation.'
    when transaction.debit_credit = 'credit' or transaction.amount_cad <= 0 then 'Exclude this credit or non-expense item from reimbursement review.'
    when coalesce(violation_rollup.has_preapproval_rule, false)
      and coalesce(latest_preapproval.status, 'missing') in ('missing', 'denied') then 'Collect or document the required approval evidence before approval.'
    when cardinality(coalesce(policy_check.missing_information, array[]::text[])) > 0 then 'Collect the missing business context before deciding compliance.'
    when latest_preapproval.status = 'requested' then 'Follow up on the pending manager preauthorization before finance approval.'
    when coalesce(violation_rollup.has_evidence_readiness_rule, false) then 'Flag this transaction for evidence readiness and collect receipt evidence during report assembly if reimbursement proceeds.'
    when coalesce(violation_rollup.violation_count, 0) > 0 then 'Route this transaction to finance review.'
    else 'No policy action required.'
  end
from public.transactions as transaction
left join latest_preapproval
  on latest_preapproval.transaction_id = transaction.id
left join violation_rollup
  on violation_rollup.transaction_id = transaction.id
where policy_check.transaction_id = transaction.id;
