from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from postgrest.exceptions import APIError

from app.config import Settings, get_settings
from app.database.supabase_client import get_supabase_client
from app.schemas.common import PlaceholderResponse

POLICY_CHUNK_MAX_CHARS = 1800
POLICY_CHUNK_MIN_CHARS = 120
POLICY_CHUNK_INSERT_BATCH_SIZE = 100


class EmbeddingClient(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass
class PolicyChunk:
    document_id: str
    chunk_index: int
    content: str
    metadata: dict[str, Any]
    rule_code: str | None = None
    embedding: list[float] | None = None


@dataclass
class PolicyRagIngestionResult:
    status: str
    chunk_count: int = 0
    embedded_count: int = 0
    model: str | None = None
    dimensions: int | None = None
    error: str | None = None


@dataclass
class PolicyChunkMatch:
    id: str
    document_id: str
    chunk_index: int
    content: str
    similarity: float
    rule_code: str | None = None
    citation: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyRagRetrievalResult:
    status: str
    query_text: str
    chunks: list[PolicyChunkMatch] = field(default_factory=list)
    model: str | None = None
    dimensions: int | None = None
    error: str | None = None


class OpenAIEmbeddingClient:
    def __init__(self, api_key: str, model: str, dimensions: int):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]


def get_rag_status() -> PlaceholderResponse:
    settings = get_settings()
    configured = bool(settings.openai_api_key)
    return PlaceholderResponse(
        status="available" if configured else "configuration_needed",
        service="rag",
        implemented=True,
        message=(
            "Policy RAG chunking and retrieval are implemented."
            if configured
            else "Policy RAG chunking is available, but embeddings need OPENAI_API_KEY."
        ),
    )


def ingest_policy_document_chunks(
    document: dict[str, Any],
    embedding_client: EmbeddingClient | None = None,
    supabase_client: Any | None = None,
    settings: Settings | None = None,
) -> PolicyRagIngestionResult:
    settings = settings or get_settings()
    model = settings.openai_embedding_model
    dimensions = settings.openai_embedding_dimensions
    chunks = chunk_policy_document(document, model=model, dimensions=dimensions)
    if not chunks:
        return PolicyRagIngestionResult(
            status="skipped",
            model=model,
            dimensions=dimensions,
            error="Policy document has no extractable text to chunk.",
        )

    status = "embedded"
    error: str | None = None
    embedded_count = 0

    if embedding_client or settings.openai_api_key:
        try:
            client = embedding_client or OpenAIEmbeddingClient(
                api_key=str(settings.openai_api_key),
                model=model,
                dimensions=dimensions,
            )
            embeddings = client.embed_texts([chunk.content for chunk in chunks])
            if len(embeddings) != len(chunks):
                raise RuntimeError(
                    f"OpenAI returned {len(embeddings)} embeddings for {len(chunks)} policy chunks."
                )
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                chunk.embedding = embedding
                chunk.metadata["embedding_status"] = "embedded"
            embedded_count = len(chunks)
        except Exception as exc:
            status = "failed"
            error = f"Policy chunk embedding failed: {exc}"
            for chunk in chunks:
                chunk.embedding = None
                chunk.metadata["embedding_status"] = "failed"
                chunk.metadata["embedding_error"] = error
    else:
        status = "skipped"
        error = "OPENAI_API_KEY is not configured; policy chunks were stored without embeddings."
        for chunk in chunks:
            chunk.metadata["embedding_status"] = "skipped"
            chunk.metadata["embedding_error"] = error

    try:
        store_policy_chunks(chunks, supabase_client=supabase_client)
    except Exception as exc:
        return PolicyRagIngestionResult(
            status="failed",
            chunk_count=len(chunks),
            embedded_count=embedded_count,
            model=model,
            dimensions=dimensions,
            error=f"Policy chunk storage failed: {exc}",
        )

    return PolicyRagIngestionResult(
        status=status,
        chunk_count=len(chunks),
        embedded_count=embedded_count,
        model=model,
        dimensions=dimensions,
        error=error,
    )


