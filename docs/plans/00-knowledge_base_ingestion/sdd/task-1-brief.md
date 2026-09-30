### Task 1: Package, constants, and both models

This task creates the Python package, records the constants, downloads both pinned models into the local cache, and proves each one runs.

The embedding model is `BAAI/bge-small-en-v1.5`, revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, 384 dimensions. The reranker is `cross-encoder/ms-marco-MiniLM-L12-v2`, revision `7b0235231ca2674cb8ca8f022859a6eba2b1c968`. Download those two revisions with the Hugging Face cache and no other revisions. The weight files stay out of git.

`load_embedder` reads that bge-small revision from the cache and does not send a question prefix. `embed_passages` embeds each passage string as its own words. `embed_query` embeds the exact prefix `Represent this sentence for searching relevant passages: `, including the trailing space, and then the question. `embedding_prefix` returns that string so the smoke test can see the prefix without guessing it. `load_reranker` reads the MiniLM revision from the cache. `rerank_pairs` sends the question and one passage through the cross-encoder and keeps the raw score, one number per passage, in the same order as the input.

`write_model_outputs` runs those functions on two fixed passages: one about BGP route limits, one about SLA credits. It writes `passage_embeddings.json`, `query_embedding.json`, and `rerank_scores.json` under `tests/kbindex/output/`. The test reads those files back and checks them against a fresh call: the BGP vector has 384 numbers, it matches the raw passage and differs from the same words with the query prefix, the question file matches `embed_query`, and the BGP rerank score is higher than the SLA-credits score.

**Files:**
- Create: `pyproject.toml`
- Create: `kbindex/__init__.py`
- Create: `kbindex/config.py`
- Create: `kbindex/embed.py`
- Create: `kbindex/rerank.py`
- Modify: `.gitignore`
- Test: `tests/kbindex/test_embed_and_rerank_prefer_the_relevant_passage.py`
- Generated, not committed: `tests/kbindex/output/passage_embeddings.json`, `tests/kbindex/output/query_embedding.json`, `tests/kbindex/output/rerank_scores.json`

**Functions:**
- `load_embedder()` loads the pinned bge-small revision from the local cache and returns it. Comment: `Load the pinned bge-small model from the local cache.`
- `embed_passages(texts) -> list[list[float]]` embeds each string as plain text. Comment: `Embed passage text with no query prefix.`
- `embed_query(text) -> list[float]` embeds `QUERY_PREFIX` plus the text. Comment: `Embed a question with the bge query prefix.`
- `embedding_prefix(question) -> str` returns that exact prefixed string. Comment: `Return the exact string sent to the embedding model for a question.`
- `load_reranker()` loads the pinned MiniLM revision from the local cache. Comment: `Load the pinned MiniLM cross-encoder from the local cache.`
- `rerank_pairs(question, passages) -> list[float]` returns one raw score per passage, in the same order. Comment: `Score each passage against the question and return the raw scores in order.`
- `write_model_outputs(output_dir)` writes the three JSON files for one BGP route-limits passage and one unrelated SLA-credits passage. Comment: `Write the smoke-test embedding and rerank files.`

**Constants in `kbindex/config.py`:** `USER_AGENT`, `RATE_LIMIT_SECONDS` (1), `EMBEDDING_MODEL`, `EMBEDDING_REVISION`, `EMBEDDING_DIMENSIONS` (384), `RERANKER_MODEL`, `RERANKER_REVISION`, `QUERY_PREFIX`, `PASSAGE_TOKEN_CAP` (400), `SLICE_NEW_TOKENS` (350), `SLICE_OVERLAP_TOKENS` (50).

- [ ] **Step 1: Write the failing test**

`test_embed_and_rerank_prefer_the_relevant_passage` reads the three files in `tests/kbindex/output/`. It checks that the BGP embedding has 384 numbers, that this vector matches `embed_passages` on the raw passage and differs from the same words with the query prefix, that the question file matches `embed_query`, and that the rerank file scores the BGP passage above the SLA-credits passage. The files must equal a fresh call of `embed_passages`, `embed_query`, and `rerank_pairs`.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_embed_and_rerank_prefer_the_relevant_passage.py -v`

Expected: fail because the output files are absent.

- [ ] **Step 3: Download both models and generate the files**

Create the package for Python 3.12 with pytest, httpx, psycopg (binary), pgvector, and sentence-transformers. `kbindex/__init__.py` is empty. Assign the constants above.

Download `BAAI/bge-small-en-v1.5` revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` and `cross-encoder/ms-marco-MiniLM-L12-v2` revision `7b0235231ca2674cb8ca8f022859a6eba2b1c968` into the local cache. Implement the loaders and `write_model_outputs`, then run `write_model_outputs` so the three JSON files exist. Add `tests/kbindex/output/` and the Hugging Face weight cache to `.gitignore`.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_embed_and_rerank_prefer_the_relevant_passage.py -v`

Expected: pass. The files match a fresh run of the same two models.

- [ ] **Step 5: Commit**

Commit the package, the loaders, the test, and the gitignore entries. Do not commit the weights or `tests/kbindex/output/`.

Commit message: `Install kbindex and the pinned embedding and reranker models.`

---
