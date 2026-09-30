from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, field_validator


class CustomerAccount(BaseModel):
    account_id: str
    tier: Literal["Enterprise", "Standard", "Unknown"]
    domain: str
    admin_email: str


class Ticket(BaseModel):
    ticket_id: str
    account_id: str
    site_id: str
    priority: str
    status: str
    history: list[str]
    requester: str | None = None


class TelemetryEvidence(BaseModel):
    tool_name: str
    metric_key: str
    raw_value: str
    timestamp: AwareDatetime
    is_anomaly: bool

    @field_validator("timestamp")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class Citation(BaseModel):
    slug: str
    title: str
    heading: str
    heading_anchor: str
    public_url: str
    rrf_score: float
    rerank_score: float


class ApprovalRecord(BaseModel):
    action_type: Literal["credit", "mfa_reset", "security_override"]
    payload: dict[str, Any]
    status: Literal["pending", "approved", "edited", "rejected"]
    reviewer_notes: str | None = None


class AgentTrace(BaseModel):
    agent_role: str
    tool_calls: list[dict[str, Any]]
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
