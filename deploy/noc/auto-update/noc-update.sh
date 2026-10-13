#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${NOC_ENV_FILE:-/opt/noc/.env}"
COMPOSE_FILE="${NOC_COMPOSE_FILE:-/opt/noc/deploy/noc/docker-compose.single-host.yml}"
HEALTH_URL="${NOC_HEALTH_URL:-http://127.0.0.1:8000/readyz}"
HEALTH_TIMEOUT="${NOC_HEALTH_TIMEOUT:-120}"
STATUS_FILE="${NOC_UPDATE_STATUS_FILE:-/var/lib/noc-update/status.json}"
PREVIOUS_TAG="noc:previous"

log() {
    printf '%s noc-update: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

env_value() {
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | tr -d '"'
}

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

healthy() {
    local waited=0
    while ((waited < HEALTH_TIMEOUT)); do
        if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done
    return 1
}

json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

write_status() {
    local result="$1" image_ref="$2" message="$3"
    local tmp="$STATUS_FILE.tmp"
    mkdir -p "$(dirname "$STATUS_FILE")"
    printf '{"ts":"%s","result":"%s","image":"%s","message":"%s"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$result" \
        "$(json_escape "$image_ref")" "$(json_escape "$message")" >"$tmp"
    chmod 0644 "$tmp"
    mv -f "$tmp" "$STATUS_FILE"
}

report() {
    write_status "$@" || log "could not write $STATUS_FILE"
}

image=$(env_value NOC_IMAGE)
if [[ -z "$image" || "$image" != */* ]]; then
    log "NOC_IMAGE in $ENV_FILE is not a registry image; nothing to do"
    report unchanged "$image" "NOC_IMAGE is not a registry image; nothing to do"
    exit 0
fi

current=$(docker image inspect --format '{{.Id}}' "$image" 2>/dev/null || true)
if ! docker pull --quiet "$image" >/dev/null; then
    log "pull of $image failed; keeping the running version"
    report pull_failed "$image" "pull failed; keeping the running version"
    exit 1
fi
latest=$(docker image inspect --format '{{.Id}}' "$image")

if [[ "$latest" == "$current" ]]; then
    report unchanged "$image" "already running ${latest:7:12}"
    exit 0
fi

log "new image ${latest:7:12} for $image (was ${current:7:12})"
if [[ -n "$current" ]]; then
    docker tag "$current" "$PREVIOUS_TAG"
fi

if compose up -d --remove-orphans && healthy; then
    log "deployed ${latest:7:12}; health check passed"
    report deployed "$image" "running ${latest:7:12}"
    docker image prune -f >/dev/null
    exit 0
fi

log "health check failed after deploying ${latest:7:12}"
if [[ -z "$current" ]]; then
    log "no previous image to roll back to"
    report failed "$image" "health check failed after deploying ${latest:7:12}; no previous image to roll back to"
    exit 1
fi
docker tag "$PREVIOUS_TAG" "$image"
if compose up -d noc && healthy; then
    log "rolled back to ${current:7:12}"
    report rolled_back "$image" "health check failed after deploying ${latest:7:12}; rolled back to ${current:7:12}"
else
    log "rollback to ${current:7:12} is not healthy either; manual action needed"
    report failed "$image" "rollback to ${current:7:12} is not healthy either; manual action needed"
fi
exit 1
