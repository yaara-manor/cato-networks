from pathlib import Path
from typing import Any
from uuid import uuid4

from streamlit.testing.v1 import AppTest

from agents.models import AgentRole
from storage import StateStore
from tests.ui.conftest import MakeTrace, SeedCase
from tests.ui.test_case_view import PSK
from tests.ui.test_reviewer_board import _open, _text

UI = Path(__file__).parents[2] / "ui"


def test_model_messages_expander_shows_redacted_and_not_recorded(
    reviewer: AppTest, store: StateStore, seed_case: SeedCase, make_trace: MakeTrace
) -> None:
    cid = seed_case()
    messages: list[dict[str, Any]] = [{"kind": "request", "parts": [{"content": f"the PSK is {PSK}"}]}]
    store.record_trace(make_trace(cid, role=AgentRole.RESOLUTION, model_messages=messages), [])

    at = _open(reviewer, cid)

    page = _text(at)
    assert '"kind": "request"' in page and "not recorded" in page  # seeded steps carry no messages
    assert PSK not in page
    assert not at.exception


def test_customer_code_path_never_touches_model_messages() -> None:
    customer_files = ("customer_app.py", "customer_widgets.py", "chat_view.py", "trace_panel.py")
    for name in customer_files:
        assert "reviewer_" not in (UI / name).read_text()


def test_open_turn_renders_steps_and_totals_match_trace_rows(reviewer: AppTest, seed_case: SeedCase) -> None:
    at = _open(reviewer, seed_case())  # three steps recorded, no reply: a turn interrupted mid-run

    assert "15 ms, 36 tokens" in _text(at)  # 3 traces x (5 ms, 10 + 2 tokens)
    assert any(e.label == "Turn 1 (open)" for e in at.expander)


def test_degraded_case_renders_every_panel_with_no_data_states(reviewer: AppTest, seed_degraded: SeedCase) -> None:
    at = _open(reviewer, seed_degraded())

    page = _text(at)
    assert not at.exception
    assert "Triage: No data" in page and "Evidence: No data" in page and "Knowledge base: No data" in page
    assert "UNAVAILABLE" in page  # the raw tool call result stays visible


def test_unknown_conversation_id_shows_not_found_and_malformed_is_ignored(reviewer: AppTest) -> None:
    at = _open(reviewer, uuid4())
    assert not at.exception
    assert [w.value for w in at.warning] == ["Conversation not found."]

    reviewer.query_params["conversation_id"] = "not-a-uuid"
    at = reviewer.run()
    assert not at.exception and "Select a conversation." in _text(at)
