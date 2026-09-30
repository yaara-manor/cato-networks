from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
import logging
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import psycopg
from pydantic import BaseModel
from pydantic_ai import Agent

from core.clock import SimulationClock
from core.config import settings
from core.models import (
    AccountTier,
    CallerIdentity,
    CustomerAccount,
    SLADeadlines,
    TicketPriority,
    TicketStatus,
)

logger = logging.getLogger(__name__)

_ZONE_TAB_PATH: Path = Path("/usr/share/zoneinfo/zone1970.tab")
_BUSINESS_START: time = time(8, 0)
_BUSINESS_END: time = time(18, 0)
_SCOPING_COUNTRY_QUESTION: str = (
    "Could you please confirm which country your primary site or organization is "
    "located in so we can apply the appropriate regional SLA hours?"
)

# Declarative SLA policy table (POL-SLA.md):
# priority -> (first_response_hours_by_tier, resolution_business_hours, update_cadence)
_SLA_TARGETS: dict[TicketPriority, tuple[dict[AccountTier, float], float, str]] = {
    "P2": (
        {"Premium": 1.0, "Standard": 4.0, "Unknown": 4.0},
        10.0,
        "every 4 business hours",
    ),
    "P3": (
        {"Premium": 4.0, "Standard": 8.0, "Unknown": 8.0},
        30.0,
        "on every state change",
    ),
    "P4": (
        {"Premium": 8.0, "Standard": 20.0, "Unknown": 20.0},
        50.0,
        "on every state change",
    ),
}


class CountryCodeOutput(BaseModel):
    country_code: str | None = None


_DEFAULT_COUNTRY_AGENT: Agent[None, CountryCodeOutput] = Agent(
    settings.llm_model,
    output_type=CountryCodeOutput,
    defer_model_check=True,
    system_prompt=(
        "Extract the 2-letter ISO 3166-1 alpha-2 uppercase country code "
        "(e.g. 'IL', 'US', 'DE') from the user's message, or null if no "
        "recognizable country is stated."
    ),
)


@lru_cache(maxsize=1)
def _country_to_tz_map() -> dict[str, str]:
    primary: dict[str, str] = {}
    fallback: dict[str, str] = {}
    if not _ZONE_TAB_PATH.exists():
        return primary
    for raw_line in _ZONE_TAB_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tz_name = parts[2].strip()
        codes = [c.strip().upper() for c in parts[0].split(",") if c.strip()]
        if not codes:
            continue
        primary.setdefault(codes[0], tz_name)
        for code in codes[1:]:
            fallback.setdefault(code, tz_name)
    return {**fallback, **primary}


