import base64
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from noc.auth.totp import (
    DIGITS,
    SECRET_BYTES,
    STEP_SECONDS,
    counter_code,
    matching_step,
    new_secret,
    provisioning_uri,
    step_at,
)

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


def at_step(step: int, offset_seconds: int = 0) -> datetime:
    return datetime.fromtimestamp(step * STEP_SECONDS + offset_seconds, tz=UTC)


def test_codes_match_the_rfc_4226_test_vectors() -> None:
    expected = ["755224", "287082", "359152", "969429", "338314", "254676"]
    assert [counter_code(RFC_SECRET, counter) for counter in range(6)] == expected


def test_rfc_6238_time_to_step() -> None:
    assert step_at(datetime.fromtimestamp(59, tz=UTC)) == 1
    assert step_at(datetime.fromtimestamp(1111111109, tz=UTC)) == 37037036


def test_new_secrets_are_long_and_different() -> None:
    first, second = new_secret(), new_secret()
    assert first != second
    assert len(base64.b32decode(first)) == SECRET_BYTES


def test_current_code_is_accepted_and_returns_its_step() -> None:
    moment = at_step(1000, 5)
    code = counter_code(RFC_SECRET, 1000)
    assert matching_step(RFC_SECRET, code, moment, None) == 1000


def test_one_step_of_clock_drift_is_accepted_but_two_are_not() -> None:
    moment = at_step(1000, 5)
    assert matching_step(RFC_SECRET, counter_code(RFC_SECRET, 999), moment, None) == 999
    assert matching_step(RFC_SECRET, counter_code(RFC_SECRET, 1001), moment, None) == 1001
    assert matching_step(RFC_SECRET, counter_code(RFC_SECRET, 998), moment, None) is None
    assert matching_step(RFC_SECRET, counter_code(RFC_SECRET, 1002), moment, None) is None


def test_a_used_step_or_an_older_one_is_refused() -> None:
    moment = at_step(1000, 5)
    code = counter_code(RFC_SECRET, 1000)
    assert matching_step(RFC_SECRET, code, moment, 1000) is None
    assert matching_step(RFC_SECRET, code, moment, 1001) is None
    assert matching_step(RFC_SECRET, code, moment, 999) == 1000


def test_malformed_codes_are_refused() -> None:
    moment = at_step(1000, 5)
    for code in ("", "12345", "1234567", "abcdef", "12 34 5x"):
        assert matching_step(RFC_SECRET, code, moment, None) is None


def test_spaces_in_the_code_are_ignored() -> None:
    moment = at_step(1000, 5)
    code = counter_code(RFC_SECRET, 1000)
    assert matching_step(RFC_SECRET, f"{code[:3]} {code[3:]}", moment, None) == 1000


def test_provisioning_uri_carries_the_secret_and_parameters() -> None:
    uri = provisioning_uri("Multi-Agent NOC", "alice", RFC_SECRET)
    parts = urlsplit(uri)
    query = parse_qs(parts.query)
    assert parts.scheme == "otpauth"
    assert parts.netloc == "totp"
    assert parts.path == "/Multi-Agent%20NOC%3Aalice"
    assert query["secret"] == [RFC_SECRET]
    assert query["issuer"] == ["Multi-Agent NOC"]
    assert query["digits"] == [str(DIGITS)]
    assert query["period"] == [str(STEP_SECONDS)]
