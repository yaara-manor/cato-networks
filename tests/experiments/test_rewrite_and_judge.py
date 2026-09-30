import pytest
import json
from pathlib import Path

from pydantic_ai.models.test import TestModel

from exp_helpers import run
from experiments.lab.retrieve import lexical_top
from experiments.llm import judge, rewrite
from experiments.llm.common import Query, read_json
from experiments.llm.prompts import JUDGE_SYSTEM


def test_rewrite_writes_a_valid_resumable_cache(queries: dict[str, Query], tmp_path: Path) -> None:
    path = tmp_path / "rewrites.json"
    model = TestModel(custom_output_args={
        "is_kb_question": True, "intent": "BGP hold time", "search_queries": ["bgp hold time", " ", "a", "b", "c"]})
    qs = [queries["Q04"], queries["Q05"]]

    pending = rewrite.pending_queries(qs, {}, limit=1)
    assert run(rewrite.run_rewrites(model, "test", pending, path, concurrency=2)) == 0

    cache = json.loads(path.read_text())
    assert list(cache) == ["Q04"]
    rec = cache["Q04"]
    assert rec["search_queries"] == ["bgp hold time", "a", "b"]
    assert rec["is_kb_question"] is True and rec["intent"] == "BGP hold time"
    assert rec["model"] == "test" and rec["usage"]["requests"] == 1
    assert rec["latency_s"] >= 0 and rec["ts"]
    assert [q["id"] for q in rewrite.pending_queries(qs, cache, None)] == ["Q05"]


def pooled_passages() -> list[str]:
    return [p["passage_id"] for p in lexical_top("bgp hold time keepalive", 2)]


def test_judge_writes_grades_with_reasons_and_logs_calls(queries: dict[str, Query], tmp_path: Path) -> None:
    pids = pooled_passages()
    pools = {"Q04": pids}
    model = TestModel(custom_output_args={"grade": 2, "reason": "States the default hold time."})
    pairs = judge.pending_pairs(pools, {}, {"Q04"}, limit=None)

    failures = run(judge.run_judging(
        model, "test", pairs, {"Q04": queries["Q04"]["text"]}, tmp_path / "passages.json",
        tmp_path / "judgments.json", tmp_path / "judge_calls.jsonl", concurrency=2))

    assert failures == 0
    assert read_json(tmp_path / "judgments.json", {}) == {
        "Q04": {pid: {"grade": 2, "reason": "States the default hold time."} for pid in pids}}
    calls = [json.loads(line) for line in (tmp_path / "judge_calls.jsonl").read_text().splitlines()]
    assert {c["passage_id"] for c in calls} == set(pids) and calls[0]["usage"]["requests"] == 1
    assert judge.pending_pairs(pools, read_json(tmp_path / "judgments.json", {}), {"Q04"}, None) == []


def test_judge_rejects_out_of_range_grades(queries: dict[str, Query], tmp_path: Path) -> None:
    model = TestModel(custom_output_args={"grade": 5, "reason": "bogus"})
    pairs = judge.pending_pairs({"Q04": pooled_passages()[:1]}, {}, {"Q04"}, None)

    failures = run(judge.run_judging(
        model, "test", pairs, {"Q04": queries["Q04"]["text"]}, tmp_path / "passages.json",
        tmp_path / "judgments.json", tmp_path / "judge_calls.jsonl", concurrency=1))

    assert failures == 1
    assert read_json(tmp_path / "judgments.json", {}) == {}


def test_judge_prompt_shows_only_query_and_passage() -> None:
    passage = judge.PassageText(slug="bgp-article", heading="Hold time", body="x" * 5000)
    prompt = judge.judge_prompt("What is the hold time?", passage)
    assert prompt.count("x") == judge.JUDGE_BODY_MAX
    assert "What is the hold time?" in prompt and "bgp-article" in prompt
    for text in (prompt, JUDGE_SYSTEM):
        assert not any(w in text.lower() for w in ("score", "rank", "variant"))


def test_judge_fetches_full_bodies_from_the_db_when_the_cache_is_truncated(tmp_path: Path) -> None:
    pid = pooled_passages()[0]
    (tmp_path / "passages.json").write_text(json.dumps({pid: {"slug": "s", "heading": "h", "body": "y" * 1200}}))

    texts = judge.load_passage_texts([pid], tmp_path / "passages.json")

    assert texts[pid].body != "y" * 1200 and texts[pid].slug != "s"


def test_sample_audit_prints_requested_number(
    queries: dict[str, Query], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pids = pooled_passages()
    judgments = {"Q04": {pid: {"grade": 1, "reason": f"r{i}"} for i, pid in enumerate(pids)}}

    judge.audit(judgments, list(queries.values()), tmp_path / "passages.json", n=1, seed=0)

    out = capsys.readouterr().out
    assert out.count("--- Q04") == 1 and "GRADE 1" in out and "QUERY:" in out
