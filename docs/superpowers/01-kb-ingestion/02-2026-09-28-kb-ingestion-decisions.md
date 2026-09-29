# Knowledge-base ingestion: decisions and why

Date: 2026-09-28

This is the decision record for the Cato support-engineer home task, from the first reading of the data bundle through the ingestion design and the implementation plan. A new session should treat three files as the source of truth, in this order:

1. This file, for why a choice was made and what was rejected.
2. `docs/superpowers/specs/2026-09-28-kb-ingestion-design.md`, for the behavior the system must have.
3. `docs/superpowers/plans/2026-09-28-kb-ingestion.md`, for the task order, tests, and file layout.

The spec and the plan were edited after the first commit. The assignment brief still says `data/sla_policy.md`. That path is stale. The file now lives at `data/policies/POL-SLA.md`.

## What this work is for

The assignment is a conversational support engineer. A customer chats. The agent identifies them from account data, looks at synthetic telemetry through tools, answers technical questions from Cato's public knowledge base with citations, and follows internal policies for credits, escalation, identity, credentials, security verdicts, and SLA. High-impact actions wait for a human. The interview is a live demo.

"Deflect" in the brief means closing the chat so a human never takes it. That is not the goal. Some conversations stay with the agent. A Sev-1 is paged to a human. A credit or an MFA reset waits for approval. A vague complaint gets scoping questions first.

Sev-1, from `POL-SEV1`, is a complete loss of connectivity for an account, two or more sites down in the same region, a suspected PoP-side outage, or a confirmed security incident. In the SLA table that is P1: 15 minutes to first response, 24×7, both tiers, and a 4-hour resolution target. A human incident commander is mandatory.

CMA is the Cato Management Application. The files under `data/telemetry/` are synthetic CMA-style data. The agent must reach them through tools. Timestamps are frozen at `2026-08-28T17:00:00Z`. Telemetry tools are not part of this ingestion design.

This three-day slice stops at ingestion and retrieval. Agents, orchestration, the chat UI, approvals, ticket storage, and telemetry tools are the next design. They must consume the contracts below. They must not re-open these choices unless a measured eval shows one of them is the bottleneck.

## The retrieval idea

The agent never reads the knowledge base in one pass. About 1,500 English articles would not fit in a prompt, and a citation has to point at a specific article and section.

At question time the system retrieves a few short passages. Each passage still carries the slug, the public URL, and the heading it came from. That is the relationship between the live site and the stored data. A reply cites the slug plus the heading. The public link is the URL plus `#` plus the heading anchor.

Internal rules are not retrieved that way. A credit request loads `POL-CREDIT`. An MFA reset loads `POL-IDV`. A full outage loads `POL-SEV1`. A pasted secret loads `POL-CRED`. A verdict override loads `POL-SEC`. An SLA statement loads `POL-SLA`. The document is loaded whole and followed. There are six short files, so search would only add a way to miss the rule or to mix it into a technical answer.

Where the public knowledge base and a policy disagree, the knowledge base wins on product behavior and the policy wins on what support is allowed to do. Separate tables make that split real.

## Crawl and the pinned snapshot

### Discover articles from the English `llms.txt`

`robots.txt` allows all crawlers and names a sitemap. That sitemap returned an error when it was fetched during design, so it is not the discovery source. The site itself tells readers to start at `https://knowledge.catonetworks.com/llms.txt`, a markdown list of about 1,470 English articles, each linked as `https://knowledge.catonetworks.com/docs/<slug>.md`.

Language-specific indexes exist. French is `https://knowledge.catonetworks.com/fr/llms.txt`, and those articles are at `https://knowledge.catonetworks.com/docs/fr/<slug>.md`. The brief says to exclude non-English articles. The filter is a path rule, applied before the request:

