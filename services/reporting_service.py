import argparse
import csv
import io
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import psycopg
from pydantic import AwareDatetime, BaseModel, ConfigDict

from core.clock import SimulationClock
from core.config import REPO_ROOT, settings
from core.models import AccountTier, TicketPriority, TicketStatus
from services.customer_service import CustomerService
from storage.sql import fetch_all

_OUT_DIR: Path = REPO_ROOT / "docs/ops"
AT_RISK_WINDOW = timedelta(hours=2)  # a resolution due within this long is a breach risk
RESOLVED_WINDOW = timedelta(hours=24)  # the report's "today": approvals decided in this long count as resolved
_TOP_ROWS = 10  # rows listed per section in the chat-sized Slack summary

_OPEN_TICKETS_SQL = """
select ticket_id, created_at, customer_id, company, tier, site_id, product_area, priority, status, subject
from tickets where status <> 'closed' order by created_at
"""
_PAGES_SQL = """
select conversation_id::text as conversation_id, coalesce(payload ->> 'summary', '') as summary, completed_at
from simulated_actions where kind = 'PAGE_ON_CALL' and status = 'DONE' order by completed_at desc
"""
_PENDING_SQL = """
select id::text as approval_id, conversation_id::text as conversation_id, action_type, requested_at
from approvals where status = 'PENDING' order by requested_at
"""
_DECIDED_SQL = """
select status, count(*)::int as total from approvals
where status <> 'PENDING' and resolved_at >= %(since)s group by status
"""
_ESCALATED_SQL = """
select count(*)::int as total from messages
where result -> 'escalation_offered' = 'true'::jsonb and created_at >= %(since)s
"""


class SlaState(StrEnum):
    BREACHED = "BREACHED"
    AT_RISK = "AT_RISK"
    ON_TRACK = "ON_TRACK"
    PAUSED = "PAUSED"  # waiting on the customer: the resolution clock is stopped


class _ReportModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class TicketSla(_ReportModel):
    ticket_id: str
    company: str
    tier: AccountTier
    priority: TicketPriority
    status: TicketStatus
    subject: str
    resolution_due: AwareDatetime
    state: SlaState


class Sev1Page(_ReportModel):
    conversation_id: str
    summary: str
    paged_at: AwareDatetime


class PendingApproval(_ReportModel):
    approval_id: str
    conversation_id: str
    action_type: str
    requested_at: AwareDatetime
    waiting_hours: float


