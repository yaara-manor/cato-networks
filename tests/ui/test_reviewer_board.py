from collections.abc import Callable
from uuid import UUID, uuid4

from streamlit.testing.v1 import AppTest

from storage import MessageSender, StateSnapshot, StateStore
from tests.ui.conftest import NOW, SeedCase


def _text(at: AppTest) -> str:
    elements = [*at.text, *at.warning, *at.info, *at.error, *at.code, *at.markdown, *at.subheader]
    return "\n".join(str(e.value) for e in elements)


def _open(at: AppTest, conversation_id: UUID) -> AppTest:
    at.query_params["conversation_id"] = str(conversation_id)
    return at.run()


def test_board_lists_pending_with_tier_and_age_and_selection_sets_query(reviewer: AppTest, seed_case: SeedCase) -> None:
    cid = seed_case()
    at = reviewer.run()
    assert not at.exception

    pick = next(b for b in at.button if b.key == f"pick-{cid}")
    assert pick.label.startswith("unknown | Standard | 1 pending | ")  # seeded without an account
    pick.click().run()

    assert at.query_params["conversation_id"] == [str(cid)]
    assert "Select a conversation" not in _text(at)


def test_escalated_tab_flags_paged_and_offered_without_buttons(
    reviewer: AppTest, store: StateStore, new_conversation: Callable[[], UUID]
) -> None:
    paged, offered = new_conversation(), new_conversation()
    store.save_state(paged, StateSnapshot(data={"oncall_paged": True}), NOW)
    turn = store.append_customer_message(offered, uuid4(), "q", NOW).turn
    result = {"escalation_offered": True}
    store.complete_turn(offered, turn, MessageSender.AGENT, "a", (), (), uuid4(), NOW, result=result)

    at = reviewer.run()

    assert "on-call paged" in _text(at) and "escalation offered" in _text(at)  # badges render as markdown
    assert not [b for b in at.button if b.key in (f"pick-{paged}", f"pick-{offered}")]  # no pending: nothing to pick
    assert str(paged) in _text(at) and str(offered) in _text(at)


def test_case_panels_show_sla_repeat_evidence_and_kb(reviewer: AppTest, seed_case: SeedCase) -> None:
    page = _text(_open(reviewer, seed_case()))

    assert "First response" in page and "Resolution" in page
    assert "Repeat contact: same site within 7 days" in page
    assert "ANOMALY get_link_quality avg_packet_loss_pct = 7.5" in page
    assert "get_bgp_status: UNAVAILABLE" in page
    assert "[cited]" in page and "[candidate]" in page
    assert reviewer.get("vega_lite_chart")  # one chart per link metric
    assert "Credit" in page and "Approve" in [b.label for b in reviewer.button]
