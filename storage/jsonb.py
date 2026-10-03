import json
import re
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from guardrails.redactor import redact

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


def _redact_leaves(value: Any) -> Any:
    """Redact string leaves only, so JSON structure survives; ISO timestamps are not secrets."""
    match value:
        case str():
            return value if _is_timestamp(value) else redact(value).text
        case dict():
            return {key: _redact_leaves(item) for key, item in value.items()}
        case list():
            return [_redact_leaves(item) for item in value]
        case _:
            return value


def _is_timestamp(text: str) -> bool:
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def redacted_json(payload: dict[str, Any], max_chars: int | None = None) -> dict[str, Any]:
    """Redact secrets in any untrusted JSON payload; `max_chars` truncates (None keeps it whole)."""
    redacted: dict[str, Any] = _redact_leaves(payload)
    if max_chars is None:
        return redacted
    text = json.dumps(redacted, ensure_ascii=False)
    return {"truncated": text[:max_chars]} if len(text) > max_chars else redacted