class DailyReport(_ReportModel):
    generated_at: AwareDatetime
    open_tickets: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    sla: tuple[TicketSla, ...]
    sev1_pages: tuple[Sev1Page, ...]
    escalations_to_human: int  # replies in the last 24 hours that offered a human handoff
    pending_approvals: tuple[PendingApproval, ...]
    decided_approvals: dict[str, int]  # last 24 hours, by decision

    def sla_counts(self) -> dict[str, int]:
        counts = Counter(t.state.value for t in self.sla)
        return {state.value: counts.get(state.value, 0) for state in SlaState}

    def attention(self) -> tuple[TicketSla, ...]:
        """Tickets that are breached or about to be, worst first."""
        order = {SlaState.BREACHED: 0, SlaState.AT_RISK: 1}
        flagged = [t for t in self.sla if t.state in order]
        return tuple(sorted(flagged, key=lambda t: (order[t.state], t.resolution_due)))

    # -- channel 1: file export ------------------------------------------------

    def to_markdown(self) -> str:
        day = self.generated_at.date().isoformat()
        sla = self.sla_counts()
        lines = [
            f"# Daily operations report, {day}",
            "",
            f"Generated {self.generated_at.isoformat(timespec='minutes')} from conversation and ticket state.",
            "",
            "## Ticket queue",
            "",
            f"**{self.open_tickets}** open tickets (anything not closed).",
            "",
            "| Status | Tickets |",
            "|---|---|",
            *(f"| {status} | {count} |" for status, count in sorted(self.by_status.items())),
            "",
            "| Priority | Tickets |",
            "|---|---|",
            *(f"| {priority} | {count} |" for priority, count in sorted(self.by_priority.items())),
            "",
            "## SLA status (resolution target)",
            "",
            " | ".join(f"{state} {count}" for state, count in sla.items()),
            "",
            f"At risk means the resolution is due within {int(AT_RISK_WINDOW.total_seconds() // 3600)} hours.",
            "",
            *self._table(
                "Breached or at risk",
                ("Ticket", "Company", "Tier", "Priority", "Due", "State"),
                [
                    (t.ticket_id, t.company, t.tier, t.priority, t.resolution_due.strftime("%Y-%m-%d %H:%M"), t.state.value)
                    for t in self.attention()
                ],
            ),
            *self._table(
                "Sev-1 pages (on-call paged by the agent)",
                ("Conversation", "Paged at", "Summary"),
                [(p.conversation_id, p.paged_at.strftime("%Y-%m-%d %H:%M"), p.summary) for p in self.sev1_pages],
            ),
            "## Escalations",
            "",
            f"{self.escalations_to_human} replies in the last 24 hours handed the customer to a human.",
            "",
            *self._table(
                "Pending approvals (oldest first)",
                ("Approval", "Action", "Requested", "Waiting (h)"),
                [
                    (a.approval_id[:8], a.action_type, a.requested_at.strftime("%Y-%m-%d %H:%M"), f"{a.waiting_hours:.1f}")
                    for a in self.pending_approvals
                ],
            ),
            "Approvals decided in the last 24 hours: "
            + (", ".join(f"{s} {n}" for s, n in sorted(self.decided_approvals.items())) or "none")
            + ".",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _table(title: str, header: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
        lines = [f"## {title}", ""]
        if not rows:
            return [*lines, "None.", ""]
        lines += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        lines += ["| " + " | ".join(row) + " |" for row in rows]
        return [*lines, ""]

    def sla_csv(self) -> str:
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["ticket_id", "company", "tier", "priority", "status", "resolution_due", "sla_state", "subject"])
        for t in self.sla:
            writer.writerow(
                [t.ticket_id, t.company, t.tier, t.priority, t.status, t.resolution_due.isoformat(), t.state.value, t.subject]
            )
        return out.getvalue()

    # -- channel 2: Slack message ----------------------------------------------

    def slack_payload(self) -> dict[str, Any]:
        """An incoming-webhook body: counts first, then what needs a person today."""
        day = self.generated_at.date().isoformat()
        sla = self.sla_counts()
        summary = (
            f"*Open tickets:* {self.open_tickets}  |  *SLA:* {sla['BREACHED']} breached, {sla['AT_RISK']} at risk  |  "
            f"*Sev-1 pages:* {len(self.sev1_pages)}  |  *Pending approvals:* {len(self.pending_approvals)}"
        )
        worst = [f"• `{t.ticket_id}` {t.company} {t.priority} {t.state.value}" for t in self.attention()[:_TOP_ROWS]]
        waiting = [
            f"• {a.action_type} waiting {a.waiting_hours:.1f} h" for a in self.pending_approvals[:_TOP_ROWS]
        ]
        blocks: list[dict[str, Any]] = [
            {"type": "header", "text": {"type": "plain_text", "text": f"Daily support operations, {day}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
        ]
        if worst:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Needs attention*\n" + "\n".join(worst)}})
        if waiting:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Approvals waiting*\n" + "\n".join(waiting)}})
        return {"text": f"Daily support operations, {day}: {summary}", "blocks": blocks}


class _OpenTicket(_ReportModel):
    ticket_id: str
    created_at: AwareDatetime
    customer_id: str
    company: str
    tier: AccountTier
    site_id: str | None
    product_area: str
    priority: TicketPriority
    status: TicketStatus
    subject: str


class _Page(_ReportModel):
    conversation_id: str
    summary: str
    completed_at: AwareDatetime


class _Pending(_ReportModel):
    approval_id: str
    conversation_id: str
    action_type: str
    requested_at: AwareDatetime


class _Decided(_ReportModel):
    status: str
    total: int


class _Count(_ReportModel):
    total: int


def sla_state(due: datetime, now: datetime, status: TicketStatus) -> SlaState:
    if status == "pending_customer":
        return SlaState.PAUSED
    if due <= now:
        return SlaState.BREACHED
    return SlaState.AT_RISK if due - now <= AT_RISK_WINDOW else SlaState.ON_TRACK


class ReportingService:
    """Reads ticket and conversation state; knows nothing about where the report goes."""

    def __init__(self, conn: psycopg.Connection[Any], customers: CustomerService, clock: SimulationClock) -> None:
        self._conn = conn
        self._customers = customers
        self._clock = clock

    def _sla_row(self, ticket: _OpenTicket, now: datetime) -> TicketSla:
        account = self._customers.lookup_account(ticket.customer_id)
        deadlines = self._customers.calculate_sla_deadlines(
            ticket.tier,
            ticket.priority,
            account.country if account else None,
            ticket.product_area,
            ticket.created_at,
            ticket.status,
        )
        return TicketSla(
            ticket_id=ticket.ticket_id,
            company=ticket.company,
            tier=ticket.tier,
            priority=ticket.priority,
            status=ticket.status,
            subject=ticket.subject,
            resolution_due=deadlines.resolution_due,
            state=sla_state(deadlines.resolution_due, now, ticket.status),
        )

    def build(self) -> DailyReport:
        now = self._clock.now()
        since = now - RESOLVED_WINDOW
        tickets = fetch_all(self._conn, _OpenTicket, _OPEN_TICKETS_SQL, {})
        pending = fetch_all(self._conn, _Pending, _PENDING_SQL, {})
        return DailyReport(
            generated_at=now,
            open_tickets=len(tickets),
            by_status=dict(Counter(t.status for t in tickets)),
            by_priority=dict(Counter(t.priority for t in tickets)),
            sla=tuple(self._sla_row(t, now) for t in tickets),
            sev1_pages=tuple(
                Sev1Page(conversation_id=p.conversation_id, summary=p.summary, paged_at=p.completed_at)
                for p in fetch_all(self._conn, _Page, _PAGES_SQL, {})
            ),
            escalations_to_human=fetch_all(self._conn, _Count, _ESCALATED_SQL, {"since": since})[0].total,
            pending_approvals=tuple(
                PendingApproval(
                    approval_id=p.approval_id,
                    conversation_id=p.conversation_id,
                    action_type=p.action_type,
                    requested_at=p.requested_at,
                    waiting_hours=max(0.0, (now - p.requested_at).total_seconds() / 3600),
                )
                for p in pending
            ),
            decided_approvals={d.status: d.total for d in fetch_all(self._conn, _Decided, _DECIDED_SQL, {"since": since})},
        )


def deliver(report: DailyReport, out_dir: Path) -> tuple[Path, ...]:
    """Channel 1 writes the Markdown report and the SLA CSV; channel 2 writes the Slack webhook body the
    reviewer's ops channel would receive. The webhook is simulated: nothing leaves the machine."""
    out_dir.mkdir(parents=True, exist_ok=True)
    day = report.generated_at.astimezone(UTC).date().isoformat()
    files = {
        f"daily_report_{day}.md": report.to_markdown(),
        f"daily_report_{day}_sla.csv": report.sla_csv(),
        f"slack_webhook_{day}.json": json.dumps(report.slack_payload(), indent=2),
    }
    paths = tuple(out_dir / name for name in files)
    for path, content in zip(paths, files.values(), strict=True):
        path.write_text(content, encoding="utf-8")
    return paths


def main(out_dir: Path) -> None:
    clock = SimulationClock()
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        report = ReportingService(conn, CustomerService(conn, clock), clock).build()
    for path in deliver(report, out_dir):
        print(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write the daily operations report.")
    parser.add_argument("--out", type=Path, default=_OUT_DIR)
    main(parser.parse_args().out)
