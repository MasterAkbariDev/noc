import uuid
from datetime import UTC, datetime

import pytest

from noc.peers.codes import make_code, parse_code
from noc.peers.signing import sign, verify

SECRET = "a" * 64
NOW = 1_800_000_000
BODY = b"{}"


def test_a_signature_checks_out_for_the_same_request() -> None:
    signature = sign(SECRET, "GET", "/api/peer/status", str(NOW), b"")
    assert verify(SECRET, "GET", "/api/peer/status", str(NOW), b"", signature, NOW)


@pytest.mark.parametrize(
    "method, path, body, secret, timestamp",
    [
        ("POST", "/api/peer/status", b"", SECRET, str(NOW)),
        ("GET", "/api/peer/hello", b"", SECRET, str(NOW)),
        ("GET", "/api/peer/status", BODY, SECRET, str(NOW)),
        ("GET", "/api/peer/status", b"", "b" * 64, str(NOW)),
        ("GET", "/api/peer/status", b"", SECRET, str(NOW - 301)),
        ("GET", "/api/peer/status", b"", SECRET, "not-a-number"),
    ],
)
def test_a_changed_request_is_refused(
    method: str, path: str, body: bytes, secret: str, timestamp: str
) -> None:
    signature = sign(SECRET, "GET", "/api/peer/status", str(NOW), b"")
    assert not verify(secret, method, path, timestamp, body, signature, NOW)


def test_a_request_within_the_clock_skew_is_accepted() -> None:
    signature = sign(SECRET, "GET", "/api/peer/status", str(NOW - 299), b"")
    assert verify(SECRET, "GET", "/api/peer/status", str(NOW - 299), b"", signature, NOW)


def test_a_join_code_round_trips_with_its_secret_and_expiry() -> None:
    peer_id = uuid.uuid4()
    expires = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)
    code = make_code(peer_id, "https://noc.example/", SECRET, expires)
    parsed = parse_code(code)
    assert parsed.peer_id == peer_id
    assert parsed.url == "https://noc.example"
    assert parsed.secret == SECRET
    assert parsed.expires_at == expires


@pytest.mark.parametrize("bad", ["", "not base64 !!", "eyJ2IjoyfQ"])
def test_a_broken_join_code_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="not valid"):
        parse_code(bad)
