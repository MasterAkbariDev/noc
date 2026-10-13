#!/usr/bin/env bash
set -euo pipefail
umask 077

NODE_EXPORTER_VERSION=1.9.1
NODE_EXPORTER_RELEASE_URL=https://github.com/prometheus/node_exporter/releases/download
NODE_EXPORTER_BIN=/usr/local/bin/node_exporter
NODE_EXPORTER_CONF=/etc/node_exporter
NODE_EXPORTER_UNIT_NAME=node_exporter.service
NODE_EXPORTER_UNIT=/etc/systemd/system/node_exporter.service
NODE_EXPORTER_USER=node_exporter
NODE_EXPORTER_COLLECTORS="--collector.disable-defaults --collector.cpu --collector.meminfo --collector.loadavg --collector.filesystem --collector.diskstats --collector.netdev --collector.netstat --collector.stat --collector.uname --collector.time --collector.pressure"
SENTINEL_VENV=/opt/noc-sentinel
SENTINEL_CONF=/etc/noc-sentinel
SENTINEL_STATE=/var/lib/noc-sentinel
SENTINEL_UNIT_NAME=noc-sentinel.service
SENTINEL_UNIT=/etc/systemd/system/noc-sentinel.service
SENTINEL_USER=noc-sentinel
UFW_NODE_COMMENT=noc-node-exporter
UFW_SENTINEL_COMMENT=noc-sentinel
RESOURCE_RE='^[a-z][a-z0-9_-]{0,30}:[A-Za-z0-9@._-]{1,128}$'
UNIT_RE='^[A-Za-z0-9@._-]{1,120}\.service$'
NAME_RE='^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$'
IPV4_RE='^[0-9]{1,3}(\.[0-9]{1,3}){3}$'
IPV6_RE='^[0-9A-Fa-f:]*:[0-9A-Fa-f:]*$'

DRY_RUN=0
UNINSTALL=0
WITH_SENTINEL=0
NOC_IP=
PKI_DIR=
CERT_NAME=
TARGET_NAME=
KEY_FILE=
KEY_ID=noc-worker
ENVIRONMENT=prod
WHEEL_DIR=
NODE_PORT=9100
LISTEN_ADDRESS=0.0.0.0
SENTINEL_PORT=9444
REGISTER_UNITS=()
SEEN_IDS=
PROBLEMS=()
CHANGED=0
FIREWALL=
SCRIPT_DIR=
WORK=

