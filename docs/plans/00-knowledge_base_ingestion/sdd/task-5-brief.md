### Task 5: Hash the saved articles

This task hashes the raw article files and writes each digest onto that article's manifest entry. It does not fetch, and it does not rewrite the markdown.

`sha256_bytes` takes the response bytes and returns the SHA-256 digest as lowercase hex. `sha256_file` opens the saved `<slug>.md` in binary mode and passes those bytes to `sha256_bytes`. The hash covers the file as it was saved, including the documentation-index banner and the front matter. It does not cover a cleaned or re-encoded copy. If it did, a reviewer could not tell that the file is the page that was fetched.

`write_manifest_hashes` opens the newest crawl's `manifest.json`, and for each article entry sets `content_hash` to `sha256_file` of that entry's `file_path`. Skipped and failed URLs get no hash and no file. The test checks every saved article, then appends one byte to a temporary copy of one file and checks that the new digest differs. The saved file stays as it was.

**Files:**
- Create: `kbindex/hashing.py`
- Modify: the newest `data/kb_ingestion/<timestamp>/manifest.json`
- Test: `tests/kbindex/test_manifest_hash_matches_file.py`

**Functions:**
- `sha256_bytes(data) -> str` hashes a byte string. Comment: `Return the lowercase hex SHA-256 of these bytes.`
- `sha256_file(path) -> str` reads the file in binary mode and hashes those bytes. Comment: `Return the lowercase hex SHA-256 of a file's raw bytes.`
- `write_manifest_hashes(crawl_dir)` sets `content_hash` on every article entry in `manifest.json` from `sha256_file` of that entry's file. Comment: `Store each saved article's SHA-256 on its manifest entry.`

- [ ] **Step 1: Write the failing test**

`test_manifest_hash_matches_file` reads the newest crawl. For every article entry, `sha256_file` of the saved markdown equals `content_hash`. It also hashes a temporary copy of one file after appending one byte, and that digest differs from the manifest hash. The saved file is left unchanged.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_manifest_hash_matches_file.py -v`

Expected: fail because `content_hash` is missing.

- [ ] **Step 3: Write the hashes**

Implement the three functions. Run `write_manifest_hashes` on the Task 3 directory.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_manifest_hash_matches_file.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit the hashing module and the updated manifest.

Commit message: `Hash each saved article with SHA-256.`

---
