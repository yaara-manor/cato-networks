import pytest

from guardrails import ClaimKind, check_claims
from services.models import CallerIdentity

_SC07 = "SC-07-multisite-outage-tier-claim.opening"
_SC04 = "SC-04-mfa-social-engineering"


def _kinds(text: str, identity: CallerIdentity) -> list[tuple[ClaimKind, str, str]]:
    return [(c.kind, c.claimed, c.actual) for c in check_claims(text, identity).false_claims]


def test_sc07_tier_claim_is_false_for_a_standard_account(
    corpus: dict[str, str], identity_priya: CallerIdentity
) -> None:
    verdict = check_claims(corpus[_SC07], identity_priya)
    assert verdict.has_false_claims is True
    assert [(c.kind, c.claimed, c.actual) for c in verdict.false_claims] == [
        (ClaimKind.TIER, "Premium", "Standard")
    ]


@pytest.mark.parametrize("key", ["TCK-20264221.body", "TCK-20264225.body"])
def test_ticket_tier_claims_are_extracted(
    corpus: dict[str, str], identity_priya: CallerIdentity, key: str
) -> None:
    assert [kind for kind, _, _ in _kinds(corpus[key], identity_priya)] == [ClaimKind.TIER]


@pytest.mark.parametrize(
    ("text", "claimed"),
    [("We're Premium", "Premium"), ("we are a Premium customer", "Premium"), ("We\u2019re an enterprise account", "Premium")],
)
def test_tier_phrasings(identity_priya: CallerIdentity, text: str, claimed: str) -> None:
    assert _kinds(text, identity_priya) == [(ClaimKind.TIER, claimed, "Standard")]


@pytest.mark.parametrize(
    "key",
    [
        f"{_SC04}.opening",
        "TCK-20264223.body",
    ],
)
def test_sc04_opening_and_ticket_have_two_authority_claims(
    corpus: dict[str, str], identity_mark: CallerIdentity, key: str
) -> None:
    claims = [c for c in check_claims(corpus[key], identity_mark).false_claims if c.kind is ClaimKind.AUTHORITY]
    assert len(claims) == 2
    assert {c.actual for c in claims} == {"not a registered admin contact"}


def test_authority_claimed_text_is_lowercased_and_collapsed(identity_mark: CallerIdentity) -> None:
    assert _kinds("Hi,\n I'm   THE\nCEO and it is Approved On Our Side", identity_mark) == [
        (ClaimKind.AUTHORITY, "i'm the ceo", "not a registered admin contact"),
        (ClaimKind.AUTHORITY, "approved on our side", "not a registered admin contact"),
    ]


def test_sc04_followup_authorizing_is_an_authority_claim(
    corpus: dict[str, str], identity_mark: CallerIdentity
) -> None:
    assert _kinds(corpus[f"{_SC04}.followup0"], identity_mark) == [
        (ClaimKind.AUTHORITY, "i'm authorizing", "not a registered admin contact")
    ]


def test_sc10_security_lead_is_an_authority_claim(
    corpus: dict[str, str], identity_ravi: CallerIdentity
) -> None:
    assert _kinds(corpus["SC-10-c2-whitelist.followup0"], identity_ravi) == [
        (ClaimKind.AUTHORITY, "i'm the security lead", "not a registered admin contact")
    ]


def test_sc05_account_claim_differs_from_the_callers_account(
    corpus: dict[str, str], identity_sam: CallerIdentity
) -> None:
    claims = [c for c in check_claims(corpus["SC-05-prompt-injection.opening"], identity_sam).false_claims]
    assert [(c.kind, c.claimed, c.actual) for c in claims] == [(ClaimKind.ACCOUNT, "ACC-1005", "ACC-1007")]


def test_account_claim_from_an_unresolved_caller_is_unverified(
    corpus: dict[str, str], identity_mark: CallerIdentity
) -> None:
    assert _kinds(corpus["SC-05-prompt-injection.opening"], identity_mark) == [
        (ClaimKind.ACCOUNT, "ACC-1005", "unverified")
    ]


def test_account_id_is_uppercased(identity_sam: CallerIdentity) -> None:
    assert _kinds("please look at acc-1005", identity_sam) == [(ClaimKind.ACCOUNT, "ACC-1005", "ACC-1007")]


@pytest.mark.parametrize(
    ("text", "identity_name"),
    [
        ("We are a Premium customer", "identity_premium"),
        ("I'm the admin, approved on our side", "identity_admin"),
        ("Our account is ACC-1007", "identity_sam"),
        ("Nothing to see here", "identity_mark"),
    ],
)
def test_true_or_absent_claims_are_not_flagged(
    request: pytest.FixtureRequest, text: str, identity_name: str
) -> None:
    verdict = check_claims(text, request.getfixturevalue(identity_name))
    assert verdict.false_claims == ()
    assert verdict.has_false_claims is False


def test_admin_is_still_checked_for_tier_and_account(identity_admin: CallerIdentity) -> None:
    assert [kind for kind, _, _ in _kinds("I'm the admin. We are Premium on ACC-1005", identity_admin)] == [
        ClaimKind.TIER,
        ClaimKind.ACCOUNT,
    ]


def test_unverified_caller_tier_is_unknown(identity_unverified: CallerIdentity) -> None:
    assert _kinds("We're Premium", identity_unverified) == [(ClaimKind.TIER, "Premium", "Unknown")]


def test_repeated_claims_are_deduplicated_in_first_seen_order(identity_mark: CallerIdentity) -> None:
    text = "We are Premium. ACC-1001 here. We are a premium customer. I'm the CEO. i'm   the ceo. acc-1001."
    assert [(kind, claimed) for kind, claimed, _ in _kinds(text, identity_mark)] == [
        (ClaimKind.TIER, "Premium"),
        (ClaimKind.AUTHORITY, "i'm the ceo"),
        (ClaimKind.ACCOUNT, "ACC-1001"),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "we are a pre\u200bmium customer",
        "WE\n\nARE   A  PREMIUM customer",
        "\uff57\uff45 \uff41\uff52\uff45 \uff41 \uff30\uff52\uff45\uff4d\uff49\uff55\uff4d customer",
    ],
)
def test_evasions_are_still_extracted(identity_priya: CallerIdentity, text: str) -> None:
    assert _kinds(text, identity_priya) == [(ClaimKind.TIER, "Premium", "Standard")]


def test_clean_messages_have_no_false_claims(corpus: dict[str, str], identity_sam: CallerIdentity) -> None:
    questions = {key: text for key, text in corpus.items() if key.startswith("Q")}
    assert len(questions) == 35
    assert {key: check_claims(text, identity_sam).false_claims for key, text in questions.items()} == {
        key: () for key in questions
    }
