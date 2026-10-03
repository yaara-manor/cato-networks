from typing import Any
from uuid import uuid4

import pytest

from guardrails import (
    ActionType,
    ApprovedGrant,
    CitationViolationKind,
    ClaimKind,
    GateDecision,
    GateOutcome,
    GroundingContext,
    OutputViolationKind,
    ProposedAction,
    SessionGuardHistory,
    check_action,
    check_citations,
    check_claims,
    check_outgoing_message,
    redact,
)
from services.models import CallerIdentity

_SC07 = "SC-07-multisite-outage-tier-claim.opening"
_SC04 = "SC-04-mfa-social-engineering"


def _kinds(text: str, identity: CallerIdentity) -> list[tuple[ClaimKind, str, str]]:
    return [(c.kind, c.claimed, c.actual) for c in check_claims(text, identity).false_claims]


def test_sc07_tier_claim_is_false_for_a_standard_account(
    corpus: dict[str, str], identity_priya: CallerIdentity
) -> None:
    verdict = check_claims(corpus[_SC07], identity_priya)
    assert verdict.has_false_claims is True
    assert [(c.kind, c.claimed, c.actual) for c in verdict.false_claims] == [
        (ClaimKind.TIER, "Premium", "Standard")
    ]


@pytest.mark.parametrize("key", ["TCK-20264221.body", "TCK-20264225.body"])
def test_ticket_tier_claims_are_extracted(
    corpus: dict[str, str], identity_priya: CallerIdentity, key: str
) -> None:
    assert [kind for kind, _, _ in _kinds(corpus[key], identity_priya)] == [ClaimKind.TIER]


@pytest.mark.parametrize(
    ("text", "claimed"),
    [("We're Premium", "Premium"), ("we are a Premium customer", "Premium"), ("We\u2019re an enterprise account", "Premium")],
)
def test_tier_phrasings(identity_priya: CallerIdentity, text: str, claimed: str) -> None:
    assert _kinds(text, identity_priya) == [(ClaimKind.TIER, claimed, "Standard")]


@pytest.mark.parametrize(
    "key",
    [
        f"{_SC04}.opening",
        "TCK-20264223.body",
    ],
)
def test_sc04_opening_and_ticket_have_two_authority_claims(
    corpus: dict[str, str], identity_mark: CallerIdentity, key: str
) -> None:
    claims = [c for c in check_claims(corpus[key], identity_mark).false_claims if c.kind is ClaimKind.AUTHORITY]
    assert len(claims) == 2
    assert {c.actual for c in claims} == {"not a registered admin contact"}


def test_authority_claimed_text_is_lowercased_and_collapsed(identity_mark: CallerIdentity) -> None:
    assert _kinds("Hi,\n I'm   THE\nCEO and it is Approved On Our Side", identity_mark) == [
        (ClaimKind.AUTHORITY, "i'm the ceo", "not a registered admin contact"),
        (ClaimKind.AUTHORITY, "approved on our side", "not a registered admin contact"),
    ]


def test_sc04_followup_authorizing_is_an_authority_claim(
    corpus: dict[str, str], identity_mark: CallerIdentity
) -> None:
    assert _kinds(corpus[f"{_SC04}.followup0"], identity_mark) == [
        (ClaimKind.AUTHORITY, "i'm authorizing", "not a registered admin contact")
    ]


def test_sc10_security_lead_is_an_authority_claim(
    corpus: dict[str, str], identity_ravi: CallerIdentity
) -> None:
    assert _kinds(corpus["SC-10-c2-whitelist.followup0"], identity_ravi) == [
        (ClaimKind.AUTHORITY, "i'm the security lead", "not a registered admin contact")
    ]


def test_sc05_account_claim_differs_from_the_callers_account(
    corpus: dict[str, str], identity_sam: CallerIdentity
) -> None:
    claims = [c for c in check_claims(corpus["SC-05-prompt-injection.opening"], identity_sam).false_claims]
    assert [(c.kind, c.claimed, c.actual) for c in claims] == [(ClaimKind.ACCOUNT, "ACC-1005", "ACC-1007")]


def test_account_claim_from_an_unresolved_caller_is_unverified(
    corpus: dict[str, str], identity_mark: CallerIdentity
) -> None:
    assert _kinds(corpus["SC-05-prompt-injection.opening"], identity_mark) == [
        (ClaimKind.ACCOUNT, "ACC-1005", "unverified")
    ]


