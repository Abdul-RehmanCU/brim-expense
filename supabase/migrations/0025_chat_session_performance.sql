create index if not exists idx_chat_messages_session_id_created_at
on public.chat_messages(session_id, created_at);

create index if not exists idx_chat_sessions_created_by_updated_at
on public.chat_sessions(created_by_employee_id, updated_at desc);

create or replace function public.touch_chat_session_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  update public.chat_sessions
  set updated_at = now()
  where id = new.session_id;
  return new;
end;
$$;

drop trigger if exists touch_chat_session_updated_at on public.chat_messages;
create trigger touch_chat_session_updated_at
after insert on public.chat_messages
for each row
execute function public.touch_chat_session_updated_at();
