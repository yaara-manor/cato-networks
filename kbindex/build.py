import os
from pathlib import Path

import psycopg

from kbindex.store import load_index

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data" / "kb_ingestion"
POLICIES_DIR = REPO / "data" / "policies"


def newest_crawl_dir() -> Path:
    if not ROOT.exists():
        raise RuntimeError(f"No crawl directory found under {ROOT}")
    dirs = sorted(p for p in ROOT.iterdir() if p.is_dir())
    if not dirs:
        raise RuntimeError(f"No crawl directory found under {ROOT}")
    return dirs[-1]


def build():
    crawl_dir = newest_crawl_dir()
    db_url = os.environ.get("DATABASE_URL", "postgresql://kb:kb@localhost:5432/kb")
    with psycopg.connect(db_url) as connection:
        load_index(connection, crawl_dir, POLICIES_DIR)


if __name__ == "__main__":
    build()
