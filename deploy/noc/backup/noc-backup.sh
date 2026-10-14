#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${NOC_ENV_FILE:-/opt/noc/.env}"
COMPOSE_FILE="${NOC_COMPOSE_FILE:-/opt/noc/deploy/noc/docker-compose.single-host.yml}"
BACKUP_DIR="${NOC_BACKUP_DIR:-/var/backups/noc}"
KEEP_DAYS="${NOC_BACKUP_KEEP_DAYS:-7}"
DB_USER="${NOC_DB_USER:-noc}"
DB_NAME="${NOC_DB_NAME:-noc}"
RESTORE_DB="noc_restore_test"

log() {
    printf '%s noc-backup: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

latest_backup() {
    find "$BACKUP_DIR" -maxdepth 1 -name 'noc-*.dump' -type f | sort | tail -1
}

dump() {
    local stamp target tmp
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    target="$BACKUP_DIR/noc-$stamp.dump"
    tmp="$target.partial"
    mkdir -p "$BACKUP_DIR"
    chmod 0700 "$BACKUP_DIR"
    umask 0077
    if ! compose exec -T postgres pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom >"$tmp"; then
        rm -f "$tmp"
        log "pg_dump failed"
        return 1
    fi
    if [[ ! -s "$tmp" ]]; then
        rm -f "$tmp"
        log "pg_dump produced an empty file"
        return 1
    fi
    mv -f "$tmp" "$target"
    log "wrote $target ($(wc -c <"$target") bytes)"
    find "$BACKUP_DIR" -maxdepth 1 -name 'noc-*.dump' -type f -mtime "+$KEEP_DAYS" -print -delete |
        while read -r removed; do log "removed old backup $removed"; done
}

verify() {
    local file
    file=$(latest_backup)
    if [[ -z "$file" ]]; then
        log "no backup found in $BACKUP_DIR"
        return 1
    fi
    compose exec -T postgres pg_restore --list <"$file" >/dev/null
    log "$file is a readable archive"
}

restore_test() {
    local file tables
    file=$(latest_backup)
    if [[ -z "$file" ]]; then
        log "no backup found in $BACKUP_DIR"
        return 1
    fi
    compose exec -T postgres psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $RESTORE_DB" >/dev/null
    compose exec -T postgres psql -U "$DB_USER" -d postgres -c "CREATE DATABASE $RESTORE_DB" >/dev/null
    compose exec -T postgres pg_restore -U "$DB_USER" -d "$RESTORE_DB" --no-owner <"$file"
    tables=$(compose exec -T postgres psql -U "$DB_USER" -d "$RESTORE_DB" -Atc \
        "select count(*) from information_schema.tables where table_schema = 'public'")
    compose exec -T postgres psql -U "$DB_USER" -d postgres -c "DROP DATABASE $RESTORE_DB" >/dev/null
    log "restored $file into a scratch database: $tables tables"
}

case "${1:-backup}" in
backup) dump ;;
verify) verify ;;
restore-test) restore_test ;;
*)
    echo "usage: noc-backup [backup|verify|restore-test]" >&2
    exit 2
    ;;
esac
