import logging
import os
import time

from demo_app.chaos import ChaosState
from demo_app.settings import Settings
from demo_app.store import ProductStore, connect_postgres

logger = logging.getLogger("demo_reports")


def summarise(store: ProductStore) -> str:
    products = store.list_products()
    total_cents = sum(product.price_cents for product in products)
    return f"products={len(products)} catalogue_value_cents={total_cents}"


def run_once(store: ProductStore, database_url: str | None) -> None:
    if database_url is None:
        logger.info("no DEMO_DATABASE_URL set; nothing to report")
        return
    try:
        logger.info("report %s", summarise(store))
    except Exception:
        logger.exception("report failed")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = Settings.from_env(os.environ)
    store = ProductStore(settings.database_url, connect_postgres, ChaosState())
    while True:
        run_once(store, settings.database_url)
        time.sleep(settings.reports_interval_seconds)


if __name__ == "__main__":
    main()
