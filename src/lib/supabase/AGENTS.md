# src/lib/supabase/AGENTS.md

This folder owns frontend-safe Supabase client access.

## Responsibilities

- Create the browser Supabase client.
- Provide typed query and mutation helpers used by hooks/pages.
- Avoid spreading Supabase query details throughout components.

## Rules

- Use only `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
- Never use the service role key here.
- Do not bypass row-level security from frontend code.
- Keep query functions typed and named by business intent.
- Return normalized errors that the UI can display safely.
- When working with imported transactions, preserve both `business_category` and `normalized_category` until the category migration is fully complete.

## Do not

- Call Claude or OpenAI directly.
- Store secrets.
- Build raw SQL strings.
