import psycopg
import pytest

from actions import approved_action_key
from core.clock import SimulationClock
from core.config import settings
from encoders import embed, rerank
from services.approval_models import SettleOutcome
from storage import ApprovalResolution, ApprovalStatus, SimulatedActionStatus
from tests.approval_desk import Desk
from ui import reviewer_session
from ui.reviewer_session import ReviewerRuntime
from ui.reviewer_view import DecisionForm, DecisionFormError, DecisionKind


def _form(desk: Desk, kind: DecisionKind, **fields: object) -> DecisionForm:
    approval = desk.propose()
    values = {"note": "", "customer_reason": "", "original_payload": approval.payload} | fields
    return DecisionForm.model_validate({"approval_id": approval.id, "kind": kind} | values)


def test_runtime_start_loads_no_models(desk: Desk, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise AssertionError("model loaded")

    monkeypatch.setattr(embed, "load_embedder", boom)
    monkeypatch.setattr(rerank, "load_reranker", boom)

    assert isinstance(ReviewerRuntime.start(desk.conn), ReviewerRuntime)


def test_decision_kinds_map_to_resolutions(desk: Desk) -> None:
    approve = _form(desk, DecisionKind.APPROVE, note=" ok ", customer_reason="Credit applied").to_decision()
    assert (approve.resolution.status, approve.resolution.reviewer_notes) == (ApprovalStatus.APPROVED, "ok")
    assert approve.customer_reason == "Credit applied"

    base = desk.propose().payload
    edit = _form(desk, DecisionKind.EDIT, edited_payload=base | {"amount": "100"}).to_decision()
    assert edit.resolution.status is ApprovalStatus.EDITED and edit.customer_reason is None

    reject = _form(desk, DecisionKind.REJECT, note="no").to_decision()
    assert reject.resolution == ApprovalResolution(status=ApprovalStatus.REJECTED, reviewer_notes="no")


def test_form_blocks_reject_without_note_and_key_changes(desk: Desk) -> None:
    with pytest.raises(DecisionFormError, match="note"):
        _form(desk, DecisionKind.REJECT, note="  ").to_decision()
    base = desk.propose().payload
    for edited in ({**base, "extra": "x"}, {k: v for k, v in base.items() if k != "amount"}, None):
        with pytest.raises(DecisionFormError, match="keys"):
            _form(desk, DecisionKind.EDIT, original_payload=base, edited_payload=edited).to_decision()


def test_runtime_start_settles_approved_but_unsettled(desk: Desk) -> None:
    form = _form(desk, DecisionKind.APPROVE)
    approval = desk.service.resolve(form.to_decision())  # durable decision, no settle: the crash window
    assert approval.settled_at is None

    with psycopg.connect(settings.database_url, autocommit=True) as fresh:
        ReviewerRuntime.start(fresh)

    settled = desk.store.get_approval(approval.id)
    assert settled is not None and settled.settled_at is not None
    actions = desk.store.list_simulated_actions(approval.conversation_id)
    outcome = [a.status for a in actions if a.idempotency_key == approved_action_key(approval.id)]
    assert outcome == [SimulatedActionStatus.DONE]
    assert len([m for m in desk.store.list_messages(approval.conversation_id) if m.turn > 1]) == 1


def test_card_shows_done_dispatch_after_decision(desk: Desk) -> None:
    form = _form(desk, DecisionKind.APPROVE)
    result = ReviewerRuntime(SimulationClock()).approvals(desk.conn).decide(form.to_decision())
    assert result.settle is SettleOutcome.SETTLED

    case = reviewer_session.load_case(result.approval.conversation_id)

    assert case is not None
    (card,) = case.approvals
    assert card.dispatch is not None and card.dispatch.status is SimulatedActionStatus.DONE
