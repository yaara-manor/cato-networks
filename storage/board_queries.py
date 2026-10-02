from typing import Any

import psycopg

from storage.models import BoardRow
from storage.sql import fetch_all

# Flags use jsonb equality so a missing path or malformed value reads as false, never an error.
_BOARD_SQL = """
select c.id as conversation_id, c.account_id, c.customer_tier, c.stage,
       coalesce(p.pending_count, 0) as pending_count, p.oldest_pending_at, c.updated_at,
       coalesce(c.state -> 'data' -> 'oncall_paged' = 'true'::jsonb, false) as oncall_paged,
       coalesce(m.result -> 'escalation_offered' = 'true'::jsonb, false) as escalation_offered
from conversations c
left join (
    select conversation_id, count(*) as pending_count, min(requested_at) as oldest_pending_at
    from approvals where status = 'PENDING' group by conversation_id
) p on p.conversation_id = c.id
left join lateral (
    select result from messages
    where conversation_id = c.id and result is not null order by turn desc limit 1
) m on true
order by p.oldest_pending_at nulls last, c.updated_at desc
limit %(limit)s
"""


def list_board_rows(conn: psycopg.Connection[Any], limit: int) -> list[BoardRow]:
    return fetch_all(conn, BoardRow, _BOARD_SQL, {"limit": limit})
