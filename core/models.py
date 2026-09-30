from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel

AccountTier = Literal["Premium", "Standard", "Unknown"]
TicketPriority = Literal["P1", "P2", "P3", "P4"]
TicketStatus = Literal["open", "closed", "pending_customer", "pending_approval"]


class CustomerAccount(BaseModel):
    account_id: str
    company: str
    tier: AccountTier
    email_domain: str
    registered_admin_contact: str
    country: str | None = None


class CallerIdentity(BaseModel):
    account: CustomerAccount | None
    caller_email: str | None
    effective_tier: AccountTier
    is_verified_account_member: bool
    is_registered_admin: bool
    claimed_tier_rejected: bool
    needs_country_clarification: bool
    scoping_question: str | None = None


class SLADeadlines(BaseModel):
    priority: TicketPriority
    tier: AccountTier
    timezone_name: str
    product_area: str | None
    started_at: AwareDatetime
    first_response_due: AwareDatetime
    resolution_due: AwareDatetime
    update_cadence: str
    is_24x7: bool
    resolution_paused: bool


class Ticket(BaseModel):
    ticket_id: str
    created_at: AwareDatetime
    channel: str
    customer_id: str
    customer_name: str
    requester_email: str
    company: str
    tier: AccountTier
    site_id: str | None
    product_area: str
    priority: TicketPriority
    subject: str
    body: str
    status: TicketStatus


class RepeatContactResult(BaseModel):
    is_repeat_contact: bool
    matching_tickets: list[Ticket]
    prior_closed_tickets: list[Ticket]
    reason: str | None


class TelemetryEvidence(BaseModel):
    tool_name: str
    metric_key: str
    raw_value: str
    timestamp: AwareDatetime
    is_anomaly: bool


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
