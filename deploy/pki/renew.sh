#!/usr/bin/env bash
set -euo pipefail
umask 077

if (($# < 2)); then
    echo "usage: renew.sh <server-name> <ip-or-dns>..." >&2
    echo "re-issues <server-name>, noc-worker and noc-prometheus when they expire within RENEW_DAYS (default 21); FORCE=1 renews all" >&2
    exit 2
fi

server="$1"
shift

pki="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="${PKI_OUT:-deploy/pki/out}"
renew_days="${RENEW_DAYS:-21}"
force="${FORCE:-0}"
retired="$out/retired/$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! "$renew_days" =~ ^[0-9]+$ ]]; then
    echo "RENEW_DAYS must be a whole number of days" >&2
    exit 2
fi

needs_renewal() {
    local certificate="$out/$1.pem"
    [[ "$force" == "1" ]] && return 0
    [[ ! -f "$certificate" ]] && return 0
    ! openssl x509 -in "$certificate" -noout -checkend $((renew_days * 86400)) >/dev/null
}

retire() {
    mkdir -p "$retired"
    for file in "$1.pem" "$1-key.pem"; do
        if [[ -e "$out/$file" ]]; then
            mv "$out/$file" "$retired/$file"
        fi
    done
}

renewed=()
for name in "$server" noc-worker noc-prometheus; do
    if ! needs_renewal "$name"; then
        echo "keep   $name ($(openssl x509 -in "$out/$name.pem" -noout -enddate | cut -d= -f2))"
        continue
    fi
    retire "$name"
    if [[ "$name" == "$server" ]]; then
        issue=("$pki/issue-server.sh" "$name" "$@")
    else
        issue=("$pki/issue-client.sh" "$name")
    fi
    if ! log="$("${issue[@]}" 2>&1)"; then
        echo "$log" >&2
        echo "could not issue $name; the old pair is in $retired" >&2
        exit 1
    fi
    echo "renew  $name (until $(openssl x509 -in "$out/$name.pem" -noout -enddate | cut -d= -f2))"
    renewed+=("$name")
done

if ((${#renewed[@]} == 0)); then
    echo "nothing to renew"
else
    echo "renewed ${#renewed[@]}; old pairs are in $retired"
fi