- Keep only `https://knowledge.catonetworks.com/docs/<slug>.md` where the slug contains no slash.
- Drop `/docs/fr/<slug>.md` and any `/{language}/llms.txt`.
- Keep `viewing-translated-knowledge-base-articles`, because that page is English and its path has no language segment.

Index pages that are mostly links stay. They are real public articles with slugs. A heuristic that drops "link-only" pages would also drop short real articles.

The crawler fetches `robots.txt` first and skips disallowed paths. It identifies itself as `CatoHomeTaskBot/1.0 (educational assignment)` and waits at least one second between requests. Image binaries are not downloaded. Facts that exist only in images will be missing. That is an accepted gap.

### Save the raw response, and hash those bytes

Each article file is the response body, unchanged. The content hash is SHA-256 of those bytes. Parsing does not rewrite the file. The repeated "Documentation Index" banner at the top of the markdown is removed only when passage text is built. If the hash covered cleaned text, a reviewer could not tell it was the page that was fetched.

The citation URL stored on the article is `https://knowledge.catonetworks.com/docs/<slug>` with no `.md`, because that is the form the eval files use. `site_updated_at` comes from the article's own `updated` field. When the field is missing it is null. The crawl date is a different value and is never copied into `site_updated_at`. `answers.md` prints the crawl date from the snapshot.

Failed fetches are listed in the manifest and omitted. The crawl does not invent a body. Skips record a reason: language, robots, or not an article.

### Layout

| Path | What it is |
|---|---|
| `data/kb_ingestion/<YYYY-MM-DDTHHMMSSZ>/<slug>.md` | Raw article bytes for one crawl. |
| `data/kb_ingestion/<YYYY-MM-DDTHHMMSSZ>/manifest.json` | Crawl date, user agent, rate limit, robots decision, discovery source `llms.txt`, per-article slug, path, hash, title, public URL, site updated time, plus every skip and failure. |
| `data/kb_ingestion/<YYYY-MM-DDTHHMMSSZ>/passages.jsonl` | Passage records chunked from that crawl. Written after the article files exist. |
| `kb/postgres/kb.dump` | Custom-format Postgres dump. It sits outside the snapshot and is documented as an addition. |
| `data/policies/POL-*.md` | The six policy files. Not crawled. |

Change-detecting re-crawls are a bonus in the brief, not the required path. The required path is one polite crawl, a pinned snapshot, and a dump. An unchanged article hash does let a later rebuild skip that article's passages. That check is in the loader because it is cheap. It is not a second product feature.

## Policies

`data/sla_policy.md` was moved to `data/policies/POL-SLA.md` and is cited as `POL-SLA`. It is a rule the agent must follow, same as the other five. Leaving it in a one-off path would have forced a second loader.

Policy rows store the id, the title (the first heading), the file hash, the repo-relative `file_path`, and the full body. They have no embedding and no snapshot row. Startup reads the six files and upserts them. The agent reads `body` from Postgres.

`file_path` is also on knowledge-base articles. The path is not only a function of the id: policies, the snapshot, and the dump live in different directories, and the brief allows extra files if they are separated and documented. The column is how the loader finds the bytes it hashes. The agent does not open the file while answering.

## Postgres, and why not a vector-only product

The passage vectors are tens of megabytes. A file of vectors would hold them. Postgres is the store because the rest of the system already needs a database: conversations, tool results, and approvals must survive a restart. Passage rows live in that same database, with the text, the slug, the heading, the hash, a full-text column, and a `vector(384)` column. One backup, and a changed article is an upsert of that slug's rows.

A separate vector-database server would be a second service for the same job. `pgvector` is the vector store.

The dump is what gets committed, not a live Postgres data directory. A data directory is tied to one machine and one Postgres version. `docker compose up` restores `kb/postgres/kb.dump`. The reviewer does not crawl and does not embed the corpus.

Startup then hashes every article file and every policy file and compares them to the rows. A mismatch stops the process before it answers. An embedding-width mismatch does the same. When retrieval or the model fails to load, this component returns an error. It does not answer a technical question from memory. The later agent design decides what the customer is told.

