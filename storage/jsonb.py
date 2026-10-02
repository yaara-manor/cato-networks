import json
import re
from typing import Any

from psycopg.types.json import Jsonb

# Postgres rejects NUL in text and jsonb. In JSON text NUL appears as the escape \u0000;
# the pattern only matches an escape preceded by an even run of backslashes, so a literal
# backslash followed by "u0000" in user text survives.
_NUL_ESCAPE = re.compile(r"(?<!\\)((?:\\\\)*)\\u0000")


def strip_nul(text: str) -> str:
    return text.replace("\x00", "")


def _dumps(value: Any) -> str:
    return _NUL_ESCAPE.sub(r"\1", json.dumps(value))


def to_jsonb(value: Any) -> Jsonb:
    return Jsonb(value, dumps=_dumps)
