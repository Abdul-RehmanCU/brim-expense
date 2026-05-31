alter table public.departments enable row level security;
alter table public.employees enable row level security;
alter table public.raw_transactions enable row level security;
alter table public.transactions enable row level security;
alter table public.receipts enable row level security;
alter table public.preapprovals enable row level security;
alter table public.policy_rules enable row level security;
alter table public.policy_checks enable row level security;
alter table public.violations enable row level security;
alter table public.risk_scores enable row level security;
alter table public.approval_requests enable row level security;
alter table public.expense_reports enable row level security;
alter table public.expense_report_items enable row level security;
alter table public.policy_documents enable row level security;
alter table public.policy_chunks enable row level security;
alter table public.audit_log enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;

grant usage on schema public to anon, authenticated;
grant select on public.departments to anon, authenticated;
grant select on public.employees to anon, authenticated;
grant select, insert on public.raw_transactions to anon, authenticated;
grant select, insert on public.transactions to anon, authenticated;
grant select, insert, update on public.receipts to anon, authenticated;
grant select, insert, update on public.preapprovals to anon, authenticated;
grant select on public.policy_rules to anon, authenticated;
grant select, insert on public.policy_checks to anon, authenticated;
grant select, insert on public.violations to anon, authenticated;
grant select, insert on public.risk_scores to anon, authenticated;
grant select, insert, update on public.approval_requests to anon, authenticated;
grant select, insert, update on public.expense_reports to anon, authenticated;
grant select, insert on public.expense_report_items to anon, authenticated;
grant select on public.policy_documents to anon, authenticated;
grant select on public.policy_chunks to anon, authenticated;
grant select, insert on public.audit_log to anon, authenticated;
grant select, insert, update on public.chat_sessions to anon, authenticated;
grant select, insert on public.chat_messages to anon, authenticated;

create policy "demo read departments" on public.departments
for select to anon, authenticated using (true);

create policy "demo read employees" on public.employees
for select to anon, authenticated using (true);

create policy "demo read raw transactions" on public.raw_transactions
for select to anon, authenticated using (true);

create policy "demo insert raw transactions" on public.raw_transactions
for insert to anon, authenticated with check (true);

create policy "demo read transactions" on public.transactions
for select to anon, authenticated using (true);

create policy "demo insert transactions" on public.transactions
for insert to anon, authenticated with check (true);

create policy "demo manage receipts" on public.receipts
for all to anon, authenticated using (true) with check (true);

create policy "demo manage preapprovals" on public.preapprovals
for all to anon, authenticated using (true) with check (true);

create policy "demo read policy rules" on public.policy_rules
for select to anon, authenticated using (true);

create policy "demo insert policy checks" on public.policy_checks
for insert to anon, authenticated with check (true);

create policy "demo read policy checks" on public.policy_checks
for select to anon, authenticated using (true);

create policy "demo insert violations" on public.violations
for insert to anon, authenticated with check (true);

create policy "demo read violations" on public.violations
for select to anon, authenticated using (true);

create policy "demo insert risk scores" on public.risk_scores
for insert to anon, authenticated with check (true);

create policy "demo read risk scores" on public.risk_scores
for select to anon, authenticated using (true);

create policy "demo manage approval requests" on public.approval_requests
for all to anon, authenticated using (true) with check (true);

create policy "demo manage expense reports" on public.expense_reports
for all to anon, authenticated using (true) with check (true);

create policy "demo insert expense report items" on public.expense_report_items
for insert to anon, authenticated with check (true);

create policy "demo read expense report items" on public.expense_report_items
for select to anon, authenticated using (true);

create policy "demo read policy documents" on public.policy_documents
for select to anon, authenticated using (true);

create policy "demo read policy chunks" on public.policy_chunks
for select to anon, authenticated using (true);

create policy "demo insert audit log" on public.audit_log
for insert to anon, authenticated with check (true);

create policy "demo read audit log" on public.audit_log
for select to anon, authenticated using (true);

create policy "demo manage chat sessions" on public.chat_sessions
for all to anon, authenticated using (true) with check (true);

create policy "demo insert chat messages" on public.chat_messages
for insert to anon, authenticated with check (true);

create policy "demo read chat messages" on public.chat_messages
for select to anon, authenticated using (true);
