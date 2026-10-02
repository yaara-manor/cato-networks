from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from core.config import settings
from guardrails.models import (
    InjectionCategory,
    InjectionVerdict,
    RedactionFinding,
    RedactionResult,
    SecretKind,
    SessionGuardHistory,
)
from storage import ConversationStage, MessageSender, StateSnapshot, StateStore
from tools.models import TelemetryEvidence

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
Restart = Callable[[], psycopg.Connection[Any]]
NewConversation = Callable[[], UUID]
LATER = datetime(2026, 10, 1, 9, 1, tzinfo=UTC)
EVIDENCE = TelemetryEvidence(
    tool_name="get_bgp_status",
    metric_key="routes_count",
    raw_value="1024",
    timestamp=NOW,
    is_anomaly=True,
)


def _reply(store: StateStore, cid: UUID, turn: int, content: str = "done") -> None:
    store.complete_turn(cid, turn, MessageSender.AGENT, content, (), (), uuid4(), NOW)


def test_turn_roundtrip_with_citation_and_evidence(
    store: StateStore, created_ids: list[UUID], restart: Restart
) -> None:
    cid = store.create_conversation("ACC-1007", "a@b.co", "Premium", NOW).id
    created_ids.append(cid)
    store.append_customer_message(cid, uuid4(), "tunnel down", NOW)
    store.complete_turn(
        cid,
        1,
        MessageSender.AGENT,
        "check bgp",
        [{"tag": "[kb:x#y]"}],
        [EVIDENCE],
        uuid4(),
        LATER,
    )
    with restart() as fresh:
        messages = StateStore(fresh).list_messages(cid)
        conversation = StateStore(fresh).get_conversation(cid)
    assert [(m.turn, m.sender) for m in messages] == [
        (1, MessageSender.CUSTOMER),
        (1, MessageSender.AGENT),
    ]
    assert messages[1].citations == ({"tag": "[kb:x#y]"},)
    assert messages[1].telemetry_evidence == (EVIDENCE,)
    assert conversation is not None
    assert (conversation.stage, conversation.last_turn) == (ConversationStage.IDLE, 1)


def test_duplicate_customer_message_is_idempotent(
    store: StateStore, new_conversation: NewConversation, conn: psycopg.Connection[Any]
) -> None:
    cid = new_conversation()
    message_id = uuid4()
    first = store.append_customer_message(cid, message_id, "hi", NOW)
    store.set_stage(cid, ConversationStage.TRIAGE, NOW)
    assert store.append_customer_message(cid, message_id, "hi", NOW) == first
    conversation = store.get_conversation(cid)
    assert conversation is not None
    assert (conversation.last_turn, conversation.stage) == (1, ConversationStage.TRIAGE)
    assert conn.execute("select count(*) from messages where conversation_id = %s", (cid,)).fetchone() == (1,)


def test_stage_follows_customer_message_and_ignores_stale_turn(
    store: StateStore, new_conversation: NewConversation
) -> None:
    cid = new_conversation()
    store.append_customer_message(cid, uuid4(), "one", NOW)
    store.append_customer_message(cid, uuid4(), "two", NOW)
    conversation = store.get_conversation(cid)
    assert conversation is not None
    assert conversation.stage is ConversationStage.INGESTION_GUARD
    _reply(store, cid, 1)  # stale retry of turn 1
    stale = store.get_conversation(cid)
    assert stale is not None
    assert stale.stage is ConversationStage.INGESTION_GUARD
    _reply(store, cid, 2)
    final = store.get_conversation(cid)
    assert final is not None
    assert final.stage is ConversationStage.IDLE


def test_complete_turn_rejects_customer_sender(store: StateStore, new_conversation: NewConversation) -> None:
    cid = new_conversation()
    with pytest.raises(ValueError):
        store.complete_turn(cid, 1, MessageSender.CUSTOMER, "x", (), (), uuid4(), NOW)


def test_complete_turn_idempotent_on_message_id(store: StateStore, new_conversation: NewConversation) -> None:
    cid = new_conversation()
    store.append_customer_message(cid, uuid4(), "q", NOW)
    message_id = uuid4()
    first = store.complete_turn(cid, 1, MessageSender.AGENT, "a", (), (), message_id, NOW)
    assert store.complete_turn(cid, 1, MessageSender.AGENT, "a", (), (), message_id, NOW) == first
    assert len(store.list_messages(cid)) == 2


def test_hostile_text_roundtrips(store: StateStore, new_conversation: NewConversation) -> None:
    cid = new_conversation()
    content = "nul\x00 emoji \U0001f525 " + "x" * 50_000
    stored = store.append_customer_message(cid, uuid4(), content, NOW)
    assert stored.content == content.replace("\x00", "")
    assert store.list_messages(cid)[0] == stored


def test_guard_history_survives_restart(
    store: StateStore, new_conversation: NewConversation, restart: Restart
) -> None:
    cid = new_conversation()
    verdict = InjectionVerdict(
        blocked=True,
        categories=frozenset({InjectionCategory.ROLE_OVERRIDE}),
        rule_ids=("r1",),
    )
    finding = RedactionFinding(kind=SecretKind.JWT, start=0, end=1, sha256="abc")
    history = (
        SessionGuardHistory()
        .with_injection(verdict)
        .with_redaction(RedactionResult(text="x", findings=(finding,)))
    )
    store.save_guard_history(cid, history, NOW)
    with restart() as fresh:
        loaded = StateStore(fresh).get_conversation(cid)
    assert loaded is not None
    assert loaded.guard_history == history
    assert isinstance(loaded.guard_history.secret_hashes, frozenset)


def test_non_autocommit_connection_rejected() -> None:
    with psycopg.connect(settings.database_url) as plain, pytest.raises(ValueError):
        StateStore(plain)


def test_identity_and_state_survive_restart(
    store: StateStore, new_conversation: NewConversation, restart: Restart
) -> None:
    cid = new_conversation()
    store.update_identity(cid, "ACC-1007", "a@b.co", "Premium", "S-1007-01", NOW)
    store.save_state(cid, StateSnapshot(version=1, data={"triage": {"scope": ["a", 1]}}), NOW)
    with restart() as fresh:
        loaded = StateStore(fresh).get_conversation(cid)
    assert loaded is not None
    assert (loaded.customer_tier, loaded.active_site_id, loaded.account_id) == (
        "Premium",
        "S-1007-01",
        "ACC-1007",
    )
    assert loaded.state == StateSnapshot(version=1, data={"triage": {"scope": ["a", 1]}})


def test_default_state_and_unknown_conversation(store: StateStore, new_conversation: NewConversation) -> None:
    loaded = store.get_conversation(new_conversation())
    assert loaded is not None
    assert loaded.state == StateSnapshot(version=1, data={})
    with pytest.raises(LookupError):
        store.set_stage(uuid4(), ConversationStage.IDLE, NOW)


def test_message_id_of_another_conversation_is_rejected(
    store: StateStore, new_conversation: NewConversation
) -> None:
    first, second = new_conversation(), new_conversation()
    message_id = uuid4()
    store.append_customer_message(first, message_id, "hi", NOW)
    with pytest.raises(ValueError, match="another conversation"):
        store.append_customer_message(second, message_id, "hi", NOW)
