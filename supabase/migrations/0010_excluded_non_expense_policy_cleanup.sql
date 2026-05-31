delete from public.violations as violation
using public.transactions as transaction
where violation.transaction_id = transaction.id
  and (transaction.debit_credit = 'credit' or transaction.amount_cad <= 0);

update public.policy_checks as policy_check
set
  status = 'excluded_non_expense',
  max_severity = 'low',
  severity_score = 0,
  scan_version = 'python-policy-engine-v3-evidence-cleanup',
  engine_version = 'python-policy-engine-v3',
  recommended_next_action = 'Exclude this credit or non-expense item from reimbursement review.'
from public.transactions as transaction
where policy_check.transaction_id = transaction.id
  and (transaction.debit_credit = 'credit' or transaction.amount_cad <= 0);
