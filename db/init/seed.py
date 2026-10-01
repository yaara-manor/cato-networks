import csv
import json
from pathlib import Path
from typing import LiteralString, TypedDict, cast

import psycopg
import psycopg.sql

from core.config import REPO_ROOT
from kbindex.hashing import sha256_file


class PolicySeed(TypedDict):
    id: str
    title: str
    content_hash: str
    file_path: str
    body: str


class AccountSeed(TypedDict):
    customer_id: str
    company: str
    tier: str
    email_domain: str
    registered_admin_contact: str
    country: str | None


class TicketSeed(TypedDict):
    ticket_id: str
    created_at: str
    channel: str
    customer_id: str
    customer_name: str
    requester_email: str
    company: str
    tier: str
    site_id: str | None
    product_area: str
    priority: str
    subject: str
    body: str
    status: str


def apply_schema(connection: psycopg.Connection) -> None:
    migrations_dir = REPO_ROOT / "db" / "migrations"
    with connection.cursor() as cursor:
        for migration_path in sorted(migrations_dir.glob("*.sql")):
            migration_text = cast(LiteralString, migration_path.read_text(encoding="utf-8"))
            cursor.execute(psycopg.sql.SQL(migration_text))
    connection.commit()


def load_policies(
    policies_dir: Path | str = REPO_ROOT / "data" / "policies",
) -> list[PolicySeed]:
    policies_path = Path(policies_dir)
    records: list[PolicySeed] = []
    for path in sorted(policies_path.glob("POL-*.md")):
        text = path.read_text(encoding="utf-8")
        title = next(
            (line.lstrip("#").strip() for line in text.splitlines() if line.strip().startswith("#")),
            "",
        )
        try:
            rel_path = path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel_path = str(path)
        records.append({
            "id": path.stem,
            "title": title,
            "content_hash": sha256_file(path),
            "file_path": rel_path,
            "body": text,
        })
    return records


def load_accounts_seed(
    accounts_path: Path | str = REPO_ROOT / "data" / "tickets" / "accounts.csv",
    sites_path: Path | str | None = REPO_ROOT / "data" / "telemetry" / "sites.json",
) -> list[AccountSeed]:
    country_by_customer: dict[str, str] = {}
    if sites_path is not None and Path(sites_path).exists():
        sites_data = json.loads(Path(sites_path).read_text(encoding="utf-8"))
        for site in sites_data.get("sites", []):
            site_id = site.get("site_id", "")
            customer_id = site.get("customer_id", "")
            country = site.get("country")
            if site_id.endswith("-01") and customer_id and country:
                country_by_customer[customer_id] = country

    accounts: list[AccountSeed] = []
    with Path(accounts_path).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            cid = row["customer_id"].strip()
            accounts.append({
                "customer_id": cid,
                "company": row["company"].strip(),
                "tier": row["tier"].strip(),
                "email_domain": row["email_domain"].strip(),
                "registered_admin_contact": row["registered_admin_contact"].strip(),
                "country": country_by_customer.get(cid),
            })
    return accounts


def load_tickets_seed(
    tickets_path: Path | str = REPO_ROOT / "data" / "tickets" / "tickets.jsonl",
) -> list[TicketSeed]:
    path = Path(tickets_path)
    tickets: list[TicketSeed] = []
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as f:
            raw_rows = list(csv.DictReader(f))
    else:
        with path.open(encoding="utf-8") as f:
            raw_rows = [json.loads(line) for line in f if line.strip()]

    for row in raw_rows:
        raw_site = row.get("site_id")
        site_id: str | None = raw_site.strip() if isinstance(raw_site, str) and raw_site.strip() else None
        tickets.append({
            "ticket_id": str(row["ticket_id"]).strip(),
            "created_at": str(row["created_at"]).strip(),
            "channel": str(row["channel"]).strip(),
            "customer_id": str(row["customer_id"]).strip(),
            "customer_name": str(row["customer_name"]).strip(),
            "requester_email": str(row["requester_email"]).strip(),
            "company": str(row["company"]).strip(),
            "tier": str(row["tier"]).strip(),
            "site_id": site_id,
            "product_area": str(row["product_area"]).strip(),
            "priority": str(row["priority"]).strip(),
            "subject": str(row["subject"]).strip(),
            "body": str(row["body"]).strip(),
            "status": str(row["status"]).strip(),
        })
    return tickets


