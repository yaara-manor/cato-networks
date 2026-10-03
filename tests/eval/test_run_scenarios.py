import uuid

from eval.run_scenarios import Expected, Scenario, cited_refs, score_scenario

_REPLY = (
    "Routes at limit [telemetry:get_bgp_status]. Summarize them [kb:xops-network-playbook-bgp-prefix-exhaustion#step-2]. "
    "See [policy:POL-SLA]."
)


def test_cited_refs_use_must_cite_vocabulary() -> None:
    assert cited_refs([_REPLY]) == (
        "telemetry:bgp_status",
        "xops-network-playbook-bgp-prefix-exhaustion",
        "POL-SLA",
    )


def test_scenario_sends_opening_then_followups_in_order() -> None:
    scenario = Scenario.model_validate(
        {
            "scenario_id": "SC-X",
            "requester_email": "a@b.c",
            "opening_message": "first",
            "simulated_customer_followups": [{"if_agent": "x", "customer": "second"}, {"customer": "third"}],
            "expected": {},
        }
    )
    assert scenario.customer_messages == ("first", "second", "third")


def test_client_diagnostics_marker_counts_as_the_clients_source() -> None:
    assert cited_refs(["Error 408 [telemetry:get_client_diagnostics]"]) == ("telemetry:clients",)


def test_score_flags_missing_cites_and_tools() -> None:
    scenario = Scenario(
        scenario_id="SC-X",
        requester_email="a@b.c",
        opening_message="hi",
        expected=Expected(
            must_cite=("telemetry:bgp_status", "configuring-bgp-neighbors-for-a-cato-socket"),
            must_use_tools=("get_bgp_status", "get_events", "request_human_approval"),
        ),
    )
    calls = [("get_bgp_status", "OK"), ("search_knowledge_base", "LOW_CONFIDENCE_REFUSAL")]
    score = score_scenario(scenario, uuid.uuid4(), ["hello", _REPLY], calls)
    assert score.missing_cites == ("configuring-bgp-neighbors-for-a-cato-socket",)
    assert score.missing_tools == ("get_events",)  # request_human_approval is an action, not scored
    assert (score.kb_searches, score.kb_refusals, score.passed) == (1, 1, False)
