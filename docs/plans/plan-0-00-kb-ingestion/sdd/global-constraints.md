## Global Constraints

- User agent is `CatoHomeTaskBot/1.0 (educational assignment)`. Wait at least one second between crawl requests.
- Discovery index is only `https://knowledge.catonetworks.com/llms.txt`. Keep a URL only when its path is `/docs/<slug>.md` and the slug has no slash. Drop `/{language}/llms.txt` and `/docs/fr/<slug>.md` before any request.
- Save the raw response bytes. The article hash is SHA-256 of those bytes. The public URL has no `.md`. `site_updated_at` comes from the article `updated` field and is null when that field is missing. The crawl time is never copied into `site_updated_at`.
- Each crawl writes `data/kb_ingestion/<YYYY-MM-DDTHHMMSSZ>/`. Article files are `<slug>.md`. The manifest is `manifest.json` in that same directory. Chunking adds `passages.jsonl` there. Nothing else is written into that directory.
- The dump is `db/kb.dump`. It sits outside the crawl directory.
- Policy ids and files: `POL-CREDIT`, `POL-SEV1`, `POL-IDV`, `POL-SEC`, `POL-CRED`, `POL-SLA`, each `data/policies/<id>.md`.
- A stored passage is at most 400 tokens of the pinned bge-small tokenizer. A sliced section keeps the same heading, takes at most 350 new tokens, plus at most 50 tokens of whole sentences from the previous slice of that same section, and never copies text across headings. A heading with no body produces no passage.
- Passages are embedded as plain text. A question is embedded with the prefix `Represent this sentence for searching relevant passages: `, including the trailing space. The smoke test checks that prefix. Query-time search is not part of this plan.
- Vector search, when it is added later, is an exact cosine scan. This plan creates no HNSW index. The keyword column uses the Postgres `simple` text configuration.
- Model weights are not committed. Task 1 downloads both pinned revisions into the local cache. The image build downloads the same revisions into the image. The running container does not fetch them.
- The crawl command hits the live site once. Tests written after that read the saved files. They do not crawl again.
- Fusion, the search function, and `RERANK_MIN_SCORE` are a later retrieval plan. This plan does not build agents, the chat UI, approvals, or telemetry tools.

## File map

- `pyproject.toml` — package `kbindex`, pytest, runtime dependencies.
- `kbindex/config.py` — the constants in Global Constraints.
- `kbindex/embed.py` — load bge-small, embed passages, embed a question, write the smoke-test files, probe width.
- `kbindex/rerank.py` — load the MiniLM cross-encoder and score question-passage pairs.
- `kbindex/schema.sql` — the four empty tables.
- `kbindex/store.py` — apply the schema, load the crawl and the policies, compare hashes.
- `kbindex/crawl.py` — fetch allowed URLs and write one timestamped directory.
- `kbindex/discover.py` — classify a URL, parse `llms.txt`, apply `robots.txt`.
- `kbindex/hashing.py` — SHA-256 of bytes and of a file, then store those hashes on the manifest.
- `kbindex/chunk.py` — strip the documentation-index banner, split headings, slice, anchors, write `passages.jsonl`.
- `kbindex/policies.py` — read the six policy files into records.
- `kbindex/startup.py` — reload policies, hash check, width check.
- `kbindex/build.py` — operator command: load the crawl into Postgres and write the dump.
- `tests/kbindex/fixtures/article.md` — chunk fixture with a banner, a preamble, a long section, an empty heading, and one sentence over 400 tokens.
- `tests/kbindex/output/` — smoke-test embeddings and rerank scores. Gitignored.
- `docker-compose.yml`, `Dockerfile`, `README.md`.

A passage record has slug, heading, heading_anchor, position, and body. A policy record has id, title, content_hash, file_path, and body.

## Tests

Each test is written first, run, and seen to fail. The implementation step then produces the real files or the real database rows. The test is run again and checks that output.

- `test_embed_and_rerank_prefer_the_relevant_passage` — the pinned models. A BGP passage embeds to 384 numbers with no query prefix. The question embedding matches the prefixed question. The reranker scores the BGP passage above an unrelated SLA-credits passage.
- `test_tables_are_readable` — a connection can read `snapshots`, `kb_articles`, `passages`, and `policies`.
- `test_crawled_article_has_text` — the newest `data/kb_ingestion/<timestamp>/` directory has a manifest and at least one `<slug>.md` whose body is non-empty text. The public URL for that slug has no `.md`. No saved path contains `/docs/fr/`.
- `test_saved_articles_are_english_docs` — every saved file is an English `/docs/<slug>.md` article, and every skipped URL in the manifest was classified as language, robots, or not an article.
- `test_manifest_hash_matches_file` — every saved article's SHA-256 equals its manifest hash. A one-byte copy of one file does not.
- `test_chunk_keeps_every_sentence` — `passages.jsonl` and the fixture. Every sentence that fits the cap appears in a passage. The over-cap sentence appears only as the prefix that was kept. No body is over 400 bge-small tokens.
- `test_chunks_are_whole_sentences` — every passage from the fixture starts and ends on a sentence boundary, except the hard-cut sentence, which ends at the token cap. Overlap text stays inside its own section.
- `test_database_holds_the_crawl_and_policies` — the database has one snapshot, one `kb_articles` row per saved file, passage rows for those articles, and all six policies including `POL-SLA`. One stored embedding has 384 numbers.
- `test_startup_rejects_a_hash_or_width_mismatch` — startup passes on the filled database. A reader that returns different bytes raises `HashMismatch`. A probe width other than 384 raises `StartupError`.

---
