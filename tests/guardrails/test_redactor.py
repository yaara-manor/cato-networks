import hashlib

import pytest

from guardrails import redact

_PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA7vbqajDw\n4pS6xZq9kR2TfLw=\n-----END RSA PRIVATE KEY-----"
_PEM_TRUNCATED = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEF"
_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4"
_GHP = "ghp_" + "a" * 36

_STRUCTURAL_CASES: list[tuple[str, str, str, str]] = [
    ("pem", f"here is my key:\n{_PEM}\nplease check", _PEM, "PRIVATE_KEY"),
    ("pem_truncated", f"pasted:\n{_PEM_TRUNCATED}", _PEM_TRUNCATED, "PRIVATE_KEY"),
    (
        "bearer_header",
        "curl -H 'Authorization: Bearer abcdefghijklmnop1234' https://api.example.com/v1/sites",
        "abcdefghijklmnop1234",
        "BEARER_TOKEN",
    ),
    ("authorization_basic", "Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz", "BEARER_TOKEN"),
    ("jwt", f"my session token {_JWT} stopped working", _JWT, "JWT"),
    ("aws_akia", "the access key AKIAIOSFODNN7EXAMPLE was rotated", "AKIAIOSFODNN7EXAMPLE", "VENDOR_KEY"),
    ("openai_sk", "we use sk-abcdefghijklmnopqrstuvwx for the bot", "sk-abcdefghijklmnopqrstuvwx", "VENDOR_KEY"),
    ("github_ghp", f"clone with {_GHP} as the credential", _GHP, "VENDOR_KEY"),
    ("slack_xoxb", "bot credential xoxb-1234567890-abcdef in the workspace", "xoxb-1234567890-abcdef", "VENDOR_KEY"),
    ("kv_equals", "login uses password=hunter2 on the portal", "hunter2", "KEY_VALUE"),
    ("kv_yaml", "config:\n  api_key: abc123XYZ\n  region: eu", "abc123XYZ", "KEY_VALUE"),
    (
        "kv_json_spaces",
        '{"client_secret": "s3cr3t value!", "x": 1}',
        "s3cr3t value!",
        "KEY_VALUE",
    ),
    ("radius_secret", "radius_secret = Tr0ub4dor", "Tr0ub4dor", "KEY_VALUE"),
    ("scim_token_env", "SCIM_TOKEN=tok-12345", "tok-12345", "KEY_VALUE"),
    ("psk_key", "pre_shared_key: abc123", "abc123", "KEY_VALUE"),
    ("url_userinfo", "see https://admin:P4ss@host.example.com/x for details", "P4ss", "KEY_VALUE"),
    ("curl_user", "curl -u admin:P4ss https://x", "P4ss", "KEY_VALUE"),
]

_VENDOR_CASES: list[tuple[str, str, str, str]] = [
    ("forti_enc", "set psksecret ENC abcdEFG==", "abcdEFG==", "VENDOR_CONFIG"),
    ("forti_quoted", 'set psksecret "abcd1234"', "abcd1234", "VENDOR_CONFIG"),
    ("cisco_key7", "crypto isakmp key 7 0822455D0A16 address 1.2.3.4", "0822455D0A16", "VENDOR_CONFIG"),
    ("cisco_password0", "username a password 0 hunter2", "hunter2", "VENDOR_CONFIG"),
    ("cisco_secret5", "enable secret 5 $1$abc$xyz", "$1$abc$xyz", "VENDOR_CONFIG"),
    ("cisco_psk_local", "pre-shared-key local 0 MyKey123", "MyKey123", "VENDOR_CONFIG"),
    ("strongswan", ': PSK "abc def"', "abc def", "VENDOR_CONFIG"),
    ("env_key", "STRIPE_SECRET_KEY=abc", "abc", "VENDOR_CONFIG"),
    ("env_export_key", 'export DEPLOY_KEY="k3y-value"', "k3y-value", "VENDOR_CONFIG"),
]

_ENTROPY_CASES: list[tuple[str, str, str, str]] = [
    (
        "bare_token",
        "here q3Zx9LkP0mNb7VcR2tYwH5jA8sDf end",
        "q3Zx9LkP0mNb7VcR2tYwH5jA8sDf",
        "HIGH_ENTROPY",
    ),
    ("base64", "tok dGhpcyBpcyBhIHZlcnkgbG9uZyBzZWNyZXQ= end", "dGhpcyBpcyBhIHZlcnkgbG9uZyBzZWNyZXQ=", "HIGH_ENTROPY"),
    (
        "mixed_case_with_separators",
        "value aB3-x_9KqLmN2-pQ7r_ZzYw1vv here",
        "aB3-x_9KqLmN2-pQ7r_ZzYw1vv",
        "HIGH_ENTROPY",
    ),
]

