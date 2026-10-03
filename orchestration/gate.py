from typing import assert_never

from pydantic import BaseModel, ConfigDict

from agents import SupportAction
from core.models import TicketPriority
from guardrails import ActionType, GateOutcome, ProposedAction, check_action
from services.models import CallerIdentity


class GatedActions(BaseModel):
    model_config = ConfigDict(frozen=True)

    executable: tuple[SupportAction, ...] = ()
    pending: tuple[tuple[int, ProposedAction], ...] = ()  # (index in plan, action)
    denial_reasons: tuple[str, ...] = ()


def gate_actions(
    actions: tuple[SupportAction, ...],
    identity: CallerIdentity,
    priority: TicketPriority,
    sev1_corroborated: bool,
    already_paged: bool,
) -> GatedActions:
    """Pure: runs every action through `check_action`; no account means nothing may execute."""
    if identity.account is None:
        return GatedActions()
    executable: list[SupportAction] = []
    pending: list[tuple[int, ProposedAction]] = []
    denials: list[str] = []
    paged = already_paged
    for index, action in enumerate(actions):
        proposed = action.to_proposed_action(identity.account.account_id)
        if proposed is None:  # ungated kind
            executable.append(action)
            continue
        decision = check_action(
            proposed, identity, priority=priority, sev1_corroborated=sev1_corroborated, already_paged=paged
        )
        match decision.outcome:
            case GateOutcome.ALLOW:
                executable.append(action)
                paged = paged or proposed.action_type is ActionType.PAGE_ON_CALL
            case GateOutcome.REQUIRE_APPROVAL:
                pending.append((index, proposed))
            case GateOutcome.DENY:
                denials.append(decision.reason)
            case _:
                assert_never(decision.outcome)
    return GatedActions(
        executable=tuple(executable),
        pending=tuple(pending),
        denial_reasons=tuple(denials),
    )
