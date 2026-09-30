"""Judging pools: the union, per query, of the top-10 passage ids of every variant and every agent search.

    uv run python -m experiments.build_pools

Reads cache/runs/*.json and cache/d_runs/*/*.json; writes cache/pools.json {query_id: [passage_id, ...]}.
"""
import argparse
import statistics
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from experiments.llm.common import CACHE_DIR, read_json, write_json

POOL_DEPTH: int = 10


def run_ids(entry: dict[str, Any]) -> list[str]:
    return [r["passage_id"] for r in sorted(entry["results"], key=lambda r: r["rank"])[:POOL_DEPTH]]


def agent_ids(record: dict[str, Any]) -> list[str]:
    return [pid for s in record["searches"] for pid in s["passage_ids"][:POOL_DEPTH]]


def build_pools(cache_dir: Path) -> dict[str, list[str]]:
    pools: dict[str, set[str]] = {}
    for path in sorted((cache_dir / "runs").glob("*.json")):
        for qid, entry in read_json(path, {}).items():
            pools.setdefault(qid, set()).update(run_ids(entry))
    for path in sorted((cache_dir / "d_runs").glob("*/*.json")):
        record = read_json(path, {})
        pools.setdefault(record["query_id"], set()).update(agent_ids(record))
    return {qid: sorted(ids) for qid, ids in sorted(pools.items())}


def print_stats(pools: dict[str, list[str]]) -> None:
    sizes = [len(v) for v in pools.values()]
    if not sizes:
        print("pools are empty: run experiments.run_variants first")
        return
    print(f"queries={len(pools)} pairs={sum(sizes)} (= judge calls)")
    print(f"pool size per query: min={min(sizes)} median={statistics.median(sizes):g} max={max(sizes)}")
    print(f"distinct passages={len({pid for v in pools.values() for pid in v})}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    pools = build_pools(args.cache_dir)
    write_json(args.cache_dir / "pools.json", pools, indent=None)
    print_stats(pools)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
