from collections.abc import Callable
from typing import Final, Protocol

import psycopg
from pydantic import BaseModel

from demo_app.chaos import ChaosState
from demo_app.metrics import DB_CONNECTIONS_IN_USE


class Product(BaseModel):
    id: int
    name: str
    price_cents: int


STATIC_PRODUCTS: Final[tuple[Product, ...]] = (
    Product(id=1, name="Mug", price_cents=900),
    Product(id=2, name="T-shirt", price_cents=2500),
    Product(id=3, name="Sticker pack", price_cents=400),
)

CREATE_TABLE_SQL: Final = """
CREATE TABLE IF NOT EXISTS products (
    id integer PRIMARY KEY,
    name text NOT NULL,
    price_cents integer NOT NULL
)
"""

SEED_SQL: Final = """
INSERT INTO products (id, name, price_cents) VALUES
    (1, 'Mug', 900),
    (2, 'T-shirt', 2500),
    (3, 'Sticker pack', 400)
ON CONFLICT (id) DO NOTHING
"""

SELECT_PRODUCTS_SQL: Final = "SELECT id, name, price_cents FROM products ORDER BY id"


class SqlCursor(Protocol):
    def fetchall(self) -> list[tuple[object, ...]]: ...


class SqlConnection(Protocol):
    def execute(self, query: str) -> SqlCursor: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...


ConnectFn = Callable[[str], SqlConnection]


def connect_postgres(database_url: str) -> SqlConnection:
    return psycopg.connect(database_url, connect_timeout=5)


class ProductStore:
    def __init__(self, database_url: str | None, connect: ConnectFn, chaos: ChaosState) -> None:
        self._database_url = database_url
        self._connect = connect
        self._chaos = chaos
        self._checked_out = 0
        self._leaked: list[SqlConnection] = []

    def ensure_schema(self) -> None:
        if self._database_url is None:
            return
        connection = self._connect(self._database_url)
        try:
            connection.execute(CREATE_TABLE_SQL)
            connection.execute(SEED_SQL)
            connection.commit()
        finally:
            connection.close()

    def list_products(self) -> list[Product]:
        if self._database_url is None:
            return list(STATIC_PRODUCTS)
        connection = self._connect(self._database_url)
        self._check_out()
        try:
            rows = connection.execute(SELECT_PRODUCTS_SQL).fetchall()
        finally:
            self._return(connection)
        return [
            Product.model_validate({"id": row[0], "name": row[1], "price_cents": row[2]})
            for row in rows
        ]

    def find_product(self, product_id: int) -> Product | None:
        return next((item for item in self.list_products() if item.id == product_id), None)

    def release_leaked(self) -> None:
        for connection in self._leaked:
            connection.close()
        self._checked_out -= len(self._leaked)
        self._leaked.clear()
        DB_CONNECTIONS_IN_USE.set(self._checked_out)

    def _check_out(self) -> None:
        self._checked_out += 1
        DB_CONNECTIONS_IN_USE.set(self._checked_out)

    def _return(self, connection: SqlConnection) -> None:
        if self._chaos.settings.connection_leak:
            self._leaked.append(connection)
            return
        self._checked_out -= 1
        DB_CONNECTIONS_IN_USE.set(self._checked_out)
        connection.close()
