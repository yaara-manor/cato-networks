import os
from pathlib import Path
import subprocess
import sys

import psycopg
import pytest

from kbindex.embed import embed_passages, load_embedder, probe_width
from kbindex.startup import HashMismatch, StartupError, main, run_startup
from kbindex.store import HashMismatch as StoreHashMismatch
from kbindex.store import StartupError as StoreStartupError
from kbindex.store import verify_hashes


def test_exception_imports():
    assert HashMismatch is StoreHashMismatch
    assert StartupError is StoreStartupError
    assert issubclass(HashMismatch, Exception)
    assert issubclass(StartupError, Exception)


def test_startup_rejects_a_hash_or_width_mismatch():
    repo = Path(__file__).resolve().parents[2]
    policies_dir = repo / "data" / "policies"

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        # run_startup against the filled database succeeds
        run_startup(connection, embed_passages, policies_dir)

        # verify_hashes with a reader that changes one byte expects HashMismatch
        def reader_with_changed_byte(path):
            return Path(path).read_bytes() + b"\x01"

        with pytest.raises(HashMismatch):
            verify_hashes(connection, read_file=reader_with_changed_byte)

        # width check with a stand-in embedder returning length != 384 expects StartupError
        bad_embedder = lambda texts: [[0.0] * 128]
        with pytest.raises(StartupError):
            run_startup(connection, embed=bad_embedder, policies_dir=policies_dir)

        # real probe_width equals 384 and equals the snapshot row
        row = connection.execute(
            "select embedding_dimensions from snapshots order by crawled_at desc limit 1"
        ).fetchone()
        assert row is not None
        assert row[0] == 384
        assert probe_width(embed_passages) == 384
        assert probe_width(load_embedder()) == 384
        assert probe_width() == 384


def test_startup_cli():
    result = subprocess.run(
        [sys.executable, "-m", "kbindex.startup"],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
