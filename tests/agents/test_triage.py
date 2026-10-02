import json
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agents.messages import tool_returns
from agents.models import Intent, TriageInput
from agents.runner import run_role
from agents.triage import build_triage_agent, run_triage
from core.config import REPO_ROOT
from core.models import Ticket
from tests.agents.conftest import MakeDeps, scripted_model

PSK = "Fg7!qwe-DC-2026-tunnel"
UNKNOWN_EMAIL = "nobody@unknown.example"


def _decision(**fields: Any) -> dict[str, Any]:
    return {"intent": "KB_INQUIRY", "priority": "P3", "symptom_summary": "summary", **fields}


def _scenario_message(prefix: str) -> str:
    with (REPO_ROOT / "data/eval/scenarios.jsonl").open() as f:
        return next(r["opening_message"] for r in map(json.loads, f) if r["scenario_id"].startswith(prefix))


def _triage(make_deps: MakeDeps, email: str, message: str, final: dict[str, Any] | None) -> Any:
    deps = make_deps(email)
    return run_triage(TriageInput(message=message, identity=deps.identity), deps, scripted_model([], final))


def _history_for(make_deps: MakeDeps, email: str) -> list[Ticket]:
    deps = make_deps(email)
    model = scripted_model([("get_ticket_history", {})], _decision())
    outcome = run_role(build_triage_agent(model), "hi", deps, "triage")
    (tickets,) = tool_returns(list(outcome.messages), "get_ticket_history")
    return tickets


def test_history_redacts_psk_and_quarantines_injection(make_deps: MakeDeps) -> None:
    psk_ticket = next(
        t for t in _history_for(make_deps, "it.support@cobaltmining.co") if t.ticket_id == "TCK-20264230"
    )
    assert PSK not in f"{psk_ticket.subject} {psk_ticket.body}"
    assert "[REDACTED" in psk_ticket.body

    tickets = {t.ticket_id: t for t in _history_for(make_deps, "sysadmin@atlas-eng.com")}
    injected = tickets["TCK-20264246"]
    assert injected.subject.startswith("[QUARANTINED") and injected.body.startswith("[QUARANTINED")
    clean = next(t for t in tickets.values() if not t.body.startswith("[QUARANTINED"))
    assert "REDACTED" not in clean.body


def test_history_empty_for_unknown_caller(make_deps: MakeDeps) -> None:
    assert _history_for(make_deps, UNKNOWN_EMAIL) == []


def _instructions(make_deps: MakeDeps, email: str) -> str:
    seen: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.extend(m.instructions for m in messages if isinstance(m, ModelRequest) and m.instructions)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, _decision())])

    run_role(build_triage_agent(FunctionModel(respond)), "hi", make_deps(email), "triage")
    return "\n".join(seen)



def test_identity_block_for_member_and_unknown(make_deps: MakeDeps) -> None:
    member = _instructions(make_deps, "priya.patel@bluebirdretail.com")
    assert "effective tier Standard" in member and "ACC-1002" in member
    unknown = _instructions(make_deps, UNKNOWN_EMAIL)
    assert "unrecognized caller" in unknown and "ACC-" not in unknown


def test_repeat_contact_on_prior_closed_tickets(make_deps: MakeDeps) -> None:
    final = _decision(intent="TELEMETRY_DIAGNOSIS", site_id="S-1008-01", product_area="connectivity")
    run = _triage(make_deps, "grace.novak@solsticemedia.com", _scenario_message("SC-06"), final)

    assert run.output.repeat_contact.is_repeat_contact
    assert run.output.sla.priority == "P3"
    assert run.trace.agent_role == "triage"


def test_tier_claim_does_not_raise_effective_tier(make_deps: MakeDeps) -> None:
    final = _decision(intent="TELEMETRY_DIAGNOSIS", priority="P1")
    run = _triage(make_deps, "priya.patel@bluebirdretail.com", _scenario_message("SC-07"), final)

    assert run.output.identity.effective_tier == "Standard"
    assert run.output.sla.tier == "Standard" and run.output.sla.is_24x7


def test_unknown_caller_has_no_sla_or_repeat_contact(make_deps: MakeDeps) -> None:
    run = _triage(make_deps, UNKNOWN_EMAIL, "hello", _decision())

    assert run.output.identity.account is None
    assert run.output.sla is None and run.output.repeat_contact is None


def test_missing_country_skips_sla_and_asks_country(make_deps: MakeDeps) -> None:
    base = make_deps("sysadmin@atlas-eng.com")
    question = "Which country?"
    identity = base.identity.model_copy(
        update={"needs_country_clarification": True, "scoping_question": question}
    )
    deps = make_deps("sysadmin@atlas-eng.com", identity=identity)

    run = run_triage(TriageInput(message="hi", identity=identity), deps, scripted_model([], _decision()))

    assert run.output.sla is None
    assert run.output.scoping_question == question


def test_model_failure_keeps_identity_and_sla(make_deps: MakeDeps) -> None:
    message = f"our PSK is {PSK}, tunnel down"
    run = _triage(make_deps, "sysadmin@atlas-eng.com", message, None)

    assert run.output.decision.intent == Intent.KB_INQUIRY
    assert PSK not in run.output.decision.symptom_summary
    assert run.output.identity.account is not None and run.output.sla is not None
    assert run.trace.agent_role == "triage" and run.trace.error


@pytest.mark.parametrize("intent", list(Intent))
def test_every_intent_round_trips(make_deps: MakeDeps, intent: Intent) -> None:
    run = _triage(make_deps, "sysadmin@atlas-eng.com", "hi", _decision(intent=intent.value))

    assert run.output.decision.intent == intent
