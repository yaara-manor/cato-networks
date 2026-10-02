from typing import Self

from pydantic import BaseModel, ConfigDict

from guardrails import ActionType, ApprovalStatus
from storage import Approval

# Payload keys a customer may see, per action type; everything else (ticket ids, free text) stays internal.
_SHOWN_FIELDS: dict[ActionType, tuple[str, ...]] = {
    ActionType.CREDIT: ("amount", "currency"),
    ActionType.MFA_RESET: ("user_email",),
}
_CREDIT, _MFA = ActionType.CREDIT, ActionType.MFA_RESET
_APPROVED, _EDITED, _REJECTED = ApprovalStatus.APPROVED, ApprovalStatus.EDITED, ApprovalStatus.REJECTED
_TEMPLATES: dict[tuple[ActionType, ApprovalStatus], str] = {
    (_CREDIT, _APPROVED): "Your service credit request has been approved by our Escalation Board. "
    "Credit: {amount} {currency}.",
    (_CREDIT, _EDITED): "Your service credit request has been approved with changes by our Escalation Board. "
    "Credit: {amount} {currency}.",
    (_CREDIT, _REJECTED): "Your service credit request was reviewed and could not be approved.",
    (_MFA, _APPROVED): "Your MFA reset request for {user_email} has been approved by our Escalation Board "
    "and processed.",
    (_MFA, _EDITED): "Your MFA reset request has been approved with changes by our Escalation Board "
    "and processed for {user_email}.",
    (_MFA, _REJECTED): "Your MFA reset request was reviewed and could not be approved.",
}
_REJECTED_CLOSING = "Reply here if you want to discuss alternatives or request an engineer."


class ApprovalNotice(BaseModel):
    """Deterministic customer text for a resolved approval; never carries reviewer notes."""

    model_config = ConfigDict(frozen=True)

    text: str

    @classmethod
    def from_approval(cls, approval: Approval) -> Self:
        template = _TEMPLATES.get((approval.action_type, approval.status))
        if template is None:
            raise ValueError(f"no notice for {approval.action_type}/{approval.status}")
        payload = approval.effective_payload
        shown = {key: payload[key] for key in _SHOWN_FIELDS[approval.action_type] if key in payload}
        parts = [template.format_map({"currency": "USD"} | shown)]
        if approval.customer_reason:
            parts.append(f"Reason: {approval.customer_reason}")
        if approval.status is ApprovalStatus.REJECTED:
            parts.append(_REJECTED_CLOSING)
        return cls(text=" ".join(parts))
