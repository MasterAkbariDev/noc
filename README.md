# NOC

A small network operations center for a handful of Linux servers. Prometheus raises alerts, and a team of LLM agents investigates each incident using typed, read-only tools (no shell access). A deterministic policy engine decides what may be done, and the system writes an incident report.

Built to run on small VPSes: the whole NOC fits in about 1 GB of RAM, and the agent on each monitored server uses under 100 MB. LLM access uses free-tier providers (Groq first, Gemini with several rotating keys as the fallback) through one OpenAI-compatible adapter.

## What's in here

| Path | Contents |
|---|---|
| `noc/` | The NOC: API, worker, alert ingestion, tool layer, policy engine, LLM layer, agents, LangGraph orchestration, reports, CLI |
| `sentinel/` | The small agent that runs on each monitored server (mTLS + signed requests, read-only tools) |
| `shared/` | Contracts shared by both (request signing, resource ids, tool envelopes) |
| `frontend/` | Optional web panel (React + Vite), served by the NOC |
| `deploy/` | Docker Compose and Prometheus config for the NOC; installer, systemd units and PKI scripts for targets |
| `lab/demo-app/` | A small demo shop used to stage incidents |
| `scenarios/` | Reproducible incident scenarios |
| `tests/` | Unit and integration tests |

## Development

Requirements: Docker and [uv](https://docs.astral.sh/uv/).

```bash
make setup
```

```bash
cp .env.example .env
```

```bash
make check
```

`make check` runs lint, strict type checking and the test suite (Postgres runs in Docker). Run the full stack with:

```bash
docker compose -f deploy/noc/docker-compose.yml up -d
```

The terminal is the main interface (`noc --help`); the web panel is optional.

## Deployment

Every push to `main` runs the checks, and if they pass, CI publishes `ghcr.io/masterakbaridev/noc:main` (plus a `sha-…` tag). On a server, set `NOC_IMAGE=ghcr.io/masterakbaridev/noc:main` in `/opt/noc/.env` and install the updater from `deploy/noc/auto-update/`. Every 5 minutes it pulls the image, redeploys when it changed, checks `/readyz`, and rolls back to the previous image if the new one isn't healthy. CI never gets SSH access to the servers.

```bash
install -m 0755 deploy/noc/auto-update/noc-update.sh /usr/local/bin/noc-update
install -m 0644 deploy/noc/auto-update/noc-update.{service,timer} /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now noc-update.timer
```

## Web panel

The panel is optional. It shows the overview, incidents, servers, system health, the audit log and the accounts, and the API serves it on the same port. The API listens on the server's loopback address only, so open it through an SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 <server>
```

Then open http://localhost:8000 in a browser.

Create the first admin on the server. The command asks for the password twice:

```bash
docker compose --env-file /opt/noc/.env -f /opt/noc/deploy/noc/docker-compose.single-host.yml exec noc noc users create <name> --role admin
```

To read the password from a pipe instead, add `-T` after `exec` and `--password-stdin` at the end.

There are three roles, each one including the ones before it:

- **viewer** can read everything.
- **operator** can also close escalated incidents and approve or reject waiting actions.
- **admin** can also create and change accounts.

The API token is for the CLI and automation only. People sign in to the panel with their username and password.

## Configuration

All settings use the `NOC_` prefix; see `.env.example`. LLM keys go in `GEMINI_API_KEYS` / `GROQ_API_KEYS`, one per line inside double quotes. Without keys, `NOC_LLM_MODE=replay` answers from recorded responses.
