import types
from collections.abc import Mapping
from typing import Any

import psycopg

from retrieval.models import PolicyDocument


def _normalize_policy_id(policy_id: str) -> str:
    return policy_id.strip().upper().removesuffix(".MD")


class RetrievalService:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._conn: psycopg.Connection[Any] = connection
        with self._conn.cursor() as cur:
            cur.execute("select id, title, file_path, body from policies order by id")
            rows = cur.fetchall()
        self._policies: Mapping[str, PolicyDocument] = types.MappingProxyType(
            {
                row[0]: PolicyDocument(
                    policy_id=row[0],
                    title=row[1],
                    file_path=row[2],
                    body=row[3],
                )
                for row in rows
            }
        )

    def get_policy(self, policy_id: str) -> PolicyDocument | None:
        return self._policies.get(_normalize_policy_id(policy_id))

    def list_policies(self) -> list[PolicyDocument]:
        return list(self._policies.values())
