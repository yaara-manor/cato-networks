from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_core import to_jsonable_python

# PydanticAI's default name for the structured-output tool; not a real tool call.
_OUTPUT_TOOL_PREFIX = "final_result"


def tool_returns(messages: list[ModelMessage], tool_name: str) -> tuple[Any, ...]:
    """Raw returned objects of `tool_name`, in call order."""
    return tuple(
        part.content
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == tool_name
    )


def _jsonable_dict(content: Any) -> dict[str, Any]:
    jsonable = to_jsonable_python(content)
    return jsonable if isinstance(jsonable, dict) else {"result": jsonable}


def tool_call_dicts(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    """Kwargs for `ToolCall`, pairing each call with its return by `tool_call_id`.

    Calls without a return (failed validation, retries) are skipped.
    """
    returns = {
        part.tool_call_id: part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    calls: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if not isinstance(part, ToolCallPart) or part.tool_name.startswith(_OUTPUT_TOOL_PREFIX):
                continue
            ret = returns.get(part.tool_call_id)
            if ret is None:
                continue
            elapsed = ret.timestamp - message.timestamp
            calls.append(
                {
                    "tool_name": part.tool_name,
                    "arguments": part.args_as_dict(),
                    "status": str(getattr(ret.content, "status", "OK")),
                    "result": _jsonable_dict(ret.content),
                    "latency_ms": max(0, int(elapsed.total_seconds() * 1000)),
                }
            )
    return calls
