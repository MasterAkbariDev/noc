# NOC

A small network operations center for a handful of Linux servers. Prometheus raises alerts, and a team of LLM agents investigates each incident using typed, read-only tools (no shell access). A deterministic policy engine decides what may be done, and the system writes an incident report.

Built to run on small VPSes: the whole NOC fits in about 1 GB of RAM, and the agent on each monitored server uses under 100 MB. LLM access uses free-tier providers (Gemini, with Groq as a fallback) through one OpenAI-compatible adapter.

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

## Configuration

All settings use the `NOC_` prefix; see `.env.example`. LLM keys go in `GEMINI_API_KEYS` / `GROQ_API_KEYS`, one per line inside double quotes. Without keys, `NOC_LLM_MODE=replay` answers from recorded responses.
