# src/lib/rag/AGENTS.md

This folder owns frontend-safe policy RAG helpers and compatibility wrappers.

Long-term RAG orchestration should prefer the backend boundary.

## Responsibilities

- Chunk seeded policy text where needed.
- Provide typed wrappers for policy clause retrieval.
- Keep any browser-side helpers free of secrets and direct model calls.

## Rules

- Do not call OpenAI directly from frontend code.
- Do not store API keys.
- RAG is for policy explanations and source-backed context only.
- RAG must not calculate spend totals or enforce compliance.
- Retrieval output should include clause text, similarity score, rule codes, and source metadata.

## Backend boundary

Embedding and pgvector similarity search should happen in trusted server-side code such as FastAPI services, Supabase Edge Functions, or database RPCs, not in browser-only code.
