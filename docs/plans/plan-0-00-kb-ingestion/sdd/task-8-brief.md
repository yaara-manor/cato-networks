### Task 8: Startup checks

This task checks that the filled database still matches the files on disk and the embedding model that built the vectors. It does not crawl, and it does not embed the articles again. `python -m kbindex.startup` runs the checks and exits 0 only when all of them pass. A failure raises before any later caller can answer from this database.

`run_startup` does three checks, in this order:

1. Read the six files in `data/policies/` again and `upsert_policies`, so a policy edit on disk is loaded before the hash check.
2. `verify_hashes` reads every `kb_articles.file_path` and every `policies.file_path`, computes `sha256_file` of those bytes, and compares it to the stored `content_hash`. One mismatch raises `HashMismatch` and startup stops. The test covers that path by passing a reader that returns one different byte, so the saved crawl is not edited.
3. `probe_width` embeds the fixed string `width-check` with the pinned bge-small model and returns how many numbers came back. `run_startup` compares that length to `snapshots.embedding_dimensions`. The expected length is 384. A different length raises `StartupError`. The individual numbers in the probe vector are not compared.

The real model must return 384, and that 384 must equal the snapshot row written in Task 7.

**Files:**
- Create: `kbindex/startup.py`
- Modify: `kbindex/embed.py`
- Modify: `kbindex/store.py`
- Test: `tests/kbindex/test_startup_rejects_a_hash_or_width_mismatch.py`

**Functions:**
- `verify_hashes(connection, read_file)` hashes each `kb_articles.file_path` and each `policies.file_path` with `sha256_file` and compares it to `content_hash`. Comment: `Raise HashMismatch when a stored hash differs from the file at file_path.` `read_file` is the normal file read, except the test passes a reader that returns different bytes.
- `probe_width(embed) -> int` embeds the fixed string `width-check` and returns the vector length. Comment: `Embed the fixed string width-check and return the vector length.` The probe's numeric values are not compared.
- `run_startup(connection, embed, policies_dir)` calls `upsert_policies` on the six files, then `verify_hashes`, then checks `probe_width` equals `snapshots.embedding_dimensions`. Comment: `Reload policies, check file hashes, check the embedding width, and stop on a mismatch.` A hash failure raises `HashMismatch`. A width failure raises `StartupError`. The command `python -m kbindex.startup` calls this and exits 0 when both checks pass.

- [ ] **Step 1: Write the failing test**

`test_startup_rejects_a_hash_or_width_mismatch` calls `run_startup` against the filled database and expects success. It calls `verify_hashes` with a reader that changes one byte and expects `HashMismatch`. It calls the width check with a stand-in embedder that returns a vector whose length is not 384 and expects `StartupError`. The real `probe_width(load_embedder())` equals 384 and equals the snapshot row.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_startup_rejects_a_hash_or_width_mismatch.py -v`

Expected: fail because `run_startup` is missing.

- [ ] **Step 3: Implement the checks**

Add `probe_width` to `embed.py`. Add `verify_hashes` to `store.py`. Add `run_startup`.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_startup_rejects_a_hash_or_width_mismatch.py -v`

Expected: pass. Also run `python -m kbindex.startup` and expect exit code 0.

- [ ] **Step 5: Commit**

Commit message: `Stop startup when a file hash or the embedding width is wrong.`

---
