import os

import psycopg


def test_tables_are_readable() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for table in ("snapshots", "kb_articles", "passages", "policies", "accounts", "tickets"):
            row = connection.execute(f"select count(*) from {table}").fetchone()
            assert row is not None
            assert row[0] >= 0

