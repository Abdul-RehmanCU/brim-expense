alter table public.review_queue_items
  add column if not exists reviewer_brief jsonb;
