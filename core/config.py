from datetime import datetime, timezone
from pathlib import Path

from pydantic import AwareDatetime
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT: Path = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    repo_root: Path = REPO_ROOT
    database_url: str = "postgresql://kb:kb@localhost:5432/kb"
    simulation_time: AwareDatetime = datetime(2026, 8, 28, 17, 0, 0, tzinfo=timezone.utc)
    user_agent: str = "CatoHomeTaskBot/1.0 (educational assignment)"
    rate_limit_seconds: float = 1.0
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    embedding_dimensions: int = 384
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L12-v2"
    reranker_revision: str = "7b0235231ca2674cb8ca8f022859a6eba2b1c968"
    rerank_min_score: float = 0.0
    query_prefix: str = "Represent this sentence for searching relevant passages: "
    passage_token_cap: int = 400
    slice_new_tokens: int = 350
    slice_overlap_tokens: int = 50
    llm_model: str = "openai:gpt-4o-mini"
    country_resolver_model: str = "openai:gpt-4o-mini"


settings: Settings = Settings()

USER_AGENT: str = settings.user_agent
RATE_LIMIT_SECONDS: float = settings.rate_limit_seconds
EMBEDDING_MODEL: str = settings.embedding_model
EMBEDDING_REVISION: str = settings.embedding_revision
EMBEDDING_DIMENSIONS: int = settings.embedding_dimensions
RERANKER_MODEL: str = settings.reranker_model
RERANKER_REVISION: str = settings.reranker_revision
QUERY_PREFIX: str = settings.query_prefix
PASSAGE_TOKEN_CAP: int = settings.passage_token_cap
SLICE_NEW_TOKENS: int = settings.slice_new_tokens
SLICE_OVERLAP_TOKENS: int = settings.slice_overlap_tokens
