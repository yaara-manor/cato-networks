from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import logging
from zoneinfo import ZoneInfo

import psycopg
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from core.clock import DEFAULT_ANCHOR, SimulationClock
from core.config import settings
from db.init.seed import seed_all
from services import CountryCodeOutput, CustomerService, TicketService


@pytest.fixture()
def db_conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from tickets where substring(ticket_id from 5)::int > 20264253")
        conn.commit()
        seed_all(conn, preserve_existing_tickets=False)
        yield conn
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("delete from tickets where substring(ticket_id from 5)::int > 20264253")
        conn.commit()
        seed_all(conn, preserve_existing_tickets=False)


def test_repeat_contact_and_regional_sla_flow(db_conn: psycopg.Connection) -> None:
    clock = SimulationClock.frozen(DEFAULT_ANCHOR)
    cust_svc = CustomerService(db_conn, clock)
    ticket_svc = TicketService(db_conn, clock)

    # 1. Authenticate Grace Novak at Solstice Media (ACC-1008, Standard, US)
    identity = cust_svc.authenticate_caller("grace.novak@solsticemedia.com")
    assert identity.account is not None
    assert identity.account.account_id == "ACC-1008"
    assert identity.account.country == "US"
    assert identity.effective_tier == "Standard"
    assert identity.is_verified_account_member is True
    assert identity.is_registered_admin is False
    assert identity.claimed_tier_rejected is False
    assert identity.needs_country_clarification is False
    assert identity.scoping_question is None

    # 2. Regional SLA calculations:
    # P1 runs 24x7 regardless of timezone
    p1_sla = cust_svc.calculate_sla_deadlines(
        tier="Standard",
        priority="P1",
        country_code="DE",
    )
    assert p1_sla.is_24x7 is True
    assert p1_sla.first_response_due == DEFAULT_ANCHOR + timedelta(minutes=15)
    assert p1_sla.resolution_due == DEFAULT_ANCHOR + timedelta(hours=4)
    assert p1_sla.update_cadence == "every 30 minutes"
    assert p1_sla.resolution_paused is False

    # US (America/New_York): 2026-08-28T17:00:00Z is Friday 13:00 EDT (5 business hours left on Friday)
    # Standard P2: first response = 4h -> Friday 17:00 EDT (21:00Z)
    # Resolution = 1 business day (10h) -> 5h Friday + 5h Monday (08:00..13:00 EDT) -> 2026-08-31T17:00:00Z
    us_p2_sla = cust_svc.calculate_sla_deadlines(
        tier="Standard",
        priority="P2",
        country_code="US",
    )
    assert us_p2_sla.timezone_name == "America/New_York"
    assert us_p2_sla.is_24x7 is False
    assert us_p2_sla.first_response_due == datetime(2026, 8, 28, 21, 0, 0, tzinfo=timezone.utc)
    assert us_p2_sla.resolution_due == datetime(2026, 8, 31, 17, 0, 0, tzinfo=timezone.utc)
    assert us_p2_sla.update_cadence == "every 4 business hours"

    # DE (Europe/Berlin): 2026-08-28T17:00:00Z is Friday 19:00 CEST (after 18:00 business hours)
    # Clock rolls to Monday 2026-08-31 08:00 CEST (06:00Z).
    # Standard P2: first response (+4h) = Monday 12:00 CEST (10:00Z), resolution (+10h) = Monday 18:00 CEST (16:00Z)
    de_p2_sla = cust_svc.calculate_sla_deadlines(
        tier="Standard",
        priority="P2",
        country_code="DE",
    )
    assert de_p2_sla.timezone_name == "Europe/Berlin"
    assert de_p2_sla.first_response_due == datetime(2026, 8, 31, 10, 0, 0, tzinfo=timezone.utc)
    assert de_p2_sla.resolution_due == datetime(2026, 8, 31, 16, 0, 0, tzinfo=timezone.utc)

    # Premium + performance on P4 overrides first response to 8 business hours; Standard P4 is 20h (2 business days)
    prem_perf_p4 = cust_svc.calculate_sla_deadlines(
        tier="Premium",
        priority="P4",
        country_code="DE",
        product_area="performance",
    )
    assert prem_perf_p4.first_response_due == datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc)
    assert prem_perf_p4.update_cadence == "on every state change"

    # Clock pause rules: pending_customer pauses resolution; pending_approval does NOT pause; elapsed_before_pause deducts time
    paused_sla = cust_svc.calculate_sla_deadlines(
        tier="Standard",
        priority="P2",
        country_code="DE",
        status="pending_customer",
    )
    assert paused_sla.resolution_paused is True

    approval_sla = cust_svc.calculate_sla_deadlines(
        tier="Standard",
        priority="P2",
        country_code="DE",
        status="pending_approval",
        elapsed_before_pause=timedelta(hours=3),
    )
    assert approval_sla.resolution_paused is False
    assert approval_sla.resolution_due == datetime(2026, 8, 31, 13, 0, 0, tzinfo=timezone.utc)

    # 3. Unbounded ticket history & repeat-contact detection for Chicago site S-1008-01 (SC-06)
    chicago_history = ticket_svc.get_ticket_history("ACC-1008", site_id="S-1008-01")
    assert [t.ticket_id for t in chicago_history] == [
        "TCK-20264200",
        "TCK-20264201",
        "TCK-20264216",
    ]
    closed_only = ticket_svc.get_ticket_history("ACC-1008", site_id="S-1008-01", include_open=False)
    assert [t.ticket_id for t in closed_only] == ["TCK-20264200", "TCK-20264201"]

    repeat_chicago = ticket_svc.detect_repeat_contact(
        account_id="ACC-1008",
        site_id="S-1008-01",
        product_area="connectivity",
        exclude_ticket_id="TCK-20264216",
    )
    assert repeat_chicago.is_repeat_contact is True
    assert [t.ticket_id for t in repeat_chicago.prior_closed_tickets] == [
        "TCK-20264200",
        "TCK-20264201",
    ]
    assert repeat_chicago.reason is not None

    # Single-incident open sites (SC-01 S-1001-02, SC-11 S-1009-01, SC-12 S-1010-01) must NOT flag repeat contact
    assert (
        ticket_svc.detect_repeat_contact(
            "ACC-1001", site_id="S-1001-02", exclude_ticket_id="TCK-20264219"
        ).is_repeat_contact
        is False
    )
    assert (
        ticket_svc.detect_repeat_contact(
            "ACC-1009", site_id="S-1009-01", exclude_ticket_id="TCK-20264232"
        ).is_repeat_contact
        is False
    )
    assert (
        ticket_svc.detect_repeat_contact(
            "ACC-1010", site_id="S-1010-01", exclude_ticket_id="TCK-20264217"
        ).is_repeat_contact
        is False
    )

    # Unrelated same-site open tickets (S-1003-01 firmware vs IPS; S-1010-02 cloud/IPsec vs routing/BGP) must NOT flag repeat contact
    assert (
        ticket_svc.detect_repeat_contact(
            "ACC-1003",
            site_id="S-1003-01",
            product_area="security",
            exclude_ticket_id="TCK-20264252",
        ).is_repeat_contact
        is False
    )
    assert (
        ticket_svc.detect_repeat_contact(
            "ACC-1010",
            site_id="S-1010-02",
            product_area="routing",
            exclude_ticket_id="TCK-20264249",
        ).is_repeat_contact
        is False
    )


