from actions.simulated import HANDLERS, REFUSED_KINDS
from agents.models import SupportActionKind


def test_every_action_kind_is_handled_or_refused() -> None:
    handled = set(HANDLERS)
    assert handled | REFUSED_KINDS == set(SupportActionKind)
    assert not handled & REFUSED_KINDS
