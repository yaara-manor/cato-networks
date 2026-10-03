import pytest
from pydantic import BaseModel

from actions import (
    CloseTicketPayload,
    CreateTicketPayload,
    CreditPayload,
    MfaResetPayload,
    PageOnCallPayload,
    UpdateTicketPayload,
)
from agents.base import load_prompt

HEADINGS = ("Role", "Inputs you receive", "Tools and when to use them", "Rules", "Output fields", "Examples")


@pytest.mark.parametrize("name", ("triage", "diagnostics", "knowledge", "resolution"))
def test_prompt_has_headings_and_no_leaks(name: str) -> None:
    prompt = load_prompt(name)
    assert all(f"## {heading}" in prompt for heading in HEADINGS)
    assert "SC-" not in prompt and "expected" not in prompt.lower()


def test_resolution_prompt_has_marker_grammar() -> None:
    prompt = load_prompt("resolution")
    assert all(prefix in prompt for prefix in ("[kb:", "[policy:", "[telemetry:"))


@pytest.mark.parametrize(
    "model",
    (CreateTicketPayload, UpdateTicketPayload, CloseTicketPayload, PageOnCallPayload, CreditPayload, MfaResetPayload),
)
def test_resolution_prompt_names_every_payload_key(model: type[BaseModel]) -> None:
    prompt = load_prompt("resolution")
    assert all(f"`{key}`" in prompt for key in model.model_fields)
    assert "known_ticket_id" in prompt
