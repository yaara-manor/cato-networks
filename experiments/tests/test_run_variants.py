import json
from pathlib import Path

import pytest

from experiments import build_pools, run_variants
from experiments.llm.common import Query, read_json


@pytest.fixture(scope="module")
def cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("cache")
    (path / "rewrites.json").write_text(json.dumps({
        "Q04": {"is_kb_question": True, "intent": "BGP hold time and keepalive defaults",
                "search_queries": ["bgp hold time", "bgp keepalive interval"]},
        "Q05": {"is_kb_question": False, "intent": "", "search_queries": []},
    }))
    return path


@pytest.fixture(scope="module")
def two_queries() -> list[Query]:
    by_id = {q["id"]: q for q in run_variants.load_queries()}
    return [by_id["Q04"], by_id["Q05"]]


@pytest.fixture(scope="module", autouse=True)
def computed(cache_dir: Path, two_queries: list[Query]) -> None:
    run_variants.run_queries(two_queries, cache_dir)


def load(cache_dir: Path, name: str) -> dict[str, dict]:
    return json.loads((cache_dir / "runs" / f"{name}.json").read_text())


def ids(entry: dict) -> list[str]:
    return [r["passage_id"] for r in entry["results"]]


def test_every_variant_is_written_with_ranked_bodyless_results(cache_dir: Path) -> None:
    names = [p.stem for p in (cache_dir / "runs").glob("*.json")]
    expected = {"R0_lex", "R1_dense", "R2_rrf", "R3_current", "A_clean", "B_rewrite_intent", "B_rewrite_orig"}
    expected |= {f"FUS_rrf_wl{w}{s}" for w in ("0.25", "0.5", "1", "2", "4") for s in ("", "+rerank")}
    expected |= {f"FUS_lin_wl{w}{s}" for w in ("0", "0.25", "0.5", "0.75", "1") for s in ("", "+rerank")}
    assert set(names) == expected
    for name in names:
        data = load(cache_dir, name)
        assert set(data) == {"Q04", "Q05"}, name
        for entry in data.values():
            assert entry["latency_ms"] > 0
            assert 1 <= len(entry["results"]) <= 20
            assert [r["rank"] for r in entry["results"]] == list(range(1, len(entry["results"]) + 1))
            assert set(entry["results"][0]) == {"passage_id", "slug", "heading", "score", "rank"}
            assert entry["results"][0]["score"] == round(entry["results"][0]["score"], 4)
        assert (cache_dir / "runs" / f"{name}.json").stat().st_size < 2_000_000
    assert len(load(cache_dir, "R1_dense")["Q04"]["results"]) == 20


def test_passage_bodies_are_stored_once_and_capped(cache_dir: Path) -> None:
    bodies = read_json(cache_dir / "passages.json", {})
    used = {pid for name in ("R3_current", "B_rewrite_intent") for e in load(cache_dir, name).values() for pid in ids(e)}
    assert used <= set(bodies)
    assert all(set(v) == {"slug", "heading", "body"} and len(v["body"]) <= 1200 for v in bodies.values())


def test_weight_one_fusion_matches_the_baselines_and_production(cache_dir: Path) -> None:
    for qid in ("Q04", "Q05"):
        assert ids(load(cache_dir, "FUS_rrf_wl1")[qid]) == ids(load(cache_dir, "R2_rrf")[qid])
        assert ids(load(cache_dir, "FUS_rrf_wl1+rerank")[qid]) == ids(load(cache_dir, "R3_current")[qid])


def test_rewrite_without_sub_queries_falls_back_to_the_original_message(cache_dir: Path) -> None:
    assert ids(load(cache_dir, "B_rewrite_orig")["Q05"]) == ids(load(cache_dir, "R3_current")["Q05"])


def test_second_run_is_a_no_op(
    cache_dir: Path, two_queries: list[Query], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(text: str) -> None:
        raise AssertionError("retrieval should not rerun for cached queries")

    monkeypatch.setattr(run_variants, "fetch_branches", boom)
    run_variants.run_queries(two_queries, cache_dir)


def test_pools_are_the_union_of_top_ten_of_runs_and_agent_searches(cache_dir: Path, tmp_path: Path) -> None:
    (cache_dir / "d_runs" / "d_hidden_b3").mkdir(parents=True)
    (cache_dir / "d_runs" / "d_hidden_b3" / "Q04.json").write_text(json.dumps({
        "query_id": "Q04", "searches": [{"query": "x", "passage_ids": ["agent-only-id"], "scores": [0.1]}]}))

    pools = build_pools.build_pools(cache_dir)

    top10 = {pid for p in (cache_dir / "runs").glob("*.json") for pid in ids(load(cache_dir, p.stem)["Q04"])[:10]}
    assert set(pools["Q04"]) == top10 | {"agent-only-id"}
    assert pools["Q04"] == sorted(pools["Q04"])
    assert set(pools) == {"Q04", "Q05"}
