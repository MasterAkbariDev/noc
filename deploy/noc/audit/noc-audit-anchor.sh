#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${NOC_ENV_FILE:-/opt/noc/.env}"
COMPOSE_FILE="${NOC_COMPOSE_FILE:-/opt/noc/deploy/noc/docker-compose.single-host.yml}"
ANCHOR_DIR="${NOC_ANCHOR_DIR:-/var/lib/noc-audit-anchors}"
REMOTE="${NOC_ANCHOR_REMOTE:-}"

log() {
    printf '%s noc-audit-anchor: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

mkdir -p "$ANCHOR_DIR"
chmod 0700 "$ANCHOR_DIR"
umask 0077

stamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$ANCHOR_DIR/anchor-$stamp-host.json"
tmp="$target.partial"

if ! compose exec -T noc noc audit anchor >"$tmp"; then
    rm -f "$tmp"
    log "creating the anchor failed"
    exit 1
fi
mv -f "$tmp" "$target"
log "wrote $target"

if [[ -n "$REMOTE" ]]; then
    rsync -a --ignore-existing "$ANCHOR_DIR"/ "$REMOTE"/
    log "copied anchors to $REMOTE"
else
    log "NOC_ANCHOR_REMOTE is not set; the anchors are only on this host"
fi
