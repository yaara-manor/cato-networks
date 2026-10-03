from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from streamlit.testing.v1 import AppTest

from agents import SupportAction
from agents.models import SupportActionKind as Kind
from guardrails import ApprovalStatus
from orchestration import TurnResult
from retrieval.models import RetrievedPassage
from services.approval_models import ReviewerDecision
from storage import ApprovalResolution, MessageSender, StateStore, TurnLockTimeout
from tests.approval_desk import PRIYA, Desk
from tests.orchestration.conftest import Scripted
from tests.ui.conftest import MakeApp
from tools.models import TelemetryEvidence
from ui import session

AMOUNT = "7777"
CREDIT = SupportAction(
    kind=Kind.CREDIT,
    payload={"ticket_id": "x", "amount": AMOUNT, "incident_id": "INC-1", "period": "2026-09"},
    reason="outage",
)
TICKET = SupportAction(
    kind=Kind.CREATE_TICKET,
    payload={"subject": "Site down", "body": "tunnel down", "product_area": "VPN"},
    reason="track",
)


def _page(at: AppTest) -> str:
    elements = [*at.markdown, *at.text, *at.info, *at.success, *at.warning, *at.caption, *at.code]
    return "\n".join(str(e.value) for e in elements)


def _button(at: AppTest, label: str) -> Any:
    return next(b for b in at.button if b.label == label)


def _send(at: AppTest, text: str) -> AppTest:
    return at.chat_input[0].set_value(text).run()


def _as_priya(at: AppTest) -> AppTest:
    at.run()
    at.selectbox(key="scenario").set_value("Custom").run()
    at.text_input(key="email").set_value(PRIYA).run()
    return _button(at, "New conversation").click().run()


def _conversation_id(at: AppTest) -> UUID:
    return at.session_state.conversation_id


