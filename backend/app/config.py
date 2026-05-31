from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_db_url: str | None = Field(default=None, alias="SUPABASE_DB_URL")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-haiku-4-5", alias="ANTHROPIC_MODEL")
    anthropic_model2: str | None = Field(default=None, alias="ANTHROPIC_MODEL2")
    anthropic_sql_guard_model: str = Field(default="claude-haiku-4-5", alias="ANTHROPIC_SQL_GUARD_MODEL")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    ai_rule_extraction_provider: str = Field(default="openai", alias="AI_RULE_EXTRACTION_PROVIDER")
    ai_rule_extraction_model: str | None = Field(default=None, alias="AI_RULE_EXTRACTION_MODEL")
    openai_rule_extraction_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_RULE_EXTRACTION_MODEL")
    openai_reviewer_brief_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_REVIEWER_BRIEF_MODEL")
    openai_approval_recommendation_model: str = Field(
        default="gpt-5.4-mini",
        alias="OPENAI_APPROVAL_RECOMMENDATION_MODEL",
    )
    openai_insight_response_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_INSIGHT_RESPONSE_MODEL")
    openai_embedding_model: str = Field(default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL")
    openai_embedding_dimensions: int = Field(default=1536, alias="OPENAI_EMBEDDING_DIMENSIONS")
    policy_rag_top_k: int = Field(default=5, alias="POLICY_RAG_TOP_K")
    policy_rag_match_threshold: float = Field(default=0.72, alias="POLICY_RAG_MATCH_THRESHOLD")
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
        alias="CORS_ORIGINS",
    )

    vite_supabase_url: str | None = Field(default=None, alias="VITE_SUPABASE_URL")
    vite_supabase_anon_key: str | None = Field(default=None, alias="VITE_SUPABASE_ANON_KEY")

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]

        return value

    @property
    def resolved_supabase_url(self) -> str | None:
        return self.supabase_url or self.vite_supabase_url

    @property
    def resolved_supabase_anon_key(self) -> str | None:
        return self.supabase_anon_key or self.vite_supabase_anon_key

    @property
    def resolved_anthropic_insights_model(self) -> str:
        return self.anthropic_model2 or self.anthropic_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
