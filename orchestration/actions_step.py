from actions import ActionResult, ActionStatus
from agents import SupportActionKind
from guardrails import ProposedAction


def stamp_ticket_id(
    pending: tuple[tuple[int, ProposedAction], ...], ticket_id: str | None
) -> tuple[tuple[int, ProposedAction], ...]:
    """Bind pending approvals to the conversation's ticket, overwriting whatever the model wrote.

    No known ticket means nothing can be bound: returns ().
    """
    if ticket_id is None:
        return ()
    return tuple(
        (index, action.model_copy(update={"payload": action.payload | {"ticket_id": ticket_id}}))
        for index, action in pending
    )


def next_active_ticket(results: tuple[ActionResult, ...], current: str | None) -> str | None:
    created = [r.reference for r in results if r.kind is SupportActionKind.CREATE_TICKET and r.status is ActionStatus.DONE]
    return created[-1] if created else current


def was_paged(results: tuple[ActionResult, ...]) -> bool:
    return any(r.kind is SupportActionKind.PAGE_ON_CALL and r.status is ActionStatus.DONE for r in results)


def confirmations(results: tuple[ActionResult, ...]) -> tuple[str, ...]:
    return tuple(r.customer_line for r in results if r.customer_line)


def has_failure(results: tuple[ActionResult, ...]) -> bool:
    return any(r.status is not ActionStatus.DONE and r.customer_line for r in results)