def upsert_policies(connection: psycopg.Connection, policies: list[PolicySeed]) -> None:
    query = """
    insert into policies (id, title, content_hash, file_path, body)
    values (%s, %s, %s, %s, %s)
    on conflict (id) do update set
        title = excluded.title,
        content_hash = excluded.content_hash,
        file_path = excluded.file_path,
        body = excluded.body
    """
    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            [(p["id"], p["title"], p["content_hash"], p["file_path"], p["body"]) for p in policies],
        )
    connection.commit()


def upsert_accounts(connection: psycopg.Connection, accounts: list[AccountSeed]) -> None:
    query = """
    insert into accounts (customer_id, company, tier, email_domain, registered_admin_contact, country)
    values (%s, %s, %s, %s, %s, %s)
    on conflict (customer_id) do update set
        company = excluded.company,
        tier = excluded.tier,
        email_domain = excluded.email_domain,
        registered_admin_contact = excluded.registered_admin_contact,
        country = excluded.country
    """
    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            [
                (
                    a["customer_id"],
                    a["company"],
                    a["tier"],
                    a["email_domain"],
                    a["registered_admin_contact"],
                    a["country"],
                )
                for a in accounts
            ],
        )
    connection.commit()


def upsert_tickets(
    connection: psycopg.Connection,
    tickets: list[TicketSeed],
    preserve_existing: bool = False,
) -> None:
    conflict_clause = (
        "on conflict (ticket_id) do nothing"
        if preserve_existing
        else """
        on conflict (ticket_id) do update set
            created_at = excluded.created_at,
            channel = excluded.channel,
            customer_id = excluded.customer_id,
            customer_name = excluded.customer_name,
            requester_email = excluded.requester_email,
            company = excluded.company,
            tier = excluded.tier,
            site_id = excluded.site_id,
            product_area = excluded.product_area,
            priority = excluded.priority,
            subject = excluded.subject,
            body = excluded.body,
            status = excluded.status
        """
    )
    query = cast(
        LiteralString,
        f"""
        insert into tickets (
            ticket_id, created_at, channel, customer_id, customer_name, requester_email,
            company, tier, site_id, product_area, priority, subject, body, status
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        {conflict_clause}
        """,
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            [
                (
                    t["ticket_id"],
                    t["created_at"],
                    t["channel"],
                    t["customer_id"],
                    t["customer_name"],
                    t["requester_email"],
                    t["company"],
                    t["tier"],
                    t["site_id"],
                    t["product_area"],
                    t["priority"],
                    t["subject"],
                    t["body"],
                    t["status"],
                )
                for t in tickets
            ],
        )
    connection.commit()


def seed_all(
    connection: psycopg.Connection,
    policies_dir: Path | str = REPO_ROOT / "data" / "policies",
    tickets_dir: Path | str = REPO_ROOT / "data" / "tickets",
    sites_path: Path | str | None = REPO_ROOT / "data" / "telemetry" / "sites.json",
    preserve_existing_tickets: bool = False,
) -> None:
    apply_schema(connection)
    upsert_policies(connection, load_policies(policies_dir))
    t_dir = Path(tickets_dir)
    accounts_file = t_dir / "accounts.csv"
    if accounts_file.exists():
        upsert_accounts(connection, load_accounts_seed(accounts_file, sites_path))
    tickets_file = t_dir / "tickets.jsonl"
    if tickets_file.exists():
        upsert_tickets(
            connection,
            load_tickets_seed(tickets_file),
            preserve_existing=preserve_existing_tickets,
        )
