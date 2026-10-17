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
    local domain port admin password
    domain="$(ask "Domain for the panel (for example noc.example.com, empty for an IP-only install)" "")"
    port="$(ask "Port the panel listens on inside this server" "8000")"
    admin="$(ask "Admin username" "admin")"
    password="$(ask_secret "Admin password (at least 12 characters)")"
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
EOF
    chmod 600 "$HOME_DIR/.env"

    cat > "$HOME_DIR/compose.yml" <<EOF
services:
  postgres:
    image: postgres:17-alpine
    restart: unless-stopped
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
    ports:
      - "127.0.0.1:${port}:${port}"
    volumes:
      - secrets:/var/lib/noc/secrets
      - ./pki:/etc/noc/pki:ro

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

volumes:
  pgdata:
  secrets:
  caddy_data:
EOF

    local site="${domain:-:80}"
    cat > "$HOME_DIR/Caddyfile" <<EOF
${site} {
    reverse_proxy noc:${port}
}
EOF

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
    choice="$(ask "Choose" "1")"
    case "$choice" in
        1) install_panel ;;
        2) install_cli ;;
        *) echo "Unknown choice." >&2; exit 1 ;;
    esac
}

main "$@"