def test_multi_turn_history_reload_and_garbage_id(
    make_app: MakeApp, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    at = make_app().run()
    assert not at.exception
    _send(at, "first question")
    _send(at, "second question")
    assert "Here is your answer." in _page(at)
    assert [t.content for t in scripted.inputs["resolution"][-1][0].history][:1] == ["first question"]

    reloaded = make_app()
    reloaded.query_params["conversation_id"] = str(_conversation_id(at))
    reloaded.run()
    assert reloaded.session_state.conversation_id == _conversation_id(at)
    assert "first question" in _page(reloaded) and "second question" in _page(reloaded)

    garbage = make_app()
    garbage.query_params["conversation_id"] = "not-a-uuid"
    garbage.run()
    assert not garbage.exception
    assert garbage.session_state.conversation_id != _conversation_id(at)
    assert "first question" not in _page(garbage)


def test_scenario_switch_starts_conversation_for_that_account(make_app: MakeApp, conn: psycopg.Connection[Any]) -> None:
    at = make_app().run()
    first = _conversation_id(at)
    options = at.selectbox(key="scenario").options
    at.selectbox(key="scenario").set_value(options[2]).run()
    assert _conversation_id(at) != first
    row = conn.execute(
        "select account_id, contact_email, customer_tier from conversations where id = %s", (_conversation_id(at),)
    ).fetchone()
    assert row is not None and row[0] is not None and row[1] == at.text_input(key="email").value
    assert not [w for w in at.text_input if "tier" in w.label.lower() or "account" in w.label.lower()]


def test_citations_and_evidence_chips(make_app: MakeApp, scripted: Scripted) -> None:
    scripted.reply = "Lower the MTU [kb:tunnels#mtu]. Escalation rules [policy:POL-SEV1]."
    scripted.passages = (
        RetrievedPassage(
            passage_id="p1", slug="tunnels", title="Tunnel MTU", public_url="https://help.example.com/mtu",
            site_updated_at=None, heading="MTU", heading_anchor="mtu", body="b", lex_rank=1, vec_rank=1,
            rrf_score=0.1, rerank_score=0.9,
        ),
    )  # fmt: skip
    scripted.evidence = (
        TelemetryEvidence(
            tool_name="get_bgp", metric_key="flaps", raw_value="42", timestamp=datetime(2026, 8, 28, tzinfo=UTC),
            is_anomaly=True,
        ),
    )  # fmt: skip
    at = make_app().run()
    _send(at, "tunnel drops")

    assert not at.exception
    assert not at.get("link_button")
    assert any("Lower the MTU [1](https://help.example.com/mtu#mtu)." in str(m.value) for m in at.markdown)
    assert not any("[kb:" in str(m.value) for m in at.markdown)
    assert any("flaps 42" in str(m.value) for m in at.markdown)
    _button(at, "POL-SEV1: Sev-1 definition and escalation (internal policy)").click().run()
    assert "Sev-1 definition and escalation" in _page(at)


def test_reply_without_citations_or_evidence_and_markup_is_safe(make_app: MakeApp, scripted: Scripted) -> None:
    scripted.reply = "<script>alert(1)</script> **bold** " + "long " * 2000
    at = make_app().run()
    for turn in range(25):  # 50+ messages
        _send(at, f"<img src=x onerror=alert({turn})>")
    assert not at.exception
    assert len(at.chat_message) >= 50
    assert not at.get("link_button")
    assert not [m for m in at.markdown if m.proto.allow_html]


def test_pending_banner_titles_action_only_and_input_stays_enabled(
    make_app: MakeApp, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    scripted.actions = (TICKET, CREDIT)
    at = _as_priya(make_app())
    _send(at, "credit please")
    assert any("Awaiting review by our support team: Service credit" in str(i.value) for i in at.info)
    assert AMOUNT not in _page(at)
    assert not at.chat_input[0].disabled

    service = Desk.create(conn).service
    (approval,) = StateStore(conn).list_approvals(_conversation_id(at))
    approved = ApprovalResolution(status=ApprovalStatus.APPROVED)
    service.resolve(ReviewerDecision(approval_id=approval.id, resolution=approved))
    at.run()
    assert any("being finalized" in str(i.value) for i in at.info)

    service.settle_unsettled()
    at.run()
    assert any(str(s.value) == "Approved: Service credit" for s in at.success)
    notices = [m for m in StateStore(conn).list_messages(_conversation_id(at)) if m.turn > 1]
    assert len(notices) == 1 and notices[0].sender is MessageSender.AGENT
    assert notices[0].content in _page(at)


def test_rejection_shows_customer_reason_never_reviewer_notes(
    make_app: MakeApp, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    scripted.actions = (TICKET, CREDIT)
    at = _as_priya(make_app())
    _send(at, "credit please")
    (approval,) = StateStore(conn).list_approvals(_conversation_id(at))
    rejection = ApprovalResolution(status=ApprovalStatus.REJECTED, reviewer_notes="INTERNAL-NOTE-XYZ")
    service = Desk.create(conn).service
    reason = "Outside the credit window"
    service.resolve(ReviewerDecision(approval_id=approval.id, resolution=rejection, customer_reason=reason))
    service.settle_unsettled()
    at.run()

    page = _page(at)
    assert any("Not approved: Service credit" in str(w.value) for w in at.warning)
    assert "Outside the credit window" in page and "INTERNAL-NOTE-XYZ" not in page


def test_escalation_banner_then_gone_after_next_reply(make_app: MakeApp, scripted: Scripted) -> None:
    scripted.escalate = True
    at = make_app().run()
    _send(at, "help")
    assert any("support engineer will follow up" in str(i.value) for i in at.info)
    scripted.escalate = False
    _send(at, "thanks")
    assert not any("support engineer will follow up" in str(i.value) for i in at.info)


def test_lock_timeout_notice_then_retry_reuses_message_id(
    make_app: MakeApp, conn: psycopg.Connection[Any], monkeypatch: Any
) -> None:
    real = session.run_customer_turn
    seen: list[UUID] = []

    def flaky(conversation_id: UUID, text: str, message_id: UUID) -> TurnResult:
        seen.append(message_id)
        if len(seen) == 1:
            raise TurnLockTimeout
        return real(conversation_id, text, message_id)

    monkeypatch.setattr(session, "run_customer_turn", flaky)
    at = make_app().run()
    _send(at, "hello")
    assert any(session.LOCK_NOTICE in str(w.value) for w in at.warning)

    _button(at, "Retry").click().run()

    assert len(seen) == 2 and seen[0] == seen[1]
    assert not any(session.LOCK_NOTICE in str(w.value) for w in at.warning)
    messages = StateStore(conn).list_messages(_conversation_id(at))
    customer_rows = [m for m in messages if m.sender is MessageSender.CUSTOMER]
    assert len(customer_rows) == 1


def test_trace_tab_lists_the_turn(make_app: MakeApp) -> None:
    at = make_app().run()
    _send(at, "site down")
    labels = [e.label for e in at.expander]
    assert len(labels) == 2 and labels[0].startswith("Worked for ") and labels[1] == "Turn 1"
    assert "TRIAGE" in _page(at)


def test_finished_reply_folds_its_steps_and_shows_the_answer(make_app: MakeApp, scripted: Scripted) -> None:
    scripted.reply = "Here is the fix."
    at = make_app().run()
    _send(at, "site down")
    work = next(e for e in at.expander if e.label.startswith("Worked for "))
    assert "Here is the fix." in _page(at)
    assert "TRIAGE" in "\n".join(str(t.value) for t in work.text)
    assert all(s.state != "running" for s in at.status)
