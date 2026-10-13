import base64
import hashlib
import hmac
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

HEADER_KEY_ID = "X-NOC-Key-Id"
HEADER_TIMESTAMP = "X-NOC-Timestamp"
HEADER_NONCE = "X-NOC-Nonce"
HEADER_SIGNATURE = "X-NOC-Signature"

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DEFAULT_MAX_SKEW_SECONDS = 30


class SignatureFailure(StrEnum):
    MISSING_HEADER = "missing_header"
    UNKNOWN_KEY = "unknown_key"
    BAD_TIMESTAMP = "bad_timestamp"
    CLOCK_SKEW = "clock_skew"
    BAD_SIGNATURE = "bad_signature"


class SignatureError(Exception):
    def __init__(self, failure: SignatureFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure


@dataclass(frozen=True)
class SignedHeaders:
    key_id: str
    timestamp: str
    nonce: str
    signature: str

    def as_dict(self) -> dict[str, str]:
        return {
            HEADER_KEY_ID: self.key_id,
            HEADER_TIMESTAMP: self.timestamp,
            HEADER_NONCE: self.nonce,
            HEADER_SIGNATURE: self.signature,
        }


@dataclass(frozen=True)
class VerifiedRequest:
    key_id: str
    nonce: str
    signed_at: datetime


def format_timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def body_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_string(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    parts = [method.upper(), path, timestamp, nonce, body_digest(body)]
    return "\n".join(parts).encode()


def compute_signature(
    secret: bytes, method: str, path: str, timestamp: str, nonce: str, body: bytes
) -> str:
    message = canonical_string(method, path, timestamp, nonce, body)
    digest = hmac.new(secret, message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def sign_request(
    key_id: str,
    secret: bytes,
    method: str,
    path: str,
    body: bytes,
    now: datetime | None = None,
    nonce: str | None = None,
) -> SignedHeaders:
    timestamp = format_timestamp(now or datetime.now(UTC))
    nonce_value = nonce or secrets.token_hex(16)
    signature = compute_signature(secret, method, path, timestamp, nonce_value, body)
    return SignedHeaders(key_id, timestamp, nonce_value, signature)


def verify_request(
    lookup_secret: Callable[[str], bytes | None],
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    now: datetime,
    max_skew_seconds: int = DEFAULT_MAX_SKEW_SECONDS,
) -> VerifiedRequest:
    key_id = headers.get(HEADER_KEY_ID)
    timestamp = headers.get(HEADER_TIMESTAMP)
    nonce = headers.get(HEADER_NONCE)
    signature = headers.get(HEADER_SIGNATURE)
    if not (key_id and timestamp and nonce and signature):
        raise SignatureError(SignatureFailure.MISSING_HEADER)

    secret = lookup_secret(key_id)
    if secret is None:
        raise SignatureError(SignatureFailure.UNKNOWN_KEY)

    try:
        signed_at = parse_timestamp(timestamp)
    except ValueError as exc:
        raise SignatureError(SignatureFailure.BAD_TIMESTAMP) from exc

    if abs((now - signed_at).total_seconds()) > max_skew_seconds:
        raise SignatureError(SignatureFailure.CLOCK_SKEW)

    expected = compute_signature(secret, method, path, timestamp, nonce, body)
    if not hmac.compare_digest(expected, signature):
        raise SignatureError(SignatureFailure.BAD_SIGNATURE)

    return VerifiedRequest(key_id=key_id, nonce=nonce, signed_at=signed_at)
