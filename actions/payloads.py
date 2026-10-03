from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.models import TicketPriority, TicketStatus


class ActionPayload(BaseModel):
    """Typed view of `SupportAction.payload`: unknown, missing, blank and NUL-bearing values are errors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def from_payload(cls, raw: dict[str, str]) -> Self:
        if any(not value.strip() or "\x00" in value for value in raw.values()):
            raise ValueError("payload has a blank or NUL value")
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            # Field names only: error text would echo customer-derived input.
            fields = ", ".join(sorted({".".join(map(str, error["loc"])) or "payload" for error in exc.errors()}))
            raise ValueError(f"invalid payload fields: {fields}") from None


class CreateTicketPayload(ActionPayload):
    subject: str
    body: str
    product_area: str
    priority: TicketPriority | None = None  # None: use the triage priority
    site_id: str | None = None


class UpdateTicketPayload(ActionPayload):
    ticket_id: str
    status: TicketStatus | None = None
    site_id: str | None = None
    priority: TicketPriority | None = None

    @model_validator(mode="after")
    def _needs_a_change(self) -> Self:
        if self.status is None and self.site_id is None and self.priority is None:
            raise ValueError("no change requested")
        return self


class CloseTicketPayload(ActionPayload):
    ticket_id: str


class PageOnCallPayload(ActionPayload):
    summary: str
    site_ids: str = ""  # comma-separated

    @property
    def sites(self) -> tuple[str, ...]:
        return tuple(site.strip() for site in self.site_ids.split(",") if site.strip())


class CreditPayload(ActionPayload):
    ticket_id: str
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    currency: str = "USD"
    incident_id: str
    period: str


class MfaResetPayload(ActionPayload):
    ticket_id: str
    user_email: str
