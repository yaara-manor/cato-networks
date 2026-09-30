### Task 4: URL discovery

This task moves the URL rules out of the body of `crawl` into three functions in `discover.py`. The saved crawl does not change, and the live site is not fetched again. After this task, `crawl` calls these functions for the same decisions it already made inline.

`parse_llms_links` reads the `llms.txt` markdown and returns every link target, the URL inside each `](url)`. It does not fetch.

`classify_url` looks only at the URL string. It returns `keep` for `https://knowledge.catonetworks.com/docs/<slug>.md` when the slug has no slash, including `viewing-translated-knowledge-base-articles`. It returns `skip_language` for `/docs/fr/<slug>.md`, for any other `/docs/<language>/<slug>.md`, and for `/fr/llms.txt` or any `/<language>/llms.txt`. It returns `skip_not_article` for every remaining URL. It does not fetch.

`robots_allows` parses the robots text with `urllib.robotparser` and returns whether `CatoHomeTaskBot/1.0 (educational assignment)` may fetch that URL. A false result is the `robots` skip. It does not fetch.

`crawl` then uses them in this order: parse the English `llms.txt` body, `classify_url` on each link, and `robots_allows` on the ones classified `keep`. Only a `keep` that robots allows is passed to `fetch`. The inline copies of these rules are deleted in this same task.

**Files:**
- Create: `kbindex/discover.py`
- Modify: `kbindex/crawl.py`
- Test: `tests/kbindex/test_saved_articles_are_english_docs.py`

**Functions:**
- `classify_url(url) -> str` returns `keep`, `skip_language`, or `skip_not_article`. Comment: `Decide whether a URL is an English article, a translation, or something else.` `keep` is only `https://knowledge.catonetworks.com/docs/<slug>.md` with a single slug segment. `skip_language` is a `/{language}/llms.txt` index or a `/docs/<language>/<slug>.md` path. Everything else is `skip_not_article`.
- `parse_llms_links(markdown) -> list[str]` returns the markdown link targets. Comment: `Collect the markdown link targets from an llms.txt page.` Use a standard-library pattern for `](url)`.
- `robots_allows(robots_text, url, user_agent) -> bool` uses `urllib.robotparser`. Comment: `Return whether robots.txt allows this user agent to fetch this URL.`

- [ ] **Step 1: Write the failing test**

`test_saved_articles_are_english_docs` reads the newest crawl. Every saved file's manifest URL classifies as `keep`. Every skipped URL classifies as `skip_language` or `skip_not_article`, or the manifest reason is `robots` and `robots_allows` is false for the saved robots text. No saved file's path has a slash in the slug.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_saved_articles_are_english_docs.py -v`

Expected: fail because `classify_url` is missing.

- [ ] **Step 3: Move the filter into `discover.py`**

Implement the three functions. Change `crawl` so it calls them and deletes the inline copies of the same rules. Do not crawl again.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_saved_articles_are_english_docs.py tests/kbindex/test_crawled_article_has_text.py -v`

Expected: both pass against the directory saved in Task 3.

- [ ] **Step 5: Commit**

Commit message: `Classify knowledge-base URLs before they are fetched.`

---
