import json
import os
from pathlib import Path

from pgvector.psycopg import register_vector
import psycopg

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "kb_ingestion"
POLICIES_DIR = REPO / "data" / "policies"

EXPECTED_POLICY_IDS = {
    "POL-CRED",
    "POL-CREDIT",
    "POL-IDV",
    "POL-SEC",
    "POL-SEV1",
    "POL-SLA",
}


def test_database_holds_the_crawl_and_policies():
    crawl_dir = sorted(path for path in ROOT.iterdir() if path.is_dir())[-1]
    manifest = json.loads((crawl_dir / "manifest.json").read_text(encoding="utf-8"))

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        register_vector(connection)

        snapshots = connection.execute(
            "select id, crawled_at, embedding_model, embedding_dimensions, reranker_model from snapshots"
        ).fetchall()
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot[1].isoformat().replace("+00:00", "Z") == manifest["crawled_at"]
        assert snapshot[2] == "BAAI/bge-small-en-v1.5"
        assert snapshot[3] == 384
        assert snapshot[4] == "cross-encoder/ms-marco-MiniLM-L12-v2"

        articles = connection.execute(
            "select slug, title, public_url, site_updated_at, content_hash, file_path from kb_articles"
        ).fetchall()
        assert len(articles) == len(manifest["articles"])
        articles_by_slug = {row[0]: row for row in articles}

        for manifest_article in manifest["articles"]:
            slug = manifest_article["slug"]
            assert slug in articles_by_slug
            row = articles_by_slug[slug]
            assert row[4] == manifest_article["content_hash"]
            if manifest_article["site_updated_at"] is None:
                assert row[3] is None
            else:
                assert row[3].isoformat().replace("+00:00", "Z") == manifest_article["site_updated_at"]

        passages_file = crawl_dir / "passages.jsonl"
        with passages_file.open(encoding="utf-8") as f:
            first_line = json.loads(f.readline())
            sample_slug = first_line["slug"]

        with passages_file.open(encoding="utf-8") as f:
            expected_bodies = [
                json.loads(line)["body"]
                for line in f
                if json.loads(line)["slug"] == sample_slug
            ]

        passage_rows = connection.execute(
            "select body, embedding from passages where article_slug = %s order by position",
            (sample_slug,),
        ).fetchall()
        assert len(passage_rows) == len(expected_bodies)
        assert [r[0] for r in passage_rows] == expected_bodies
        sample_embedding = passage_rows[0][1]
        numbers = sample_embedding.to_list() if hasattr(sample_embedding, "to_list") else sample_embedding
        assert len(numbers) == 384

        policies = connection.execute("select id, body from policies").fetchall()
        assert len(policies) == 6
        policy_dict = {p[0]: p[1] for p in policies}
        assert set(policy_dict.keys()) == EXPECTED_POLICY_IDS
        sla_file = POLICIES_DIR / "POL-SLA.md"
        assert policy_dict["POL-SLA"] == sla_file.read_text(encoding="utf-8")