### Tables

`snapshots` has one row per pinned build: crawl time, embedding model name, vector width, reranker model name. `kb_articles.slug` is the primary key, so the database holds the current build, not a history of every crawl. History is the committed snapshot files.

`kb_articles` holds slug, snapshot id, title, public URL, site updated time, content hash, and file path.

`passages` holds article slug, heading, heading anchor, position, body, content hash, a `simple` full-text vector, and the embedding. The unique key is `(article_slug, position)`. Position distinguishes slices that share a heading.

`policies` holds id, title, content hash, file path, and body.

### Exact cosine scan, not HNSW

Nearest-neighbor search scans every embedding and sorts by cosine distance. There is no HNSW index.

HNSW is an approximate index for hundreds of thousands of vectors and up. This corpus is about 1,500 articles and a few thousand passages. The scan is a few milliseconds. HNSW would spend build time and memory to approximate that scan, and it can skip the true nearest passage. That miss matters more than the time saved.

Keyword search still has a GIN index, because full-text search is a different structure. The text configuration is `simple`, so tokens such as `IKEv2` and `DTLS` are not stemmed away.

## Chunking

Passages follow the article's headings so a citation can name a section. Every markdown heading can start a passage. Text before the first heading becomes a passage whose heading is the article title. A heading with no body produces no passage. Index pages are chunked by the same rules.

`bge-small-en-v1.5` reads at most 512 tokens. The reranker has the same ceiling and spends it on the question and the passage together. A slice cut at 512 would lose its tail once the question is attached. The stored passage is therefore capped at 400 tokens, counted by the embedding model's tokenizer.

Most sections are shorter than that and stay one passage, with no copied text. When a section is longer, each slice after the first holds at most 350 new tokens plus at most 50 tokens copied from the tail of the previous slice of the same section. The copy is whole sentences (a `.`, `?`, or `!` followed by whitespace). The first slice has no copied prefix and may use the full 400. Every slice keeps that section's heading and anchor. Text is never copied across headings, because the citation would name the wrong section. If a single sentence exceeds the cap, it is hard-cut until it fits.

Overlap is still a normal RAG practice when a fixed window would cut a sentence in half. It is used only for that case. Fifty tokens is enough to repeat the boundary sentence and still leave room for the question inside the reranker's 512-token budget.

`heading_anchor` is the heading in lowercase, spaces turned into hyphens, punctuation removed. If two headings in one article produce the same anchor, the later one appends `-` and its position.

Passage hash is SHA-256 of the body. Article hash is SHA-256 of the raw file. A rebuild that sees the same article hash leaves that article's passages in place.

## How a question becomes five passages

1. Keyword search returns the top 20 passages.
2. Exact cosine search returns the top 20 passages.
3. Reciprocal rank fusion merges the two lists.
4. The local cross-encoder scores the question beside each remaining passage.
5. At most five passages at or above `RERANK_MIN_SCORE` are returned, with slug, heading, anchor, public URL, fusion score, and rerank score.

Scores are not stored on the passage row. The caller stores them on the conversation trace. `answers.md` needs the snapshot date, the citations, and those scores. That report is a later deliverable. This component's job is to return the fields.

Below the threshold, retrieval returns no passages. The caller refuses instead of guessing. The shipped threshold is the lowest value that still returns nothing for this question from the ticket bundle:

> Our network architect is asking whether Cato supports IPv6-only branch sites and what's on the roadmap next year. Can you share dates?

That number does not exist until the snapshot has been embedded. This ingestion plan does not set it. A later retrieval plan measures it and writes it into config. One question is a rough yardstick. The eval report records the value. If later questions show the cutoff is too harsh or too loose, changing it is a config edit, not a new crawl.

### Why fusion uses ranks and the constant 60

