#!/usr/bin/env bash
set -euo pipefail
umask 077

out="${PKI_OUT:-deploy/pki/out}"
mkdir -p "$out"
chmod 700 "$out"

for file in root-key.pem root.pem intermediate-key.pem intermediate.pem ca.pem; do
    if [[ -e "$out/$file" ]]; then
        echo "refusing to overwrite $out/$file; move the PKI directory away first" >&2
        exit 1
    fi
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

printf '%s\n' \
    'basicConstraints = critical,CA:TRUE' \
    'keyUsage = critical,keyCertSign,cRLSign' \
    'subjectKeyIdentifier = hash' >"$work/root.cnf"

printf '%s\n' \
    'basicConstraints = critical,CA:TRUE,pathlen:0' \
    'keyUsage = critical,keyCertSign,cRLSign' \
    'subjectKeyIdentifier = hash' \
    'authorityKeyIdentifier = keyid' >"$work/intermediate.cnf"

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$work/root-key.pem"
openssl req -new -key "$work/root-key.pem" -subj "/CN=NOC Root CA" -out "$work/root.csr"
openssl x509 -req -in "$work/root.csr" -signkey "$work/root-key.pem" -sha256 -days 3650 \
    -set_serial "0x$(openssl rand -hex 16)" -extfile "$work/root.cnf" -out "$work/root.pem"

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$work/intermediate-key.pem"
openssl req -new -key "$work/intermediate-key.pem" -subj "/CN=NOC Intermediate CA" \
    -out "$work/intermediate.csr"
openssl x509 -req -in "$work/intermediate.csr" -CA "$work/root.pem" -CAkey "$work/root-key.pem" \
    -sha256 -days 1825 -set_serial "0x$(openssl rand -hex 16)" \
    -extfile "$work/intermediate.cnf" -out "$work/intermediate.pem"

cat "$work/intermediate.pem" "$work/root.pem" >"$work/ca.pem"

for file in root-key.pem root.pem intermediate-key.pem intermediate.pem ca.pem; do
    mv "$work/$file" "$out/$file"
done
chmod 600 "$out/root-key.pem" "$out/intermediate-key.pem"
