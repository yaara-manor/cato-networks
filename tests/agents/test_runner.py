import json
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agents.base import SupportDeps, build_agent, load_prompt
from agents.messages import tool_call_dicts, tool_returns
from agents.runner import run_role
from core.config import REPO_ROOT, settings
from guardrails import InjectionCategory, InjectionVerdict, SessionGuardHistory
from retrieval.models import KBSearchResult, KBSearchStatus
from tests.agents.conftest import MakeDeps, scripted_model


class Answer(BaseModel):
    text: str


def _agent(model: FunctionModel) -> Agent[SupportDeps, Answer]:
    agent = build_agent("You are a test role.", Answer, model)

    @agent.tool
    def search_kb(ctx: RunContext[SupportDeps], query: str) -> KBSearchResult:
        return ctx.deps.retrieval.search_kb(query)

    return agent


def _q10() -> str:
    with (REPO_ROOT / "data/eval/questions.jsonl").open() as f:
        return next(r["question"] for r in map(json.loads, f) if r["question_id"] == "Q10")


def test_load_prompt_missing_blank_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "repo_root", tmp_path)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "blank.md").write_text("  \n")
    (tmp_path / "prompts" / "role.md").write_text("be helpful")

    with pytest.raises(FileNotFoundError):
        load_prompt("missing")
    with pytest.raises(ValueError, match="blank"):
        load_prompt("blank")
    assert load_prompt("role") == "be helpful"


def _recording_model(seen: list[str]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.extend(m.instructions for m in messages if isinstance(m, ModelRequest) and m.instructions)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"text": "ok"})])

    return FunctionModel(respond)


@pytest.mark.parametrize("blocked", [True, False])
def test_guard_note_reaches_model_only_with_bypass_history(make_deps: MakeDeps, blocked: bool) -> None:
    history = SessionGuardHistory()
    if blocked:
        verdict = InjectionVerdict(
            blocked=True, categories=frozenset({InjectionCategory.ROLE_OVERRIDE}), rule_ids=()
        )
        history = history.with_injection(verdict)
    seen: list[str] = []

    run_role(_agent(_recording_model(seen)), "hi", make_deps(guard_history=history), "TRIAGE")

    joined = "\n".join(seen)
    assert "You are a test role." in joined
    assert ("Guard history" in joined) is blocked


def test_extractors_keep_typed_tool_returns(make_deps: MakeDeps) -> None:
    model = scripted_model([("search_kb", {"query": _q10()})], {"text": "done"})

    outcome = run_role(_agent(model), "hi", make_deps(), "KNOWLEDGE")

    assert outcome.output == Answer(text="done")
    (result,) = tool_returns(list(outcome.messages), "search_kb")
    assert isinstance(result, KBSearchResult)
    assert result.status == KBSearchStatus.CONFIDENT
    (call,) = outcome.trace.tool_calls
    assert (call.tool_name, call.status) == ("search_kb", "CONFIDENT")
    assert call.arguments == {"query": _q10()}
    assert call.result["status"] == "CONFIDENT"
    assert tool_call_dicts(list(outcome.messages))[0]["tool_name"] == "search_kb"


def test_exhausted_output_retries_return_fallback_outcome(make_deps: MakeDeps) -> None:
    model = scripted_model([("search_kb", {"query": _q10()})], None)

    outcome = run_role(_agent(model), "hi", make_deps(), "KNOWLEDGE")

    assert outcome.output is None
    assert outcome.trace.agent_role == "KNOWLEDGE"
    assert outcome.trace.status == "ERROR"
    assert outcome.trace.error
    # Messages survive the failure, so fallbacks can still read tool returns.
    assert len(tool_returns(list(outcome.messages), "search_kb")) == 1
    assert len(outcome.trace.tool_calls) == 1


def test_transport_errors_propagate(make_deps: MakeDeps) -> None:
    def boom(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=429, model_name="scripted")

    with pytest.raises(ModelHTTPError):
        run_role(_agent(FunctionModel(boom)), "hi", make_deps(), "TRIAGE")


def test_no_tool_call_run_gives_empty_extracts_and_usage(make_deps: MakeDeps) -> None:
    outcome = run_role(_agent(scripted_model([], {"text": "hi"})), "hi", make_deps(), "TRIAGE")

    assert tool_returns(list(outcome.messages), "search_kb") == ()
    assert outcome.trace.tool_calls == []
    assert outcome.trace.latency_ms >= 0
    assert outcome.trace.prompt_tokens > 0 and outcome.trace.completion_tokens > 0
    assert outcome.trace.cost_usd is None


def test_cost_set_for_known_model(make_deps: MakeDeps) -> None:
    model = scripted_model([], {"text": "hi"}, model_name="gpt-5-nano")

    outcome = run_role(_agent(model), "hi", make_deps(), "TRIAGE")

    assert outcome.trace.cost_usd is not None and outcome.trace.cost_usd > 0

