import json
from typing import Any

import pytest

from core.config import settings
from core.models import AccountTier, CustomerAccount
from services.models import CallerIdentity


def _read_jsonl(relative_path: str) -> list[dict[str, Any]]:
    with (settings.repo_root / "data" / relative_path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@pytest.fixture(scope="session")
def corpus() -> dict[str, str]:
    questions = _read_jsonl("eval/questions.jsonl")
    tickets = _read_jsonl("tickets/tickets.jsonl")
    scenarios = _read_jsonl("eval/scenarios.jsonl")
    assert (len(questions), len(tickets), len(scenarios)) == (35, 54, 12)
    texts = {row["question_id"]: row["question"] for row in questions}
    for ticket in tickets:
        texts[f"{ticket['ticket_id']}.subject"] = ticket["subject"]
        texts[f"{ticket['ticket_id']}.body"] = ticket["body"]
    for scenario in scenarios:
        texts[f"{scenario['scenario_id']}.opening"] = scenario["opening_message"]
        for i, followup in enumerate(scenario["simulated_customer_followups"]):
            texts[f"{scenario['scenario_id']}.followup{i}"] = followup["customer"]
    return texts


def _identity(
    account_id: str | None,
    company: str,
    tier: AccountTier,
    domain: str,
    *,
    email: str,
    member: bool,
    admin: bool,
    admin_email: str | None = None,
) -> CallerIdentity:
    account = (
        CustomerAccount(
            account_id=account_id,
            company=company,
            tier=tier,
            email_domain=domain,
            registered_admin_contact=admin_email or email,
        )
        if account_id
        else None
    )
    return CallerIdentity(
        account=account,
        caller_email=email,
        effective_tier=tier if member else "Unknown",
        is_verified_account_member=member,
        is_registered_admin=admin,
        claimed_tier_rejected=False,
        needs_country_clarification=False,
    )


_ATLAS = ("ACC-1007", "Atlas Engineering", "Standard", "atlas-eng.com")


@pytest.fixture
def identity_priya() -> CallerIdentity:
    return _identity(
        "ACC-1002",
        "Bluebird Retail",
        "Standard",
        "bluebirdretail.com",
        email="priya@bluebirdretail.com",
        member=True,
        admin=False,
        admin_email="it-admin@bluebirdretail.com",
    )


@pytest.fixture
def identity_mark() -> CallerIdentity:
    return _identity(None, "", "Unknown", "", email="mark@example.com", member=False, admin=False)


@pytest.fixture
def identity_ravi() -> CallerIdentity:
    return _identity(
        "ACC-1004",
        "Ironclad Manufacturing",
        "Standard",
        "ironclad-mfg.com",
        email="ravi@ironclad-mfg.com",
        member=True,
        admin=False,
        admin_email="infra@ironclad-mfg.com",
    )


@pytest.fixture
def identity_sam() -> CallerIdentity:
    return _identity(
        *_ATLAS, email="sam@atlas-eng.com", member=True, admin=False, admin_email="sysadmin@atlas-eng.com"
    )


@pytest.fixture
def identity_admin() -> CallerIdentity:
    return _identity(*_ATLAS, email="sysadmin@atlas-eng.com", member=True, admin=True)


@pytest.fixture
def identity_unverified() -> CallerIdentity:
    return _identity(
        *_ATLAS, email="sam@gmail.com", member=False, admin=False, admin_email="sysadmin@atlas-eng.com"
    )


@pytest.fixture
def identity_premium() -> CallerIdentity:
    return _identity(
        "ACC-1005",
        "Quartz Financial",
        "Premium",
        "quartzfin.com",
        email="dana@quartzfin.com",
        member=True,
        admin=False,
        admin_email="secops@quartzfin.com",
    )
