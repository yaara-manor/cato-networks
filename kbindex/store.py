from collections import defaultdict
import json
from pathlib import Path
import uuid

from pgvector.psycopg import register_vector
from psycopg import ClientCursor

from kbindex.config import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    REPO_ROOT,
    RERANKER_MODEL,
)
from kbindex.embed import embed_passages
from kbindex.hashing import sha256_bytes, sha256_file
from kbindex.policies import load_policies


class HashMismatch(Exception):
    pass


class StartupError(Exception):
    pass


def apply_schema(connection):
    """Create the four knowledge-base tables when they are missing."""
    with ClientCursor(connection) as cursor:
        cursor.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    connection.commit()


def upsert_policies(connection, policies):
    # Insert or replace each policy row from its file record.
    query = """
    insert into policies (id, title, content_hash, file_path, body)
    values (%s, %s, %s, %s, %s)
    on conflict (id) do update set
        title = excluded.title,
        content_hash = excluded.content_hash,
        file_path = excluded.file_path,
        body = excluded.body
    """
    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            [
                (p["id"], p["title"], p["content_hash"], p["file_path"], p["body"])
                for p in policies
            ],
        )
    connection.commit()


def _insert_passages(cursor, article_slug, passages):
    if not passages:
        return
    to_embed = [p for p in passages if "embedding" not in p]
    if to_embed:
        embeddings = embed_passages([p["body"] for p in to_embed])
        for p, vec in zip(to_embed, embeddings):
            p["embedding"] = vec

    rows = []
    for p in passages:
        p_id = p.get("id") or uuid.uuid4()
        chash = p.get("content_hash") or sha256_bytes(p["body"].encode("utf-8"))
        rows.append((
            p_id,
            article_slug,
            p["heading"],
            p["heading_anchor"],
            p["position"],
            p["body"],
            chash,
            p["embedding"],
        ))

    cursor.executemany(
        """
        insert into passages (id, article_slug, heading, heading_anchor, position, body, content_hash, embedding)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )


def upsert_article(connection, snapshot_id, article, passages):
    # Replace an article's passages only when its content hash changes.
    file_path = article.get("file_path", "")
    try:
        file_path = Path(file_path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pass

    with connection.cursor() as cursor:
        cursor.execute("select content_hash from kb_articles where slug = %s", (article["slug"],))
        row = cursor.fetchone()

        if row is None:
            cursor.execute(
                """
                insert into kb_articles (slug, snapshot_id, title, public_url, site_updated_at, content_hash, file_path)
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    article["slug"],
                    snapshot_id,
                    article["title"],
                    article["public_url"],
                    article.get("site_updated_at"),
                    article["content_hash"],
                    file_path,
                ),
            )
            _insert_passages(cursor, article["slug"], passages)
        elif row[0] != article["content_hash"]:
            cursor.execute(
                """
                update kb_articles
                set snapshot_id = %s,
                    title = %s,
                    public_url = %s,
                    site_updated_at = %s,
                    content_hash = %s,
                    file_path = %s
                where slug = %s
                """,
                (
                    snapshot_id,
                    article["title"],
                    article["public_url"],
                    article.get("site_updated_at"),
                    article["content_hash"],
                    file_path,
                    article["slug"],
                ),
            )
            cursor.execute("delete from passages where article_slug = %s", (article["slug"],))
            _insert_passages(cursor, article["slug"], passages)
        else:
            cursor.execute(
                """
                update kb_articles
                set snapshot_id = %s,
                    title = %s,
                    public_url = %s,
                    site_updated_at = %s,
                    file_path = %s
                where slug = %s
                """,
                (
                    snapshot_id,
                    article["title"],
                    article["public_url"],
                    article.get("site_updated_at"),
                    file_path,
                    article["slug"],
                ),
            )
    connection.commit()


def load_index(connection, crawl_dir, policies_dir):
    # Insert the snapshot, the articles, the embedded passages, and the policies.
    apply_schema(connection)
    register_vector(connection)
    crawl_dir = Path(crawl_dir)
    policies_dir = Path(policies_dir)
    manifest = json.loads((crawl_dir / "manifest.json").read_text(encoding="utf-8"))
    crawled_at = manifest["crawled_at"]

    with connection.cursor() as cursor:
        cursor.execute("select id from snapshots where crawled_at = %s", (crawled_at,))
        row = cursor.fetchone()
        if row:
            snapshot_id = row[0]
        else:
            snapshot_id = uuid.uuid4()
            cursor.execute(
                """
                insert into snapshots (id, crawled_at, embedding_model, embedding_dimensions, reranker_model)
                values (%s, %s, %s, %s, %s)
                """,
                (snapshot_id, crawled_at, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, RERANKER_MODEL),
            )
    connection.commit()

    passages_file = crawl_dir / "passages.jsonl"
    passages_by_slug = defaultdict(list)
    if passages_file.exists():
        with passages_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    p = json.loads(line)
                    passages_by_slug[p["slug"]].append(p)

    articles = manifest["articles"]
    total = len(articles)
    for idx, article in enumerate(articles, 1):
        slug = article["slug"]
        upsert_article(connection, snapshot_id, article, passages_by_slug[slug])
        if idx % 200 == 0 or idx == total:
            print(f"Loaded article {idx}/{total}: {slug}")

    policies = load_policies(policies_dir)
    upsert_policies(connection, policies)
    connection.commit()


def verify_hashes(connection, read_file=None):
    # Raise HashMismatch when a stored hash differs from the file at file_path.
    with connection.cursor() as cursor:
        cursor.execute("select file_path, content_hash from kb_articles order by slug")
        kb_articles = cursor.fetchall()
        cursor.execute("select file_path, content_hash from policies order by id")
        policies = cursor.fetchall()

    for file_path, stored_hash in kb_articles + policies:
        path = REPO_ROOT / file_path if not Path(file_path).is_absolute() else Path(file_path)
        if read_file is None:
            actual_hash = sha256_file(path)
        else:
            raw = read_file(path)
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            actual_hash = sha256_bytes(raw)

        if actual_hash != stored_hash:
            raise HashMismatch(
                f"Hash mismatch for {file_path}: expected {stored_hash}, got {actual_hash}"
            )