def retrieve_policy_chunks(
    query: str | None = None,
    rule_code: str | None = None,
    transaction_context: dict[str, Any] | None = None,
    top_k: int | None = None,
    match_threshold: float | None = None,
    embedding_client: EmbeddingClient | None = None,
    supabase_client: Any | None = None,
    settings: Settings | None = None,
) -> PolicyRagRetrievalResult:
    settings = settings or get_settings()
    query_text = policy_retrieval_query(query, rule_code, transaction_context)
    if not query_text:
        return PolicyRagRetrievalResult(
            status="skipped",
            query_text="",
            model=settings.openai_embedding_model,
            dimensions=settings.openai_embedding_dimensions,
            error="A query, rule code, or transaction context is required for policy retrieval.",
        )
    if not embedding_client and not settings.openai_api_key:
        return PolicyRagRetrievalResult(
            status="skipped",
            query_text=query_text,
            model=settings.openai_embedding_model,
            dimensions=settings.openai_embedding_dimensions,
            error="OPENAI_API_KEY is not configured; policy retrieval embeddings cannot run.",
        )

    try:
        client = embedding_client or OpenAIEmbeddingClient(
            api_key=str(settings.openai_api_key),
            model=settings.openai_embedding_model,
            dimensions=settings.openai_embedding_dimensions,
        )
        embeddings = client.embed_texts([query_text])
        if not embeddings:
            raise RuntimeError("OpenAI returned no embedding for the policy retrieval query.")
        rows = match_policy_chunks(
            embeddings[0],
            rule_code=rule_code,
            top_k=top_k or settings.policy_rag_top_k,
            match_threshold=(
                settings.policy_rag_match_threshold
                if match_threshold is None
                else match_threshold
            ),
            supabase_client=supabase_client,
        )
    except Exception as exc:
        return PolicyRagRetrievalResult(
            status="failed",
            query_text=query_text,
            model=settings.openai_embedding_model,
            dimensions=settings.openai_embedding_dimensions,
            error=f"Policy retrieval failed: {exc}",
        )

    return PolicyRagRetrievalResult(
        status="ok",
        query_text=query_text,
        chunks=[policy_chunk_match_from_row(row) for row in rows],
        model=settings.openai_embedding_model,
        dimensions=settings.openai_embedding_dimensions,
    )


def chunk_policy_document(
    document: dict[str, Any],
    model: str,
    dimensions: int,
    max_chars: int = POLICY_CHUNK_MAX_CHARS,
) -> list[PolicyChunk]:
    text = normalize_policy_text(
        str(document.get("extracted_text") or document.get("raw_text") or document.get("content") or "")
    )
    if not text:
        return []

    document_id = str(document.get("id") or "")
    title = str(document.get("title") or "Untitled policy")
    version = str(document.get("version") or "")
    source_type = str(document.get("source_type") or "unknown")
    chunks: list[PolicyChunk] = []
    current_blocks: list[tuple[str, int, int]] = []
    current_section: str | None = None
    current_start: int | None = None
    current_end = 0

    def flush() -> None:
        nonlocal current_blocks, current_start, current_end
        if not current_blocks or current_start is None:
            return
        content = "\n\n".join(block for block, _, _ in current_blocks).strip()
        if not content:
            current_blocks = []
            current_start = None
            return
        chunk_index = len(chunks)
        metadata = {
            "document_id": document_id,
            "chunk_index": chunk_index,
            "source_title": title,
            "source_version": version,
            "source_type": source_type,
            "section_label": current_section,
            "char_start": current_start,
            "char_end": current_end,
            "estimated_token_start": estimate_token_offset(current_start),
            "estimated_token_end": estimate_token_offset(current_end),
            "embedding_model": model,
            "embedding_dimensions": dimensions,
            "embedding_status": "pending",
            "rag_role": "evidence_only",
        }
        chunks.append(
            PolicyChunk(
                document_id=document_id,
                chunk_index=chunk_index,
                content=content,
                metadata=metadata,
            )
        )
        current_blocks = []
        current_start = None

    for block, start, end in iter_policy_text_blocks(text):
        section_label = infer_section_label(block)
        current_length = sum(len(item[0]) for item in current_blocks) + max(0, len(current_blocks) - 1) * 2
        would_exceed = current_blocks and current_length + len(block) + 2 > max_chars
        if would_exceed and (current_length >= POLICY_CHUNK_MIN_CHARS or section_label):
            flush()

        if section_label:
            current_section = section_label

        if current_start is None:
            current_start = start
        current_blocks.append((block, start, end))
        current_end = end

    flush()
    return chunks


def store_policy_chunks(chunks: list[PolicyChunk], supabase_client: Any | None = None) -> None:
    if not chunks:
        return

    client = supabase_client or get_supabase_client()
    document_id = chunks[0].document_id
    client.table("policy_chunks").delete().eq("document_id", document_id).execute()
    payloads = [
        {
            "document_id": chunk.document_id,
            "rule_code": chunk.rule_code,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "embedding": chunk.embedding,
            "metadata": chunk.metadata,
            "synthetic": False,
        }
        for chunk in chunks
    ]
    for batch in chunked(payloads, POLICY_CHUNK_INSERT_BATCH_SIZE):
        client.table("policy_chunks").insert(batch).execute()


