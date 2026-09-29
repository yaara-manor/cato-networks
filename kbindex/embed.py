from typing import Any

from sentence_transformers import SentenceTransformer

from kbindex.config import EMBEDDING_MODEL, EMBEDDING_REVISION, QUERY_PREFIX

BGP_PASSAGE = "BGP route limits cap the number of routes a Socket accepts from a neighbor."
SLA_PASSAGE = "SLA credits refund a share of the fee after a qualifying service outage."
SMOKE_QUESTION = "What happens when a Socket hits its BGP route limit?"

_embedder = None


def load_embedder():
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


def embed_passages(texts) -> list[list[float]]:
    # Embed passage text with no query prefix.
    model = load_embedder()
    return [
        [float(value) for value in model.encode(text, prompt="", show_progress_bar=False)]
        for text in texts
    ]


def embedding_prefix(question) -> str:
    # Return the exact string sent to the embedding model for a question.
    return QUERY_PREFIX + question


def embed_query(text) -> list[float]:
    # Embed a question with the bge query prefix.
    return embed_passages([embedding_prefix(text)])[0]


def probe_width(embed: Any = None) -> int:
    # Embed the fixed string width-check and return the vector length.
    target: Any = embed_passages if embed is None else embed

    if hasattr(target, "encode"):
        vec: Any = target.encode("width-check")
        if hasattr(vec, "shape"):
            return int(vec.shape[-1])
        return len(vec)

    try:
        res: Any = target(["width-check"])
    except Exception:
        res = target("width-check")

    if hasattr(res, "shape"):
        return int(res.shape[-1])
    if isinstance(res, (list, tuple)) and len(res) > 0 and isinstance(res[0], (list, tuple)):
        return len(res[0])
    return len(res)