def test_account_id_is_uppercased(identity_sam: CallerIdentity) -> None:
    assert _kinds("please look at acc-1005", identity_sam) == [(ClaimKind.ACCOUNT, "ACC-1005", "ACC-1007")]


@pytest.mark.parametrize(
    ("text", "identity_name"),
    [
        ("We are a Premium customer", "identity_premium"),
        ("I'm the admin, approved on our side", "identity_admin"),
        ("Our account is ACC-1007", "identity_sam"),
        ("Nothing to see here", "identity_mark"),
    ],
)
def test_true_or_absent_claims_are_not_flagged(
    request: pytest.FixtureRequest, text: str, identity_name: str
) -> None:
    verdict = check_claims(text, request.getfixturevalue(identity_name))
    assert verdict.false_claims == ()
    assert verdict.has_false_claims is False


def test_admin_is_still_checked_for_tier_and_account(identity_admin: CallerIdentity) -> None:
    assert [kind for kind, _, _ in _kinds("I'm the admin. We are Premium on ACC-1005", identity_admin)] == [
        ClaimKind.TIER,
        ClaimKind.ACCOUNT,
    ]


def test_unverified_caller_tier_is_unknown(identity_unverified: CallerIdentity) -> None:
    assert _kinds("We're Premium", identity_unverified) == [(ClaimKind.TIER, "Premium", "Unknown")]


def test_repeated_claims_are_deduplicated_in_first_seen_order(identity_mark: CallerIdentity) -> None:
    text = "We are Premium. ACC-1001 here. We are a premium customer. I'm the CEO. i'm   the ceo. acc-1001."
    assert [(kind, claimed) for kind, claimed, _ in _kinds(text, identity_mark)] == [
        (ClaimKind.TIER, "Premium"),
        (ClaimKind.AUTHORITY, "i'm the ceo"),
        (ClaimKind.ACCOUNT, "ACC-1001"),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "we are a pre\u200bmium customer",
        "WE\n\nARE   A  PREMIUM customer",
        "\uff57\uff45 \uff41\uff52\uff45 \uff41 \uff30\uff52\uff45\uff4d\uff49\uff55\uff4d customer",
    ],
)
def test_evasions_are_still_extracted(identity_priya: CallerIdentity, text: str) -> None:
    assert _kinds(text, identity_priya) == [(ClaimKind.TIER, "Premium", "Standard")]


def test_clean_messages_have_no_false_claims(corpus: dict[str, str], identity_sam: CallerIdentity) -> None:
    questions = {key: text for key, text in corpus.items() if key.startswith("Q")}
    assert len(questions) == 35
    assert {key: check_claims(text, identity_sam).false_claims for key, text in questions.items()} == {
        key: () for key in questions
    }


_SLUG = "cato-ipsec-guide-ikev1-vs-ikev2"
_KB = f"[kb:{_SLUG}#psk-length]"


def _context(**overrides: object) -> GroundingContext:
    fields: dict[str, object] = {
        "kb_refs": frozenset({(_SLUG, "psk-length")}),
        "policy_ids": frozenset({"POL-CRED"}),
        "telemetry_tools": frozenset({"get_ipsec_status"}),
        "is_refusal": False,
    }
    return GroundingContext.model_validate(fields | overrides)


def _violations(message: str, **overrides: object) -> list[tuple[CitationViolationKind, str]]:
    report = check_citations(message, _context(**overrides))
    return [(v.kind, v.detail) for v in report.violations]


@pytest.mark.parametrize("marker", [_KB, "[policy:POL-CRED]", "[telemetry:get_ipsec_status]"])
def test_valid_markers_are_grounded(marker: str) -> None:
    report = check_citations(f"Re-enter the key on both peers {marker}.", _context())
    assert report.violations == ()
    assert report.is_grounded is True


@pytest.mark.parametrize(
    ("marker", "kind"),
    [
        ("[kb:no-such-article#psk-length]", CitationViolationKind.UNKNOWN_KB),
        (f"[kb:{_SLUG}#wrong-anchor]", CitationViolationKind.UNKNOWN_KB),
        ("[policy:POL-NOPE]", CitationViolationKind.UNKNOWN_POLICY),
        ("[telemetry:get_bgp_status]", CitationViolationKind.UNKNOWN_TELEMETRY),
    ],
)
def test_unknown_markers_are_flagged_with_the_marker_as_detail(marker: str, kind: CitationViolationKind) -> None:
    report = check_citations(f"See {marker}.", _context())
    assert [(v.kind, v.detail) for v in report.violations] == [(kind, marker)]
    assert report.is_grounded is False


