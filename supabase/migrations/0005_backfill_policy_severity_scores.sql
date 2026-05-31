with violation_counts as (
  select
    transaction_id,
    count(*)::integer as violation_count
  from public.violations
  where status = 'open'
  group by transaction_id
)
update public.policy_checks as policy_check
set severity_score = least(
  100,
  case policy_check.max_severity
    when 'critical' then 90
    when 'high' then 60
    when 'medium' then 30
    when 'low' then 10
    else 0
  end
  + least(30, greatest(0, coalesce(violation_counts.violation_count, 0) - 1) * 8)
  + case when abs(coalesce(transaction.amount_cad, 0)) >= 500 then 10 else 0 end
  + case when abs(coalesce(transaction.amount_cad, 0)) >= 1000 then 10 else 0 end
),
scan_version = coalesce(policy_check.scan_version, 'python-policy-engine-v2')
from public.transactions as transaction
left join violation_counts
  on violation_counts.transaction_id = transaction.id
where transaction.id = policy_check.transaction_id;
