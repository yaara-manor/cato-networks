import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from actions.models import ActionResult, DispatchContext, DispatchRequest
from actions.simulated import (
    HANDLERS,
    REFUSED_KINDS,
    ActionOutcome,
    ActionRejected,
    HandlerCall,
    Runner,
)
from agents.models import SupportAction, SupportActionKind, support_kind_for
from core.clock import SimulationClock
from guardrails import GateOutcome, check_action
from services import TicketService
from storage import (
    Approval,
    ApprovalStatus,
    ClaimedAction,
    SimulatedAction,
    SimulatedActionStatus,
    StateStore,
)

logger = logging.getLogger(__name__)

_ALREADY_PAGED = "conversation already paged"


def approved_action_key(approval_id: UUID) -> str:
    """Idempotency key of the action an approval executes; readers match the outcome row by it."""
    return f"approval:{approval_id}"
_OUTCOME_UNKNOWN = "outcome unknown; a previous attempt did not finish"


class ActionDispatcher:
    """Executes gate-cleared actions as simulated effects; `simulated_actions` is audit log and idempotency store."""

    def __init__(self, store: StateStore, tickets: TicketService, clock: SimulationClock) -> None:
        self._store = store
        self._tickets = tickets
        self._clock = clock

    def dispatch_turn(self, actions: Sequence[SupportAction], context: DispatchContext) -> tuple[ActionResult, ...]:
        return tuple(
            self._run(
                DispatchRequest(
                    action=action, idempotency_key=_turn_key(action.kind, index, context), context=context
                )
            )
            for index, action in enumerate(actions)
        )

    def dispatch_approved(self, approval: Approval, context: DispatchContext) -> ActionResult:
        kind = support_kind_for(approval.action_type)
        if approval.conversation_id != context.conversation_id:
            return ActionResult.refused(kind, "approval belongs to another conversation")
        if approval.status not in (ApprovalStatus.APPROVED, ApprovalStatus.EDITED):
            return ActionResult.refused(kind, "approval is not approved")
        payload = approval.edited_payload if approval.status is ApprovalStatus.EDITED else approval.payload
        assert payload is not None  # ApprovalResolution guarantees it for EDITED
        if payload.get("ticket_id") != approval.payload.get("ticket_id"):
            return ActionResult.invalid(kind, "edit changed the bound ticket")
        return self._run(
            DispatchRequest(
                action=SupportAction(kind=kind, payload=payload, reason="approved"),
                idempotency_key=approved_action_key(approval.id),
                context=context,
                approval_id=approval.id,
            )
        )

    def mark_pending(self, approval: Approval, context: DispatchContext) -> ActionResult:
        if approval.status is not ApprovalStatus.PENDING:
            return ActionResult.refused(SupportActionKind.UPDATE_TICKET, "approval is not pending")
        payload = {"status": "pending_approval"} | {k: v for k, v in approval.payload.items() if k == "ticket_id"}
        return self._run(
            DispatchRequest(
                action=SupportAction(kind=SupportActionKind.UPDATE_TICKET, payload=payload, reason="approval pending"),
                idempotency_key=f"approval:{approval.id}:pending",
                context=context,
                approval_id=approval.id,
            )
        )

    def _run(self, request: DispatchRequest) -> ActionResult:
        kind = request.action.kind
        if (refusal := self._recheck(request)) is not None:
            return self._logged(refusal, request)
        runner = _parse(request)
        if isinstance(runner, ActionResult):
            return self._logged(runner, request)
        claimed = self._claim(request)
        if not claimed.is_new:
            return self._logged(_replay(kind, claimed.action, request.context), request)
        result, effect = self._execute(runner, request, claimed.action.id)
        self._finish(claimed.action.id, result, effect)
        return self._logged(result, request)

    def _recheck(self, request: DispatchRequest) -> ActionResult | None:
        """Defense in depth: the dispatcher never invents policy, it only re-asks `check_action`."""
        kind, context = request.action.kind, request.context
        if kind in REFUSED_KINDS:
            return ActionResult.refused(kind, "kind is never dispatched")
        account = context.identity.account
        proposed = request.action.to_proposed_action(account.account_id if account else "")
        if proposed is None:
            return None  # ungated kind
        decision = check_action(
            proposed,
            context.identity,
            priority=context.priority,
            sev1_corroborated=context.sev1_corroborated,
            already_paged=context.already_paged,
        )
        required = GateOutcome.REQUIRE_APPROVAL if request.approval_id else GateOutcome.ALLOW
        if decision.outcome is not required:
            return ActionResult.refused(kind, "gate does not clear this action")
        return None

    def _claim(self, request: DispatchRequest) -> ClaimedAction:
        action = request.action
        return self._store.claim_action(
            request.context.conversation_id,
            None if request.approval_id else request.context.message_id,
            request.approval_id,
            action.kind.value,
            request.idempotency_key,
            action.payload,
            self._clock.now(),
        )

    def _execute(self, runner: Runner, request: DispatchRequest, action_id: UUID) -> tuple[ActionResult, dict[str, Any]]:
        """One `except Exception` around the handler only; logs the class name, never the message."""
        kind = request.action.kind
        try:
            outcome: ActionOutcome = runner(HandlerCall(request.context, self._tickets, action_id))
        except ActionRejected as exc:
            return ActionResult.unsuccessful(kind, exc.status, str(exc)), {}
        except Exception as exc:  # noqa: BLE001 - any handler failure becomes FAILED
            logger.warning(f"action handler error kind={kind} error={type(exc).__name__}")
            return ActionResult.failed(kind, "handler error"), {}
        return ActionResult.done(kind, outcome.reference, outcome.customer_line), outcome.result

    def _finish(self, action_id: UUID, result: ActionResult, effect: dict[str, Any]) -> None:
        self._store.finish_action(
            action_id,
            SimulatedActionStatus(result.status.value),
            result.model_dump(mode="json") | {"effect": effect},
            self._clock.now(),
        )

    @staticmethod
    def _logged(result: ActionResult, request: DispatchRequest) -> ActionResult:
        logger.info(
            f"action kind={result.kind} status={result.status} reference={result.reference}"
            f" replayed={result.replayed} conversation_id={request.context.conversation_id}"
        )
        return result


def _turn_key(kind: SupportActionKind, index: int, context: DispatchContext) -> str:
    if kind is SupportActionKind.PAGE_ON_CALL:
        return f"{context.conversation_id}:PAGE_ON_CALL"  # at most one page per conversation, DB-enforced
    return f"{context.message_id}:{kind.value}:{index}"


def _parse(request: DispatchRequest) -> Runner | ActionResult:
    kind = request.action.kind
    try:
        return HANDLERS[kind](request.action.payload)
    except ValueError:
        return ActionResult.invalid(kind, "invalid payload")


def _replay(kind: SupportActionKind, stored: SimulatedAction, context: DispatchContext) -> ActionResult:
    if stored.message_id is not None and stored.message_id != context.message_id:
        return ActionResult.refused(kind, _ALREADY_PAGED, silent=True)  # only the conversation-scoped page key
    if stored.status is SimulatedActionStatus.CLAIMED or stored.result is None:
        return ActionResult.failed(kind, _OUTCOME_UNKNOWN)  # ponytail: tickets are at-most-once; natural key to upgrade
    return ActionResult.model_validate(stored.result).as_replay()
