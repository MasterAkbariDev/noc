# Multi-Agent Autonomous NOC

A resource-efficient, multi-agent AI system that monitors Linux servers, detects incidents, investigates them with specialized LLM agents using **typed, policy-checked tools** (never a shell), proposes or executes safe remediations with human approval, verifies recovery, and writes incident reports.

**Status (2026-10-13):** the **walking skeleton** is implemented and tested. One alert becomes one incident, the investigator agent calls a signed read tool on the target, a grounded diagnosis is stored, the policy engine decides (nothing can execute yet), and a report is written. It survives worker crashes. 102 tests pass. Next steps: [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).

## Quick start (development)

Requirements: Docker, and [uv](https://docs.astral.sh/uv/) (or the bundled `.tools/bin/uv`).

```bash
make setup
```

```bash
cp .env.example .env
```

```bash
make check
```

```bash
make migrate
```

```bash
make api
```

`make check` runs lint, strict type checking and all tests (it starts Postgres in Docker). The full NOC stack (Postgres, Prometheus, migrate, API, worker) runs with:

```bash
docker compose -f deploy/noc/docker-compose.yml up -d
```

No LLM key is needed for development: `NOC_LLM_MODE=replay` answers from recorded cassettes. To use the free-tier providers, set `GEMINI_API_KEY` / `GROQ_API_KEY` and `NOC_LLM_MODE=live` (see `noc/src/noc/llm/providers.yaml`).

## Start here

1. [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md): goals, principles, stack summary, deliberate deviations from the brief
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): components, diagrams, resource budget, repo layout, DB schema
3. [`docs/code/README.md`](docs/code/README.md): **how the code works**, file by file, with a presentation script
4. [`TASKS.md`](TASKS.md): the roadmap; [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md): the next task cards
5. [`CLAUDE.md`](CLAUDE.md): rules for anyone (human or AI agent) changing the code

Design review: [Review summary](docs/DESIGN_REVIEW_2026-10.md) · [Production remediation](docs/PRODUCTION_REMEDIATION.md) · [Detection rules](docs/DETECTION_RULES.md)

Further reading: [Technology decisions](docs/TECHNOLOGY_DECISIONS.md) · [ADRs](docs/DECISIONS.md) · [Agents](docs/AGENTS.md) · [Tools](docs/TOOLS.md) · [Security](docs/SECURITY.md) · [Incident lifecycle](docs/INCIDENT_LIFECYCLE.md) · [Evaluation](docs/EVALUATION.md) · [Demo scenarios](docs/DEMO_SCENARIOS.md)

## Repository layout

| Path | Contents |
|---|---|
| `shared/` | `noc_shared`: contracts shared by NOC and sentinel (signing, resource ids, tool envelopes, taxonomy) |
| `sentinel/` | `noc_sentinel`: the small agent on each monitored server |
| `noc/` | `noc`: API, worker, detection, tools, policy, LLM layer, agents, LangGraph orchestration, reports, CLI |
| `deploy/` | Docker Compose + Prometheus config for the NOC; systemd unit and config for targets |
| `tests/` | Unit and integration tests |
| `docs/` | Design documents, and `docs/code/` explaining the code |

## Footprint targets

| Host | Budget |
|---|---|
| NOC: recommended 2 vCPU / 4 GB / 30 GB (`standard-4g`) | core stack ≈ 1.1–1.7 GB RAM, ≈ 20 GB disk |
| NOC: minimum 1 vCPU / 2 GB / 18 GB (`small-2g`) | ≈ 0.8–1.3 GB RAM, ≈ 12 GB disk |
| Target (1–2 GB) | node_exporter + noc-sentinel < 100 MB RAM, < 2 % CPU |
| LLM | **$0**: Gemini free tier (primary), Groq free tier (fallback), offline replay for demos |
