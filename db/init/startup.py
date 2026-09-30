from collections.abc import Callable
import os
from pathlib import Path
import sys

import psycopg

from core.config import REPO_ROOT
from db.init.seed import seed_all
from kbindex.embed import embed_passages, probe_width
from kbindex.store import HashMismatch, StartupError, verify_hashes

__all__ = [
    "HashMismatch",
    "StartupError",
    "run_startup",
    "main",
    "verify_hashes",
    "probe_width",
]


def run_startup(
    connection: psycopg.Connection | None = None,
    embed: Callable[[list[str]], list[list[float]]] | None = None,
    policies_dir: Path | str | None = None,
    read_file: Callable[[Path], bytes | str] | None = None,
    tickets_dir: Path | str | None = None,
) -> None:
    if policies_dir is None:
        policies_dir = REPO_ROOT / "data" / "policies"
    if tickets_dir is None:
        tickets_dir = REPO_ROOT / "data" / "tickets"
    if embed is None:
        embed = embed_passages

    if connection is None:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise StartupError("DATABASE_URL environment variable is not set")
        with psycopg.connect(db_url) as conn:
            _execute_startup(conn, embed, policies_dir, tickets_dir, read_file)
    else:
        _execute_startup(connection, embed, policies_dir, tickets_dir, read_file)


def _execute_startup(
    connection: psycopg.Connection,
    embed: Callable[[list[str]], list[list[float]]],
    policies_dir: Path | str,
    tickets_dir: Path | str = REPO_ROOT / "data" / "tickets",
    read_file: Callable[[Path], bytes | str] | None = None,
) -> None:
    seed_all(
        connection,
        policies_dir=policies_dir,
        tickets_dir=tickets_dir,
        preserve_existing_tickets=True,
    )
    verify_hashes(connection, read_file=read_file)

    with connection.cursor() as cursor:
        cursor.execute("select embedding_dimensions from snapshots order by crawled_at desc limit 1")
        row = cursor.fetchone()
        if not row:
            raise StartupError("No snapshot found in database")
        expected_dim: int = row[0]

    width = probe_width(embed)
    if width != expected_dim or width != 384:
        raise StartupError(
            f"Embedding width {width} does not match expected dimensions {expected_dim}"
        )


def main() -> None:
    run_startup()
    sys.exit(0)


if __name__ == "__main__":
    main()
