alter table public.policy_checks
add column if not exists severity_score integer not null default 0
check (severity_score >= 0 and severity_score <= 100);

alter table public.policy_checks
add column if not exists scan_version text not null default 'python-policy-engine-v2';

create index if not exists idx_policy_checks_severity_score
on public.policy_checks(severity_score desc);
