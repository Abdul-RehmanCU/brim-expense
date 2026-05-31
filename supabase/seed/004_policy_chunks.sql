insert into public.policy_documents (title, version, source_type, content, synthetic, active)
values (
  'Synthetic Brim Demo Expense Policy',
  '2026-demo-v1',
  'seed',
  'Synthetic demo policy used for Brim Expense Intelligence Copilot. This policy text supports RAG explanations only; deterministic TypeScript rules enforce compliance.',
  true,
  true
)
on conflict (title, version) do update set
  content = excluded.content,
  synthetic = true,
  active = true;

insert into public.policy_chunks (document_id, rule_code, chunk_index, content, embedding, metadata, synthetic)
select doc.id, chunk.rule_code, chunk.chunk_index, chunk.content, array_fill(0::real, array[1536])::vector, chunk.metadata::jsonb, true
from public.policy_documents doc
cross join (
  values
    ('PREAPPROVAL_OVER_50', 0, 'Expenses over CAD 50 require manager pre-authorization before reimbursement or approval.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('RECEIPT_REQUIRED', 1, 'Receipts are required before reimbursement can be completed.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('RECEIPT_CURRENT_MONTH', 2, 'Receipts should be submitted within the current month where possible.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('FALSIFICATION_PROHIBITED', 3, 'Falsified, altered, or misleading expense reports are prohibited.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('ENTERTAINMENT_CONTEXT_REQUIRED', 4, 'Customer entertainment requires guest names and a clear business purpose.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('ALCOHOL_RESTRICTED', 5, 'Alcohol is not permitted unless dining with a customer and the business context is recorded.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('TIPS_SERVICE_15', 6, 'Tips for services or porterage may be expensed up to 15 percent.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('MEAL_TIPS_20', 7, 'Meal tips are not reimbursed above 20 percent.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('PARKING_ALLOWED', 8, 'Reasonable parking expenses may be reimbursed when business related.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('TOLLS_ALLOWED', 9, 'Business toll expenses may be reimbursed.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('TICKETS_NOT_REIMBURSABLE', 10, 'Traffic tickets and parking tickets are not reimbursable.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('CAR_RENTAL_RECEIPTS_REQUIRED', 11, 'Car rental, parking, and gasoline expenses require receipts.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('CARD_NAMED_INDIVIDUAL_ONLY', 12, 'Corporate cards may only be used by the named individual assigned to the card.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('PERSONAL_CARD_USE_PROHIBITED', 13, 'Personal expenses on corporate cards are prohibited.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}'),
    ('CONSISTENT_ABUSE_REVIEW', 14, 'Consistent abuse can restrict or revoke corporate card privileges.', '{"embedding_status":"placeholder_zero_vector","model":"text-embedding-3-small"}')
) as chunk(rule_code, chunk_index, content, metadata)
where doc.title = 'Synthetic Brim Demo Expense Policy'
  and doc.version = '2026-demo-v1'
on conflict (document_id, chunk_index) do update set
  rule_code = excluded.rule_code,
  content = excluded.content,
  metadata = excluded.metadata,
  synthetic = true;
