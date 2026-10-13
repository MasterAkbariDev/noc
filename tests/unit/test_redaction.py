from noc.llm.redaction import redact


def test_secrets_are_removed_in_every_policy() -> None:
    text = "password=hunter2 Authorization: Bearer abc.def postgres://app:s3cret@db/app"
    result = redact(text, "full")
    assert "hunter2" not in result.text
    assert "abc.def" not in result.text
    assert "s3cret" not in result.text
    assert result.replacements == 3


def test_public_ips_and_emails_are_pseudonymized_unless_full() -> None:
    text = "login from 93.184.216.34 and 10.0.0.5 by ops@example.com"
    redacted = redact(text, "redacted").text
    assert "93.184.216.34" not in redacted
    assert "10.0.0.5" in redacted
    assert "[EMAIL]" in redacted
    assert "93.184.216.34" in redact(text, "full").text


def test_pseudonyms_are_stable() -> None:
    assert redact("1.2.3.4", "redacted").text == redact("1.2.3.4", "redacted").text
