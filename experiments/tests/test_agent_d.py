import json
from pathlib import Path
from typing import Any

from experiments.tests.exp_helpers import run, scripted_model
from experiments.llm import agent_d
from experiments.llm.agent_d import EXHAUSTED, AgentAnswer, SearchSession, VARIANTS, validate
from experiments.llm.common import Query
from experiments.llm.prompts import render_agent_system


def answer(ids: list[str]) -> dict[str, Any]:
    return {"decision": "ANSWER", "citations": ids[:1], "answer_text": "Grounded answer."}


def test_two_real_searches_and_a_real_citation_pass_the_validator(queries: dict[str, Query]) -> None:
    model = scripted_model(["BGP hold time keepalive", "BGP neighbor default timers"], answer)

    rec = run(agent_d.run_agent(model, "scripted", "d_hidden_b3", queries["Q04"]))

    assert rec["n_searches"] == 2
    assert [len(s["passage_ids"]) for s in rec["searches"]] == [5, 5]
    assert len(rec["searches"][0]["scores"]) == 5
    assert rec["decision"] == rec["final_decision"] == "ANSWER"
    assert rec["invalid_citations"] == []
    assert rec["citations"][0] in {pid for s in rec["searches"] for pid in s["passage_ids"]}
    assert rec["query_id"] == "Q04" and rec["variant"] == "d_hidden_b3" and rec["model"] == "scripted"
    assert rec["usage"]["requests"] == 3 and rec["latency_s"] >= 0


def test_made_up_citation_is_downgraded_to_not_in_kb(queries: dict[str, Query]) -> None:
    fake = "00000000-0000-0000-0000-000000000000"
    model = scripted_model(
        ["mtu socket"], lambda ids: {"decision": "ANSWER", "citations": [fake], "answer_text": "Made up."}
    )

    rec = run(agent_d.run_agent(model, "scripted", "d_hidden_b3", queries["Q01"]))

    assert rec["decision"] == "ANSWER"
    assert rec["final_decision"] == "NOT_IN_KB"
    assert rec["invalid_citations"] == [fake]


def test_validator_rules() -> None:
    seen = {"p1", "p2"}
    ok = AgentAnswer(decision="ANSWER", citations=["p1"], answer_text="")
    assert validate(ok, seen) == {"final_decision": "ANSWER", "invalid_citations": []}
    empty = AgentAnswer(decision="ANSWER", citations=[], answer_text="")
    assert validate(empty, seen)["final_decision"] == "NOT_IN_KB"
    ask = AgentAnswer(decision="ASK_CUSTOMER", citations=["zzz"], answer_text="")
    assert validate(ask, seen) == {"final_decision": "ASK_CUSTOMER", "invalid_citations": ["zzz"]}


def test_budget_is_enforced_on_the_fourth_search(queries: dict[str, Query]) -> None:
    returns: list[str] = []
    model = scripted_model(["bgp", "mtu", "bfd", "dtls"], lambda ids: {
        "decision": "NOT_IN_KB", "citations": [], "answer_text": "none"}, returns)

    rec = run(agent_d.run_agent(model, "scripted", "d_hidden_b3", queries["Q04"]))

    assert [r == EXHAUSTED for r in returns] == [False, False, False, True]
    assert rec["n_searches"] == 3 and len(rec["searches"]) == 3


def test_budget_one_variant_allows_a_single_search() -> None:
    session = SearchSession(VARIANTS["d_hidden_b1"])
    assert session.search("bgp hold time") != EXHAUSTED
    assert session.search("bgp hold time") == EXHAUSTED
    assert len(session.searches) == 1


def test_scores_are_shown_only_when_the_variant_says_so() -> None:
    hidden, shown = SearchSession(VARIANTS["d_hidden_b3"]), SearchSession(VARIANTS["d_shown_b3"])
    assert "score=" not in hidden.search("bgp hold time")
    assert "score=" in shown.search("bgp hold time")
    assert "score" not in render_agent_system(3, 5, show_scores=False)
    assert "score" in render_agent_system(3, 5, show_scores=True)


def test_top_k_follows_the_variant() -> None:
    session = SearchSession(VARIANTS["d_hidden_b3_k10"])
    session.search("bgp hold time")
    assert len(session.searches[0]["passage_ids"]) == 10


def test_variant_run_is_resumable_and_writes_one_file_per_query(
    queries: dict[str, Query], tmp_path: Path
) -> None:
    model = scripted_model(["bgp"], answer)
    out_dir = agent_d.run_dir(tmp_path, "d_hidden_b3")
    pending = agent_d.pending_queries([queries["Q04"], queries["Q05"]], out_dir, limit=1)
    assert [q["id"] for q in pending] == ["Q04"]

    failures = run(agent_d.run_variant(model, "scripted", "d_hidden_b3", pending, out_dir, concurrency=2))

    assert failures == 0
    saved = json.loads((out_dir / "Q04.json").read_text())
    assert set(saved) == {"query_id", "variant", "decision", "final_decision", "citations", "invalid_citations",
                          "answer_text", "searches", "n_searches", "usage", "latency_s", "model", "ts"}
    assert [q["id"] for q in agent_d.pending_queries([queries["Q04"], queries["Q05"]], out_dir, None)] == ["Q05"]
