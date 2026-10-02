import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from core.config import REPO_ROOT, settings
from db.init.build import RUNTIME_TABLES, write_dump

PG_IMAGE = "pgvector/pgvector:0.8.6-pg18"


def _toc(dump: Path) -> str:
    """`pg_restore --list` output, locally or via docker; skips if neither works."""
    commands = [
        ["pg_restore", "--list", str(dump)],
        [
            "docker", "run", "--rm", "-v", f"{dump.parent}:/dump", PG_IMAGE,
            "pg_restore", "--list", f"/dump/{dump.name}",
        ],
    ]
    for cmd in commands:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            continue
        if proc.returncode == 0:
            return proc.stdout
    pytest.skip("neither pg_restore nor docker available")


def _assert_no_runtime_tables(toc: str) -> None:
    for line in toc.splitlines():
        assert not any(f" {table} " in f"{line} " for table in RUNTIME_TABLES), line


def test_fresh_dump_excludes_runtime_tables(tmp_path: Path) -> None:
    conversation_id = uuid4()
    now = datetime.now(UTC)
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(
            "insert into conversations (id, customer_tier, stage, created_at, updated_at)"
            " values (%(id)s, 'Standard', 'IDLE', %(now)s, %(now)s)",
            {"id": conversation_id, "now": now},
        )
        try:
            toc = _toc(write_dump(tmp_path / "x.dump"))
        finally:
            conn.execute("delete from conversations where id = %(id)s", {"id": conversation_id})
    _assert_no_runtime_tables(toc)
    assert "TABLE DATA public passages" in toc


def test_committed_seed_dump_excludes_runtime_tables() -> None:
    _assert_no_runtime_tables(_toc(REPO_ROOT / "db" / "seed.dump"))