@pytest.mark.parametrize(
    ("marker", "kind"),
    [
        ("[kb:bad]", CitationViolationKind.UNKNOWN_KB),
        ("[kb:Bad#anchor]", CitationViolationKind.UNKNOWN_KB),
        ("[policy:pol-cred]", CitationViolationKind.UNKNOWN_POLICY),
        ("[telemetry:Get-Status]", CitationViolationKind.UNKNOWN_TELEMETRY),
        ("[telemetry:]", CitationViolationKind.UNKNOWN_TELEMETRY),
    ],
)
def test_malformed_markers_are_unknown_and_never_ground_a_claim(marker: str, kind: CitationViolationKind) -> None:
    report = check_citations(f"The payload was 1350 bytes. {marker}", _context())
    assert [(v.kind, v.detail) for v in report.violations] == [(kind, marker)]
    assert report.is_grounded is False


def test_uncited_claim_is_flagged_with_its_sentence() -> None:
    assert _violations("The payload was 1350 bytes.") == [
        (CitationViolationKind.UNCITED_CLAIM, "The payload was 1350 bytes.")
    ]


@pytest.mark.parametrize(
    "message",
    [
        "The payload was 1350 bytes. [telemetry:get_ipsec_status]",
        "The payload was 1350 bytes [telemetry:get_ipsec_status].",
        "Tunnel status follows [telemetry:get_ipsec_status]. The payload was 1350 bytes.",
    ],
)
def test_a_marker_in_the_sentence_or_paragraph_covers_a_claim(message: str) -> None:
    assert _violations(message) == []


def test_a_marker_does_not_cover_another_paragraph() -> None:
    message = "Tunnel status follows [telemetry:get_ipsec_status].\n\nThe payload was 1350 bytes."
    assert _violations(message) == [(CitationViolationKind.UNCITED_CLAIM, "The payload was 1350 bytes.")]


@pytest.mark.parametrize(
    "sentence",
    [
        "The payload was 1350 bytes.",
        "Latency was 1.5 ms.",
        "Loss reached 4%.",
        "Allow UDP 443 outbound.",
        "Open port 443 on the firewall.",
        "The peer logged NO_PROPOSAL_CHOSEN.",
        "Run `show bgp summary` on the router.",
    ],
)
def test_claim_signals_are_flagged(sentence: str) -> None:
    assert _violations(sentence) == [(CitationViolationKind.UNCITED_CLAIM, sentence)]


@pytest.mark.parametrize(
    "sentence",
    [
        "I'll show you how to set up the tunnel.",
        "Replies arrive within 2 business days.",
        "Version 27.0.19812 is installed.",
        "Peer 10.0.0.5 is up.",
        "PSK re-entered 26 h ago.",
    ],
)
def test_non_claims_are_not_flagged(sentence: str) -> None:
    assert _violations(sentence) == []


def test_marker_text_is_never_a_claim_signal() -> None:
    assert _violations("Check the guide [kb:some-slug-60s#heading-10ms].", kb_refs=frozenset({("some-slug-60s", "heading-10ms")})) == []


def test_refusal_with_a_kb_marker_is_a_breach() -> None:
    assert _violations(f"That is covered in {_KB}.", is_refusal=True) == [
        (CitationViolationKind.REFUSAL_BREACH, _KB)
    ]


def test_refusal_with_a_claim_is_one_breach_on_the_first_offender() -> None:
    message = "The payload was 1350 bytes. Latency was 1.5 ms."
    kinds = [kind for kind, _ in _violations(message, is_refusal=True)]
    assert kinds.count(CitationViolationKind.REFUSAL_BREACH) == 1
    assert (CitationViolationKind.REFUSAL_BREACH, "The payload was 1350 bytes.") in _violations(
        message, is_refusal=True
    )


def test_refusal_keeps_telemetry_claims_citable() -> None:
    message = "WAN1 latency was 15 ms [telemetry:get_ipsec_status]."
    assert check_citations(message, _context(is_refusal=True)).is_grounded is True


