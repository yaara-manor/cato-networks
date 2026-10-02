from pathlib import Path
from typing import Any

import pytest

from agents.base import load_prompt
from agents.diagnostics import build_diagnostics_agent, run_diagnostics
from agents.messages import tool_returns
from agents.models import DiagnosticsInput, Intent, TriageDecision, TriageResult
from agents.runner import run_role
from tests.agents.conftest import MakeDeps, scripted_model
from tools.models import TelemetryStatus
from tools.telemetry import TelemetryService

OWN_EMAIL = "sysadmin@atlas-eng.com"  # ACC-1007
OWN_SITE = "S-1007-01"
FOREIGN_SITE = "S-1005-01"  # ACC-1005
FOREIGN_EMAIL = "priya.patel@bluebirdretail.com"  # ACC-1002
HEADINGS = ("Role", "Inputs you receive", "Tools and when to use them", "Rules", "Output fields", "Examples")
SITE_TOOLS = ("get_site_status", "get_link_quality", "get_events", "get_bgp_status", "get_ipsec_status")
HYPOTHESIS = {"root_cause_hypothesis": "BGP route limit hit"}


def _call_tool(deps: Any, name: str, args: dict[str, Any]) -> Any:
    model = scripted_model([(name, args)], {})
    outcome = run_role(build_diagnostics_agent(model), "hi", deps, "diagnostics")
    (result,) = tool_returns(list(outcome.messages), name)
    return result


def _input(make_deps: MakeDeps) -> DiagnosticsInput:
    triage = TriageResult(
        decision=TriageDecision(intent=Intent.TELEMETRY_DIAGNOSIS, priority="P2", symptom_summary="s"),
        identity=make_deps(OWN_EMAIL).identity,
    )
    return DiagnosticsInput(triage=triage, message="BGP is flapping")


def test_own_site_and_site_list_are_served(make_deps: MakeDeps) -> None:
    deps = make_deps(OWN_EMAIL)
    own = _call_tool(deps, "get_bgp_status", {"site_id": OWN_SITE})
    assert own.status == TelemetryStatus.OK and own.evidence
    listed = _call_tool(deps, "list_sites", {})
    assert listed.status == TelemetryStatus.OK
    assert OWN_SITE in {s.site_id for s in listed.data.sites}


@pytest.mark.parametrize("tool", SITE_TOOLS)
def test_foreign_site_refused_by_every_site_tool(make_deps: MakeDeps, tool: str) -> None:
    result = _call_tool(make_deps(OWN_EMAIL), tool, {"site_id": FOREIGN_SITE})
    assert result.status == TelemetryStatus.INVALID_ARGUMENT
    assert result.tool_name == tool
    assert result.data is None and result.evidence == []
    assert result.error == "site not in caller account"


def test_foreign_client_diagnostics_refused_after_call(make_deps: MakeDeps) -> None:
    deps = make_deps(OWN_EMAIL)
    assert deps.telemetry.get_client_diagnostics(FOREIGN_EMAIL).status == TelemetryStatus.OK
    result = _call_tool(deps, "get_client_diagnostics", {"user_email": FOREIGN_EMAIL})
    assert result.status == TelemetryStatus.INVALID_ARGUMENT
    assert result.data is None and result.evidence == []
    own = _call_tool(deps, "get_client_diagnostics", {"user_email": "sam.dubois@atlas-eng.com"})
    assert own.status == TelemetryStatus.OK


@pytest.mark.parametrize("tool", ("list_sites", "get_bgp_status", "get_client_diagnostics"))
def test_unverified_or_unknown_caller_refused(make_deps: MakeDeps, tool: str) -> None:
    args = {"user_email": OWN_EMAIL} if tool == "get_client_diagnostics" else {"site_id": OWN_SITE}
    args = {} if tool == "list_sites" else args
    base = make_deps(OWN_EMAIL).identity
    for identity in (
        base.model_copy(update={"is_verified_account_member": False}),
        base.model_copy(update={"account": None}),
    ):
        result = _call_tool(make_deps(OWN_EMAIL, identity=identity), tool, args)
        assert result.status == TelemetryStatus.INVALID_ARGUMENT and result.data is None


def test_run_collects_evidence_in_call_order(make_deps: MakeDeps) -> None:
    deps = make_deps(OWN_EMAIL)
    model = scripted_model(
        [("get_site_status", {"site_id": OWN_SITE}), ("get_bgp_status", {"site_id": OWN_SITE})], HYPOTHESIS
    )
    run = run_diagnostics(_input(make_deps), deps, model)
    assert run.output.inspected_tools == ("get_site_status", "get_bgp_status")
    assert run.output.has_anomaly and not run.output.unavailable_tools
    assert run.output.findings.root_cause_hypothesis == HYPOTHESIS["root_cause_hypothesis"]


def test_foreign_site_in_run_lands_in_unavailable_without_evidence(make_deps: MakeDeps) -> None:
    model = scripted_model([("get_bgp_status", {"site_id": FOREIGN_SITE})], {})
    run = run_diagnostics(_input(make_deps), make_deps(OWN_EMAIL), model)
    assert run.output.evidence_items == ()
    assert [t.tool_name for t in run.output.unavailable_tools] == ["get_bgp_status"]


def test_empty_telemetry_dir_completes_with_unavailable_tools(make_deps: MakeDeps, tmp_path: Path) -> None:
    deps = make_deps(OWN_EMAIL, telemetry=TelemetryService(telemetry_dir=tmp_path))
    model = scripted_model([("list_sites", {}), ("get_bgp_status", {"site_id": OWN_SITE})], {})
    run = run_diagnostics(_input(make_deps), deps, model)
    assert run.output.evidence_items == ()
    assert {t.tool_name for t in run.output.unavailable_tools} == {"list_sites", "get_bgp_status"}


def test_no_tool_call_drops_hypothesis(make_deps: MakeDeps) -> None:
    run = run_diagnostics(_input(make_deps), make_deps(OWN_EMAIL), scripted_model([], HYPOTHESIS))
    assert run.output.inspected_tools == ()
    assert run.output.findings.root_cause_hypothesis is None


def test_model_failure_keeps_gathered_evidence(make_deps: MakeDeps) -> None:
    model = scripted_model([("get_bgp_status", {"site_id": OWN_SITE})], {"kb_query_hints": 5})
    run = run_diagnostics(_input(make_deps), make_deps(OWN_EMAIL), model)
    assert run.output.findings.root_cause_hypothesis is None
    assert run.output.has_anomaly and run.trace.error


def test_prompt_has_headings_and_no_leaks() -> None:
    prompt = load_prompt("diagnostics")
    assert all(f"## {heading}" in prompt for heading in HEADINGS)
    assert "SC-" not in prompt and "expected" not in prompt.lower()
