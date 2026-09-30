from typing import Any

from pydantic import BaseModel


class AgentTrace(BaseModel):
    agent_role: str
    tool_calls: list[dict[str, Any]]
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
