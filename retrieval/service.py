from collections.abc import Mapping
from typing import Any

import psycopg
from psycopg.rows import class_row

from retrieval.models import PolicyDocument


def _normalize_policy_id(policy_id: str) -> str:
    return policy_id.strip().upper().removesuffix(".MD")


class RetrievalService:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._conn: psycopg.Connection[Any] = connection
        with self._conn.cursor(row_factory=class_row(PolicyDocument)) as cur:
            cur.execute(
                "select id as policy_id, title, file_path, body "
                "from policies order by id"
            )
            self._policies: Mapping[str, PolicyDocument] = {
                p.policy_id: p for p in cur.fetchall()
            }

    def get_policy(self, policy_id: str) -> PolicyDocument | None:
        return self._policies.get(_normalize_policy_id(policy_id))

    def list_policies(self) -> list[PolicyDocument]:
        return list(self._policies.values())
