import hashlib
import hmac
from typing import Final

MAX_SKEW_SECONDS: Final = 300
HEADER_PEER: Final = "X-NOC-Peer"
HEADER_TIMESTAMP: Final = "X-NOC-Timestamp"
HEADER_SIGNATURE: Final = "X-NOC-Signature"


def canonical(method: str, path: str, timestamp: str, body: bytes) -> bytes:
    digest = hashlib.sha256(body).hexdigest()
    return "\n".join([method.upper(), path, timestamp, digest]).encode()


def sign(secret: str, method: str, path: str, timestamp: str, body: bytes) -> str:
    return hmac.new(
        secret.encode(), canonical(method, path, timestamp, body), hashlib.sha256
    ).hexdigest()


def verify(
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    signature: str,
    now: int,
) -> bool:
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(now - sent_at) > MAX_SKEW_SECONDS:
        return False
    expected = sign(secret, method, path, timestamp, body)
    return hmac.compare_digest(expected, signature)
