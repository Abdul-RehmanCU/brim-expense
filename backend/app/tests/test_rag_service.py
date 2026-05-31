from app.config import Settings
from app.services import policy_service
from app.services.rag_service import (
    chunk_policy_document,
    ingest_policy_document_chunks,
    retrieve_policy_chunks,
)
from app.schemas.policy import PolicyDocumentTextRequest


class FakeEmbeddingClient:
    def __init__(self, embeddings=None):
        self.embeddings = embeddings
        self.calls = []

    def embed_texts(self, texts):
        self.calls.append(texts)
        if self.embeddings is not None:
            return self.embeddings
        return [[float(index + 1), 0.1, 0.2] for index, _text in enumerate(texts)]


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakePolicyChunksTable:
    def __init__(self):
        self.deleted_document_id = None
        self.inserted = []
        self._operation = None

    def delete(self):
        self._operation = "delete"
        return self

    def eq(self, column, value):
        assert column == "document_id"
        self.deleted_document_id = value
        return self

    def insert(self, payload):
        self._operation = "insert"
        self.inserted.extend(payload)
        return self

    def execute(self):
        return FakeResponse([])


class FakePolicyDocumentsTable:
    def __init__(self):
        self.inserted = []

    def insert(self, payload):
        self.inserted.append(payload)
        return self

    def execute(self):
        return FakeResponse(self.inserted)


class FakeSupabaseClient:
    def __init__(self, rpc_rows=None):
        self.policy_chunks = FakePolicyChunksTable()
        self.policy_documents = FakePolicyDocumentsTable()
        self.rpc_rows = rpc_rows or []
        self.rpc_name = None
        self.rpc_args = None

    def table(self, table_name):
        if table_name == "policy_chunks":
            return self.policy_chunks
        if table_name == "policy_documents":
            return self.policy_documents
        raise AssertionError(f"Unexpected table {table_name}")

    def rpc(self, rpc_name, args):
        self.rpc_name = rpc_name
        self.rpc_args = args
        return self

    def execute(self):
        return FakeResponse(self.rpc_rows)


class FallbackRpcCall:
    def __init__(self, client, args):
        self.client = client
        self.args = args

    def execute(self):
        self.client.rpc_calls.append(self.args)
        if "rule_filter" in self.args:
            from postgrest.exceptions import APIError

            raise APIError(
                {
                    "message": "Could not find the function public.match_policy_chunks(match_count, match_threshold, query_embedding, rule_filter) in the schema cache",
                    "code": "PGRST202",
                }
            )
        return FakeResponse(self.client.rpc_rows)


class FakeFallbackSupabaseClient(FakeSupabaseClient):
    def __init__(self, rpc_rows=None):
        super().__init__(rpc_rows=rpc_rows)
        self.rpc_calls = []

    def rpc(self, rpc_name, args):
        self.rpc_name = rpc_name
        self.rpc_args = args
        return FallbackRpcCall(self, args)


def rag_settings(api_key="test-key"):
    return Settings(
        openai_api_key=api_key,
        openai_embedding_model="text-embedding-3-small",
        openai_embedding_dimensions=1536,
        policy_rag_top_k=5,
        policy_rag_match_threshold=0.72,
    )


def policy_document(text=None):
    return {
        "id": "doc-1",
        "title": "Travel and Meal Policy",
        "version": "v1",
        "source_type": "pasted_text",
        "extracted_text": text
        or (
            "Meals and Entertainment\n\n"
            "Customer meals require a business purpose and guest names.\n\n"
            "Receipts\n\n"
            "Receipts are required for car rental, parking, and gasoline expenses."
        ),
    }


def test_policy_chunking_adds_citation_offsets_and_section_metadata():
    chunks = chunk_policy_document(
        policy_document(),
        model="text-embedding-3-small",
        dimensions=1536,
        max_chars=90,
    )

    assert len(chunks) >= 2
    first = chunks[0]
    assert first.metadata["document_id"] == "doc-1"
    assert first.metadata["source_title"] == "Travel and Meal Policy"
    assert first.metadata["source_version"] == "v1"
    assert first.metadata["section_label"] == "Meals and Entertainment"
    assert first.metadata["char_start"] == 0
    assert first.metadata["char_end"] > first.metadata["char_start"]
    assert first.metadata["estimated_token_end"] >= first.metadata["estimated_token_start"]
    assert first.metadata["rag_role"] == "evidence_only"


