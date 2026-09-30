# SDD progress
Base: 9057fe11f41d586484a46a26dc4425b053d064fd feat/kb-ingestion


Task 2: complete (commits 9057fe1..bb88fe1, review clean). Minor: test_tables_are_readable checks counts only, not column types or indexes.

Task 1: complete (commits 9057fe1..6bd5cec, review clean). Verified pinned HF snapshots and smoke JSON exist; rerank scores are raw logits. Minor: embed_passages encodes one string at a time with no comment.
Task 3: in progress, base 81c1dff, branch task/3-crawl
Task 3: complete (commits 81c1dff..ea02c98, review clean). Verified 1471 non-empty files, 159 null site_updated_at match missing front-matter updated, no content_hash. Minor: language label has no host check; crawl test does not cover skip/robots/failed.
Task 5: complete (commits 8f27436..628e152, review clean).
Task 4: complete (commits 8f27436..0dddfd2, review clean). Minor: saved crawl has an empty skipped list, so the committed test does not exercise language or robots skips.
Task 6 minors (pending final review): token counts clip at encoder max+1; tests duplicate _encoder_max.
Task 6: complete (commits 2e4549d..031346d, review clean). Encoder model_max_length checked at merge. Minors: a first word over 512 is dropped with no error; anchor suffix is not rechecked for collision; tests do not lock the 50-token overlap cap or the over-max raise.
Task 7: complete (commits 95432f9..ecba4f7, review clean).
Task 8: complete (commits a437ae5..38fdf9e, review clean). Minor: error message on dimension mismatch could clarify required constant 384; HashMismatch could inherit from StartupError.
Task 9: complete (commits 180cc14..c3c6bc2, review clean). Dump written atomically via pg_dump custom format to db/kb.dump, pinned offline models in Dockerfile, docker compose verified.
