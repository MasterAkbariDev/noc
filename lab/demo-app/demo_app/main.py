import logging
import os
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from demo_app.chaos import ChaosState, build_chaos_app
from demo_app.metrics import REQUEST_DURATION, REQUESTS_TOTAL, SERVER_ERRORS_TOTAL
from demo_app.settings import CHAOS_HOST, Settings
from demo_app.store import Product, ProductStore, connect_postgres

logger = logging.getLogger("demo_app")


class PaymentReceipt(BaseModel):
    status: Literal["approved"]
    reference: str


class PaymentsStub:
    def __init__(self, sleep: Callable[[float], None] = time.sleep) -> None:
        self._sleep = sleep

    def charge(self, delay_ms: int) -> PaymentReceipt:
        if delay_ms > 0:
            self._sleep(delay_ms / 1000)
        return PaymentReceipt(status="approved", reference=f"pay_{uuid4().hex[:12]}")


class CheckoutRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=10)


class CheckoutResponse(BaseModel):
    status: Literal["approved"]
    reference: str
    total_cents: int


@dataclass(frozen=True)
class Services:
    store: ProductStore
    chaos: ChaosState
    payments: PaymentsStub


class ChaosListener:
    def __init__(self, app: FastAPI, port: int) -> None:
        config = uvicorn.Config(app, host=CHAOS_HOST, port=port, log_config=None)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="chaos-listener", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def instrument(app: FastAPI) -> None:
    @app.middleware("http")
    async def record_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = route_template(request)
            REQUEST_DURATION.labels(route, request.method).observe(time.perf_counter() - started)
            REQUESTS_TOTAL.labels(route, request.method, str(status_code)).inc()
            if status_code >= 500:
                SERVER_ERRORS_TOTAL.labels(route).inc()


def register_shop_routes(app: FastAPI, services: Services) -> None:
    @app.get("/")
    def index() -> dict[str, str]:
        return {"service": "demo-shop", "status": "ok"}

    @app.get("/products")
    def products() -> list[Product]:
        services.chaos.leak_memory_if_enabled()
        return services.store.list_products()

    @app.post("/checkout")
    def checkout(body: CheckoutRequest) -> CheckoutResponse:
        product = services.store.find_product(body.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="unknown product")
        receipt = services.payments.charge(services.chaos.settings.upstream_delay_ms)
        return CheckoutResponse(
            status=receipt.status,
            reference=receipt.reference,
            total_cents=product.price_cents * body.quantity,
        )

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@dataclass(frozen=True)
class ShopApps:
    public: FastAPI
    chaos: FastAPI


def build_shop(settings: Settings) -> ShopApps:
    chaos = ChaosState()
    store = ProductStore(settings.database_url, connect_postgres, chaos)
    services = Services(store=store, chaos=chaos, payments=PaymentsStub())
    chaos_app = build_chaos_app(chaos, store.release_leaked)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            store.ensure_schema()
        except Exception:
            logger.exception("could not prepare the products table; serving what is available")
        listener = ChaosListener(chaos_app, settings.chaos_port)
        listener.start()
        yield
        listener.stop()

    public = FastAPI(title="demo-shop", lifespan=lifespan)
    instrument(public)
    register_shop_routes(public, services)
    return ShopApps(public=public, chaos=chaos_app)


app = build_shop(Settings.from_env(os.environ)).public
