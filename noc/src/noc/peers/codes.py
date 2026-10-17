import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

CODE_VERSION = 1


@dataclass(frozen=True)
class JoinCode:
    peer_id: uuid.UUID
    url: str
    secret: str
    expires_at: datetime


def make_code(peer_id: uuid.UUID, url: str, secret: str, expires_at: datetime) -> str:
    payload = {
        "v": CODE_VERSION,
        "id": str(peer_id),
        "url": url,
        "secret": secret,
        "exp": int(expires_at.timestamp()),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def parse_code(code: str) -> JoinCode:
    padded = code.strip() + "=" * (-len(code.strip()) % 4)
    try:
        data: Any = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, json.JSONDecodeError) as error:
        raise ValueError("this join code is not valid") from error
    if not isinstance(data, dict) or data.get("v") != CODE_VERSION:
        raise ValueError("this join code is not valid")
    try:
        return JoinCode(
            peer_id=uuid.UUID(str(data["id"])),
            url=str(data["url"]).rstrip("/"),
            secret=str(data["secret"]),
            expires_at=datetime.fromtimestamp(int(data["exp"]), UTC),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("this join code is not valid") from error
