from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from guardrails import ActionType, ApprovalStatus, MarkerKind
from guardrails.models import SessionGuardHistory
from orchestration import TurnResult
from storage import Approval, ConversationSnapshot, ConversationStage, MessageSender, StoredMessage
from storage.models import Conversation, StateSnapshot
from tools.models import TelemetryEvidence
from ui.chat_view import ApprovalBannerState, ChatView, MessageRole

NOW = datetime(2026, 8, 28, 17, tzinfo=UTC)
CID = uuid4()


def _evidence(value: str = "3") -> TelemetryEvidence:
    return TelemetryEvidence(tool_name="get_bgp", metric_key="flaps", raw_value=value, timestamp=NOW, is_anomaly=True)


def _message(sender: MessageSender, content: str, **fields: Any) -> StoredMessage:
    base: dict[str, Any] = {
        "id": uuid4(), "conversation_id": CID, "turn": 1, "sender": sender, "content": content,
        "citations": (), "telemetry_evidence": (), "created_at": NOW,
    }  # fmt: skip
    return StoredMessage(**(base | fields))


def _approval(status: ApprovalStatus, settled: bool = False) -> Approval:
    return Approval(
        id=uuid4(), conversation_id=CID, message_id=uuid4(), action_type=ActionType.CREDIT,
        payload={"amount": "500"}, status=status, idempotency_key="k", reviewer_notes="SECRET-NOTE",
        edited_payload=None, requested_at=NOW, resolved_at=None, customer_reason=None,
        settled_at=NOW if settled else None,
    )  # fmt: skip


def _snapshot(*messages: StoredMessage) -> ConversationSnapshot:
    conversation = Conversation(
        id=CID, account_id=None, contact_email=None, customer_tier="Unknown", active_site_id=None,
        stage=ConversationStage.IDLE, guard_history=SessionGuardHistory(), last_turn=1, last_seq=0,
        state=StateSnapshot(), created_at=NOW, updated_at=NOW,
    )  # fmt: skip
    return ConversationSnapshot(
        conversation=conversation, messages=messages, pending_approvals=(), open_turn_traces=()
    )


@pytest.mark.parametrize(
    ("status", "settled", "state"),
    [
        (ApprovalStatus.PENDING, False, ApprovalBannerState.PENDING),
        (ApprovalStatus.APPROVED, False, ApprovalBannerState.FINALIZING),
        (ApprovalStatus.EDITED, False, ApprovalBannerState.FINALIZING),
        (ApprovalStatus.APPROVED, True, ApprovalBannerState.APPROVED),
        (ApprovalStatus.EDITED, True, ApprovalBannerState.APPROVED),
        (ApprovalStatus.REJECTED, True, ApprovalBannerState.REJECTED),
    ],
)
def test_banner_state_and_title_only(status: ApprovalStatus, settled: bool, state: ApprovalBannerState) -> None:
    view = ChatView.from_snapshot(_snapshot(), [_approval(status, settled)])
    assert [(b.state, b.title) for b in view.banners] == [(state, "Service credit")]
    assert "500" not in view.model_dump_json() and "SECRET-NOTE" not in view.model_dump_json()


@pytest.mark.parametrize(
    ("result", "offered"),
    [
        (TurnResult(reply="r", path=(), escalation_offered=True).model_dump(mode="json"), True),
        (TurnResult(reply="r", path=()).model_dump(mode="json"), False),
        (None, False),
    ],
)
def test_escalation_flag_from_latest_reply(result: dict[str, Any] | None, offered: bool) -> None:
    messages = (_message(MessageSender.CUSTOMER, "hi"), _message(MessageSender.AGENT, "r", result=result))
    assert ChatView.from_snapshot(_snapshot(*messages), []).escalation_offered is offered


def test_messages_strip_markers_dedupe_chips_and_map_badges() -> None:
    reply = _message(
        MessageSender.AGENT,
        "Raise MTU [kb:tunnels#mtu] and see [policy:POL-SLA] [telemetry:get_bgp]",
        citations=(
            {"kind": "kb", "ref": "tunnels#mtu", "title": "MTU", "url": "https://x/mtu"},
            {"kind": "policy", "ref": "POL-SLA", "title": "SLA", "url": ""},
        ),
        telemetry_evidence=(_evidence(), _evidence(), _evidence("9")),
    )
    view = ChatView.from_snapshot(_snapshot(_message(MessageSender.CUSTOMER, "[kb:a#b] hi"), reply), [])
    customer, support = view.messages
    assert (customer.role, customer.text, customer.citations) == (MessageRole.CUSTOMER, "[kb:a#b] hi", ())
    assert support.role is MessageRole.SUPPORT
    assert support.text == "Raise MTU and see"
    assert [(b.kind, b.url) for b in support.citations] == [(MarkerKind.KB, "https://x/mtu"), (MarkerKind.POLICY, None)]
    assert [c.text for c in support.evidence] == ["flaps 3", "flaps 9"]


def test_escalation_banner_survives_settle_notice() -> None:
    reply = TurnResult(reply="r", path=(), escalation_offered=True).model_dump(mode="json")
    messages = (
        _message(MessageSender.CUSTOMER, "hi"),
        _message(MessageSender.AGENT, "r", result=reply),
        _message(MessageSender.AGENT, "Your request was reviewed.", result=None),
    )
    assert ChatView.from_snapshot(_snapshot(*messages), []).escalation_offered is True
