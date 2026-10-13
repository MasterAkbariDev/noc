from collections.abc import Callable
from datetime import datetime

from fastapi import HTTPException, Request, status

from noc_sentinel.nonce_store import NonceStore
from noc_shared.signing import SignatureError, VerifiedRequest, verify_request


class RequestVerifier:
    def __init__(
        self,
        secrets: dict[str, bytes],
        nonce_store: NonceStore,
        clock: Callable[[], datetime],
        max_skew_seconds: int,
    ) -> None:
        self._secrets = secrets
        self._nonces = nonce_store
        self._clock = clock
        self._max_skew = max_skew_seconds

    async def __call__(self, request: Request) -> VerifiedRequest:
        body = await request.body()
        now = self._clock()
        try:
            verified = verify_request(
                self._secrets.get,
                request.method,
                request.url.path,
                body,
                request.headers,
                now,
                self._max_skew,
            )
        except SignatureError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, exc.failure.value) from exc

        if not self._nonces.remember(verified.nonce, now):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "replayed_nonce")
        return verified
