import asyncio
import time
import uuid
from datetime import datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, get_session, get_settings_dep, require_role
from noc.auth.roles import Role
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import Peer
from noc.peers.service import (
    PAIRED,
    SERVES,
    PeerRefused,
    accept_hello,
    create_join_code,
    ensure_served,
    local_status,
    redeem_join_code,
    refresh_status,
    revoke_peer,
    secret_name,
)
from noc.peers.signing import HEADER_PEER, HEADER_SIGNATURE, HEADER_TIMESTAMP, verify
from noc.secret_store import SecretStore

peers_router = APIRouter(prefix="/api/peers", tags=["peers"])
peer_router = APIRouter(prefix="/api/peer", tags=["peer"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
AdminPrincipal = Annotated[Principal, Depends(require_role(Role.ADMIN))]
UNKNOWN_PEER = "unknown peer"
BAD_SIGNATURE = "the request signature is not valid"


def secret_store(settings: AppSettings) -> SecretStore:
    return SecretStore(settings.secrets_dir)


Store = Annotated[SecretStore, Depends(secret_store)]


class JoinCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)


class JoinCodeView(BaseModel):
    code: str
    expires_at: datetime


class JoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=2000)


class PeerView(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    direction: str
    status: str
    paired_at: datetime | None
    expires_at: datetime | None
    last_seen_at: datetime | None
    last_error: str | None
    last_status: dict[str, Any] | None


def peer_view(peer: Peer) -> PeerView:
    return PeerView(
        id=peer.id,
        name=peer.name,
        url=peer.url,
        direction=peer.direction,
        status=peer.status,
        paired_at=peer.paired_at,
        expires_at=peer.expires_at,
        last_seen_at=peer.last_seen_at,
        last_error=peer.last_error,
        last_status=peer.last_status,
    )


async def load_peer(session: AsyncSession, peer_id: uuid.UUID) -> Peer:
    peer = await session.get(Peer, peer_id)
    if peer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, UNKNOWN_PEER)
    return peer


ViewerPrincipal = Annotated[Principal, Depends(require_role(Role.VIEWER))]


@peers_router.get("")
async def list_peers(viewer: ViewerPrincipal, session: Session) -> list[PeerView]:
    rows = await session.scalars(select(Peer).order_by(Peer.created_at))
    return [peer_view(peer) for peer in rows]


@peers_router.post("/join-codes")
async def make_join_code(
    body: JoinCodeRequest,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
    settings: AppSettings,
) -> JoinCodeView:
    try:
        code, peer = await create_join_code(session, store, settings, body.name, admin.username)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    await session.commit()
    return JoinCodeView(code=code, expires_at=peer.expires_at or utc_now())


def peer_transport(request: Request) -> httpx.AsyncBaseTransport | None:
    # Production uses the network. Tests put another app behind this hook.
    transport: httpx.AsyncBaseTransport | None = getattr(request.app.state, "peer_transport", None)
    return transport


@peers_router.post("/join")
async def join(
    request: Request,
    body: JoinRequest,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
) -> PeerView:
    try:
        peer = await redeem_join_code(
            session, store, body.code, admin.username, peer_transport(request)
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    await session.commit()
    return peer_view(peer)


@peers_router.post("/{peer_id}/refresh")
async def refresh(
    request: Request,
    peer_id: uuid.UUID,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
) -> PeerView:
    peer = await load_peer(session, peer_id)
    try:
        await refresh_status(session, store, peer, admin.username, peer_transport(request))
    except PeerRefused as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    await session.commit()
    return peer_view(peer)


@peers_router.delete("/{peer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    peer_id: uuid.UUID,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
) -> None:
    peer = await load_peer(session, peer_id)
    await revoke_peer(session, store, peer, admin.username)
    await session.commit()


async def verified_peer(
    request: Request, session: AsyncSession, store: SecretStore, now: int
) -> Peer:
    raw_id = request.headers.get(HEADER_PEER, "")
    try:
        peer_id = uuid.UUID(raw_id)
    except ValueError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, UNKNOWN_PEER) from error
    peer = await session.get(Peer, peer_id)
    if peer is None or peer.direction != SERVES:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, UNKNOWN_PEER)
    secret = await asyncio.to_thread(store.read, secret_name(peer.id))
    body = await request.body()
    valid = secret is not None and verify(
        secret,
        request.method,
        request.url.path,
        request.headers.get(HEADER_TIMESTAMP, ""),
        body,
        request.headers.get(HEADER_SIGNATURE, ""),
        now,
    )
    if not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_SIGNATURE)
    return peer


@peer_router.post("/hello")
async def hello(request: Request, session: Session, store: Store) -> dict[str, str]:
    peer = await verified_peer(request, session, store, int(time.time()))
    try:
        accept_hello(peer, utc_now())
    except PeerRefused as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    await session.commit()
    return {"status": PAIRED}


@peer_router.get("/status")
async def peer_status(
    request: Request, session: Session, store: Store, settings: AppSettings
) -> dict[str, Any]:
    peer = await verified_peer(request, session, store, int(time.time()))
    try:
        ensure_served(peer)
    except PeerRefused as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    return await local_status(session, settings)
