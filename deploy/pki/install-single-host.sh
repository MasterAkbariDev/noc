#!/usr/bin/env bash
set -euo pipefail

if (($# < 3)) || [[ "$2" != "--" ]]; then
    echo "usage: install-single-host.sh <server-name> -- <ssh arguments...>" >&2
    echo "example: install-single-host.sh staging-104 -- -i ~/.ssh/key root@203.0.113.7" >&2
    exit 2
fi

server="$1"
shift 2
ssh_args=("$@")
out="${PKI_OUT:-deploy/pki/out}"

if [[ ! "$server" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "invalid certificate name: $server" >&2
    exit 2
fi

files=(ca.pem "$server.pem" "$server-key.pem" noc-worker.pem noc-worker-key.pem noc-prometheus.pem noc-prometheus-key.pem)
for file in "${files[@]}"; do
    if [[ ! -f "$out/$file" ]]; then
        echo "missing $out/$file; run deploy/pki/renew.sh first" >&2
        exit 1
    fi
done

staging_dir="$(tar -C "$out" -cf - "${files[@]}" | ssh "${ssh_args[@]}" 'umask 077; d="$(mktemp -d /root/noc-pki-new-XXXXXX)"; tar -C "$d" -xf - && echo "$d"')"

ssh "${ssh_args[@]}" bash -s -- "$staging_dir" "$server" <<'REMOTE'
set -euo pipefail
new="$1"
server="$2"
compose=(docker compose --env-file /opt/noc/.env -f /opt/noc/deploy/noc/docker-compose.single-host.yml)
backup="/root/noc-pki-backup-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$backup"
cp -a /etc/noc-sentinel/tls "$backup/sentinel-tls"
cp -a /opt/noc/pki "$backup/noc-pki"

install -o root -g noc-sentinel -m 644 "$new/$server.pem" /etc/noc-sentinel/tls/server.pem
install -o root -g noc-sentinel -m 640 "$new/$server-key.pem" /etc/noc-sentinel/tls/server-key.pem
install -o root -g noc-sentinel -m 644 "$new/ca.pem" /etc/noc-sentinel/tls/ca.pem
install -o root -g root -m 644 "$new/ca.pem" /opt/noc/pki/ca.pem
install -o root -g root -m 644 "$new/noc-worker.pem" /opt/noc/pki/noc-worker.pem
install -o 10001 -g 10001 -m 400 "$new/noc-worker-key.pem" /opt/noc/pki/noc-worker-key.pem
install -o root -g root -m 644 "$new/noc-prometheus.pem" /opt/noc/pki/prometheus.pem
install -o nobody -g nogroup -m 400 "$new/noc-prometheus-key.pem" /opt/noc/pki/prometheus-key.pem
rm -rf "$new"

systemctl restart noc-sentinel
"${compose[@]}" restart noc prometheus >/dev/null
for attempt in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/readyz >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
echo "installed; previous files are in $backup"
"${compose[@]}" exec -T noc noc doctor
REMOTE