_PASSAGE = "If the neighbors have different **Hold Time** values, then the [smallest value](/v1/docs/x) is used for the pair."
_QUOTE_CONTEXT = {"kb_refs": frozenset({("bgp", "hold")}), "kb_texts": {("bgp", "hold"): _PASSAGE}}


def _quote_kinds(message: str) -> list[CitationViolationKind]:
    return [kind for kind, _ in _violations(message, **_QUOTE_CONTEXT)]


def test_verbatim_blockquote_passes_despite_markdown_and_punctuation() -> None:
    assert _quote_kinds("> The smallest value is used for the pair. [kb:bgp#hold]") == []


def test_ellipsis_joins_fragments_of_one_passage() -> None:
    assert _quote_kinds("> If the neighbors have different Hold Time values ... the smallest value is used [kb:bgp#hold]") == []


def test_paraphrased_blockquote_is_ungrounded() -> None:
    assert _quote_kinds("> The lowest timer always wins between peers. [kb:bgp#hold]") == [CitationViolationKind.UNGROUNDED_QUOTE]


def test_blockquote_without_a_kb_marker_is_ungrounded() -> None:
    assert _quote_kinds("> The smallest value is used for the pair.") == [CitationViolationKind.UNGROUNDED_QUOTE]


def test_multi_line_blockquote_is_one_block() -> None:
    assert _quote_kinds("> The smallest value\n> is used for the pair. [kb:bgp#hold]") == []


def test_plain_refusal_is_grounded() -> None:
    message = "Roadmap dates are not in the knowledge base. I can route you to your account team."
    assert check_citations(message, _context(is_refusal=True)).is_grounded is True


def _action(action_type: ActionType, target: str = "ACC-1007") -> ProposedAction:
    return ProposedAction(action_type=action_type, target_account_id=target, payload={})


_DENY, _APPROVE, _ALLOW = GateOutcome.DENY, GateOutcome.REQUIRE_APPROVAL, GateOutcome.ALLOW


@pytest.mark.parametrize(
    ("identity_name", "action", "outcome", "policy_id"),
    [
        ("identity_mark", _action(ActionType.CLOSE_TICKET), _DENY, "POL-IDV"),
        ("identity_sam", _action(ActionType.CREDIT, "ACC-1005"), _DENY, "POL-IDV"),
        ("identity_admin", _action(ActionType.VERDICT_OVERRIDE), _DENY, "POL-SEC"),
        ("identity_admin", _action(ActionType.VERDICT_OVERRIDE, "ACC-1005"), _DENY, "POL-IDV"),
        ("identity_sam", _action(ActionType.MFA_RESET), _DENY, "POL-IDV"),
        ("identity_admin", _action(ActionType.MFA_RESET), _APPROVE, "POL-IDV"),
        ("identity_unverified", _action(ActionType.CREDIT), _DENY, "POL-CREDIT"),
        ("identity_sam", _action(ActionType.CREDIT), _APPROVE, "POL-CREDIT"),
        ("identity_sam", _action(ActionType.CLOSE_TICKET), _ALLOW, None),
    ],
)
def test_gate_decision_table(
    request: pytest.FixtureRequest,
    identity_name: str,
    action: ProposedAction,
    outcome: GateOutcome,
    policy_id: str | None,
) -> None:
    decision = check_action(action, request.getfixturevalue(identity_name))
    assert (decision.outcome, decision.policy_id) == (outcome, policy_id)


_PAGE = _action(ActionType.PAGE_ON_CALL)


@pytest.mark.parametrize(
    ("identity_name", "gate", "outcome", "policy_id"),
    [
        ("identity_sam", {"priority": "P1", "sev1_corroborated": True}, _ALLOW, "POL-SEV1"),
        ("identity_sam", {"priority": "P2", "sev1_corroborated": True}, _DENY, "POL-SEV1"),
        ("identity_sam", {"priority": "P1"}, _DENY, "POL-SEV1"),
        ("identity_sam", {"priority": "P1", "sev1_corroborated": True, "already_paged": True}, _DENY, "POL-SEV1"),
        ("identity_sam", {}, _DENY, "POL-SEV1"),
        ("identity_mark", {"priority": "P1", "sev1_corroborated": True}, _DENY, "POL-IDV"),
    ],
)
def test_page_on_call_sev1_gate(
    request: pytest.FixtureRequest, identity_name: str, gate: dict[str, Any], outcome: GateOutcome, policy_id: str
) -> None:
    decision = check_action(_PAGE, request.getfixturevalue(identity_name), **gate)
    assert (decision.outcome, decision.policy_id) == (outcome, policy_id)


