from collections.abc import Mapping
from typing import Any, LiteralString, cast

import psycopg
from psycopg import sql

from core.clock import SimulationClock
from core.models import (
    AccountTier,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from core.stopwords import EXCLUDED_WORDS
from services.models import RepeatContactResult

# Space-joined exclusion list, stemmed by postgres on every _stem_texts call so it
# always matches the 'english' stemmer's own output.
_EXCLUDED_TEXT: str = " ".join(sorted(EXCLUDED_WORDS))

_TICKET_COLUMNS: LiteralString = (
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


def _shares_stems(stems_a: frozenset[str], stems_b: frozenset[str]) -> bool:
    return len(stems_a & stems_b) >= 2


def _matches_area_or_symptom(
    candidate: Ticket,
    product_area: str | None,
    symptom_stems: frozenset[str] | None,
    stems_by_ticket: Mapping[str, frozenset[str]],
    peer_tickets: list[Ticket],
) -> bool:
    candidate_stems = stems_by_ticket[candidate.ticket_id]
    if product_area is not None:
        if candidate.product_area.lower() == product_area.strip().lower():
            return True
        return bool(symptom_stems and _shares_stems(candidate_stems, symptom_stems))
    if symptom_stems is not None:
        return _shares_stems(candidate_stems, symptom_stems)
    return any(
        peer.ticket_id != candidate.ticket_id
        and (
            peer.product_area.lower() == candidate.product_area.lower()
            or _shares_stems(candidate_stems, stems_by_ticket[peer.ticket_id])
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
                f"select {_TICKET_COLUMNS} from tickets where ticket_id = %(ticket_id)s",
                {"ticket_id": value},
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
        clauses: list[LiteralString] = ["customer_id = %(account_id)s"]
        params: dict[str, Any] = {"account_id": account_id.strip()}

        if site_id is not None:
            clauses.append("site_id = %(site_id)s")
            params["site_id"] = site_id.strip()
        if product_area is not None:
            clauses.append("lower(product_area) = lower(%(product_area)s)")
            params["product_area"] = product_area.strip()
        if not include_open:
            clauses.append("status != 'open'")

        where_sql: LiteralString = " and ".join(clauses)
        query: LiteralString = (
            f"select {_TICKET_COLUMNS} from tickets "
            f"where {where_sql} order by created_at asc, ticket_id asc"
        )
        with self._conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [_row_to_ticket(row) for row in rows]

    def _stem_texts(self, texts: list[str]) -> list[frozenset[str]]:
        if not texts:
            return []
        with self._conn.cursor() as cur:
            cur.execute(
                """
                select tsvector_to_array(
                    ts_delete(
                        to_tsvector('english', t),
                        tsvector_to_array(to_tsvector('english', %(excluded)s))
                    )
                )
                from unnest(%(texts)s::text[]) with ordinality as x(t, ord)
                order by ord
                """,
                {"texts": texts, "excluded": _EXCLUDED_TEXT},
            )
            rows = cur.fetchall()
        return [frozenset(row[0]) for row in rows]

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
        texts = [f"{t.subject} {t.body}" for t in candidates]
        if symptom_text is not None:
            texts.append(symptom_text)
        stems = self._stem_texts(texts)
        if symptom_text is not None:
            *ticket_stems, symptom_stems = stems
        else:
            ticket_stems, symptom_stems = stems, None
        stems_by_ticket: dict[str, frozenset[str]] = {
            t.ticket_id: stem for t, stem in zip(candidates, ticket_stems, strict=True)
        }
        matching = [
            t
            for t in candidates
            if _matches_area_or_symptom(
                t, product_area, symptom_stems, stems_by_ticket, candidates
            )
        ]
        prior_closed = [t for t in matching if t.status == "closed"]

        is_repeat = len(prior_closed) >= 1 or len(matching) >= 2
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
                    %(created_at)s, %(channel)s, %(customer_id)s, %(customer_name)s,
                    %(requester_email)s, %(company)s, %(tier)s, %(site_id)s,
                    %(product_area)s, %(priority)s, %(subject)s, %(body)s, 'open'
                )
                returning {_TICKET_COLUMNS}
                """,
                {
                    "created_at": created_at,
                    "channel": channel,
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "requester_email": requester_email,
                    "company": company,
                    "tier": tier,
                    "site_id": site_id,
                    "product_area": product_area,
                    "priority": priority,
                    "subject": subject,
                    "body": body,
                },
            )
            row = cur.fetchone()
        if row is None:
            raise RuntimeError("Failed to insert ticket row")
        self._conn.commit()
        return _row_to_ticket(row)

    def update_ticket_status(self, ticket_id: str, status: TicketStatus) -> Ticket:
        return self.update_ticket(ticket_id, status=status)

    def update_ticket(
        self,
        ticket_id: str,
        status: TicketStatus | None = None,
        site_id: str | None = None,
        priority: TicketPriority | None = None,
    ) -> Ticket:
        changes = {
            column: value
            for column, value in (("status", status), ("site_id", site_id), ("priority", priority))
            if value is not None
        }
        if not changes:
            raise ValueError("update_ticket needs at least one of status, site_id, priority")
        query = sql.SQL("update tickets set {} where ticket_id = %(ticket_id)s returning {}").format(
            sql.SQL(", ").join(
                sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder(column)) for column in changes
            ),
            sql.SQL(_TICKET_COLUMNS),
        )
        with self._conn.cursor() as cur:
            row = cur.execute(query, changes | {"ticket_id": ticket_id.strip()}).fetchone()
        if row is None:
            raise ValueError(f"Ticket not found: {ticket_id}")
        self._conn.commit()
        return _row_to_ticket(row)