usage() {
    cat <<'EOF'
usage: install.sh --noc-ip <ip> --pki-dir <dir> [options]
       install.sh --uninstall --noc-ip <ip> [options]

Installs node_exporter (pinned version, mTLS) on an Ubuntu 24.04 target and,
with --with-sentinel, the noc-sentinel service. Safe to run twice: a second run
changes nothing. Run with --dry-run first to see the plan.

install options
  --noc-ip <ip>                NOC address allowed to reach our ports (ufw rules, when ufw is active)
  --pki-dir <dir>              directory with <cert-name>.pem, <cert-name>-key.pem and ca.pem
  --cert-name <name>           PKI name of this target certificate (default: --target-name)
  --target-name <name>         target name written to the sentinel config (default: hostname -s)
  --node-port <port>           node_exporter port (default: 9100)
  --with-sentinel              also install noc-sentinel
  --sentinel-port <port>       sentinel port (default: 9444)
  --listen-address <ip>        address both services bind to (default: 0.0.0.0; use 127.0.0.1 when the NOC runs on the same host)
  --key-file <file>            HMAC key shared with the NOC worker (required with --with-sentinel)
  --key-id <id>                key id the worker sends as X-NOC-Key-Id (default: noc-worker)
  --wheel-dir <dir>            directory with noc_shared-*.whl and noc_sentinel-*.whl (required with --with-sentinel)
  --environment <lab|prod>     sentinel environment (default: prod)
  --register-unit <id>=<unit>  register a systemd unit as a sentinel resource, repeatable
                               (id like svc:demo-shop, unit like demo-shop.service; default: none)

other options
  --dry-run                    print every action, change nothing
  --uninstall                  stop and remove our units, users, files and ufw rules
  -h, --help                   show this help
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

warn() {
    printf 'WARNING: %s\n' "$*" >&2
}

need_arg() {
    if (($# < 2)); then
        die "$1 needs a value"
    fi
}

parse_args() {
    while (($#)); do
        case "$1" in
            --noc-ip) need_arg "$@"; NOC_IP="$2"; shift 2 ;;
            --pki-dir) need_arg "$@"; PKI_DIR="$2"; shift 2 ;;
            --cert-name) need_arg "$@"; CERT_NAME="$2"; shift 2 ;;
            --target-name) need_arg "$@"; TARGET_NAME="$2"; shift 2 ;;
            --node-port) need_arg "$@"; NODE_PORT="$2"; shift 2 ;;
            --sentinel-port) need_arg "$@"; SENTINEL_PORT="$2"; shift 2 ;;
            --listen-address) need_arg "$@"; LISTEN_ADDRESS="$2"; shift 2 ;;
            --key-file) need_arg "$@"; KEY_FILE="$2"; shift 2 ;;
            --key-id) need_arg "$@"; KEY_ID="$2"; shift 2 ;;
            --wheel-dir) need_arg "$@"; WHEEL_DIR="$2"; shift 2 ;;
            --environment) need_arg "$@"; ENVIRONMENT="$2"; shift 2 ;;
            --register-unit) need_arg "$@"; REGISTER_UNITS+=("$2"); shift 2 ;;
            --with-sentinel) WITH_SENTINEL=1; shift ;;
            --dry-run) DRY_RUN=1; shift ;;
            --uninstall) UNINSTALL=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) die "unknown argument: $1 (see --help)" ;;
        esac
    done
}

