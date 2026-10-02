from pydantic import AwareDatetime, BaseModel

from core.models import AccountTier, CustomerAccount, Ticket, TicketPriority


class CountryCodeOutput(BaseModel):
    country_code: str | None = None


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


class RepeatContactResult(BaseModel):
    is_repeat_contact: bool
    matching_tickets: list[Ticket]
    prior_closed_tickets: list[Ticket]
    reason: str | None