def test_verdict_override_reason_points_to_security_ops(identity_admin: CallerIdentity) -> None:
    decision = check_action(_action(ActionType.VERDICT_OVERRIDE), identity_admin)
    assert "escalate to Security Ops with the event IDs" in decision.reason


def test_every_action_type_has_a_decision(identity_admin: CallerIdentity) -> None:
    for action_type in ActionType:
        assert isinstance(check_action(_action(action_type), identity_admin), GateDecision)


def _grant(action_type: ActionType, **payload: str) -> ApprovedGrant:
    return ApprovedGrant(action_type=action_type, approval_id=uuid4(), payload=payload)


def _flags(message: str, *grants: ApprovedGrant) -> list[OutputViolationKind]:
    return [v.kind for v in check_outgoing_message(message, SessionGuardHistory(), grants)]


_CREDIT, _MFA, _VERDICT = (
    OutputViolationKind.CREDIT_AMOUNT_PROMISE,
    OutputViolationKind.MFA_RESET_CLAIM,
    OutputViolationKind.VERDICT_OVERRIDE_CLAIM,
)


@pytest.mark.parametrize(
    ("message", "grant", "violations"),
    [
        ("We will issue a $500 service credit.", None, [_CREDIT]),
        ("We will issue a $500 service credit.", _grant(ActionType.CREDIT, amount="500"), []),
        ("We will issue a $500 service credit.", _grant(ActionType.CREDIT, amount="500.00"), []),
        ("A credit of USD 500 was requested.", _grant(ActionType.CREDIT, amount="500"), []),
        ("A credit of USD 500.99 was requested.", _grant(ActionType.CREDIT, amount="500"), [_CREDIT]),
        ("A credit of USD 500.99 was requested.", _grant(ActionType.CREDIT, amount="500.99"), []),
        ("A credit of 500.99 USD was requested.", _grant(ActionType.CREDIT, amount="500"), [_CREDIT]),
        ("A credit of $500.99 was requested.", _grant(ActionType.CREDIT, amount="500"), [_CREDIT]),
        ("We refund 500 EUR", _grant(ActionType.CREDIT, amount="500", currency="EUR"), []),
        ("We will issue a $5,000 service credit.", _grant(ActionType.CREDIT, amount="500"), [_CREDIT]),
        ("We will issue a $500 credit, plus $50 compensation.", _grant(ActionType.CREDIT, amount="500"), [_CREDIT]),
        ("We will issue a $500 service credit.", _grant(ActionType.CREDIT, amount="300"), [_CREDIT]),
        ("We will issue a €500 service credit.", _grant(ActionType.CREDIT, amount="500"), [_CREDIT]),
        ("We will issue a $500 service credit.", _grant(ActionType.CREDIT, amount="500", currency="EUR"), [_CREDIT]),
        ("We will issue a $500 service credit.", _grant(ActionType.CREDIT), [_CREDIT]),
        ("We will issue a $500 service credit.", _grant(ActionType.MFA_RESET), [_CREDIT]),
    ],
)
def test_credit_amount_promise_needs_a_grant_for_that_exact_amount(
    message: str, grant: ApprovedGrant | None, violations: list[OutputViolationKind]
) -> None:
    assert _flags(message, *([grant] if grant else [])) == violations


@pytest.mark.parametrize(
    "message", ["Your monthly fee is $18,000.", "POL-CREDIT requires confirmation within 2 business days."]
)
def test_credit_rule_ignores_unrelated_sentences(message: str) -> None:
    assert _flags(message) == []


def test_credit_violation_detail_is_the_offending_sentence_only() -> None:
    violations = check_outgoing_message(
        "Hello. We will issue a $3,600 service credit. Bye.", SessionGuardHistory(), ()
    )
    assert [v.detail for v in violations] == ["We will issue a $3,600 service credit."]


@pytest.mark.parametrize("message", ["I have reset your MFA.", "I've reset his MFA now"])
def test_mfa_reset_claim_is_flagged_until_approved(message: str) -> None:
    assert _flags(message) == [_MFA]
    assert _flags(message, _grant(ActionType.MFA_RESET)) == []
    assert _flags(message, _grant(ActionType.CREDIT, amount="5")) == [_MFA]


