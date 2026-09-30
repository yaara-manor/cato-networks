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


@pytest.mark.parametrize(
    "case_id,text,secret,kind",
    _STRUCTURAL_CASES,
    ids=[case[0] for case in _STRUCTURAL_CASES],
)
def test_structural_secret_is_redacted(case_id: str, text: str, secret: str, kind: str) -> None:
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
