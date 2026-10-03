import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from agents import (
    AgentRun,
    DiagnosticEvidence,
    DiagnosticsInput,
    SupportDeps,
    TriageInput,
    TriageResult,
)
from core.config import settings
from orchestration import TurnResult
from storage import ConversationStage, MessageSender, StateStore, TurnLockTimeout
from tests.orchestration.conftest import PRIYA, Harness, Scripted


@dataclass
class Slow(Scripted):
    """Scripted agents that sleep; `spans` records triage timing, `in_diagnostics` marks the crash point."""

    triage_delay: float = 0.0
    diagnostics_delay: float = 0.0
    spans: list[tuple[float, float]] = field(default_factory=list)
    in_diagnostics: threading.Event = field(default_factory=threading.Event)

    def triage(self, data: TriageInput, deps: SupportDeps) -> AgentRun[TriageResult]:
        start = time.monotonic()
        time.sleep(self.triage_delay)
        run = super().triage(data, deps)
        self.spans.append((start, time.monotonic()))
        return run

    def diagnostics(self, data: DiagnosticsInput, deps: SupportDeps) -> AgentRun[DiagnosticEvidence]:
        self.in_diagnostics.set()
        time.sleep(self.diagnostics_delay)
        return super().diagnostics(data, deps)


WorkerConns = Callable[[], psycopg.Connection[Any]]


def _in_thread(fn: Callable[[], TurnResult], out: list[TurnResult | BaseException]) -> threading.Thread:
    def run() -> None:
        try:
            out.append(fn())
        except BaseException as exc:  # noqa: BLE001 - surfaced to the asserting test thread
            out.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


@pytest.fixture
def worker_conns() -> Iterator[Callable[[], psycopg.Connection[Any]]]:
    conns: list[psycopg.Connection[Any]] = []

    def connect() -> psycopg.Connection[Any]:
        conn = psycopg.connect(settings.database_url, autocommit=True)
        conns.append(conn)
        return conn

    yield connect
    for conn in conns:
        conn.close()


def _messages(harness: Harness, conversation_id: UUID) -> Any:
    with harness.connect() as conn:
        snapshot = StateStore(conn).rehydrate(conversation_id)
    assert snapshot is not None
    return snapshot


def test_concurrent_turns_serialize(harness: Harness, worker_conns: WorkerConns) -> None:
    cid = harness.new_conversation(PRIYA)
    a, b = Slow(triage_delay=0.5), Slow(triage_delay=0.5)
    wa, wb = harness.workflow(a, worker_conns()), harness.workflow(b, worker_conns())
    out: list[TurnResult | BaseException] = []
    threads = [
        _in_thread(lambda: wa.run_turn(cid, "first", uuid4()), out),
        _in_thread(lambda: wb.run_turn(cid, "second", uuid4()), out),
    ]
    for t in threads:
        t.join()
    assert all(isinstance(r, TurnResult) for r in out)
    first, second = sorted(a.spans + b.spans)
    assert first[1] <= second[0]
    snapshot = _messages(harness, cid)
    assert sorted({m.turn for m in snapshot.messages}) == [1, 2]
    later = a if a.spans[0] == second else b
    assert len(later.inputs["triage"][0].history) == 2


def test_concurrent_duplicate_message_id_runs_once(harness: Harness, worker_conns: WorkerConns) -> None:
    cid, mid = harness.new_conversation(PRIYA), uuid4()
    a, b = Slow(triage_delay=0.3), Slow(triage_delay=0.3)
    wa, wb = harness.workflow(a, worker_conns()), harness.workflow(b, worker_conns())
    out: list[TurnResult | BaseException] = []
    threads = [
        _in_thread(lambda: wa.run_turn(cid, "help", mid), out),
        _in_thread(lambda: wb.run_turn(cid, "help", mid), out),
    ]
    for t in threads:
        t.join()
    assert [r.reply for r in out if isinstance(r, TurnResult)] == ["Here is your answer."] * 2
    assert a.calls.count("triage") + b.calls.count("triage") == 1
    assert a.calls.count("resolution") + b.calls.count("resolution") == 1
    customer = [m for m in _messages(harness, cid).messages if m.sender is MessageSender.CUSTOMER]
    assert len(customer) == 1


def test_lock_timeout_leaves_no_rows(
    harness: Harness, worker_conns: WorkerConns, monkeypatch: pytest.MonkeyPatch
) -> None:
    cid, blocked_id = harness.new_conversation(PRIYA), uuid4()
    holder = Slow(triage_delay=2)
    wa = harness.workflow(holder, worker_conns())
    wb = harness.workflow(Scripted(), worker_conns())
    out: list[TurnResult | BaseException] = []
    thread = _in_thread(lambda: wa.run_turn(cid, "first", uuid4()), out)
    time.sleep(0.3)
    monkeypatch.setattr(settings, "turn_lock_timeout_s", 0.3)
    with pytest.raises(TurnLockTimeout):
        wb.run_turn(cid, "second", blocked_id)
    thread.join()
    assert all(m.id != blocked_id for m in _messages(harness, cid).messages)


def test_killed_worker_retry_completes_turn(harness: Harness, worker_conns: WorkerConns) -> None:
    cid, mid = harness.new_conversation(PRIYA), uuid4()
    crashing = Slow(diagnostics_delay=3)
    conn_a = worker_conns()
    pid = conn_a.execute("select pg_backend_pid()").fetchone()
    assert pid is not None
    out: list[TurnResult | BaseException] = []
    thread = _in_thread(lambda: harness.workflow(crashing, conn_a).run_turn(cid, "help", mid), out)
    assert crashing.in_diagnostics.wait(5)
    with harness.connect() as killer:
        killer.execute("select pg_terminate_backend(%s)", (pid[0],))
    thread.join()
    assert isinstance(out[0], psycopg.OperationalError)
    harness.workflow(Scripted(), worker_conns()).run_turn(cid, "help", mid)
    snapshot = _messages(harness, cid)
    replies = [m for m in snapshot.messages if m.sender is MessageSender.AGENT]
    assert len(replies) == 1
    assert snapshot.conversation.stage is ConversationStage.IDLE
