"""Shared plumbing for the Gemini runners: model resolution, retries, caches, CLI selection."""
import argparse
import asyncio
import json
import os
import random
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, TypeVar

from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.models import Model, infer_model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from core.config import settings

EXPERIMENTS_DIR: Path = Path(__file__).resolve().parents[1]
CACHE_DIR: Path = EXPERIMENTS_DIR / "cache"
QUERIES_PATH: Path = EXPERIMENTS_DIR / "data" / "queries.jsonl"

API_KEY_VARS: tuple[str, ...] = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
MODEL_SETTINGS: ModelSettings = ModelSettings(temperature=0.0)
RETRY_ATTEMPTS: int = 6
RETRY_BASE_DELAY_S: float = 2.0

T = TypeVar("T")
R = TypeVar("R")


class Query(TypedDict):
    id: str
    set: str
    text: str
    gold_hint: list[str] | str


class CallMeta(TypedDict):
    model: str
    usage: dict[str, int]
    latency_s: float
    ts: str


# ---------------------------------------------------------------- model

def model_name(env_var: str) -> str:
    """Model id from `env_var`, defaulting to the production `settings.llm_model`."""
    return os.environ.get(env_var) or settings.llm_model


def require_api_key(name: str) -> None:
    if name.startswith("google") and not any(os.environ.get(v) for v in API_KEY_VARS):
        raise SystemExit(
            f"None of {' / '.join(API_KEY_VARS)} is set, but model '{name}' needs one. "
            "Run with: uv run --env-file .env python -m <module> (or use --dry-run)."
        )


def build_model(name: str) -> Model:
    require_api_key(name)
    return infer_model(name)


def usage_dict(usage: RunUsage) -> dict[str, int]:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "requests": usage.requests,
    }


def call_meta(name: str, usage: RunUsage, started: float) -> CallMeta:
    """Metadata for one finished call; `started` is a `time.perf_counter()` reading."""
    return CallMeta(
        model=name,
        usage=usage_dict(usage),
        latency_s=round(time.perf_counter() - started, 3),
        ts=datetime.now(UTC).isoformat(timespec="seconds"),
    )


# ---------------------------------------------------------------- retries and concurrency

def is_retryable(exc: BaseException) -> bool:
    """429 and 5xx responses, plus transport-level failures, are worth retrying."""
    if isinstance(exc, ModelHTTPError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, ModelAPIError)


async def with_retries(
    call: Callable[[], Awaitable[T]],
    attempts: int = RETRY_ATTEMPTS,
    base_delay_s: float = RETRY_BASE_DELAY_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Await `call()`, retrying retryable errors with jittered exponential backoff."""
    attempt = 1
    while True:
        try:
            return await call()
        except Exception as exc:
            if attempt >= attempts or not is_retryable(exc):
                raise
            await sleep(base_delay_s * 2 ** (attempt - 1) * (0.5 + random.random()))
            attempt += 1


async def run_pool(
    items: Sequence[T],
    worker: Callable[[T], Awaitable[R]],
    on_result: Callable[[T, R], None],
    concurrency: int,
) -> int:
    """Run `worker` over `items` with bounded concurrency; return the number of failures.

    `on_result` runs on the event loop as each item finishes, so callers can persist
    incrementally without locks. A failed item is reported on stderr and skipped.
    """
    gate = asyncio.Semaphore(max(1, concurrency))
    failures = 0

    async def one(item: T) -> None:
        nonlocal failures
        async with gate:
            try:
                result = await worker(item)
            except Exception as exc:
                failures += 1
                print(f"FAILED {item!r}: {type(exc).__name__}: {exc}", file=sys.stderr)
                return
        on_result(item, result)

    await asyncio.gather(*(one(i) for i in items))
    return failures


# ---------------------------------------------------------------- files

def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any, indent: int | None = 2) -> None:
    """Atomic write (temp file + rename) so an interrupted run never corrupts a cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_queries(path: Path = QUERIES_PATH) -> list[Query]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------- CLI

def add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=None, help="process at most N not-yet-cached items")
    parser.add_argument("--ids", default=None, help="comma-separated query ids to restrict to")
    parser.add_argument("--concurrency", type=int, default=4, help="parallel calls (default 4)")
    parser.add_argument("--dry-run", action="store_true", help="print counts only; make no calls")
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR, help=argparse.SUPPRESS)


def select_queries(queries: Sequence[Query], ids: str | None) -> list[Query]:
    if not ids:
        return list(queries)
    wanted = [i.strip() for i in ids.split(",") if i.strip()]
    known = {q["id"] for q in queries}
    missing = [i for i in wanted if i not in known]
    if missing:
        raise SystemExit(f"unknown query ids: {', '.join(missing)}")
    return [q for q in queries if q["id"] in set(wanted)]


def take(items: Sequence[T], limit: int | None) -> list[T]:
    return list(items[:limit]) if limit is not None else list(items)


def progress(done: int, total: int, label: str, latency_s: float) -> None:
    print(f"[{done}/{total}] {label} ({latency_s:.1f}s)", flush=True)
