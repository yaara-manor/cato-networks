from typing import Literal

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


class Citation(BaseModel):
    slug: str
    title: str
    heading: str
    heading_anchor: str
    public_url: str
    rrf_score: float
    rerank_score: float