def match_policy_chunks(
    query_embedding: list[float],
    rule_code: str | None,
    top_k: int,
    match_threshold: float,
    supabase_client: Any | None = None,
) -> list[dict[str, Any]]:
    client = supabase_client or get_supabase_client()
    payload = {
        "query_embedding": query_embedding,
        "match_threshold": match_threshold,
        "match_count": top_k,
        "rule_filter": rule_code,
    }
    try:
        response = client.rpc("match_policy_chunks", payload).execute()
    except APIError as exc:
        if not should_retry_without_rule_filter(exc):
            raise
        legacy_payload = {
            "query_embedding": query_embedding,
            "match_threshold": match_threshold,
            "match_count": top_k,
        }
        response = client.rpc("match_policy_chunks", legacy_payload).execute()
    return response.data or []


def should_retry_without_rule_filter(error: APIError) -> bool:
    message = str(error)
    return "match_policy_chunks" in message and "rule_filter" in message


def policy_chunk_match_from_row(row: dict[str, Any]) -> PolicyChunkMatch:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    document_title = str(row.get("document_title") or metadata.get("source_title") or "Policy document")
    document_version = str(row.get("document_version") or metadata.get("source_version") or "")
    chunk_index = int(row.get("chunk_index") if row.get("chunk_index") is not None else metadata.get("chunk_index") or 0)
    citation = {
        "document_id": str(row.get("document_id") or metadata.get("document_id") or ""),
        "title": document_title,
        "version": document_version,
        "chunk_index": chunk_index,
        "section_label": metadata.get("section_label"),
        "char_start": metadata.get("char_start"),
        "char_end": metadata.get("char_end"),
    }
    return PolicyChunkMatch(
        id=str(row.get("id") or ""),
        document_id=citation["document_id"],
        chunk_index=chunk_index,
        content=str(row.get("content") or ""),
        similarity=float(row.get("similarity") or 0),
        rule_code=str(row.get("rule_code")) if row.get("rule_code") else None,
        citation=citation,
        metadata=metadata,
    )


def policy_retrieval_query(
    query: str | None,
    rule_code: str | None,
    transaction_context: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    if query and query.strip():
        parts.append(query.strip())
    if rule_code and rule_code.strip():
        parts.append(f"Policy rule code: {rule_code.strip().upper()}")
    if transaction_context:
        parts.append(f"Transaction context: {summarize_transaction_context(transaction_context)}")
    return "\n".join(part for part in parts if part.strip()).strip()


def summarize_transaction_context(context: dict[str, Any]) -> str:
    keys = [
        "merchant",
        "merchant_name",
        "merchant_raw",
        "normalized_merchant_name",
        "amount_cad",
        "business_category",
        "normalized_category",
        "policy_category",
        "transaction_date",
        "employee_role",
        "department_name",
        "has_receipt_evidence",
        "has_pending_preapproval",
    ]
    pairs = []
    for key in keys:
        value = context.get(key)
        if value not in (None, "", []):
            pairs.append(f"{key}={value}")
    return "; ".join(pairs)[:1200]


def iter_policy_text_blocks(text: str) -> list[tuple[str, int, int]]:
    blocks: list[tuple[str, int, int]] = []
    for match in re.finditer(r"\S.*?(?=\n\s*\n|\Z)", text, flags=re.DOTALL):
        block = normalize_policy_text(match.group(0))
        if block:
            blocks.append((block, match.start(), match.end()))
    return blocks


def infer_section_label(block: str) -> str | None:
    first_line = block.splitlines()[0].strip()
    cleaned = re.sub(r"\s+", " ", first_line).strip(" :-")
    if not cleaned or len(cleaned) > 120:
        return None
    word_count = len(cleaned.split())
    numbered_heading = bool(re.match(r"^([A-Z]|\d+(\.\d+)*)([.)])?\s+[A-Za-z]", cleaned))
    title_like = word_count <= 10 and cleaned[:1].isupper() and not cleaned.endswith((".", ",", ";"))
    all_caps = word_count <= 12 and cleaned.upper() == cleaned and any(char.isalpha() for char in cleaned)
    if numbered_heading or title_like or all_caps:
        return cleaned
    return None


def normalize_policy_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def estimate_token_offset(char_offset: int) -> int:
    return int(math.floor(max(char_offset, 0) / 4))


def chunked[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
