import asyncio
from pathlib import Path

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from experiments.tests.exp_helpers import run
from experiments.llm import agent_d, common, judge, rewrite


def test_retries_back_off_on_429_and_5xx_then_succeed() -> None:
    errors = [ModelHTTPError(429, "m"), ModelHTTPError(503, "m")]
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def call() -> str:
        if errors:
            raise errors.pop(0)
        return "ok"

    assert run(common.with_retries(call, sleep=fake_sleep)) == "ok"
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] * 0.5


def test_non_retryable_errors_and_exhaustion_raise() -> None:
    calls = 0

    async def bad_request() -> str:
        nonlocal calls
        calls += 1
        raise ModelHTTPError(400, "m")

    async def no_sleep(delay: float) -> None:
        await asyncio.sleep(0)

    with pytest.raises(ModelHTTPError):
        run(common.with_retries(bad_request, sleep=no_sleep))
    assert calls == 1

    async def always_429() -> str:
        nonlocal calls
        calls += 1
        raise ModelHTTPError(429, "m")

    calls = 0
    with pytest.raises(ModelHTTPError):
        run(common.with_retries(always_429, attempts=3, sleep=no_sleep))
    assert calls == 3


def test_pool_reports_failures_and_keeps_going() -> None:
    stored: list[int] = []

    async def worker(i: int) -> int:
        if i == 2:
            raise RuntimeError("boom")
        return i * 10

    failures = run(common.run_pool([1, 2, 3], worker, lambda i, r: stored.append(r), concurrency=2))
    assert failures == 1 and sorted(stored) == [10, 30]


def test_model_defaults_to_cheap_openai_and_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXPERIMENT_LLM_MODEL", raising=False)
    assert common.model_name("EXPERIMENT_LLM_MODEL") == "openai:gpt-6-luna"
    monkeypatch.setenv("EXPERIMENT_LLM_MODEL", "google-gla:other")
    assert common.model_name("EXPERIMENT_LLM_MODEL") == "google-gla:other"


@pytest.mark.parametrize("module", [rewrite, agent_d, judge])
def test_dry_run_needs_no_key_and_a_real_run_fails_clearly_without_one(
    module: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for variables in common.API_KEY_VARS.values():
        for var in variables:
            monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("EXPERIMENT_LLM_MODEL", raising=False)
    monkeypatch.delenv("EXPERIMENT_JUDGE_MODEL", raising=False)
    (tmp_path / "pools.json").write_text('{"Q01": ["a-passage-id"]}')
    base = ["--ids", "Q01", "--cache-dir", str(tmp_path)]

    assert module.main([*base, "--dry-run"]) == 0  # type: ignore[attr-defined]
    assert "pending=1" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="OPENAI_API_KEY"):
        module.main(base)  # type: ignore[attr-defined]
