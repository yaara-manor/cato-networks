from actions import ActionStatus
from agents.models import SupportActionKind as Kind
from storage import SimulatedActionStatus
from tests.actions.conftest import Actions, action

PAGE = action(Kind.PAGE_ON_CALL, summary="two sites down", site_ids="S-1, S-2")


def test_corroborated_p1_pages_with_incident_ref_and_ack(actions: Actions) -> None:
    context = actions.make_context(priority="P1", sev1_corroborated=True)
    (result,) = actions.dispatcher.dispatch_turn([PAGE], context)
    assert result.status is ActionStatus.DONE
    assert result.reference is not None and result.reference.startswith("INC-")
    assert result.customer_line == (
        f"I paged the on-call engineer (incident {result.reference}); expect acknowledgement within 15 minutes."
    )
    (row,) = actions.store.list_simulated_actions(context.conversation_id)
    assert row.result is not None
    assert row.result["effect"] == {
        "event": "oncall_paged",
        "incident_ref": result.reference,
        "summary": "two sites down",
        "site_ids": ["S-1", "S-2"],
        "priority": "P1",
        "ack_minutes": 15,
    }


def test_uncorroborated_or_non_p1_is_refused_and_writes_nothing(actions: Actions) -> None:
    for kwargs in ({"priority": "P1"}, {"priority": "P2", "sev1_corroborated": True}):
        context = actions.make_context(**kwargs)
        (result,) = actions.dispatcher.dispatch_turn([PAGE], context)
        assert result.status is ActionStatus.REFUSED
        assert actions.store.list_simulated_actions(context.conversation_id) == []


def test_second_page_from_another_message_is_refused_silently(actions: Actions) -> None:
    context = actions.make_context(priority="P1", sev1_corroborated=True)
    actions.dispatcher.dispatch_turn([PAGE], context)
    later = actions.next_turn(context)
    (result,) = actions.dispatcher.dispatch_turn([PAGE], later)
    assert (result.status, result.customer_line) == (ActionStatus.REFUSED, None)
    rows = actions.store.list_simulated_actions(context.conversation_id)
    assert [r.status for r in rows] == [SimulatedActionStatus.DONE]


def test_same_message_retry_replays_the_page(actions: Actions) -> None:
    context = actions.make_context(priority="P1", sev1_corroborated=True)
    (first,) = actions.dispatcher.dispatch_turn([PAGE], context)
    (again,) = actions.dispatcher.dispatch_turn([PAGE], context)
    assert (again.status, again.replayed, again.reference) == (ActionStatus.DONE, True, first.reference)

