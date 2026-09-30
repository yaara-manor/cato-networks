from sentence_transformers import CrossEncoder

from core.config import RERANKER_MODEL, RERANKER_REVISION

_reranker: CrossEncoder | None = None


def load_reranker() -> CrossEncoder:
    # Load the pinned MiniLM cross-encoder from the local cache.
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(
            RERANKER_MODEL,
            revision=RERANKER_REVISION,
            local_files_only=True,
            device="cpu",
        )
    return _reranker


def rerank_pairs(question: str, passages: list[str]) -> list[float]:
    # Score each passage against the question and return the raw scores in order.
    scores = load_reranker().predict(
        [[question, passage] for passage in passages],
        show_progress_bar=False,
    )
    return [float(score) for score in scores]
