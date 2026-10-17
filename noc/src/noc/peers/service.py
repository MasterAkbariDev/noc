import asyncio
import secrets
import socket
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import Incident, Peer, Target
from noc.domain.incident_status import ACTIVE_STATUSES
from noc.peers.codes import make_code, parse_code
from noc.peers.signing import HEADER_PEER, HEADER_SIGNATURE, HEADER_TIMESTAMP, sign
from noc.secret_store import SecretStore

CODE_TTL: Final = timedelta(minutes=10)
REQUEST_TIMEOUT_SECONDS: Final = 10.0
NAME_MAX_LENGTH: Final = 64
HELLO_PATH: Final = "/api/peer/hello"
STATUS_PATH: Final = "/api/peer/status"
SERVES: Final = "serves"
FOLLOWS: Final = "follows"
PENDING: Final = "pending"
PAIRED: Final = "paired"


class PeerRefused(Exception):
    pass


def secret_name(peer_id: uuid.UUID) -> str:
    return f"peer-{peer_id}"


def clean_name(raw: str) -> str:
    name = raw.strip()
    if not name or len(name) > NAME_MAX_LENGTH:
        raise ValueError(f"the name must be 1-{NAME_MAX_LENGTH} characters")
    return name


async def create_join_code(
    session: AsyncSession, store: SecretStore, settings: Settings, name: str, actor: str
) -> tuple[str, Peer]:
    if not settings.public_url:
        raise ValueError("Set NOC_PUBLIC_URL to this panel's address before creating a join code.")
    label = clean_name(name)
    secret = secrets.token_hex(32)
    peer = Peer(
        name=label,
        url="",
        direction=SERVES,
        status=PENDING,
        expires_at=utc_now() + CODE_TTL,
        created_by=actor,
    )
    session.add(peer)
    await session.flush()
    await asyncio.to_thread(store.write, secret_name(peer.id), secret)
    await append_audit(session, actor, "peer_join_code_created", f"peer:{peer.id}", {"name": label})
    expires_at = peer.expires_at or utc_now() + CODE_TTL
    code = make_code(peer.id, settings.public_url.rstrip("/"), secret, expires_at)
    return code, peer


def accept_hello(peer: Peer, now: datetime) -> None:
    if peer.direction != SERVES:
        raise PeerRefused("this node does not serve that peer")
    if peer.status == PAIRED:
        return
    if peer.expires_at is None or peer.expires_at <= now:
        raise PeerRefused("the join code has expired")
    peer.status = PAIRED
    peer.paired_at = now
    peer.expires_at = None


def ensure_served(peer: Peer) -> None:
    if peer.direction != SERVES or peer.status != PAIRED:
        raise PeerRefused("this peer is not paired")


async def signed_request(
    method: str,
    base_url: str,
    path: str,
    peer_id: uuid.UUID,
    secret: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    timestamp = str(int(time.time()))
    signature = sign(secret, method, path, timestamp, b"")
    headers = {
        HEADER_PEER: str(peer_id),
        HEADER_TIMESTAMP: timestamp,
        HEADER_SIGNATURE: signature,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, transport=transport) as http:
        return await http.request(method, f"{base_url}{path}", headers=headers)


async def redeem_join_code(
    session: AsyncSession,
    store: SecretStore,
    code_text: str,
    actor: str,
    transport: httpx.AsyncBaseTransport | None = None,
    label: str | None = None,
) -> Peer:
    code = parse_code(code_text)
    if code.expires_at <= utc_now():
        raise ValueError("this join code has expired")
    peer = await session.get(Peer, code.peer_id)
    if peer is not None and peer.direction != FOLLOWS:
        raise ValueError("this node already has that peer under another direction")
    if peer is not None and peer.status == PAIRED:
        raise ValueError("this join code was already used")
    if peer is None:
        host = urlsplit(code.url).hostname or "node"
        chosen = (label or "").strip() or host
        peer = Peer(
            id=code.peer_id,
            name=chosen[:NAME_MAX_LENGTH],
            url=code.url,
            direction=FOLLOWS,
            status=PENDING,
            created_by=actor,
        )
        session.add(peer)
        await session.flush()
    await asyncio.to_thread(store.write, secret_name(peer.id), code.secret)
    try:
        response = await signed_request(
            "POST", code.url, HELLO_PATH, peer.id, code.secret, transport
        )
    except httpx.HTTPError as error:
        peer.last_error = f"{type(error).__name__}"[:255]
    else:
        if response.status_code == 200:
            peer.status = PAIRED
            peer.paired_at = utc_now()
            peer.last_error = None
        else:
            peer.last_error = f"the other node answered HTTP {response.status_code}"[:255]
    await append_audit(
        session, actor, "peer_joined", f"peer:{peer.id}", {"status": peer.status, "url": code.url}
    )
    return peer


async def refresh_status(
    session: AsyncSession,
    store: SecretStore,
    peer: Peer,
    actor: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Peer:
    if peer.direction != FOLLOWS or peer.status != PAIRED:
        raise PeerRefused("this node is not paired with that peer")
    secret = await asyncio.to_thread(store.read, secret_name(peer.id))
    if not secret:
        raise PeerRefused("the key for this peer is missing; remove it and join again")
    try:
        response = await signed_request("GET", peer.url, STATUS_PATH, peer.id, secret, transport)
    except httpx.HTTPError as error:
        peer.last_error = f"{type(error).__name__}"[:255]
        return peer
    if response.status_code != 200:
        peer.last_error = f"the other node answered HTTP {response.status_code}"[:255]
        return peer
    payload: dict[str, Any] = response.json()
    peer.last_status = payload
    peer.last_seen_at = utc_now()
    peer.last_error = None
    node = payload.get("node_name")
    if isinstance(node, str) and node.strip() and peer.name == (urlsplit(peer.url).hostname or ""):
        peer.name = node.strip()[:NAME_MAX_LENGTH]
    return peer


async def revoke_peer(session: AsyncSession, store: SecretStore, peer: Peer, actor: str) -> None:
    await asyncio.to_thread(store.delete, secret_name(peer.id))
    await append_audit(session, actor, "peer_removed", f"peer:{peer.id}", {"name": peer.name})
    await session.delete(peer)


async def local_status(session: AsyncSession, settings: Settings) -> dict[str, Any]:
    targets = list(await session.scalars(select(Target).order_by(Target.name)))
    active = (
        await session.execute(
            select(Incident, Target.name)
            .join(Target, Target.id == Incident.target_id)
            .where(Incident.status.in_([status.value for status in ACTIVE_STATUSES]))
            .order_by(Incident.opened_at)
        )
    ).all()
    return {
        "node_name": settings.node_name or socket.gethostname(),
        "generated_at": utc_now().isoformat(),
        "targets": [
            {
                "name": target.name,
                "label": target.label,
                "environment": target.environment,
                "automation": target.automation_level,
                "halted": target.halted,
            }
            for target in targets
        ],
        "active_incidents": [
            {
                "id": str(incident.id),
                "title": incident.title,
                "status": incident.status,
                "target": name,
                "opened_at": incident.opened_at.isoformat(),
            }
            for incident, name in active
        ],
    }
