drop function if exists public.match_policy_chunks(vector, float, int);

create or replace function public.match_policy_chunks(
  query_embedding vector(1536),
  match_threshold float,
  match_count int,
  rule_filter text default null
)
returns table (
  id uuid,
  document_id uuid,
  rule_code text,
  chunk_index integer,
  content text,
  metadata jsonb,
  document_title text,
  document_version text,
  similarity float
)
language sql
stable
as $$
  select
    policy_chunks.id,
    policy_chunks.document_id,
    policy_chunks.rule_code,
    policy_chunks.chunk_index,
    policy_chunks.content,
    policy_chunks.metadata,
    policy_documents.title as document_title,
    policy_documents.version as document_version,
    1 - (policy_chunks.embedding <=> query_embedding) as similarity
  from public.policy_chunks
  join public.policy_documents
    on policy_documents.id = policy_chunks.document_id
  where policy_chunks.embedding is not null
    and policy_documents.active = true
    and (rule_filter is null or policy_chunks.rule_code = rule_filter)
    and 1 - (policy_chunks.embedding <=> query_embedding) >= match_threshold
  order by policy_chunks.embedding <=> query_embedding
  limit match_count;
$$;
