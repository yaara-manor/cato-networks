from decimal import Decimal

import pytest

from actions.payloads import (
    ActionPayload,
    CloseTicketPayload,
    CreateTicketPayload,
    CreditPayload,
    MfaResetPayload,
    PageOnCallPayload,
    UpdateTicketPayload,
)

CREATE = {"subject": "s", "body": "b", "product_area": "VPN"}
CREDIT = {"ticket_id": "TCK-1", "amount": "50.5", "incident_id": "INC-1", "period": "2026-09"}


@pytest.mark.parametrize(
    ("model", "raw", "valid"),
    [
        (CreateTicketPayload, CREATE, True),
        (CreateTicketPayload, CREATE | {"priority": "P2", "site_id": "S-1"}, True),
        (CreateTicketPayload, CREATE | {"extra": "x"}, False),
        (CreateTicketPayload, {"subject": "s", "body": "b"}, False),
        (CreateTicketPayload, CREATE | {"subject": "  "}, False),
        (CreateTicketPayload, CREATE | {"priority": "P9"}, False),
        (CreateTicketPayload, CREATE | {"body": "a\x00b"}, False),
        (UpdateTicketPayload, {"ticket_id": "TCK-1", "status": "closed"}, True),
        (UpdateTicketPayload, {"ticket_id": "TCK-1"}, False),
        (UpdateTicketPayload, {"ticket_id": "TCK-1", "status": "bogus"}, False),
        (CloseTicketPayload, {"ticket_id": "TCK-1"}, True),
        (CloseTicketPayload, {}, False),
        (PageOnCallPayload, {"summary": "down", "site_ids": "A, B"}, True),
        (PageOnCallPayload, {"summary": "down"}, True),
        (CreditPayload, CREDIT, True),
        (CreditPayload, CREDIT | {"amount": "lots"}, False),
        (CreditPayload, CREDIT | {"amount": "NaN"}, False),
        (CreditPayload, CREDIT | {"amount": "-1"}, False),
        (CreditPayload, {k: v for k, v in CREDIT.items() if k != "ticket_id"}, False),
        (MfaResetPayload, {"ticket_id": "TCK-1", "user_email": "a@b.co"}, True),
        (MfaResetPayload, {"user_email": "a@b.co"}, False),
    ],
)
def test_from_payload(model: type[ActionPayload], raw: dict[str, str], valid: bool) -> None:
    if valid:
        assert model.from_payload(raw)
    else:
        with pytest.raises(ValueError):
            model.from_payload(raw)


def test_parsed_values_are_typed() -> None:
    assert CreditPayload.from_payload(CREDIT).amount == Decimal("50.5")
    assert PageOnCallPayload.from_payload({"summary": "x", "site_ids": "A, B"}).sites == ("A", "B")
    assert PageOnCallPayload.from_payload({"summary": "x"}).sites == ()
