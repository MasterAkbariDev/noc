#!/usr/bin/env bash
set -euo pipefail
umask 077

if (($# < 2)); then
    echo "usage: issue-server.sh <name> <ip-or-dns>..." >&2
    exit 2
fi

name="$1"
shift

if [[ ! "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "invalid certificate name: $name" >&2
    exit 2
fi

out="${PKI_OUT:-deploy/pki/out}"

for file in intermediate.pem intermediate-key.pem root.pem; do
    if [[ ! -f "$out/$file" ]]; then
        echo "missing $out/$file; run deploy/pki/init-ca.sh first" >&2
        exit 1
    fi
done

for file in "$name.pem" "$name-key.pem"; do
    if [[ -e "$out/$file" ]]; then
        echo "refusing to overwrite $out/$file; move the old pair away first" >&2
        exit 1
    fi
done

san=""
for entry in "$@"; do
    if [[ "$entry" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$entry" =~ ^[0-9A-Fa-f:]*:[0-9A-Fa-f:]*$ ]]; then
        kind="IP"
    elif [[ "$entry" =~ ^[A-Za-z0-9*][A-Za-z0-9.-]*$ ]]; then
        kind="DNS"
    else
        echo "invalid subject alternative name: $entry" >&2
        exit 2
    fi
    san="${san:+$san,}$kind:$entry"
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

printf '%s\n' \
    'basicConstraints = critical,CA:FALSE' \
    'keyUsage = critical,digitalSignature,keyEncipherment' \
    'extendedKeyUsage = serverAuth' \
    "subjectAltName = $san" \
    'subjectKeyIdentifier = hash' \
    'authorityKeyIdentifier = keyid' >"$work/server.cnf"

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$work/$name-key.pem"
openssl req -new -key "$work/$name-key.pem" -subj "/CN=$name" -out "$work/$name.csr"
openssl x509 -req -in "$work/$name.csr" -CA "$out/intermediate.pem" -CAkey "$out/intermediate-key.pem" \
    -sha256 -days 90 -set_serial "0x$(openssl rand -hex 16)" \
    -extfile "$work/server.cnf" -out "$work/$name.pem"

cat "$out/intermediate.pem" "$out/root.pem" >"$work/ca.pem"

mv "$work/$name-key.pem" "$out/$name-key.pem"
mv "$work/$name.pem" "$out/$name.pem"
mv "$work/ca.pem" "$out/ca.pem"
chmod 600 "$out/$name-key.pem"
