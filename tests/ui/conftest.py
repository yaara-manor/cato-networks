from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from streamlit.testing.v1 import AppTest

from tests.orchestration.conftest import _CLEANUP_SQL, Scripted, conn, harness, scripted  # noqa: F401
from ui import session

APP = str(Path(__file__).parents[2] / "ui" / "customer_app.py")
MakeApp = Callable[[], AppTest]


@pytest.fixture
def make_app(
    scripted: Scripted, conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> Iterator[MakeApp]:
    """The real customer script on real Postgres; only the four agents are scripted, no encoder is loaded."""
    monkeypatch.setattr(session, "ports_override", scripted.ports)
    monkeypatch.setattr(session, "warm_models", lambda: None)
    before = {row[0] for row in conn.execute("select id from conversations").fetchall()}
    tickets = conn.execute("select coalesce(max(substring(ticket_id from 5)::int), 0) from tickets").fetchone()
    yield lambda: AppTest.from_file(APP, default_timeout=30)
    created = [row[0] for row in conn.execute("select id from conversations").fetchall() if row[0] not in before]
    for statement in _CLEANUP_SQL:
        conn.execute(statement, {"ids": created})
    conn.execute("delete from tickets where substring(ticket_id from 5)::int > %s", (tickets[0] if tickets else 0,))
