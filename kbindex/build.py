import os
from pathlib import Path
import subprocess
from urllib.parse import urlparse

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


def write_dump(destination: Path | str = Path("kb/postgres/kb.dump")) -> Path:
    # Write a custom-format Postgres dump of the filled database.
    dest = Path(destination)
    if not dest.is_absolute():
        dest = REPO / dest
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

    # Try local pg_dump first
    try:
        proc = subprocess.run(
            ["pg_dump", "-Fc", "-h", host, "-p", port, "-U", user, "-d", dbname, "-f", str(tmp_dest)],
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and tmp_dest.stat().st_size > 0:
            os.replace(tmp_dest, dest)
            return dest
    except FileNotFoundError:
        pass
    finally:
        _cleanup_tmp()

    # Fallback to docker exec if a postgres container is running
    try:
        ps_proc = subprocess.run(
            ["docker", "ps", "--filter", "ancestor=pgvector/pgvector:0.8.6-pg18", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        )
        containers = [c.strip() for c in ps_proc.stdout.splitlines() if c.strip()]
        if containers:
            with open(tmp_dest, "wb") as f:
                exec_proc = subprocess.run(
                    ["docker", "exec", containers[0], "pg_dump", "-U", user, "-Fc", dbname],
                    stdout=f,
                    stderr=subprocess.PIPE,
                )
            if exec_proc.returncode == 0 and tmp_dest.stat().st_size > 0:
                os.replace(tmp_dest, dest)
                return dest
    except FileNotFoundError:
        pass
    finally:
        _cleanup_tmp()

    # Fallback to docker run
    try:
        with open(tmp_dest, "wb") as f:
            run_proc = subprocess.run(
                [
                    "docker", "run", "--rm", "--network", "host",
                    "-e", f"PGPASSWORD={password}",
                    "pgvector/pgvector:0.8.6-pg18",
                    "pg_dump", "-h", host, "-p", port, "-U", user, "-Fc", dbname,
                ],
                stdout=f,
                stderr=subprocess.PIPE,
            )
        if run_proc.returncode == 0 and tmp_dest.stat().st_size > 0:
            os.replace(tmp_dest, dest)
            return dest
        err = run_proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"pg_dump failed: {err}")
    except FileNotFoundError:
        raise RuntimeError("pg_dump failed and docker is not available")
    finally:
        _cleanup_tmp()


def build():
    crawl_dir = newest_crawl_dir()
    db_url = os.environ.get("DATABASE_URL", "postgresql://kb:kb@localhost:5432/kb")
    with psycopg.connect(db_url) as connection:
        load_index(connection, crawl_dir, POLICIES_DIR)
    write_dump()


if __name__ == "__main__":
    build()

