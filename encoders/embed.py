from collections.abc import Callable

from sentence_transformers import SentenceTransformer

from core.config import EMBEDDING_MODEL, EMBEDDING_REVISION, QUERY_PREFIX

_embedder: SentenceTransformer | None = None


def load_embedder() -> SentenceTransformer:
    # Load the pinned bge-small model from the local cache.
    global _embedder
    if _embedder is None:
        model = SentenceTransformer(
            EMBEDDING_MODEL,
            revision=EMBEDDING_REVISION,
            local_files_only=True,
            device="cpu",
        )
        model.default_prompt_name = None
        _embedder = model
    return _embedder


def embed_passages(texts: list[str]) -> list[list[float]]:
    # Embed passage text with no query prefix.
    model = load_embedder()
    return [
        [float(value) for value in model.encode(text, prompt="", show_progress_bar=False)]
        for text in texts
    ]


def embedding_prefix(question: str) -> str:
    # Return the exact string sent to the embedding model for a question.
    return QUERY_PREFIX + question


def embed_query(text: str) -> list[float]:
    # Embed a question with the bge query prefix.
    return embed_passages([embedding_prefix(text)])[0]


def probe_width(embed: Callable[[list[str]], list[list[float]]] = embed_passages) -> int:
    # Embed the fixed string width-check and return the vector length (0 when no vector comes back).
    vectors = embed(["width-check"])
    return len(vectors[0]) if vectors else 0