_ALLOWLIST_CASES: list[tuple[str, str]] = [
    ("fqdn", "core-switch-01.prod.internal.company.com"),
    ("slug", "cato-ipsec-guide-ikev1-vs-ikev2-2026"),
    ("snake", "get_link_quality_24h_window_x"),
    ("uuid_upper", "123E4567-E89B-12D3-A456-426614174000"),
    ("url", "https://knowledge.catonetworks.com/docs/cato-ipsec-guide-ikev1-vs-ikev2"),
    ("email", "hana.kowalski.longname1@solsticemedia.com"),
    ("ipv6", "fe80::a1b2:c3d4:e5f6:1234:5678"),
    ("cidr6", "2001:db8:abcd:ef01:2345:6789:abcd:ef01/64"),
    ("path", "/var/log/cato-socket/ipsec-2026-08.log"),
]

_REDACTION_CASES: list[tuple[str, str, str, str]] = _STRUCTURAL_CASES + _VENDOR_CASES + _ENTROPY_CASES

_SC08_PSK = "Fg7!qwe-DC-2026-tunnel"
_SC08_TAIL = "Can you confirm what you have on your side?"


@pytest.mark.parametrize(
    "case_id,text,secret,kind",
    _REDACTION_CASES,
    ids=[case[0] for case in _REDACTION_CASES],
)
def test_secret_is_redacted(case_id: str, text: str, secret: str, kind: str) -> None:
    result = redact(text)
    assert secret not in result.text
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.kind == kind
    assert text[finding.start : finding.end] == secret
    assert finding.sha256 == hashlib.sha256(secret.encode()).hexdigest()
    assert f"[REDACTED:{kind}]" in result.text


def test_finding_never_contains_the_raw_value() -> None:
    assert "hunter2" not in redact("password=hunter2").model_dump_json()


def test_overlapping_hits_merge_with_earliest_kind() -> None:
    result = redact("Authorization: Bearer abcdefghijklmnop1234")
    assert len(result.findings) == 1
    assert result.findings[0].kind == "BEARER_TOKEN"


def test_clean_text_is_returned_unchanged() -> None:
    text = "BGP hold time is 30 seconds"
    result = redact(text)
    assert result.text == text
    assert result.findings == ()
    assert result.was_redacted is False


@pytest.mark.parametrize("separator", [":", ""], ids=["colon", "bare_is"])
def test_contextual_catches_sc08_psk_in_both_spellings(separator: str) -> None:
    text = f"PSK on our side is{separator} {_SC08_PSK}. {_SC08_TAIL}"
    result = redact(text)
    assert _SC08_PSK not in result.text
    assert _SC08_TAIL in result.text
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.kind == "CONTEXTUAL"
    assert text[finding.start : finding.end] == _SC08_PSK


@pytest.mark.parametrize(
    "text",
    [
        "The password reset is pending.",
        "the token was expired",
        "PSK was re-entered 26 h ago",
        "The PSK on the Cato side was re-entered yesterday",
        "the secret is unknown",
    ],
)
def test_contextual_value_shape_guard(text: str) -> None:
    assert redact(text).findings == ()


def test_contextual_is_bounded_to_five_words() -> None:
    assert redact("password one two three four five six is Zz9!aaaa").findings == ()


def test_key_value_and_contextual_overlap_merge_to_key_value() -> None:
    result = redact("password=hunter2")
    assert len(result.findings) == 1
    assert result.findings[0].kind == "KEY_VALUE"


@pytest.mark.parametrize("case_id,token", _ALLOWLIST_CASES, ids=[case[0] for case in _ALLOWLIST_CASES])
def test_allowlisted_token_is_not_flagged(case_id: str, token: str) -> None:
    assert redact(f"see {token} for details").findings == ()


def test_url_with_userinfo_is_not_allowlisted() -> None:
    text = "https://admin:P4ss@host.example.com/a/b"
    result = redact(text)
    assert "P4ss" not in result.text
    assert len(result.findings) == 1
    assert result.findings[0].kind == "KEY_VALUE"


@pytest.mark.parametrize(
    "token",
    ["q3Zx9LkP0mNb7VcR2tYwH5j", "ab" * 12, "abcdefghijklmnopqrstuvwxyzabcd"],
    ids=["too_short", "one_class_low_entropy", "one_class_long"],
)
def test_below_thresholds_is_not_flagged(token: str) -> None:
    assert redact(f"value {token} here").findings == ()
