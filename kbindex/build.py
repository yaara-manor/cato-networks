import os
from pathlib import Path
import subprocess
from urllib.parse import urlparse

import psycopg

from kbindex.config import REPO_ROOT
from kbindex.store import load_index

ROOT = REPO_ROOT / "data" / "kb_ingestion"
POLICIES_DIR = REPO_ROOT / "data" / "policies"


def newest_crawl_dir() -> Path:
    if not ROOT.exists():
        raise RuntimeError(f"No crawl directory found under {ROOT}")
    dirs = sorted(p for p in ROOT.iterdir() if p.is_dir())
    if not dirs:
        raise RuntimeError(f"No crawl directory found under {ROOT}")
    return dirs[-1]


def write_dump(destination: Path | str = Path("kb/postgres/kb.dump")) -> Path:
    # Write a custom-format Postgres dump of the filled database.
    dest = Path(destination)
    if not dest.is_absolute():
        dest = REPO_ROOT / dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_name(f"{dest.name}.tmp")

    db_url = os.environ.get("DATABASE_URL", "postgresql://kb:kb@localhost:5432/kb")
    parsed = urlparse(db_url)
    user = parsed.username or "kb"
    password = parsed.password or "kb"
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)
    dbname = parsed.path.lstrip("/") or "kb"

    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password

    def _cleanup_tmp():
        if tmp_dest.exists():
            tmp_dest.unlink()

    commands = [
        (["pg_dump", "-Fc", "-h", host, "-p", port, "-U", user, "-d", dbname], env),
    ]

    # Docker fallback if pg_dump is unavailable or in containerized runs
    docker_fallback = [
        "docker", "run", "--rm", "--network", "host",
        "-e", f"PGPASSWORD={password}",
        "pgvector/pgvector:0.8.6-pg18",
        "pg_dump", "-h", host, "-p", port, "-U", user, "-Fc", dbname,
    ]
    commands.append((docker_fallback, None))

    last_error = ""
    for cmd, run_env in commands:
        try:
            with open(tmp_dest, "wb") as f:
                proc = subprocess.run(
                    cmd,
                    env=run_env if run_env is not None else env,
                    stdout=f,
                    stderr=subprocess.PIPE,
                )
            if proc.returncode == 0 and tmp_dest.stat().st_size > 0:
                os.replace(tmp_dest, dest)
                return dest
            last_error = proc.stderr.decode("utf-8", errors="replace")
        except FileNotFoundError:
            continue
        finally:
            _cleanup_tmp()

    raise RuntimeError(f"pg_dump failed: {last_error or 'no pg_dump or docker available'}")


def build():
    crawl_dir = newest_crawl_dir()
    db_url = os.environ.get("DATABASE_URL", "postgresql://kb:kb@localhost:5432/kb")
    with psycopg.connect(db_url) as connection:
        load_index(connection, crawl_dir, POLICIES_DIR)
    write_dump()


if __name__ == "__main__":
    build()

