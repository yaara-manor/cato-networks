import os

import psycopg


def test_tables_are_readable():
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for table in ("snapshots", "kb_articles", "passages", "policies"):
            (count,) = connection.execute(f"select count(*) from {table}").fetchone()
            assert count == 0
