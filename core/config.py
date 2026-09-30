from datetime import datetime, timezone
from pathlib import Path

from pydantic import AwareDatetime, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT: Path = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Centralized application settings populated from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: PostgresDsn = PostgresDsn("postgresql://postgres:postgres@localhost:5432/cato")
    simulation_time: AwareDatetime = datetime(2026, 8, 28, 17, 0, 0, tzinfo=timezone.utc)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    embedding_dimensions: int = 384
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L12-v2"
    reranker_revision: str = "7b0235231ca2674cb8ca8f022859a6eba2b1c968"
    rerank_min_score: float = 0.0
    llm_model: str = "openai:gpt-4o-mini"
    query_prefix: str = "Represent this sentence for searching relevant passages: "
    user_agent: str = "CatoHomeTaskBot/1.0 (educational assignment)"
    rate_limit_seconds: int = 1
    passage_token_cap: int = 400
    slice_new_tokens: int = 350
    slice_overlap_tokens: int = 50


settings: Settings = Settings()

USER_AGENT: str = settings.user_agent
RATE_LIMIT_SECONDS: int = settings.rate_limit_seconds
EMBEDDING_MODEL: str = settings.embedding_model
EMBEDDING_REVISION: str = settings.embedding_revision
EMBEDDING_DIMENSIONS: int = settings.embedding_dimensions
RERANKER_MODEL: str = settings.reranker_model
RERANKER_REVISION: str = settings.reranker_revision
QUERY_PREFIX: str = settings.query_prefix
PASSAGE_TOKEN_CAP: int = settings.passage_token_cap
SLICE_NEW_TOKENS: int = settings.slice_new_tokens
SLICE_OVERLAP_TOKENS: int = settings.slice_overlap_tokens
