import os

import psycopg

from retrieval.service import RetrievalService

_EXPECTED_POLICY_IDS: list[str] = [
    "POL-CRED",
    "POL-CREDIT",
    "POL-IDV",
    "POL-SEC",
    "POL-SEV1",
    "POL-SLA",
]

# Review Focus 1: id spelling variants that must all resolve to POL-SLA.
_SLA_VARIANTS: list[str] = [" pol-sla ", "POL-SLA.md", "pol-sla.MD"]

# Review Focus 2: ids that must not resolve and never raise.
_UNKNOWN_IDS: list[str] = ["", "POL-SLA-EXTRA", "../POL-SLA"]


def test_agent_can_look_up_and_cite_every_policy() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        service = RetrievalService(connection)

        policies = service.list_policies()
        assert [policy.policy_id for policy in policies] == _EXPECTED_POLICY_IDS

        for policy_id in _EXPECTED_POLICY_IDS:
            policy = service.get_policy(policy_id)
            assert policy is not None
            assert policy.title != ""
            assert policy.body != ""
            assert policy.file_path.endswith(f"{policy_id}.md")
            assert policy.citation_tag() == f"[policy:{policy_id}]"

        for variant in _SLA_VARIANTS:
            resolved = service.get_policy(variant)
            assert resolved is not None
            assert resolved.policy_id == "POL-SLA"

        for unknown_id in _UNKNOWN_IDS:
            assert service.get_policy(unknown_id) is None


def test_policy_lookup_survives_db_outage() -> None:
    connection = psycopg.connect(os.environ["DATABASE_URL"])
    service = RetrievalService(connection)
    connection.close()

    policy = service.get_policy("POL-SEV1")
    assert policy is not None
    assert policy.policy_id == "POL-SEV1"
    assert len(service.list_policies()) == 6
