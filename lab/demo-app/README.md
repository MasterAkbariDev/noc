# Demo app

The shop and reports worker that the NOC monitors in the lab. It is a separate small uv project (not a workspace member) so it stays light enough for the 1 vCPU / 2 GB demo VPS.

## Run locally

```bash
cd lab/demo-app
uv sync
uv run uvicorn demo_app.main:app --port 8000
```

Without `DEMO_DATABASE_URL`, `/products` returns a static list, so the app works without Postgres.

| Variable | Default | Meaning |
|---|---|---|
| `DEMO_DATABASE_URL` | unset | Postgres DSN. When set, the app creates and seeds a `products` table on startup. |
| `DEMO_CHAOS_PORT` | `8099` | Chaos listener port. It always binds `127.0.0.1`. |
| `DEMO_REPORTS_INTERVAL_SECONDS` | `60` | Reports worker interval. |

## Routes

Public app: `GET /`, `GET /products`, `POST /checkout`, `GET /metrics`.

Chaos listener (`127.0.0.1:8099` only, not reachable through the public app):

- `GET /chaos` returns the current toggles and leaked memory in MiB.
- `PUT /chaos` with `{"memory_leak": bool, "upstream_delay_ms": 0..30000, "connection_leak": bool}` sets the toggles.
- `POST /chaos/reset` clears the toggles, the leaked memory and the leaked connections.

## Tests

```bash
cd lab/demo-app
uv run pytest -q
```

## Deploy to the demo VPS

Run as root on the VPS, from a copy of this directory:

```bash
sudo ./deploy.sh
```

The script is idempotent. It creates the `demo` system user, a venv in `/opt/demo-app`, installs the two systemd units (`demo-shop.service` with `MemoryMax=600M`, `demo-reports.service` with `MemoryMax=200M`) and restarts only those two units. The shop listens on `127.0.0.1:8000`, so nginx should proxy to it. Put the DSN in `/etc/demo-app/env` as `DEMO_DATABASE_URL=...`; the file is created empty on first run and is never overwritten.

`requirements.txt` is exported from `uv.lock` with `uv export --no-dev --no-hashes --no-emit-project --no-annotate --no-header`. Re-export it whenever dependencies change.
