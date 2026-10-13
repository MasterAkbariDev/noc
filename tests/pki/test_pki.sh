#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
pki="$repo/deploy/pki"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

out="$work/out"
export PKI_OUT="$out"
failures=0

check() {
    local description="$1"
    shift
    if "$@"; then
        echo "ok    $description"
    else
        echo "FAIL  $description" >&2
        failures=$((failures + 1))
    fi
}

check_fails() {
    local description="$1"
    shift
    if "$@"; then
        echo "FAIL  $description (command succeeded)" >&2
        failures=$((failures + 1))
    else
        echo "ok    $description"
    fi
}

quietly() {
    "$@" >/dev/null 2>&1
}

contains() {
    [[ "$1" == *"$2"* ]]
}

lacks() {
    ! contains "$1" "$2"
}

certificate_count_is() {
    [[ "$(grep -c "BEGIN CERTIFICATE" "$1")" == "$2" ]]
}

cert_extension() {
    openssl x509 -in "$1" -noout -ext "$2"
}

file_mode() {
    stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"
}

mode_is_600() {
    [[ "$(file_mode "$1")" == "600" ]]
}

verifies() {
    openssl verify -CAfile "$out/ca.pem" "$1" >/dev/null
}

same_bytes() {
    cmp -s "$1" "$2"
}

check "init-ca creates root and intermediate" quietly "$pki/init-ca.sh"
cp "$out/root-key.pem" "$work/root-key.before"
check_fails "init-ca refuses to overwrite an existing CA" quietly "$pki/init-ca.sh"
check "init-ca left the existing root key untouched" same_bytes "$out/root-key.pem" "$work/root-key.before"
check "root CA is a CA certificate" contains "$(cert_extension "$out/root.pem" basicConstraints)" "CA:TRUE"
check "intermediate verifies against root" quietly openssl verify -CAfile "$out/root.pem" "$out/intermediate.pem"
check "root key is mode 600" mode_is_600 "$out/root-key.pem"
check "intermediate key is mode 600" mode_is_600 "$out/intermediate-key.pem"

check "issue-server creates demo-1 with SANs" quietly "$pki/issue-server.sh" demo-1 10.0.0.5 demo-1.lab.example
check "server certificate verifies against ca.pem" verifies "$out/demo-1.pem"
check "server certificate has serverAuth EKU" contains "$(cert_extension "$out/demo-1.pem" extendedKeyUsage)" "TLS Web Server Authentication"
check "server certificate has no clientAuth EKU" lacks "$(cert_extension "$out/demo-1.pem" extendedKeyUsage)" "TLS Web Client Authentication"
check "server certificate has IP SAN" contains "$(cert_extension "$out/demo-1.pem" subjectAltName)" "IP Address:10.0.0.5"
check "server certificate has DNS SAN" contains "$(cert_extension "$out/demo-1.pem" subjectAltName)" "DNS:demo-1.lab.example"
check "server certificate expires in more than 89 days" quietly openssl x509 -in "$out/demo-1.pem" -noout -checkend $((89 * 86400))
check "server key is mode 600" mode_is_600 "$out/demo-1-key.pem"
cp "$out/demo-1.pem" "$work/demo-1.before"
check_fails "issue-server refuses to overwrite demo-1" quietly "$pki/issue-server.sh" demo-1 10.0.0.5
check "issue-server left demo-1 certificate untouched" same_bytes "$out/demo-1.pem" "$work/demo-1.before"
check_fails "issue-server rejects a missing SAN" quietly "$pki/issue-server.sh" demo-2
check_fails "issue-server rejects an injected SAN" quietly "$pki/issue-server.sh" demo-3 'x,IP:1.2.3.4'

check "issue-client creates noc-worker" quietly "$pki/issue-client.sh" noc-worker
check "client certificate verifies against ca.pem" verifies "$out/noc-worker.pem"
check "client certificate has clientAuth EKU" contains "$(cert_extension "$out/noc-worker.pem" extendedKeyUsage)" "TLS Web Client Authentication"
check "client certificate has no serverAuth EKU" lacks "$(cert_extension "$out/noc-worker.pem" extendedKeyUsage)" "TLS Web Server Authentication"
check "client certificate expires in more than 89 days" quietly openssl x509 -in "$out/noc-worker.pem" -noout -checkend $((89 * 86400))
check "client key is mode 600" mode_is_600 "$out/noc-worker-key.pem"
check_fails "issue-client refuses to overwrite noc-worker" quietly "$pki/issue-client.sh" noc-worker
check_fails "issue-client rejects a path-like name" quietly "$pki/issue-client.sh" '../evil'

check "ca.pem contains intermediate and root" certificate_count_is "$out/ca.pem" 2

other="$work/other"
PKI_OUT="$other" quietly "$pki/init-ca.sh"
PKI_OUT="$other" quietly "$pki/issue-client.sh" intruder
check_fails "certificate from another CA does not verify" quietly openssl verify -CAfile "$out/ca.pem" "$other/intruder.pem"

if ((failures > 0)); then
    echo "$failures PKI check(s) failed" >&2
    exit 1
fi
echo "all PKI checks passed"
