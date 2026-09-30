import json
import uuid
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, NotRequired, TypedDict

import psycopg
from pgvector.psycopg import register_vector

from core.config import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    REPO_ROOT,
    RERANKER_MODEL,
)
from db.init.seed import apply_schema, seed_all
from encoders.embed import embed_passages
from kbindex.hashing import sha256_bytes, sha256_file


class Article(TypedDict):
    slug: str
    file_path: str
    title: str
    public_url: str
    content_hash: str
    site_updated_at: NotRequired[str | None]


class HashMismatch(Exception):
    pass


class StartupError(Exception):
    pass


def _insert_passages(
    cursor: psycopg.Cursor,
    article_slug: str,
    passages: list[dict[str, Any]],
) -> None:
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


def upsert_article(
    connection: psycopg.Connection,
    snapshot_id: uuid.UUID,
    article: Article,
    passages: list[dict[str, Any]],
) -> None:
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
        else:
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
            if row[0] != article["content_hash"]:
                cursor.execute("delete from passages where article_slug = %s", (article["slug"],))
                _insert_passages(cursor, article["slug"], passages)
    connection.commit()


def load_index(
    connection: psycopg.Connection,
    crawl_dir: Path | str,
    policies_dir: Path | str = REPO_ROOT / "data" / "policies",
    tickets_dir: Path | str = REPO_ROOT / "data" / "tickets",
) -> None:
    apply_schema(connection)
    register_vector(connection)
    crawl_dir = Path(crawl_dir)
    manifest = json.loads((crawl_dir / "manifest.json").read_text(encoding="utf-8"))
    crawled_at: str = manifest["crawled_at"]

    with connection.cursor() as cursor:
        cursor.execute("select id from snapshots where crawled_at = %s", (crawled_at,))
        row = cursor.fetchone()
        if row:
            snapshot_id: uuid.UUID = row[0]
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
    passages_by_slug: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    if passages_file.exists():
        with passages_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    p = json.loads(line)
                    passages_by_slug[p["slug"]].append(p)

    articles: list[Article] = manifest["articles"]
    total = len(articles)
    for idx, article in enumerate(articles, 1):
        slug: str = article["slug"]
        upsert_article(connection, snapshot_id, article, passages_by_slug[slug])
        if idx % 200 == 0 or idx == total:
            print(f"Loaded article {idx}/{total}: {slug}")

    seed_all(
        connection,
        policies_dir=policies_dir,
        tickets_dir=tickets_dir,
        preserve_existing_tickets=False,
    )


def verify_hashes(
    connection: psycopg.Connection,
    read_file: Callable[[Path], bytes | str] | None = None,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute("select file_path, content_hash from kb_articles order by slug")
        kb_articles: list[tuple[str, str]] = cursor.fetchall()
        cursor.execute("select file_path, content_hash from policies order by id")
        policies: list[tuple[str, str]] = cursor.fetchall()

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
