### Task 3: Crawl the English articles

This task fetches the live English knowledge base once and saves the raw markdown. A later test only reads those files. About 1,470 articles at one request per second takes on the order of half an hour. The English filter is applied in this task, before any article request. Task 4 moves the same rules into `discover.py` without fetching again and without changing which files were saved.

English is a path rule, not a guess about the language of the page text. The only discovery page is `https://knowledge.catonetworks.com/llms.txt`. The crawl does not open `https://knowledge.catonetworks.com/fr/llms.txt` or any other `https://knowledge.catonetworks.com/<language>/llms.txt`. Those indexes are the lists of translated articles. It also ignores the sitemap named in `robots.txt`, because that sitemap failed during design and is not a source of URLs.

`crawl` does the following, in order:

1. Fetch `https://knowledge.catonetworks.com/robots.txt` with `User-Agent: CatoHomeTaskBot/1.0 (educational assignment)`. Remember the robots decision. Wait one second.
2. Fetch `https://knowledge.catonetworks.com/llms.txt` with the same user agent. Wait one second. Read the markdown link targets. Do not fetch any other index.
3. For each link, decide before `fetch` is called:
   - Keep `https://knowledge.catonetworks.com/docs/<slug>.md` when `<slug>` contains no slash. `https://knowledge.catonetworks.com/docs/viewing-translated-knowledge-base-articles.md` is kept, because that page is English and its path has no language segment.
   - Skip `/docs/<language>/<slug>.md`, including `/docs/fr/<slug>.md`, with reason `language`. Do not send the request.
   - Skip `/<language>/llms.txt`, including `/fr/llms.txt`, with reason `language`. Do not send the request.
   - Skip any other URL, including another host, an HTML page, a partners page, or an image, with reason `not an article`. Do not send the request. Image files linked from a saved article are not downloaded either.
   - Skip a URL that the path rule would keep when `robots.txt` disallows it for this user agent, with reason `robots`. Do not send the request.
4. For each kept URL, wait one second, then fetch. Status 200 writes the response body bytes, unchanged, to `data/kb_ingestion/<YYYY-MM-DDTHHMMSSZ>/<slug>.md`. The directory name is `now()` in UTC. Any other status or a connection error is recorded under `failed` with the status or the error text, and no file is written. The crawl does not invent a body.
5. Read `title` and `updated` from the YAML front matter, the block between the first pair of `---` lines. A missing `updated` becomes a null `site_updated_at`. The crawl clock is stored as `crawled_at` and is never copied into `site_updated_at`. The public URL stored for the article is `https://knowledge.catonetworks.com/docs/<slug>` with the `.md` suffix removed.

The manifest in that directory records `crawled_at`, `user_agent`, `rate_limit_seconds`, `robots_decision`, `discovery_source` of `llms.txt`, one entry per saved article (slug, file path relative to the repo, title, public URL, site updated time), every skipped URL and its reason, and every failed URL. Article hashes are added in Task 5, so these entries have no `content_hash` yet.

**Files:**
- Create: `kbindex/crawl.py`
- Test: `tests/kbindex/test_crawled_article_has_text.py`
- Created by the crawl, and committed: `data/kb_ingestion/<YYYY-MM-DDTHHMMSSZ>/<slug>.md` and `manifest.json`

**Function:**
- `crawl(snapshot_root, fetch, sleep, now) -> path` writes one new directory under `snapshot_root` and returns that path. The directory name comes from `now()` in UTC, formatted `YYYY-MM-DDTHHMMSSZ`. `fetch(url) -> (status, body_bytes)`. `sleep(seconds)` waits between requests. The command `python -m kbindex.crawl` uses httpx, `time.sleep`, and the current UTC time, with `snapshot_root` of `data/kb_ingestion`. Comment: `Fetch the English knowledge-base articles and write one timestamped directory of raw markdown.`

- [ ] **Step 1: Write the failing test**

`test_crawled_article_has_text` opens the newest directory under `data/kb_ingestion/`. It reads `manifest.json` and one saved `<slug>.md`. The file's text is non-empty. The manifest public URL for that slug has no `.md`. No saved relative path contains `/docs/fr/` or a language index.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_crawled_article_has_text.py -v`

Expected: fail because `data/kb_ingestion/` has no crawl directory.

- [ ] **Step 3: Crawl**

Implement `crawl` and run `python -m kbindex.crawl`. Expect a new timestamp directory, a manifest whose `discovery_source` is `llms.txt`, and raw markdown files.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_crawled_article_has_text.py tests/kbindex/test_embed_and_rerank_prefer_the_relevant_passage.py -v`

Expected: the crawl test passes by reading the saved article. The model smoke test still passes.

- [ ] **Step 5: Commit**

Commit the crawler and the timestamp directory, including every saved article and the manifest.

Commit message: `Save the English knowledge-base crawl.`

---
