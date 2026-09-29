### Task 6: Chunk the saved articles

This task splits each saved article into passages a citation can name, and writes `passages.jsonl` in the crawl directory. Token counts come from the pinned bge-small tokenizer loaded by `load_embedder`. The model is already in the cache from Task 1. There is no word counter, and this task does not embed.

`write_passages` reads the manifest and each raw `<slug>.md`. For each file it calls `chunk_article` with the manifest title. `chunk_article` does the following:

1. `strip_doc_banner` removes the repeated documentation-index banner from the text used to build passages. The `<slug>.md` file on disk is not rewritten.
2. Split the remaining markdown on headings. Text before the first heading becomes one passage whose heading is the article title from the manifest. A heading with no body produces no passage.
3. Count tokens with the bge-small tokenizer. A section of at most 400 tokens is one passage, with no copied neighbor text.
4. A longer section is cut on sentence boundaries. A sentence ends at `.`, `?`, or `!` followed by whitespace. The first slice has no copied prefix and may use the full 400 tokens. Each later slice takes at most 350 new tokens, then copies at most 50 tokens of whole sentences from the tail of the previous slice of that same section. The copy never includes the next heading, because the citation would name the wrong section. Every slice keeps that section's heading.
5. A single sentence longer than 400 tokens is cut by dropping trailing words until the tokenizer reports at most 400. That passage is the one case that ends mid-sentence.
6. `heading_anchor` lowercases the heading, turns spaces into hyphens, and removes punctuation. `position` is the passage order inside the article, starting at 0, and is what distinguishes slices that share a heading. When two headings in one article produce the same anchor, the later one appends `-` and its position.

Each `passages.jsonl` line has the article slug, heading, heading_anchor, position, and body. The fixture `tests/kbindex/fixtures/article.md` is what forces a banner, a preamble, a sliced section, an empty heading, and one over-cap sentence, in case the saved crawl does not contain all of those shapes.

**Files:**
- Create: `kbindex/chunk.py`
- Create: `tests/kbindex/fixtures/article.md`
- Modify: the crawl directory, adding `passages.jsonl`
- Test: `tests/kbindex/test_chunk_keeps_every_sentence.py`
- Test: `tests/kbindex/test_chunks_are_whole_sentences.py`

**Functions:**
- `strip_doc_banner(markdown) -> str` removes the documentation-index banner from the text used for passages. Comment: `Remove the documentation-index banner from passage text only.` The saved article file stays raw.
- `chunk_article(markdown, title) -> list` returns passage records. Comment: `Split one article into citable passages using the pinned bge-small tokenizer.` The preamble before the first heading uses `title` as its heading. Sentence boundaries are `.`, `?`, or `!` followed by whitespace. A section that fits in 400 tokens is one passage. A longer section is sliced at 350 new tokens on a sentence boundary. Each later slice starts with at most 50 tokens of whole sentences copied from the tail of the previous slice of that same section. Text is never copied across headings. A heading with no body produces no passage. One sentence longer than 400 tokens is cut by dropping trailing words until the tokenizer reports at most 400.
- `heading_anchor(heading, position, used) -> str` builds the anchor. Comment: `Build a unique heading anchor for one article.` Lowercase, spaces become hyphens, punctuation is removed. `used` is the set of anchors already emitted. A collision appends `-` plus `position`.
- `write_passages(crawl_dir)` reads the manifest and each raw file, calls `chunk_article` with the manifest title, and writes `passages.jsonl`. Comment: `Write one passage record per line for the saved crawl.` Each line has slug, heading, heading_anchor, position, and body.

The fixture `tests/kbindex/fixtures/article.md` has a documentation-index banner, a preamble, several headings, one section long enough for this tokenizer to slice, one heading with no body, and one sentence longer than 400 tokens.

- [ ] **Step 1: Write the failing tests**

`test_chunk_keeps_every_sentence` reads `passages.jsonl` for the newest crawl and checks one saved article against `chunk_article`: every sentence that fits the cap appears in at least one passage, a boundary sentence may appear twice because of overlap, and the over-cap case is covered by the fixture. Every body in the fixture output is at most 400 tokens by the pinned tokenizer.

`test_chunks_are_whole_sentences` checks the fixture passages. Each passage starts at a sentence start and ends at a sentence end, except the passage that holds the hard-cut sentence, which ends at the token cap. Overlap text does not include the next heading. The preamble heading is the article title. The empty heading produces no passage.

- [ ] **Step 2: Run the tests and see them fail**

Run: `pytest tests/kbindex/test_chunk_keeps_every_sentence.py tests/kbindex/test_chunks_are_whole_sentences.py -v`

Expected: fail because `passages.jsonl` is absent.

- [ ] **Step 3: Generate the passage file**

The models from Task 1 are already in the cache. Implement the chunk functions and run `write_passages` on the crawl directory.

- [ ] **Step 4: Run the tests and see them pass**

Run: `pytest tests/kbindex/test_chunk_keeps_every_sentence.py tests/kbindex/test_chunks_are_whole_sentences.py -v`

Expected: pass. The fixture checks use the real tokenizer. One saved article in `passages.jsonl` matches `chunk_article`.

- [ ] **Step 5: Commit**

Commit the chunker, the fixture, the tests, and `passages.jsonl`. Do not commit `tests/kbindex/output/`.

Commit message: `Split the saved articles into citable passages.`

---
