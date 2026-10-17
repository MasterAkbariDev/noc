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

If Safari keeps returning to the login page, set `NOC_SESSION_COOKIE_SECURE=false` in `/opt/noc/.env` (Chrome and Firefox accept the secure cookie on `localhost`). An account locked by failed logins is opened again with `noc users unlock <name>` on the server.

## Configuration

All settings use the `NOC_` prefix; see `.env.example`. LLM keys go in `GEMINI_API_KEYS` / `GROQ_API_KEYS`, one per line inside double quotes. Without keys, `NOC_LLM_MODE=replay` answers from recorded responses.

## Install

One command installs NOC on a Linux server. It asks whether to install the web panel. Choose 1 for the
panel (domain, port and admin account are asked) or 2 for the command line only, the way 3x-ui works.

```bash
curl -fsSL https://raw.githubusercontent.com/MasterAkbariDev/noc/main/deploy/install.sh -o install.sh && sudo bash install.sh
```

The same script is below, so you can read it before running it.

<details>
<summary>install.sh</summary>

```bash
#!/usr/bin/env bash
# NOC installer. Asks whether to install the web panel; otherwise installs only the CLI.
# Run as root on a Linux server with Docker (installed here if missing).
set -euo pipefail

IMAGE="${NOC_IMAGE:-ghcr.io/masterakbaridev/noc:main}"
HOME_DIR="/opt/noc"

ask() {
    local prompt="$1" default="${2:-}" answer
    read -r -p "$prompt${default:+ [$default]}: " answer </dev/tty
    echo "${answer:-$default}"
}

ask_secret() {
    local prompt="$1" answer
    read -r -s -p "$prompt: " answer </dev/tty
    echo >&2
    echo "$answer"
}

# Settings can come from the environment instead of prompts (used for unattended installs):
# NOC_MODE (1 panel, 2 command line), NOC_DOMAIN, NOC_PORT, NOC_ADMIN, NOC_ADMIN_PASSWORD_FILE,
# NOC_PROXY (caddy or none; none means a reverse proxy you configure yourself).

random_secret() {
    openssl rand -hex 32
}

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Run this installer as root (sudo bash install.sh)." >&2
        exit 1
    fi
}

ensure_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
    fi
    docker compose version >/dev/null 2>&1 || {
        echo "Docker Compose plugin is missing. Install docker-compose-plugin and run again." >&2
        exit 1
    }
}

install_cli() {
    mkdir -p "$HOME_DIR"
    if [ ! -f "$HOME_DIR/.env" ]; then
        printf "%s\n" "# Settings for the noc command." "NOC_DATABASE_URL=" > "$HOME_DIR/.env"
        chmod 600 "$HOME_DIR/.env"
    fi
    cat > /usr/local/bin/noc <<EOF
#!/usr/bin/env bash
# Runs the NOC command line from the container image. Reads settings from $HOME_DIR/.env.
exec docker run --rm -it --network host --env-file "$HOME_DIR/.env" "$IMAGE" noc "\$@"
EOF
    chmod 755 /usr/local/bin/noc
    echo "CLI installed: run 'noc --help'."
}

install_panel() {
    local domain port admin password proxy
    domain="${NOC_DOMAIN:-$(ask "Domain for the panel (for example noc.example.com, empty for an IP-only install)" "")}"
    port="${NOC_PORT:-$(ask "Port the panel listens on inside this server" "8000")}"
    admin="${NOC_ADMIN:-$(ask "Admin username" "admin")}"
    proxy="${NOC_PROXY:-caddy}"
    if [ -n "${NOC_ADMIN_PASSWORD_FILE:-}" ]; then
        password="$(cat "$NOC_ADMIN_PASSWORD_FILE")"
    else
        password="$(ask_secret "Admin password (at least 12 characters)")"
    fi
    if [ "${#password}" -lt 12 ]; then
        echo "The password must be at least 12 characters." >&2
        exit 1
    fi

    mkdir -p "$HOME_DIR/secrets" "$HOME_DIR/pki" "$HOME_DIR/keys"
    local db_password token
    db_password="$(random_secret)"
    token="$(random_secret)"

    cat > "$HOME_DIR/.env" <<EOF
NOC_DATABASE_URL=postgresql+psycopg://noc:${db_password}@postgres:5432/noc
NOC_API_TOKEN=${token}
NOC_LLM_MODE=live
NOC_EXECUTION_ENABLED=false
NOC_SECRETS_DIR=/var/lib/noc/secrets
POSTGRES_PASSWORD=${db_password}
NOC_PUBLIC_URL=${domain:+https://$domain}
EOF
    chmod 600 "$HOME_DIR/.env"

    cat > "$HOME_DIR/compose.yml" <<EOF
services:
  postgres:
    image: postgres:17-alpine
    restart: unless-stopped
    mem_limit: 384m
    environment:
      POSTGRES_USER: noc
      POSTGRES_PASSWORD: \${POSTGRES_PASSWORD}
      POSTGRES_DB: noc
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U noc -d noc"]
      interval: 5s
      retries: 20

  noc:
    image: ${IMAGE}
    restart: unless-stopped
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    command: ["noc", "all-in-one", "--host", "0.0.0.0", "--port", "${port}"]
    mem_limit: 768m
    ports:
      - "127.0.0.1:${port}:${port}"
    volumes:
      - secrets:/var/lib/noc/secrets
      - ./pki:/etc/noc/pki:ro

volumes:
  pgdata:
  secrets:
  caddy_data:
EOF

    if [ "$proxy" = "caddy" ]; then
        cat >> "$HOME_DIR/compose.yml" <<EOF
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    depends_on:
      - noc
    command: ["caddy", "run", "--config", "/etc/caddy/Caddyfile"]
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
EOF
        printf '%s {\n    reverse_proxy noc:%s\n}\n' "${domain:-:80}" "$port" > "$HOME_DIR/Caddyfile"
    fi

    cd "$HOME_DIR"
    docker compose --env-file .env -f compose.yml pull
    docker compose --env-file .env -f compose.yml up -d postgres
    docker compose --env-file .env -f compose.yml run --rm noc noc db upgrade
    printf '%s' "$password" | docker compose --env-file .env -f compose.yml run --rm -T noc \
        noc users create "$admin" --role admin --password-stdin
    docker compose --env-file .env -f compose.yml up -d

    install_cli
    echo
    echo "Panel is starting. Open https://${domain:-<server-ip>} and sign in as ${admin}."
    echo "Settings are in $HOME_DIR/.env (mode 600). Keep a copy somewhere safe."
}

main() {
    require_root
    ensure_docker
    echo "NOC installer"
    echo "1) Install the web panel (recommended)"
    echo "2) Install the command line only"
    local choice
    choice="${NOC_MODE:-$(ask "Choose" "1")}"
    case "$choice" in
        1) install_panel ;;
        2) install_cli ;;
        *) echo "Unknown choice." >&2; exit 1 ;;
    esac
}

main "$@"
```

</details>
