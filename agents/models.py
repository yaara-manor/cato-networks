from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class TraceStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"
    RETRIED = "RETRIED"


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    arguments: dict[str, Any]
    status: str
    result: dict[str, Any]
    latency_ms: int


class AgentTrace(BaseModel):
    agent_role: str
    tool_calls: list[ToolCall]
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    input: dict[str, Any] = {}
    output: dict[str, Any] | None = None
    model_messages: list[dict[str, Any]] | None = None
    status: TraceStatus = TraceStatus.OK
    error: str | None = None
    cost_usd: Decimal | None = None
