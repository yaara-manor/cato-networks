import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from services.reporting_service import (
    DailyReport,
    PendingApproval,
    SlaState,
    TicketSla,
    deliver,
    sla_state,
)

NOW = datetime(2026, 8, 28, 17, 0, tzinfo=UTC)


def _ticket(ticket_id: str, due_in: timedelta, status: str = "open") -> TicketSla:
    return TicketSla(
        ticket_id=ticket_id,
        company="Acme",
        tier="Premium",
        priority="P2",
        status=status,  # type: ignore[arg-type]
        subject="s",
        resolution_due=NOW + due_in,
        state=sla_state(NOW + due_in, NOW, status),  # type: ignore[arg-type]
    )


def _report() -> DailyReport:
    return DailyReport(
        generated_at=NOW,
        open_tickets=4,
        by_status={"open": 3, "pending_customer": 1},
        by_priority={"P2": 4},
        sla=(
            _ticket("T-ok", timedelta(hours=9)),
            _ticket("T-risk", timedelta(hours=1)),
            _ticket("T-late", timedelta(hours=-3)),
            _ticket("T-paused", timedelta(hours=-3), "pending_customer"),
        ),
        sev1_pages=(),
        escalations_to_human=2,
        pending_approvals=(
            PendingApproval(
                approval_id="abcdef123456",
                conversation_id="c1",
                action_type="CREDIT",
                requested_at=NOW - timedelta(hours=5),
                waiting_hours=5.0,
            ),
        ),
        decided_approvals={"APPROVED": 1},
    )


def test_sla_states_and_attention_order() -> None:
    report = _report()
    assert report.sla_counts() == {"BREACHED": 1, "AT_RISK": 1, "ON_TRACK": 1, "PAUSED": 1}
    assert [t.ticket_id for t in report.attention()] == ["T-late", "T-risk"]
    assert sla_state(NOW, NOW, "open") is SlaState.BREACHED


def test_both_channels_are_written(tmp_path: Path) -> None:
    markdown, csv_file, slack = deliver(_report(), tmp_path)
    assert "T-late" in markdown.read_text() and "CREDIT" in markdown.read_text()
    assert len(csv_file.read_text().splitlines()) == 5
    payload = json.loads(slack.read_text())
    assert "1 breached, 1 at risk" in payload["text"]
