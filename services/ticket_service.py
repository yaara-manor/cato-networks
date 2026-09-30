import re
from typing import Any, cast

import psycopg

from core.clock import SimulationClock
from core.models import (
    AccountTier,
    RepeatContactResult,
    Ticket,
    TicketPriority,
    TicketStatus,
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "about",
        "after",
        "again",
        "before",
        "between",
        "could",
        "during",
        "every",
        "from",
        "have",
        "into",
        "issue",
        "only",
        "other",
        "please",
        "since",
        "still",
        "their",
        "there",
        "these",
        "this",
        "today",
        "under",
        "users",
        "using",
        "where",
        "which",
        "while",
        "with",
        "would",
    }
)

_TICKET_COLUMNS: str = (
    "ticket_id, created_at, channel, customer_id, customer_name, "
    "requester_email, company, tier, site_id, product_area, "
    "priority, subject, body, status"
)


def _row_to_ticket(row: tuple[Any, ...]) -> Ticket:
    return Ticket(
        ticket_id=str(row[0]),
        created_at=row[1],
        channel=str(row[2]),
        customer_id=str(row[3]),
        customer_name=str(row[4]),
        requester_email=str(row[5]),
        company=str(row[6]),
        tier=cast(AccountTier, str(row[7])),
        site_id=str(row[8]) if row[8] is not None else None,
        product_area=str(row[9]),
        priority=cast(TicketPriority, str(row[10])),
        subject=str(row[11]),
        body=str(row[12]),
        status=cast(TicketStatus, str(row[13])),
    )


def _symptom_stems(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {tok[:5] for tok in tokens if len(tok) >= 5 and tok not in _STOPWORDS}


def _shares_keywords(text_a: str, text_b: str) -> bool:
    stems_a = _symptom_stems(text_a)
    stems_b = _symptom_stems(text_b)
    return len(stems_a & stems_b) >= 2


def _matches_area_or_symptom(
    candidate: Ticket,
    product_area: str | None,
    symptom_text: str | None,
    peer_tickets: list[Ticket],
) -> bool:
    candidate_text = f"{candidate.subject} {candidate.body}"
    if product_area is not None:
        if candidate.product_area.lower() == product_area.strip().lower():
            return True
        return bool(symptom_text and _shares_keywords(candidate_text, symptom_text))
    if symptom_text is not None:
        return _shares_keywords(candidate_text, symptom_text)
    if candidate.status == "closed":
        return True
    return any(
        peer.ticket_id != candidate.ticket_id
        and (
            peer.product_area.lower() == candidate.product_area.lower()
            or _shares_keywords(candidate_text, f"{peer.subject} {peer.body}")
        )
        for peer in peer_tickets
    )


class TicketService:
    def __init__(
        self,
        connection: psycopg.Connection[Any],
        clock: SimulationClock,
    ) -> None:
        self._conn: psycopg.Connection[Any] = connection
        self._clock: SimulationClock = clock

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        value = ticket_id.strip()
        if not value:
            return None
        with self._conn.cursor() as cur:
            cur.execute(
                f"select {_TICKET_COLUMNS} from tickets where ticket_id = %s",
                (value,),
            )
            row = cur.fetchone()
        return _row_to_ticket(row) if row is not None else None

    def get_ticket_history(
        self,
        account_id: str,
        site_id: str | None = None,
        product_area: str | None = None,
        include_open: bool = True,
    ) -> list[Ticket]:
        clauses: list[str] = ["customer_id = %s"]
        params: list[Any] = [account_id.strip()]

        if site_id is not None:
            clauses.append("site_id = %s")
            params.append(site_id.strip())
        if product_area is not None:
            clauses.append("lower(product_area) = lower(%s)")
            params.append(product_area.strip())
        if not include_open:
            clauses.append("status = 'closed'")

        where_sql = " and ".join(clauses)
        query = (
            f"select {_TICKET_COLUMNS} from tickets "
            f"where {where_sql} order by created_at asc, ticket_id asc"
        )
        with self._conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [_row_to_ticket(row) for row in rows]

    def detect_repeat_contact(
        self,
        account_id: str,
        site_id: str | None = None,
        product_area: str | None = None,
        symptom_text: str | None = None,
        exclude_ticket_id: str | None = None,
    ) -> RepeatContactResult:
        history = self.get_ticket_history(account_id=account_id, site_id=site_id, include_open=True)
        candidates = [
            t for t in history if exclude_ticket_id is None or t.ticket_id != exclude_ticket_id
        ]
        matching = [
            t
            for t in candidates
            if _matches_area_or_symptom(t, product_area, symptom_text, candidates)
        ]
        prior_closed = [t for t in matching if t.status == "closed"]

        is_repeat = (
            len(prior_closed) >= 1
            or (exclude_ticket_id is not None and len(matching) >= 1)
            or len(matching) >= 2
        )
        if not is_repeat:
            return RepeatContactResult(
                is_repeat_contact=False,
                matching_tickets=[],
                prior_closed_tickets=[],
                reason=None,
            )

        scope_label = f"site {site_id}" if site_id else f"account {account_id}"
        ticket_ids = ", ".join(t.ticket_id for t in matching)
        reason = (
            f"Repeat contact detected on {scope_label}: "
            f"{len(matching)} matching historical ticket(s) ({ticket_ids}), "
            f"including {len(prior_closed)} prior closed ticket(s)."
        )
        return RepeatContactResult(
            is_repeat_contact=True,
            matching_tickets=matching,
            prior_closed_tickets=prior_closed,
            reason=reason,
        )

    def create_ticket(
        self,
        customer_id: str,
        customer_name: str,
        requester_email: str,
        company: str,
        tier: AccountTier,
        priority: TicketPriority,
        product_area: str,
        subject: str,
        body: str,
        site_id: str | None = None,
        channel: str = "chat",
    ) -> Ticket:
        created_at = self._clock.now()
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                insert into tickets ({_TICKET_COLUMNS})
                values (
                    (
                        select 'TCK-' || (
                            coalesce(max(substring(ticket_id from 5)::int), 20264199) + 1
                        )::text
                        from tickets
                    ),
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open'
                )
                returning {_TICKET_COLUMNS}
                """,
                (
                    created_at,
                    channel,
                    customer_id,
                    customer_name,
                    requester_email,
                    company,
                    tier,
                    site_id,
                    product_area,
                    priority,
                    subject,
                    body,
                ),
            )
            row = cur.fetchone()
        if row is None:
            raise RuntimeError("Failed to insert ticket row")
        self._conn.commit()
        return _row_to_ticket(row)

    def update_ticket_status(self, ticket_id: str, status: TicketStatus) -> Ticket:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                update tickets
                set status = %s
                where ticket_id = %s
                returning {_TICKET_COLUMNS}
                """,
                (status, ticket_id.strip()),
            )
            row = cur.fetchone()
        if row is None:
            raise ValueError(f"Ticket not found: {ticket_id}")
        self._conn.commit()
        return _row_to_ticket(row)
