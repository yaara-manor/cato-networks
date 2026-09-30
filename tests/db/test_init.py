import os
import subprocess
from urllib.parse import urlparse

import psycopg

from core.config import REPO_ROOT
from db.init.seed import apply_schema, load_accounts_seed, load_tickets_seed, seed_all
from db.init.startup import run_startup


def _search_vector_expression(connection: psycopg.Connection) -> str:
    row = connection.execute(
        """
        select pg_get_expr(adbin, adrelid)
        from pg_attrdef
        join pg_attribute
            on pg_attribute.attrelid = pg_attrdef.adrelid
            and pg_attribute.attnum = pg_attrdef.adnum
        where pg_attrdef.adrelid = 'passages'::regclass
            and pg_attribute.attname = 'search_vector'
        """
    ).fetchone()
    assert row is not None
    return row[0]


def test_seed_accounts_and_tickets_and_startup_preserves_live_status() -> None:
    accounts = load_accounts_seed()
    assert len(accounts) == 12
    acc_by_id = {a["customer_id"]: a for a in accounts}
    assert acc_by_id["ACC-1001"]["country"] == "NL"
    assert all(a["country"] is not None for a in accounts)

    tickets = load_tickets_seed()
    assert len(tickets) == 54
    tck_by_id = {t["ticket_id"]: t for t in tickets}
    assert tck_by_id["TCK-20264202"]["site_id"] is None
    assert tck_by_id["TCK-20264200"]["site_id"] == "S-1008-01"

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        seed_all(connection, preserve_existing_tickets=False)

        account_rows = connection.execute(
            "select customer_id, company, tier, email_domain, registered_admin_contact, country from accounts order by customer_id"
        ).fetchall()
        assert len(account_rows) == 12
        assert account_rows[0] == (
            "ACC-1001",
            "Northwind Logistics",
            "Premium",
            "northwind-logistics.com",
            "netops@northwind-logistics.com",
            "NL",
        )

        ticket_count_row = connection.execute("select count(*) from tickets").fetchone()
        assert ticket_count_row is not None and ticket_count_row[0] == 54

        # Mutate an open ticket to closed to simulate a live support session update
        connection.execute(
            "update tickets set status = 'closed' where ticket_id = 'TCK-20264202'"
        )
        connection.commit()

        # Startup runs with preserve_existing=True so live ticket status must not be overwritten
        run_startup(connection, embed=lambda texts: [[0.0] * 384 for _ in texts])
        status_row = connection.execute(
            "select status from tickets where ticket_id = 'TCK-20264202'"
        ).fetchone()
        assert status_row is not None and status_row[0] == "closed"

        # Restore original seed state via seed_all(preserve_existing_tickets=False)
        seed_all(connection, preserve_existing_tickets=False)
        restored_row = connection.execute(
            "select status from tickets where ticket_id = 'TCK-20264202'"
        ).fetchone()
        assert restored_row is not None and restored_row[0] == "open"


def test_seed_dump_contains_all_six_tables_and_restores_cleanly() -> None:
    dump_path = REPO_ROOT / "db" / "seed.dump"
    assert dump_path.exists()
    assert dump_path.stat().st_size > 0
    assert not (REPO_ROOT / "db" / "kb.dump").exists()

    db_url = os.environ["DATABASE_URL"]
    parsed = urlparse(db_url)
    user = parsed.username or "kb"
    password = parsed.password or "kb"
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)
    dbname = parsed.path.lstrip("/") or "kb"

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    # Restore db/seed.dump using pg_restore --clean --if-exists and verify all 6 tables & indexes exist
    restore_cmds = [
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            dbname,
            str(dump_path),
        ],
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "host",
            "-v",
            f"{REPO_ROOT}:/app",
            "-w",
            "/app",
            "-e",
            f"PGPASSWORD={password}",
            "pgvector/pgvector:0.8.6-pg18",
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            dbname,
            "db/seed.dump",
        ],
    ]

    restored = False
    for cmd in restore_cmds:
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if proc.returncode == 0:
                restored = True
                break
        except FileNotFoundError:
            continue

    assert restored, "Failed to restore db/seed.dump via pg_restore or docker fallback"

    with psycopg.connect(db_url) as connection:
        expected_counts = {
            "snapshots": 1,
            "policies": 6,
            "accounts": 12,
            "tickets": 54,
        }
        for table, expected in expected_counts.items():
            row = connection.execute(f"select count(*) from {table}").fetchone()
            assert row is not None and row[0] == expected

        for kb_table in ("kb_articles", "passages"):
            row = connection.execute(f"select count(*) from {kb_table}").fetchone()
            assert row is not None and row[0] > 0

        indexes = {
            r[0]
            for r in connection.execute(
                "select indexname from pg_indexes where tablename = 'tickets'"
            ).fetchall()
        }
        assert "tickets_customer_created_idx" in indexes
        assert "tickets_customer_site_idx" in indexes

        expression = _search_vector_expression(connection)
        assert "english" in expression
        assert "simple" not in expression


def test_apply_schema_is_idempotent_and_stems_search_vector() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        apply_schema(connection)
        apply_schema(connection)

        expression = _search_vector_expression(connection)
        assert "english" in expression

        count_row = connection.execute("select count(*) from passages").fetchone()
        assert count_row is not None
        passage_count_before = count_row[0]

        apply_schema(connection)
        count_row = connection.execute("select count(*) from passages").fetchone()
        assert count_row is not None and count_row[0] == passage_count_before

        match_row = connection.execute(
            "select count(*) from passages where search_vector @@ 'polici'::tsquery"
        ).fetchone()
        assert match_row is not None and match_row[0] >= 1