Keyword scores and cosine distances are not on the same scale, so they are not added. Fusion uses place in each list. Rank 1 is the top hit. A passage's score is the sum, over each list it appears in, of `1 / (60 + rank)`. A passage in only one list gets one term.

60 is the constant from the original reciprocal-rank-fusion method. It was not tuned on Cato articles. The answer keys are held by the reviewers, so there is no labeled set to fit another constant against. With 60, rank 1 scores about 0.0164 and rank 20 scores 0.0125. Being first on one list is only a little better than being twentieth. Appearing in both lists is what moves a passage up. A small constant such as 1 would let a single list's first hit crowd out a passage both lists agree on.

The fused order is only the candidate list. The cross-encoder produces the scores that decide the top five.

### The query prefix

Passages are embedded as their own words. A question is embedded as `Represent this sentence for searching relevant passages: ` plus the question. That prefix is the instruction `bge-small-en-v1.5` was trained to see on queries. It is not part of the customer's message and it is not stored. Every query uses it, including the 35 eval questions. A question embedded without it sits in a different part of the vector space than the index was built for.

Startup embeds the fixed string `width-check`, checks that the vector length is 384, and checks that this matches `snapshots.embedding_dimensions`. The probe's numeric values are not compared. A mismatch stops startup.

## Models

Both models are local. The chat model that writes the answer stays on an API. That split is deliberate.

A question has to be embedded with the same model that embedded the passages. The dump removes the bulk job. It does not remove the one query embedding, or the rerank of the short list. An API embedding or rerank model would add a key to every chat, every eval run, and the reviewer's demo. The demo should need a key only for the chat model.

The machine this was designed on has no GPU. It is an Intel Core Ultra 9 185H, 16 cores, 30 GB of RAM. A local chat model would be slow here. A small cross-encoder scoring a few dozen passages is not. Published laptop-CPU rates put MiniLM-L12 well under a second for a list of 20. The chat reply takes longer than that.

Weights are not committed to git. The Docker build downloads pinned revisions and bakes them into the image. The running container sets Hugging Face offline. A reviewer does not download them again at chat time, and does not debug a failed fetch in the middle of the demo.

| Role | Model | Pinned revision | Why this one |
|---|---|---|---|
| Embedding | `BAAI/bge-small-en-v1.5` | `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` | English, 33M parameters, about 133 MB, 384 dimensions. MTEB retrieval 51.68. |
| Reranker | `cross-encoder/ms-marco-MiniLM-L12-v2` | `7b0235231ca2674cb8ca8f022859a6eba2b1c968` | About 33M parameters and 120 MB. The spec name `ms-marco-MiniLM-L-12-v2` is this repo. Scores a question and a passage together and returns one number. |

### Embedding alternatives that were set aside

The "retrieval score" in the model card is nDCG@10 averaged over 15 hard public datasets, written as a number out of 100. It is not the percent of Cato questions the system will get right. Rank 1 on a question scores 100. Rank 2 scores about 63. Missing the top 10 scores 0. Leaders on that column have long sat in the mid-50s to low-60s. The number that describes this system is recall@k and MRR on the 35 Cato questions, measured after the crawl.

| Model | What we saw | Why it lost |
|---|---|---|
| `bge-base-en-v1.5` | 109M, 438 MB, 768 dimensions, retrieval 53.25 | About 1.6 points over small, for more than three times the download. The keyword index and the reranker move the top few passages more than that gap. |
| `bge-large-en-v1.5` | 335M, 1.34 GB, 1024 dimensions, retrieval 54.29 | One query would still be a few hundred milliseconds on this CPU, because only the question is embedded at chat time. The install is the problem. A 1.34 GB weight file, plus PyTorch, can use up the reviewer's 10 minutes, and a failed download looks like a broken clone. |
| `text-embedding-3-small` | OpenAI overall MTEB 62.3 | Same band as `bge-small` overall (62.17). Every question would call the API. |
| `text-embedding-3-large` | OpenAI overall MTEB 64.6 | Same band as `bge-large` overall (64.23). Not a different league, and it adds a key and a per-question cost. |