def _snap_to_business_window(dt_local: datetime) -> datetime:
    current = dt_local
    if current.weekday() >= 5:
        days_to_monday = 7 - current.weekday()
        return (current + timedelta(days=days_to_monday)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
    if current.time() < _BUSINESS_START:
        return current.replace(hour=8, minute=0, second=0, microsecond=0)
    if current.time() >= _BUSINESS_END:
        next_day = (current + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        return next_day
    return current


def _advance_business_hours(start_local: datetime, hours: float) -> datetime:
    current = _snap_to_business_window(start_local)
    remaining_seconds = max(0.0, hours * 3600.0)
    if remaining_seconds == 0.0:
        return current

    while remaining_seconds > 0.0:
        window_end = current.replace(hour=18, minute=0, second=0, microsecond=0)
        available_seconds = (window_end - current).total_seconds()
        if remaining_seconds <= available_seconds:
            return current + timedelta(seconds=remaining_seconds)
        remaining_seconds -= available_seconds
        current = (current + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        while current.weekday() >= 5:
            current += timedelta(days=1)

    return current


def _row_to_account(row: tuple[Any, ...]) -> CustomerAccount:
    return CustomerAccount(
        account_id=str(row[0]),
        company=str(row[1]),
        tier=cast(AccountTier, str(row[2])),
        email_domain=str(row[3]),
        registered_admin_contact=str(row[4]),
        country=str(row[5]) if row[5] is not None else None,
    )


class CustomerService:
    def __init__(
        self,
        connection: psycopg.Connection[Any],
        clock: SimulationClock,
        country_agent: Agent[None, CountryCodeOutput] | None = None,
    ) -> None:
        self._conn: psycopg.Connection[Any] = connection
        self._clock: SimulationClock = clock
        self._country_agent: Agent[None, CountryCodeOutput] = (
            country_agent if country_agent is not None else _DEFAULT_COUNTRY_AGENT
        )

    def lookup_account(self, email_or_account_id: str) -> CustomerAccount | None:
        value = email_or_account_id.strip()
        if not value:
            return None

        with self._conn.cursor() as cur:
            if "@" in value:
                domain = value.rsplit("@", 1)[1]
                cur.execute(
                    """
                    select customer_id, company, tier, email_domain, registered_admin_contact, country
                    from accounts
                    where lower(registered_admin_contact) = lower(%s)
                       or lower(email_domain) = lower(%s)
                    limit 1
                    """,
                    (value, domain),
                )
            else:
                cur.execute(
                    """
                    select customer_id, company, tier, email_domain, registered_admin_contact, country
                    from accounts
                    where upper(customer_id) = upper(%s)
                    limit 1
                    """,
                    (value,),
                )
            row = cur.fetchone()

        return _row_to_account(row) if row is not None else None

    def resolve_timezone_for_country(self, country_code: str | None) -> ZoneInfo | None:
        if not country_code or not country_code.strip():
            logger.error("Missing country code for timezone resolution: %r", country_code)
            return None
        normalized = country_code.strip().upper()
        tz_name = _country_to_tz_map().get(normalized)
        if tz_name is None:
            logger.error("Unrecognized ISO country code for timezone resolution: %r", country_code)
            return None
        return ZoneInfo(tz_name)

    def update_account_country(self, account_id: str, country_code: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "update accounts set country = %s where upper(customer_id) = upper(%s)",
                (country_code.strip().upper(), account_id.strip()),
            )
        self._conn.commit()

    def resolve_country_from_text(
        self,
        user_text: str,
        account_id: str | None = None,
    ) -> str | None:
        if not user_text.strip():
            return None
        result = self._country_agent.run_sync(user_text)
        raw_code = result.output.country_code
        if not raw_code:
            logger.error("Could not extract ISO country code from text: %r", user_text)
            return None
        normalized = raw_code.strip().upper()
        if self.resolve_timezone_for_country(normalized) is None:
            return None
        if account_id is not None:
            self.update_account_country(account_id, normalized)
        return normalized

    def authenticate_caller(
        self,
        caller_email: str | None,
        claimed_account_id: str | None = None,
        claimed_tier: str | None = None,
    ) -> CallerIdentity:
        normalized_email = (
            caller_email.strip().lower() if caller_email and caller_email.strip() else None
        )
        email_account = self.lookup_account(normalized_email) if normalized_email else None
        claimed_account = (
            self.lookup_account(claimed_account_id)
            if claimed_account_id and claimed_account_id.strip()
            else None
        )
        account = email_account or claimed_account

        if account is None:
            return CallerIdentity(
                account=None,
                caller_email=normalized_email,
                effective_tier="Unknown",
                is_verified_account_member=False,
                is_registered_admin=False,
                claimed_tier_rejected=bool(claimed_tier),
                needs_country_clarification=False,
                scoping_question=None,
            )

        caller_domain = (
            normalized_email.rsplit("@", 1)[1]
            if normalized_email and "@" in normalized_email
            else ""
        )
        is_registered_admin = bool(
            normalized_email
            and normalized_email == account.registered_admin_contact.lower()
        )
        is_verified_member = is_registered_admin or bool(
            caller_domain and caller_domain == account.email_domain.lower()
        )
        effective_tier: AccountTier = account.tier if is_verified_member else "Unknown"
        claimed_tier_rejected = bool(
            claimed_tier and claimed_tier.strip().lower() != effective_tier.lower()
        )

        tz = self.resolve_timezone_for_country(account.country)
        needs_country = tz is None

        return CallerIdentity(
            account=account,
            caller_email=normalized_email,
            effective_tier=effective_tier,
            is_verified_account_member=is_verified_member,
            is_registered_admin=is_registered_admin,
            claimed_tier_rejected=claimed_tier_rejected,
            needs_country_clarification=needs_country,
            scoping_question=_SCOPING_COUNTRY_QUESTION if needs_country else None,
        )

    def calculate_sla_deadlines(
        self,
        tier: AccountTier,
        priority: TicketPriority,
        country_code: str | None = None,
        product_area: str | None = None,
        created_at: datetime | None = None,
        status: TicketStatus = "open",
        elapsed_before_pause: timedelta | None = None,
    ) -> SLADeadlines:
        started_utc = (created_at if created_at is not None else self._clock.now()).astimezone(
            timezone.utc
        )
        tz = self.resolve_timezone_for_country(country_code) if country_code else None
        tz_info = tz if tz is not None else ZoneInfo("UTC")
        tz_name = tz_info.key
        resolution_paused = status == "pending_customer"
        prior_elapsed_hours = (
            max(0.0, elapsed_before_pause.total_seconds() / 3600.0)
            if elapsed_before_pause is not None
            else 0.0
        )

        if priority == "P1":
            remaining_res_hours = max(0.0, 4.0 - prior_elapsed_hours)
            return SLADeadlines(
                priority=priority,
                tier=tier,
                timezone_name=tz_name,
                product_area=product_area,
                started_at=started_utc,
                first_response_due=started_utc + timedelta(minutes=15),
                resolution_due=started_utc + timedelta(hours=remaining_res_hours),
                update_cadence="every 30 minutes",
                is_24x7=True,
                resolution_paused=resolution_paused,
            )

        response_by_tier, base_resolution_hours, cadence = _SLA_TARGETS[priority]
        first_response_hours = response_by_tier[tier]
        if (
            priority == "P4"
            and tier == "Premium"
            and product_area is not None
            and product_area.strip().lower() == "performance"
        ):
            first_response_hours = 8.0

        remaining_resolution_hours = max(0.0, base_resolution_hours - prior_elapsed_hours)
        started_local = started_utc.astimezone(tz_info)
        first_response_local = _advance_business_hours(started_local, first_response_hours)
        resolution_local = _advance_business_hours(started_local, remaining_resolution_hours)

        return SLADeadlines(
            priority=priority,
            tier=tier,
            timezone_name=tz_name,
            product_area=product_area,
            started_at=started_utc,
            first_response_due=first_response_local.astimezone(timezone.utc),
            resolution_due=resolution_local.astimezone(timezone.utc),
            update_cadence=cadence,
            is_24x7=False,
            resolution_paused=resolution_paused,
        )
