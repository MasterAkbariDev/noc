from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from noc_shared.signing import (
    HEADER_SIGNATURE,
    SignatureError,
    SignatureFailure,
    sign_request,
    verify_request,
)

SECRET = b"shared-secret"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def lookup(key_id: str) -> bytes | None:
    return SECRET if key_id == "k1" else None


def signed_headers(body: bytes = b"{}", path: str = "/v1/tools/x") -> dict[str, str]:
    return sign_request("k1", SECRET, "POST", path, body, now=NOW).as_dict()


def test_valid_signature_is_accepted() -> None:
    verified = verify_request(lookup, "POST", "/v1/tools/x", b"{}", signed_headers(), NOW)
    assert verified.key_id == "k1"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [("GET", "/v1/tools/x", b"{}"), ("POST", "/v1/tools/y", b"{}"), ("POST", "/v1/tools/x", b"[]")],
)
def test_tampering_is_detected(method: str, path: str, body: bytes) -> None:
    with pytest.raises(SignatureError) as error:
        verify_request(lookup, method, path, body, signed_headers(), NOW)
    assert error.value.failure is SignatureFailure.BAD_SIGNATURE


def test_clock_skew_is_rejected() -> None:
    later = NOW + timedelta(seconds=31)
    with pytest.raises(SignatureError) as error:
        verify_request(lookup, "POST", "/v1/tools/x", b"{}", signed_headers(), later)
    assert error.value.failure is SignatureFailure.CLOCK_SKEW


def test_unknown_key_and_missing_headers_are_rejected() -> None:
    headers = sign_request("other", SECRET, "POST", "/p", b"", now=NOW).as_dict()
    with pytest.raises(SignatureError) as unknown:
        verify_request(lookup, "POST", "/p", b"", headers, NOW)
    assert unknown.value.failure is SignatureFailure.UNKNOWN_KEY

    del headers[HEADER_SIGNATURE]
    with pytest.raises(SignatureError) as missing:
        verify_request(lookup, "POST", "/p", b"", headers, NOW)
    assert missing.value.failure is SignatureFailure.MISSING_HEADER


@given(body=st.binary(max_size=512), flipped=st.integers(min_value=0, max_value=511))
def test_any_body_change_breaks_the_signature(body: bytes, flipped: int) -> None:
    headers = signed_headers(body)
    verify_request(lookup, "POST", "/v1/tools/x", body, headers, NOW)
    if body:
        index = flipped % len(body)
        changed = body[:index] + bytes([body[index] ^ 0xFF]) + body[index + 1 :]
        with pytest.raises(SignatureError):
            verify_request(lookup, "POST", "/v1/tools/x", changed, headers, NOW)
