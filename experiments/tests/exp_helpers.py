import asyncio
import re
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

T = TypeVar("T")
PASSAGE_ID_RE = re.compile(r"passage_id=(\S+)")


def run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def tool_returns(messages: list[ModelMessage]) -> list[str]:
    return [
        str(part.content)
        for m in messages
        for part in m.parts
        if isinstance(part, ToolReturnPart)
    ]


def scripted_model(
    searches: list[str],
    final: Callable[[list[str]], dict[str, Any]],
    seen_returns: list[str] | None = None,
) -> FunctionModel:
    """A model that issues one `search_kb` call per entry in `searches`, then returns `final(passage_ids)`
    as the structured answer, where passage_ids are the ids present in the tool returns it has seen."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = tool_returns(messages)
        if len(returns) < len(searches):
            return ModelResponse(parts=[ToolCallPart("search_kb", {"query": searches[len(returns)]})])
        if seen_returns is not None:
            seen_returns.extend(returns)
        ids = [pid for r in returns for pid in PASSAGE_ID_RE.findall(r)]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, final(ids))])

    return FunctionModel(respond, model_name="scripted")