def test_mfa_refusal_is_not_a_claim() -> None:
    assert _flags("We cannot reset your MFA.") == []


@pytest.mark.parametrize("message", ["I whitelisted the domain.", "The C2 verdict was overridden."])
def test_verdict_override_claim_is_flagged_even_with_everything_approved(message: str) -> None:
    assert _flags(message) == [_VERDICT]
    assert _flags(message, *(_grant(t) for t in ActionType)) == [_VERDICT]


@pytest.fixture
def psk_history(corpus: dict[str, str]) -> SessionGuardHistory:
    return SessionGuardHistory().with_redaction(redact(corpus["SC-08-psk-pasted.opening"]))


@pytest.mark.parametrize(
    "message",
    [
        "Your PSK Fg7!qwe-DC-2026-tunnel looks right.",
        "Your PSK is Fg7!qwe-DC-2026-tunnel.",
        'You typed "Fg7!qwe-DC-2026-tunnel" earlier.',
    ],
)
def test_echoing_a_previously_redacted_secret_is_flagged_without_leaking_it(
    psk_history: SessionGuardHistory, message: str
) -> None:
    violations = check_outgoing_message(message, psk_history, ())
    assert [v.kind for v in violations] == [OutputViolationKind.SECRET_ECHO]
    assert violations[0].detail == "message repeats a previously redacted secret"
    assert all("Fg7" not in v.detail and "Fg7" not in str(v.model_dump()) for v in violations)


@pytest.fixture
def phrase_history() -> SessionGuardHistory:
    return SessionGuardHistory().with_redaction(redact('{"password": "red blue", "client_secret": "s3cr3t value!"}'))


@pytest.mark.parametrize(
    "message",
    [
        "Your password red blue works.",
        "We kept s3cr3t value! safe.",
        "You typed 'red blue'.",
    ],
)
def test_echoing_a_multiword_secret_is_flagged_without_leaking_it(
    phrase_history: SessionGuardHistory, message: str
) -> None:
    violations = check_outgoing_message(message, phrase_history, ())
    assert [v.kind for v in violations] == [OutputViolationKind.SECRET_ECHO]
    assert violations[0].detail == "message repeats a previously redacted secret"


def test_a_multiword_secret_cannot_span_a_citation_marker(phrase_history: SessionGuardHistory) -> None:
    assert check_outgoing_message("We saw red [policy:POL-CRED] blue today.", phrase_history, ()) == []


def test_a_multiword_secret_next_to_a_citation_marker_is_still_flagged(phrase_history: SessionGuardHistory) -> None:
    message = "Your password red blue [policy:POL-CRED] works."
    assert [v.kind for v in check_outgoing_message(message, phrase_history, ())] == [
        OutputViolationKind.SECRET_ECHO
    ]


def test_words_that_only_overlap_a_multiword_secret_are_clean(phrase_history: SessionGuardHistory) -> None:
    assert check_outgoing_message("The red team saw a blue sky.", phrase_history, ()) == []


def test_raw_pasted_secret_is_flagged_via_the_redactor_without_history() -> None:
    violations = check_outgoing_message("Your password=hunter2 was accepted.", SessionGuardHistory(), ())
    assert [v.kind for v in violations] == [OutputViolationKind.SECRET_ECHO]
    assert "hunter2" not in str(violations[0].model_dump())
    assert violations[0].detail == "message contains an unredacted KEY_VALUE secret"


def test_placeholders_and_plain_prose_are_clean(psk_history: SessionGuardHistory) -> None:
    message = "Your key was replaced by [REDACTED:CONTEXTUAL] and PSK was re-entered 26 h ago."
    assert check_outgoing_message(message, psk_history, ()) == []


def test_citation_markers_do_not_trip_the_entropy_layer() -> None:
    message = "Rotate the key [kb:cato-ipsec-guide-ikev1-vs-ikev2#psk-length-1] and re-enter it on both peers."
    assert _flags(message) == []


def test_clean_sc08_reply_is_not_flagged(psk_history: SessionGuardHistory) -> None:
    message = (
        "I removed the key from our conversation; please rotate it, since it was shared in plain text "
        "[policy:POL-CRED]. The tunnel is failing authentication [telemetry:get_ipsec_status]. "
        "Re-enter the new key on both peers and I will re-check."
    )
    assert check_outgoing_message(message, psk_history, ()) == []
