import json
from pathlib import Path

from kbindex.config import EMBEDDING_DIMENSIONS, QUERY_PREFIX
from kbindex.embed import BGP_PASSAGE, SLA_PASSAGE, SMOKE_QUESTION, embed_passages, embed_query, embedding_prefix
from kbindex.rerank import rerank_pairs

OUTPUT = Path(__file__).parent / "output"


def test_embed_and_rerank_prefer_the_relevant_passage():
    passages = json.loads((OUTPUT / "passage_embeddings.json").read_text())
    query = json.loads((OUTPUT / "query_embedding.json").read_text())
    scores = json.loads((OUTPUT / "rerank_scores.json").read_text())

    bgp = passages[0]
    assert len(bgp) == EMBEDDING_DIMENSIONS == 384
    assert bgp == json.loads(json.dumps(embed_passages([BGP_PASSAGE])))[0]
    prefixed = embedding_prefix(BGP_PASSAGE)
    assert prefixed == QUERY_PREFIX + BGP_PASSAGE
    assert prefixed.startswith("Represent this sentence for searching relevant passages: ")
    assert bgp != json.loads(json.dumps(embed_passages([prefixed])))[0]
    assert query == json.loads(json.dumps(embed_query(SMOKE_QUESTION)))
    assert passages == json.loads(json.dumps(embed_passages([BGP_PASSAGE, SLA_PASSAGE])))
    assert scores == json.loads(json.dumps(rerank_pairs(SMOKE_QUESTION, [BGP_PASSAGE, SLA_PASSAGE])))
    assert scores[0] > scores[1]