def test_security_invariant_and_adversarial_callers(db_conn: psycopg.Connection) -> None:
    clock = SimulationClock.frozen(DEFAULT_ANCHOR)
    cust_svc = CustomerService(db_conn, clock)

    # SC-07: Standard customer claiming to be Premium
    spoofed_tier = cust_svc.authenticate_caller(
        caller_email="priya.patel@bluebirdretail.com",
        claimed_account_id="ACC-1002",
        claimed_tier="Premium",
    )
    assert spoofed_tier.account is not None
    assert spoofed_tier.account.account_id == "ACC-1002"
    assert spoofed_tier.effective_tier == "Standard"
    assert spoofed_tier.is_verified_account_member is True
    assert spoofed_tier.is_registered_admin is False
    assert spoofed_tier.claimed_tier_rejected is True

    # SC-04: External gmail caller claiming CEO assistant authority on ACC-1009
    external_caller = cust_svc.authenticate_caller(
        caller_email="mark.ellison.travel@gmail.com",
        claimed_account_id="ACC-1009",
        claimed_tier="Premium",
    )
    assert external_caller.account is not None
    assert external_caller.account.account_id == "ACC-1009"
    assert external_caller.is_verified_account_member is False
    assert external_caller.is_registered_admin is False
    assert external_caller.effective_tier == "Unknown"

    # Registered admin contact verification (ACC-1011 noc@meridian-air.com)
    admin_caller = cust_svc.authenticate_caller(caller_email="noc@meridian-air.com")
    assert admin_caller.account is not None
    assert admin_caller.account.account_id == "ACC-1011"
    assert admin_caller.effective_tier == "Premium"
    assert admin_caller.is_verified_account_member is True
    assert admin_caller.is_registered_admin is True


