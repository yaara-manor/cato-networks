from collections.abc import Mapping
from typing import Any

import psycopg
from psycopg import sql
from psycopg.abc import QueryNoTemplate
from psycopg.rows import class_row
from pydantic import BaseModel

from storage.jsonb import strip_nul, to_jsonb


def jsonable(value: Any) -> Any:
    """Make a Python value safe for a text or jsonb parameter (no NUL bytes)."""
    if isinstance(value, str):
        return strip_nul(value)
    if isinstance(value, dict | list | tuple):
        return to_jsonb(value)
    return value


def fetch_all[T: BaseModel](
    conn: psycopg.Connection[Any], model: type[T], query: QueryNoTemplate, params: Mapping[str, Any]
) -> list[T]:
    with conn.cursor(row_factory=class_row(model)) as cur:
        return cur.execute(query, params).fetchall()


def fetch_one[T: BaseModel](
    conn: psycopg.Connection[Any], model: type[T], query: QueryNoTemplate, params: Mapping[str, Any]
) -> T | None:
    with conn.cursor(row_factory=class_row(model)) as cur:
        return cur.execute(query, params).fetchone()


def insert_row(conn: psycopg.Connection[Any], table: str, values: Mapping[str, Any]) -> None:
    query = sql.SQL("insert into {} ({}) values ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, values)),
        sql.SQL(", ").join(map(sql.Placeholder, values)),
    )
    conn.execute(query, {k: jsonable(v) for k, v in values.items()})
