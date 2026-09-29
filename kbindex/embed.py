import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

from kbindex.config import EMBEDDING_MODEL, EMBEDDING_REVISION, QUERY_PREFIX
from kbindex.rerank import rerank_pairs

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


def write_model_outputs(output_dir):
    # Write the smoke-test embedding and rerank files.
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    passages = [BGP_PASSAGE, SLA_PASSAGE]
    _write(output_dir / "passage_embeddings.json", embed_passages(passages))
    _write(output_dir / "query_embedding.json", embed_query(SMOKE_QUESTION))
    _write(output_dir / "rerank_scores.json", rerank_pairs(SMOKE_QUESTION, passages))


def _write(path, value):
    path.write_text(json.dumps(value))