def test_unknown_country_clarification_and_pydantic_ai_resolver(
    db_conn: psycopg.Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = SimulationClock.frozen(DEFAULT_ANCHOR)

    test_agent: Agent[None, CountryCodeOutput] = Agent(
        TestModel(custom_output_args={"country_code": "IL"}),
        output_type=CountryCodeOutput,
    )
    cust_svc = CustomerService(db_conn, clock, country_agent=test_agent)

    # Verify default agent model setting is google-gla:gemini-3.8-flash
    assert settings.llm_model == "google-gla:gemini-3.8-flash"

    # Set ACC-1006 country to NULL and verify error log + scoping question
    with db_conn.cursor() as cur:
        cur.execute("update accounts set country = null where customer_id = 'ACC-1006'")
    db_conn.commit()

    with caplog.at_level(logging.ERROR):
        missing_country_id = cust_svc.authenticate_caller("it@verdantfoods.com")
    assert missing_country_id.needs_country_clarification is True
    assert missing_country_id.scoping_question is not None
    assert "country" in missing_country_id.scoping_question.lower()
    assert any("country" in rec.message.lower() for rec in caplog.records)

    # Resolve free-text user reply via PydanticAI agent and persist to PostgreSQL
    resolved_code = cust_svc.resolve_country_from_text("I'm in Israel", account_id="ACC-1006")
    assert resolved_code == "IL"
    assert cust_svc.resolve_timezone_for_country("IL") == ZoneInfo("Asia/Jerusalem")

    updated_account = cust_svc.lookup_account("ACC-1006")
    assert updated_account is not None
    assert updated_account.country == "IL"


def test_live_ticket_creation_and_status_lifecycle(db_conn: psycopg.Connection) -> None:
    clock = SimulationClock.frozen(DEFAULT_ANCHOR)
    ticket_svc = TicketService(db_conn, clock)

    created = ticket_svc.create_ticket(
        customer_id="ACC-1001",
        customer_name="Erik Iyer",
        requester_email="erik.iyer@northwind-logistics.com",
        company="Northwind Logistics",
        tier="Premium",
        priority="P3",
        product_area="connectivity",
        subject="Warsaw warehouse dropped again",
        body="Second drop today on Warsaw warehouse link.",
        site_id="S-1001-02",
        channel="chat",
    )
    assert created.ticket_id == "TCK-20264254"
    assert created.created_at == DEFAULT_ANCHOR
    assert created.status == "open"

    fetched = ticket_svc.get_ticket("TCK-20264254")
    assert fetched is not None
    assert fetched.subject == "Warsaw warehouse dropped again"

    closed = ticket_svc.update_ticket_status("TCK-20264254", "closed")
    assert closed.status == "closed"

    repeat_after_close = ticket_svc.detect_repeat_contact(
        account_id="ACC-1001",
        site_id="S-1001-02",
        product_area="connectivity",
        exclude_ticket_id="TCK-20264219",
    )
    assert repeat_after_close.is_repeat_contact is True
    assert [t.ticket_id for t in repeat_after_close.prior_closed_tickets] == ["TCK-20264254"]