def test_ingestion_embeds_and_stores_policy_chunks_without_zero_vectors():
    supabase = FakeSupabaseClient()
    embeddings = [[0.11, 0.22, 0.33]]
    embedding_client = FakeEmbeddingClient(embeddings=embeddings)

    result = ingest_policy_document_chunks(
        policy_document(),
        embedding_client=embedding_client,
        supabase_client=supabase,
        settings=rag_settings(),
    )

    assert result.status == "embedded"
    assert result.chunk_count == 1
    assert result.embedded_count == 1
    assert supabase.policy_chunks.deleted_document_id == "doc-1"
    assert [row["embedding"] for row in supabase.policy_chunks.inserted] == embeddings
    assert all(row["metadata"]["embedding_status"] == "embedded" for row in supabase.policy_chunks.inserted)
    assert all(row["embedding"] != [0.0, 0.0, 0.0] for row in supabase.policy_chunks.inserted)


def test_ingestion_without_openai_key_stores_unembedded_chunks_gracefully():
    supabase = FakeSupabaseClient()

    result = ingest_policy_document_chunks(
        policy_document(),
        supabase_client=supabase,
        settings=rag_settings(api_key=None),
    )

    assert result.status == "skipped"
    assert result.error == "OPENAI_API_KEY is not configured; policy chunks were stored without embeddings."
    assert result.chunk_count == 1
    assert result.embedded_count == 0
    assert all(row["embedding"] is None for row in supabase.policy_chunks.inserted)
    assert all(row["metadata"]["embedding_status"] == "skipped" for row in supabase.policy_chunks.inserted)


def test_retrieve_policy_chunks_returns_similarity_and_citation_metadata():
    supabase = FakeSupabaseClient(
        rpc_rows=[
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "rule_code": "RECEIPT_REQUIRED",
                "chunk_index": 3,
                "content": "Receipts are required for car rentals.",
                "metadata": {
                    "section_label": "Receipts",
                    "char_start": 50,
                    "char_end": 91,
                },
                "document_title": "Travel Policy",
                "document_version": "v1",
                "similarity": 0.88,
            }
        ]
    )

    result = retrieve_policy_chunks(
        query="Why is a receipt required?",
        rule_code="RECEIPT_REQUIRED",
        transaction_context={"amount_cad": 72, "business_category": "Car Rental"},
        embedding_client=FakeEmbeddingClient(embeddings=[[0.1, 0.2, 0.3]]),
        supabase_client=supabase,
        settings=rag_settings(),
    )

    assert result.status == "ok"
    assert supabase.rpc_name == "match_policy_chunks"
    assert supabase.rpc_args["rule_filter"] == "RECEIPT_REQUIRED"
    assert supabase.rpc_args["match_count"] == 5
    assert result.chunks[0].similarity == 0.88
    assert result.chunks[0].citation == {
        "document_id": "doc-1",
        "title": "Travel Policy",
        "version": "v1",
        "chunk_index": 3,
        "section_label": "Receipts",
        "char_start": 50,
        "char_end": 91,
    }


def test_retrieve_policy_chunks_retries_legacy_rpc_without_rule_filter():
    supabase = FakeFallbackSupabaseClient(
        rpc_rows=[
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "rule_code": "RECEIPT_REQUIRED",
                "chunk_index": 0,
                "content": "Receipts are required for fuel and parking expenses.",
                "metadata": {"section_label": "Receipts"},
                "document_title": "Travel Policy",
                "document_version": "v1",
                "similarity": 0.81,
            }
        ]
    )

    result = retrieve_policy_chunks(
        query="When are receipts required?",
        embedding_client=FakeEmbeddingClient(embeddings=[[0.1, 0.2, 0.3]]),
        supabase_client=supabase,
        settings=rag_settings(),
    )

    assert result.status == "ok"
    assert len(supabase.rpc_calls) == 2
    assert "rule_filter" in supabase.rpc_calls[0]
    assert "rule_filter" not in supabase.rpc_calls[1]


def test_policy_document_text_creation_reports_rag_ingestion_status(monkeypatch):
    supabase = FakeSupabaseClient()
    ingested_documents = []

    def fake_ingest(row):
        ingested_documents.append(row)
        return policy_service.PolicyRagIngestionResult(
            status="embedded",
            chunk_count=1,
            embedded_count=1,
            model="text-embedding-3-small",
            dimensions=1536,
        )

    monkeypatch.setattr(policy_service, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(policy_service, "ingest_policy_document_for_rag", fake_ingest)

    response = policy_service.create_policy_document_from_text(
        PolicyDocumentTextRequest(
            title="Company Expense Policy",
            policy_text="Expenses over CAD 50 require manager preapproval before reimbursement.",
        )
    )

    assert response.embedding_status == "embedded"
    assert response.chunk_count == 1
    assert response.embedded_chunk_count == 1
    assert ingested_documents[0]["title"] == "Company Expense Policy"
