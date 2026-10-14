import base64
import hmac
import secrets
import struct
from datetime import datetime
from typing import Final
from urllib.parse import quote, urlencode

SECRET_BYTES: Final = 20
STEP_SECONDS: Final = 30
DIGITS: Final = 6
ACCEPTED_STEP_DRIFT: Final = 1
HOTP_MASK: Final = 0x7FFFFFFF
LOW_NIBBLE: Final = 0x0F
DIGEST_NAME: Final = "sha1"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode()


def counter_code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret)
    digest = hmac.new(key, struct.pack(">Q", counter), DIGEST_NAME).digest()
    offset = digest[-1] & LOW_NIBBLE
    value = int.from_bytes(digest[offset : offset + 4], "big") & HOTP_MASK
    return str(value % 10**DIGITS).zfill(DIGITS)


def step_at(moment: datetime) -> int:
    return int(moment.timestamp()) // STEP_SECONDS


def matching_step(secret: str, code: str, moment: datetime, last_step: int | None) -> int | None:
    candidate = code.strip().replace(" ", "")
    if len(candidate) != DIGITS or not candidate.isdigit():
        return None
    current = step_at(moment)
    matched: int | None = None
    for step in range(current - ACCEPTED_STEP_DRIFT, current + ACCEPTED_STEP_DRIFT + 1):
        is_fresh = last_step is None or step > last_step
        if hmac.compare_digest(counter_code(secret, step), candidate) and is_fresh:
            matched = step
    return matched


def provisioning_uri(issuer: str, username: str, secret: str) -> str:
    label = quote(f"{issuer}:{username}", safe="")
    query = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": STEP_SECONDS,
        },
        quote_via=quote,
    )
    return f"otpauth://totp/{label}?{query}"
