from prometheus_client import Counter, Gauge, Histogram

REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "HTTP requests by route template, method and status",
    ["route", "method", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency by route template and method",
    ["route", "method"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 2.5),
)
SERVER_ERRORS_TOTAL = Counter(
    "demo_shop_errors_total",
    "Responses with a 5xx status by route template",
    ["route"],
)
DB_CONNECTIONS_IN_USE = Gauge(
    "demo_shop_db_connections_in_use",
    "Database connections checked out and not yet returned",
)
