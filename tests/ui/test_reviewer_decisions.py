from collections.abc import Callable
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from core.config import settings
from services.approval_models import ReviewerDecision
from storage import Approval, ApprovalStatus, SimulatedActionStatus
from tests.approval_desk import Desk
from ui import reviewer_session


def _text(at: AppTest) -> str:
    return "\n".join(str(e.value) for e in [*at.text, *at.warning, *at.info, *at.error, *at.code])


def _open(at: AppTest, approval: Approval) -> AppTest:
    at.query_params["conversation_id"] = str(approval.conversation_id)
    return at.run()


def _widget(elements: Any, key: str) -> Any:
    return next(e for e in elements if e.key == f"{key}")


def _dispatches(desk: Desk, approval: Approval) -> list[Any]:
    return [
        a
        for a in desk.store.list_simulated_actions(approval.conversation_id)
        if a.idempotency_key == f"approval:{approval.id}"
    ]


def test_approve_dispatches_notifies_and_shows_resolved_card(reviewer: AppTest, desk: Desk) -> None:
    approval = desk.propose()
    at = _open(reviewer, approval)
    _widget(at.text_input, f"note-{approval.id}").set_value("looks fine")
    _widget(at.text_input, f"reason-{approval.id}").set_value("Credit applied")

    _widget(at.button, f"approve-{approval.id}").click().run()

    saved = desk.store.get_approval(approval.id)
    assert saved is not None and saved.status is ApprovalStatus.APPROVED
    assert (saved.reviewer_notes, saved.customer_reason) == ("looks fine", "Credit applied")
    assert [a.status for a in _dispatches(desk, approval)] == [SimulatedActionStatus.DONE]
    assert any(m.turn > 1 for m in desk.store.list_messages(approval.conversation_id))
    page = _text(at)
    assert "APPROVED" in page and "Action DONE" in page and "Settled" in page
    assert not [b for b in at.button if b.key == f"approve-{approval.id}"]


def test_edit_persists_payload_and_reject_needs_note(reviewer: AppTest, desk: Desk) -> None:
    approval = desk.propose()
    at = _open(reviewer, approval)
    _widget(at.button, f"reject-{approval.id}").click().run()
    assert "a rejection needs an internal note" in _text(at)
    assert (desk.store.get_approval(approval.id) or approval).status is ApprovalStatus.PENDING

    _widget(at.text_input, f"edit-{approval.id}-amount").set_value("100")
    next(b for b in at.button if b.label == "Submit edit").click().run()

    saved = desk.store.get_approval(approval.id)
    assert saved is not None and saved.status is ApprovalStatus.EDITED
    assert saved.edited_payload is not None and saved.edited_payload["amount"] == "100"


def test_reject_with_note_closes_without_dispatch(reviewer: AppTest, desk: Desk) -> None:
    approval = desk.propose()
    at = _open(reviewer, approval)
    _widget(at.text_input, f"note-{approval.id}").set_value("not eligible")

    _widget(at.button, f"reject-{approval.id}").click().run()

    saved = desk.store.get_approval(approval.id)
    assert saved is not None and saved.status is ApprovalStatus.REJECTED
    assert _dispatches(desk, approval) == []


def test_losing_reviewer_sees_already_resolved_and_one_dispatch(
    reviewer: AppTest, desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    approval = desk.propose()
    at = _open(reviewer, approval)
    real_decide: Callable[[ReviewerDecision], Any] = reviewer_session.decide

    def other_reviewer_first(decision: ReviewerDecision) -> Any:
        desk.service.decide(decision)  # the winner
        return real_decide(decision)

    monkeypatch.setattr(reviewer_session, "decide", other_reviewer_first)
    _widget(at.button, f"approve-{approval.id}").click().run()

    assert not at.exception
    assert "already resolved" in _text(at)
    saved = desk.store.get_approval(approval.id)
    assert saved is not None and saved.status is ApprovalStatus.APPROVED
    assert len(_dispatches(desk, approval)) == 1


def test_busy_settle_reports_decision_saved_not_error(
    reviewer: AppTest, desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    approval = desk.propose()
    at = _open(reviewer, approval)
    monkeypatch.setattr(settings, "turn_lock_timeout_s", 0.2)

    with desk.store.turn_lock(approval.conversation_id):  # a customer turn is in flight on another connection
        _widget(at.button, f"approve-{approval.id}").click().run()

    assert not at.exception and not at.error
    saved = desk.store.get_approval(approval.id)
    assert saved is not None and saved.status is ApprovalStatus.APPROVED and saved.settled_at is None
    assert "Decision saved, customer notice pending." in _text(at)
