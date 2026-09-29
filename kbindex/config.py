from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

USER_AGENT = "CatoHomeTaskBot/1.0 (educational assignment)"
RATE_LIMIT_SECONDS = 1
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
EMBEDDING_DIMENSIONS = 384
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L12-v2"
RERANKER_REVISION = "7b0235231ca2674cb8ca8f022859a6eba2b1c968"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
PASSAGE_TOKEN_CAP = 400
SLICE_NEW_TOKENS = 350
SLICE_OVERLAP_TOKENS = 50