validate_port() {
    local label="$1" value="$2"
    if [[ ! "$value" =~ ^[0-9]{4,5}$ ]] || ((10#$value < 1024 || 10#$value > 65535)); then
        die "$label must be a port from 1024 to 65535, got: $value"
    fi
}

validate_register_unit() {
    local spec="$1" id unit
    if [[ "$spec" != *=* ]]; then
        die "--register-unit expects <resource_id>=<unit>, got: $spec"
    fi
    id="${spec%%=*}"
    unit="${spec#*=}"
    if [[ ! "$id" =~ $RESOURCE_RE ]]; then
        die "invalid resource id: $id (expected kind:name, e.g. svc:demo-shop)"
    fi
    if [[ ! "$unit" =~ $UNIT_RE ]]; then
        die "invalid unit name: $unit (must end in .service)"
    fi
    if [[ " $SEEN_IDS " == *" $id "* ]]; then
        die "duplicate resource id: $id"
    fi
    SEEN_IDS="$SEEN_IDS $id"
}

validate_inputs() {
    if [[ ! "$NOC_IP" =~ $IPV4_RE && ! "$NOC_IP" =~ $IPV6_RE ]]; then
        die "--noc-ip is required and must be an IPv4 or IPv6 address"
    fi
    if [[ ! "$LISTEN_ADDRESS" =~ $IPV4_RE && ! "$LISTEN_ADDRESS" =~ $IPV6_RE ]]; then
        die "--listen-address must be an IPv4 or IPv6 address"
    fi
    validate_port "--node-port" "$NODE_PORT"
    validate_port "--sentinel-port" "$SENTINEL_PORT"
    if ((NODE_PORT == SENTINEL_PORT)); then
        die "--node-port and --sentinel-port must differ"
    fi
    if [[ "$ENVIRONMENT" != lab && "$ENVIRONMENT" != prod ]]; then
        die "--environment must be lab or prod"
    fi
    if ((UNINSTALL)); then
        return 0
    fi
    if [[ -z "$PKI_DIR" ]]; then
        die "--pki-dir is required"
    fi
    if [[ -z "$TARGET_NAME" ]]; then
        TARGET_NAME=$(hostname -s)
    fi
    CERT_NAME="${CERT_NAME:-$TARGET_NAME}"
    if [[ ! "$TARGET_NAME" =~ $NAME_RE ]]; then
        die "invalid --target-name: $TARGET_NAME"
    fi
    if [[ ! "$CERT_NAME" =~ $NAME_RE ]]; then
        die "invalid --cert-name: $CERT_NAME"
    fi
    if [[ ! "$KEY_ID" =~ $NAME_RE ]]; then
        die "invalid --key-id: $KEY_ID"
    fi
    if ((WITH_SENTINEL)); then
        if [[ -z "$KEY_FILE" ]]; then
            die "--with-sentinel needs --key-file"
        fi
        if [[ -z "$WHEEL_DIR" ]]; then
            die "--with-sentinel needs --wheel-dir"
        fi
    elif ((${#REGISTER_UNITS[@]} > 0)) || [[ -n "$KEY_FILE$WHEEL_DIR" ]]; then
        die "--register-unit, --key-file and --wheel-dir need --with-sentinel"
    fi
    if ((${#REGISTER_UNITS[@]} > 0)); then
        for spec in "${REGISTER_UNITS[@]}"; do
            validate_register_unit "$spec"
        done
    fi
}

run() {
    if ((DRY_RUN)); then
        printf '[dry-run] %s\n' "$*"
    else
        printf 'run: %s\n' "$*"
        "$@"
    fi
}

problem() {
    PROBLEMS+=("$*")
}

report_problems() {
    local item
    if ((${#PROBLEMS[@]} == 0)); then
        return 0
    fi
    if ((DRY_RUN)); then
        for item in "${PROBLEMS[@]}"; do
            warn "a real run would stop here: $item"
        done
        return 0
    fi
    for item in "${PROBLEMS[@]}"; do
        printf 'ERROR: %s\n' "$item" >&2
    done
    exit 1
}

check_host() {
    if [[ "$(uname -s)" != Linux ]]; then
        problem "this installer only runs on Linux (uname: $(uname -s))"
    fi
    if [[ "$(id -u)" != 0 ]]; then
        problem "must run as root (use sudo)"
    fi
    if ! command -v systemctl >/dev/null 2>&1; then
        problem "systemctl not found"
    fi
}

check_os() {
    local os_id='' os_version=''
    if [[ -r /etc/os-release ]]; then
        os_id=$(awk -F= '$1 == "ID" { gsub(/"/, "", $2); print $2 }' /etc/os-release)
        os_version=$(awk -F= '$1 == "VERSION_ID" { gsub(/"/, "", $2); print $2 }' /etc/os-release)
    fi
    if [[ "$os_id $os_version" != "ubuntu 24.04" ]]; then
        problem "target must be Ubuntu 24.04 (found: ${os_id:-unknown} ${os_version:-})"
    fi
}

check_python() {
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        problem "python3 3.12 or newer is required for the sentinel venv"
    fi
}

find_wheel() {
    local matches
    shopt -s nullglob
    matches=("$WHEEL_DIR"/"$1"-*.whl)
    shopt -u nullglob
    if ((${#matches[@]} == 1)); then
        printf '%s\n' "${matches[0]}"
    fi
}

check_inputs() {
    local file
    if [[ ! -d "$PKI_DIR" ]]; then
        problem "--pki-dir is not a directory: $PKI_DIR"
    fi
    for file in "$PKI_DIR/$CERT_NAME.pem" "$PKI_DIR/$CERT_NAME-key.pem" "$PKI_DIR/ca.pem"; do
        if [[ ! -r "$file" ]]; then
            problem "missing or unreadable PKI file: $file (see deploy/pki/README.md)"
        fi
    done
    if ((WITH_SENTINEL)); then
        if [[ ! -s "$KEY_FILE" ]]; then
            problem "key file missing or empty: $KEY_FILE"
        fi
        if [[ ! -d "$WHEEL_DIR" ]]; then
            problem "--wheel-dir is not a directory: $WHEEL_DIR"
        fi
        if [[ -z "$(find_wheel noc_shared)" ]]; then
            problem "--wheel-dir must contain exactly one noc_shared-*.whl"
        fi
        if [[ -z "$(find_wheel noc_sentinel)" ]]; then
            problem "--wheel-dir must contain exactly one noc_sentinel-*.whl"
        fi
    fi
}

check_port() {
    local port="$1" unit="$2" label="$3" owner pid
    if ! command -v ss >/dev/null 2>&1; then
        problem "cannot check port $port ($label): ss not found"
        return 0
    fi
    owner=$(ss -H -ltnp "sport = :$port" 2>/dev/null || true)
    if [[ -z "$owner" ]]; then
        return 0
    fi
    pid=$(systemctl show -p MainPID --value "$unit" 2>/dev/null || true)
    if [[ -n "$pid" && "$pid" != 0 && "$owner" == *"pid=$pid,"* ]]; then
        return 0
    fi
    problem "port $port ($label) is already used by another process: $owner"
}

check_ports() {
    check_port "$NODE_PORT" "$NODE_EXPORTER_UNIT_NAME" node_exporter
    if ((WITH_SENTINEL)); then
        check_port "$SENTINEL_PORT" "$SENTINEL_UNIT_NAME" sentinel
    fi
}

ufw_state() {
    local out
    if ! command -v ufw >/dev/null 2>&1; then
        echo missing
        return 0
    fi
    if ! out=$(ufw status 2>/dev/null); then
        echo unknown
        return 0
    fi
    case "$out" in
        *"Status: active"*) echo active ;;
        *"Status: inactive"*) echo inactive ;;
        *) echo unknown ;;
    esac
}

ensure_user() {
    local name="$1" home="$2"
    if id -u "$name" >/dev/null 2>&1; then
        printf 'user exists: %s\n' "$name"
        return 0
    fi
    run useradd --system --no-create-home --home-dir "$home" --shell /usr/sbin/nologin "$name"
}

ensure_dir() {
    run install -d -m "$2" -o "${3%%:*}" -g "${3##*:}" "$1"
}

install_file() {
    local src="$1" dest="$2" mode="$3" owner="$4"
    if [[ -f "$dest" ]] && cmp -s "$src" "$dest"; then
        printf 'unchanged: %s\n' "$dest"
        return 0
    fi
    CHANGED=1
    run install -m "$mode" -o "${owner%%:*}" -g "${owner##*:}" "$src" "$dest"
}

install_node_binary() {
    local name="node_exporter-$NODE_EXPORTER_VERSION.linux-amd64"
    local tarball="$name.tar.gz"
    local base="$NODE_EXPORTER_RELEASE_URL/v$NODE_EXPORTER_VERSION"
    local dl lines version_out
    if [[ -x "$NODE_EXPORTER_BIN" ]]; then
        version_out=$("$NODE_EXPORTER_BIN" --version 2>&1 || true)
        if [[ "$version_out" == *"version $NODE_EXPORTER_VERSION "* ]]; then
            printf 'unchanged: %s is node_exporter %s\n' "$NODE_EXPORTER_BIN" "$NODE_EXPORTER_VERSION"
            return 0
        fi
    fi
    CHANGED=1
    if ((DRY_RUN)); then
        printf '[dry-run] download %s/%s\n' "$base" "$tarball"
        printf '[dry-run] download %s/sha256sums.txt and check %s against it\n' "$base" "$tarball"
        printf '[dry-run] install -m 0755 -o root -g root %s/node_exporter %s\n' "$name" "$NODE_EXPORTER_BIN"
        return 0
    fi
    dl="$WORK/node-exporter"
    mkdir -p "$dl"
    curl --proto '=https' --tlsv1.2 -fsSL -o "$dl/$tarball" "$base/$tarball"
    curl --proto '=https' --tlsv1.2 -fsSL -o "$dl/sha256sums.txt" "$base/sha256sums.txt"
    lines=$(awk -v file="$tarball" '$2 == file' "$dl/sha256sums.txt")
    if [[ "$(printf '%s\n' "$lines" | grep -c .)" != 1 ]]; then
        die "$tarball is not listed exactly once in sha256sums.txt"
    fi
    if ! (cd "$dl" && printf '%s\n' "$lines" | sha256sum -c --quiet -); then
        die "sha256 mismatch for $tarball; nothing was installed"
    fi
    tar -xzf "$dl/$tarball" -C "$dl" "$name/node_exporter"
    install -m 0755 -o root -g root "$dl/$name/node_exporter" "$NODE_EXPORTER_BIN"
}

write_node_env() {
    printf 'NODE_EXPORTER_OPTS=--web.config.file=%s/web-config.yml --web.listen-address=%s:%s %s\n' \
        "$NODE_EXPORTER_CONF" "$(listen_host)" "$NODE_PORT" "$NODE_EXPORTER_COLLECTORS"
}

activate_unit() {
    local unit="$1" active=0
    if systemctl is-active --quiet "$unit" 2>/dev/null; then
        active=1
    fi
    if ((CHANGED)); then
        run systemctl daemon-reload
    fi
    run systemctl enable "$unit"
    if ((active == 0)); then
        run systemctl start "$unit"
    elif ((CHANGED)); then
        run systemctl restart "$unit"
    fi
    if ((DRY_RUN)); then
        return 0
    fi
    sleep 3
    if ! systemctl is-active --quiet "$unit"; then
        journalctl -u "$unit" -n 20 --no-pager >&2 || true
        die "$unit is not active; see the journal lines above"
    fi
}

install_node_exporter() {
    CHANGED=0
    ensure_user "$NODE_EXPORTER_USER" /nonexistent
    install_node_binary
    ensure_dir "$NODE_EXPORTER_CONF" 0750 root:"$NODE_EXPORTER_USER"
    ensure_dir "$NODE_EXPORTER_CONF/tls" 0750 root:"$NODE_EXPORTER_USER"
    install_file "$PKI_DIR/ca.pem" "$NODE_EXPORTER_CONF/tls/ca.pem" 0644 root:root
    install_file "$PKI_DIR/$CERT_NAME.pem" "$NODE_EXPORTER_CONF/tls/server.pem" 0644 root:root
    install_file "$PKI_DIR/$CERT_NAME-key.pem" "$NODE_EXPORTER_CONF/tls/server-key.pem" 0640 root:"$NODE_EXPORTER_USER"
    install_file "$SCRIPT_DIR/node_exporter/web-config.yml" "$NODE_EXPORTER_CONF/web-config.yml" 0640 root:"$NODE_EXPORTER_USER"
    write_node_env >"$WORK/node_exporter.env"
    install_file "$WORK/node_exporter.env" "$NODE_EXPORTER_CONF/node_exporter.env" 0640 root:"$NODE_EXPORTER_USER"
    install_file "$SCRIPT_DIR/node_exporter/node_exporter.service" "$NODE_EXPORTER_UNIT" 0644 root:root
    activate_unit "$NODE_EXPORTER_UNIT_NAME"
}

ensure_python_venv() {
    local status
    status=$(dpkg-query -W -f='${Status}' python3-venv 2>/dev/null || true)
    if [[ "$status" != *"install ok installed"* ]]; then
        run env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-venv
    fi
}

ensure_sentinel_packages() {
    local shared sentinel out
    shared=$(find_wheel noc_shared)
    sentinel=$(find_wheel noc_sentinel)
    if [[ ! -x "$SENTINEL_VENV/bin/python" ]]; then
        CHANGED=1
        run python3 -m venv "$SENTINEL_VENV"
    fi
    if ((DRY_RUN)); then
        printf '[dry-run] %s/bin/pip install --upgrade %s %s\n' "$SENTINEL_VENV" "$shared" "$sentinel"
        CHANGED=1
        return 0
    fi
    out=$(umask 022 && "$SENTINEL_VENV/bin/pip" install --no-input --upgrade "$shared" "$sentinel" 2>&1) || {
        printf '%s\n' "$out" >&2
        die "pip install of the sentinel wheels failed"
    }
    chmod -R u=rwX,go=rX "$SENTINEL_VENV"
    case "$out" in
        *"Successfully installed"*) CHANGED=1 ;;
    esac
}

write_sentinel_config() {
    printf 'target: "%s"\n' "$TARGET_NAME"
    printf 'environment: "%s"\n' "$ENVIRONMENT"
    printf 'listen:\n  host: "%s"\n  port: %s\n' "$LISTEN_ADDRESS" "$SENTINEL_PORT"
    printf 'tls:\n  cert_file: "%s/tls/server.pem"\n  key_file: "%s/tls/server-key.pem"\n  client_ca_file: "%s/tls/ca.pem"\n' \
        "$SENTINEL_CONF" "$SENTINEL_CONF" "$SENTINEL_CONF"
    printf 'key_files:\n  "%s": "%s/keys/%s.key"\n' "$KEY_ID" "$SENTINEL_CONF" "$KEY_ID"
    printf 'state_dir: "%s"\n' "$SENTINEL_STATE"
    printf 'halt_file: "%s/HALT"\n' "$SENTINEL_CONF"
    if ((${#REGISTER_UNITS[@]} == 0)); then
        printf 'resources: []\n'
        return 0
    fi
    printf 'resources:\n'
    for spec in "${REGISTER_UNITS[@]}"; do
        printf '  - id: "%s"\n    kind: systemd_unit\n    name: "%s"\n    allowed_actions: [restart_service, start_service]\n' \
            "${spec%%=*}" "${spec#*=}"
    done
}

install_sentinel() {
    CHANGED=0
    ensure_user "$SENTINEL_USER" "$SENTINEL_STATE"
    ensure_python_venv
    ensure_sentinel_packages
    ensure_dir "$SENTINEL_CONF" 0750 root:"$SENTINEL_USER"
    ensure_dir "$SENTINEL_CONF/tls" 0750 root:"$SENTINEL_USER"
    ensure_dir "$SENTINEL_CONF/keys" 0750 root:"$SENTINEL_USER"
    install_file "$PKI_DIR/ca.pem" "$SENTINEL_CONF/tls/ca.pem" 0644 root:"$SENTINEL_USER"
    install_file "$PKI_DIR/$CERT_NAME.pem" "$SENTINEL_CONF/tls/server.pem" 0644 root:"$SENTINEL_USER"
    install_file "$PKI_DIR/$CERT_NAME-key.pem" "$SENTINEL_CONF/tls/server-key.pem" 0640 root:"$SENTINEL_USER"
    install_file "$KEY_FILE" "$SENTINEL_CONF/keys/$KEY_ID.key" 0640 root:"$SENTINEL_USER"
    write_sentinel_config >"$WORK/config.yaml"
    install_file "$WORK/config.yaml" "$SENTINEL_CONF/config.yaml" 0640 root:"$SENTINEL_USER"
    install_file "$SCRIPT_DIR/sentinel/noc-sentinel.service" "$SENTINEL_UNIT" 0644 root:root
    activate_unit "$SENTINEL_UNIT_NAME"
}

listen_host() {
    if [[ "$LISTEN_ADDRESS" == *:* ]]; then
        printf '[%s]' "$LISTEN_ADDRESS"
    else
        printf '%s' "$LISTEN_ADDRESS"
    fi
}

is_loopback_listen() {
    [[ "$LISTEN_ADDRESS" == 127.* || "$LISTEN_ADDRESS" == ::1 ]]
}

apply_firewall() {
    if is_loopback_listen; then
        printf 'firewall: services listen on %s only, no rule needed\n' "$LISTEN_ADDRESS"
        return 0
    fi
    local ports="$NODE_PORT"
    if ((WITH_SENTINEL)); then
        ports="$NODE_PORT and $SENTINEL_PORT"
    fi
    if [[ "$FIREWALL" != active ]]; then
        warn "ufw is $FIREWALL, so no firewall rule was added. Restrict TCP $ports to $NOC_IP in your provider firewall, or the ports are open to the internet."
        return 0
    fi
    run ufw allow from "$NOC_IP" to any port "$NODE_PORT" proto tcp comment "$UFW_NODE_COMMENT"
    if ((WITH_SENTINEL)); then
        run ufw allow from "$NOC_IP" to any port "$SENTINEL_PORT" proto tcp comment "$UFW_SENTINEL_COMMENT"
    fi
}

install_all() {
    check_host
    check_os
    check_inputs
    if ((WITH_SENTINEL)); then
        check_python
    fi
    check_ports
    FIREWALL=$(ufw_state)
    report_problems
    install_node_exporter
    if ((WITH_SENTINEL)); then
        install_sentinel
    fi
    apply_firewall
    if ((DRY_RUN)); then
        printf 'dry run complete: nothing was changed\n'
        return 0
    fi
    printf 'done: node_exporter listens on TCP %s (mTLS)\n' "$NODE_PORT"
    if ((WITH_SENTINEL)); then
        printf 'done: noc-sentinel listens on TCP %s (mTLS)\n' "$SENTINEL_PORT"
    fi
    printf 'run the same command again: it should report only "unchanged" lines\n'
}

remove_unit() {
    local unit="$1" path="$2"
    if ((DRY_RUN)) || [[ -e "$path" ]]; then
        run systemctl disable --now "$unit"
        run rm -f "$path"
    fi
}

remove_user() {
    local name="$1"
    if ((DRY_RUN)) || id -u "$name" >/dev/null 2>&1; then
        run userdel "$name"
    fi
}

remove_ufw_rule() {
    local port="$1"
    if [[ "$FIREWALL" == missing ]]; then
        return 0
    fi
    run ufw --force delete allow from "$NOC_IP" to any port "$port" proto tcp || warn "no ufw rule for $NOC_IP port $port"
}

uninstall_all() {
    check_host
    report_problems
    FIREWALL=$(ufw_state)
    remove_unit "$NODE_EXPORTER_UNIT_NAME" "$NODE_EXPORTER_UNIT"
    remove_unit "$SENTINEL_UNIT_NAME" "$SENTINEL_UNIT"
    run systemctl daemon-reload
    run rm -f "$NODE_EXPORTER_BIN"
    run rm -rf "$NODE_EXPORTER_CONF" "$SENTINEL_CONF" "$SENTINEL_VENV"
    remove_user "$NODE_EXPORTER_USER"
    remove_user "$SENTINEL_USER"
    remove_ufw_rule "$NODE_PORT"
    remove_ufw_rule "$SENTINEL_PORT"
    printf 'kept %s (sentinel action store and nonces): delete it by hand if you no longer need it\n' "$SENTINEL_STATE"
    printf 'kept the apt package python3-venv\n'
}

main() {
    parse_args "$@"
    validate_inputs
    SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    WORK=$(mktemp -d)
    trap 'rm -rf "$WORK"' EXIT
    if ((DRY_RUN)); then
        printf 'DRY RUN: the plan is printed, nothing on this host is changed\n'
    fi
    if ((UNINSTALL)); then
        uninstall_all
    else
        install_all
    fi
}

main "$@"