`bge-small` was chosen after `bge-base` had been the quality pick. The 10-minute clone path overruled it. Vectors in the dump are built with the small model, so a reviewer never runs the index build.

### Reranker alternatives that were set aside

A reranker is not a chat model. A cross-encoder packs the question, a separator, and one passage into one forward pass and returns a relevance score. It runs only on the fused short list. It has no database of its own. Article updates do not touch it.

| Model | Why it lost |
|---|---|
| `ms-marco-MiniLM-L-6-v2` | Faster and smaller, weaker scores. Retrieval quality is graded, and L12 is still small enough. |
| `bge-reranker-base` | Stronger, about 1 GB, several times slower on a list of 20. Switch to it only if the eval shows the reranker is the weak stage. That is a manifest change and a rescore, not a new crawl. |
| Cohere Rerank, or an LLM asked to order the list | Extra key, extra cost, and the reviewer's run depends on that vendor. |

## How a reviewer runs it

The brief requires a clone to reach a working chat in under 10 minutes, with the knowledge base already in the repo, and no crawl. For this subsystem the runnable check is:

1. `docker compose up` starts Postgres 18 with pgvector, image `pgvector/pgvector:0.8.6-pg18`. The data volume is `/var/lib/postgresql`. The dump is taken on that same major version, because nothing had been dumped when 18 was chosen.
2. The entrypoint restores `kb/postgres/kb.dump` when the file exists.
3. `python -m kbindex.startup` reloads the six policies, checks every file hash, checks the embedding width, and exits 0.

If the dump is missing, startup exits with a message that the operator must build it. Building is not the reviewer's job.

The operator path, once, on the machine that crawls:

1. `python -m kbindex.crawl` writes `data/kb_ingestion/<timestamp>/`.
2. Chunking writes `passages.jsonl` in that directory, then `python -m kbindex.build` embeds, loads Postgres, and writes the dump.

The dev cache downloads both pinned revisions once, after the first failing model test, so the smoke test and the chunk token counts use the real models. The image build downloads the same revisions into the image. The crawl command hits the live site once. Later tests read the saved files. They do not crawl again. Database tests use the compose Postgres.

## Implementation shape

Python 3.12 package `kbindex`. This plan's tasks are: package and models, empty database, crawl, URL discovery, hashing, chunking, fill, startup, image and dump. Fusion, search, and the refusal threshold are a later retrieval plan. Tests are written first, watched failing, then made to pass. Cleanup is left for a later pass.

Stack that is already chosen, so it should not be re-litigated during implementation: pytest, httpx, psycopg, pgvector, sentence-transformers, `pgvector/pgvector:0.8.6-pg18`.

## Accepted gaps

- Image-only facts are absent.
- Translated articles are absent on purpose.
- The sitemap was down during design. If it recovers, discovery stays on the English `llms.txt` so the snapshot remains reproducible.
- The refusal threshold is fit to one out-of-coverage question. The eval report is where that choice is shown to be good or bad.
- Fusion's constant 60 is the published default, not a Cato-specific fit.
- `bge-small` is a bit weaker than `bge-base` on the public retrieval benchmark. The install constraint won.
- This design does not yet say what the customer hears when Postgres or a model fails to load. It only requires that the failure is visible and that no technical answer is invented.

## What the next session should not rebuild

Do not put model weights in git. Do not add HNSW. Do not add a second vector database. Do not merge policies into `kb_articles`. Do not hash cleaned markdown. Do not crawl `/docs/fr/` or `/{language}/llms.txt`. Do not embed policy text. Do not prefix passage embeddings with the query instruction. Do not copy overlap across headings. Do not make the reviewer crawl or re-embed. Do not start the agent, the chat UI, or the approval gate inside this plan.
