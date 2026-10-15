# PKI scripts

Creates the certificates that protect the NOC-to-sentinel and Prometheus-to-target links. OpenSSL only, no other tools.

| Script | What it does |
|---|---|
| `init-ca.sh` | Creates a root CA (EC P-256, 10 years) and an intermediate CA (EC P-256, 5 years) signed by the root. Refuses to run if any key or certificate already exists in the output directory. |
| `issue-server.sh <name> <ip-or-dns>...` | Server certificate for one target, 90 days, `extendedKeyUsage=serverAuth`. Every argument becomes a SAN (IPv4/IPv6 literals become `IP:`, other names become `DNS:`). Needs at least one SAN. |
| `issue-client.sh <name>` | Client certificate, 90 days, `extendedKeyUsage=clientAuth`. Used for `noc-worker` (NOC to sentinel) and `noc-prometheus` (Prometheus to exporters). |

Output directory: `${PKI_OUT:-deploy/pki/out}` (git-ignored, mode 700). Each issued name produces:

- `<name>.pem`: the certificate
- `<name>-key.pem`: the private key, mode 600
- `ca.pem`: intermediate followed by root, the chain to pass as the trust anchor

The root key is `root-key.pem`, and the intermediate key is `intermediate-key.pem`. Both are mode 600.

## First-time setup

```bash
make pki-test                                  # optional: run the self-test
deploy/pki/init-ca.sh
deploy/pki/issue-server.sh demo-1 10.0.0.5 demo-1.lab.example
deploy/pki/issue-client.sh noc-worker
deploy/pki/issue-client.sh noc-prometheus
```

After issuing, move `root-key.pem` off the NOC host (USB stick or password manager). Only the intermediate is needed to issue new certificates. Losing the root key means creating a new CA and re-issuing everything. Leaking it means anyone can mint certificates the targets trust.

Where the files go:

- Target (`demo-1`): `<name>.pem` to `/etc/noc-sentinel/tls/server.pem`, `<name>-key.pem` to `/etc/noc-sentinel/tls/server-key.pem`, `ca.pem` to `/etc/noc-sentinel/tls/ca.pem`.
- NOC worker: `noc-worker.pem`, `noc-worker-key.pem` and `ca.pem`, as set in the sentinel key/cert configuration.
- Prometheus: `noc-prometheus.pem`, `noc-prometheus-key.pem` and `ca.pem` to `/etc/prometheus/pki/` (see `deploy/noc/prometheus/prometheus.yml`).

## Rotation

Certificates expire after 90 days. Renew them at least 21 days before expiry. `noc doctor` warns when the sentinel certificate gets close.

Run this on the machine that holds the intermediate key, never on the NOC host:

```bash
deploy/pki/renew.sh staging-104 127.0.0.1 localhost
```

It re-issues the server certificate (with the SANs you give, the same as when it was first issued), `noc-worker` and `noc-prometheus`, but only those that expire within `RENEW_DAYS` (default 21). `FORCE=1` renews all three. Old pairs are moved to `deploy/pki/out/retired/<time>/`, never deleted. Nothing to renew prints `nothing to renew` and changes nothing, so it is safe to run every week.

For the single-host layout (NOC, Prometheus and the sentinel on one server, as on staging), install the result with:

```bash
deploy/pki/install-single-host.sh staging-104 -- -i ~/.ssh/key root@203.0.113.7
```

Everything after `--` is passed to `ssh`. The script copies the files into a private temporary folder on the server, backs up `/etc/noc-sentinel/tls` and `/opt/noc/pki` to `/root/noc-pki-backup-<time>`, installs each file with the owner and mode its reader needs (the sentinel key readable by the `noc-sentinel` group, the worker key owned by uid 10001, the Prometheus key owned by `nobody`), restarts the sentinel, the NOC and Prometheus, and ends with `noc doctor`, which must show the sentinel answering a signed request.

To renew by hand instead: check the date with `openssl x509 -in deploy/pki/out/demo-1.pem -noout -enddate`, move the old pair to `retired/` (the issue scripts refuse to overwrite), re-issue with the same arguments, copy the files and restart the service that reads them.

## Checks

- `openssl verify -CAfile deploy/pki/out/ca.pem deploy/pki/out/demo-1.pem` prints `OK`.
- `openssl x509 -in deploy/pki/out/demo-1.pem -noout -ext extendedKeyUsage,subjectAltName` shows the EKU and SANs.
- `make pki-test` runs the same checks against a temporary directory. It runs in CI on every push, together with `shellcheck` over `deploy/pki/*.sh` and `tests/pki/*.sh`.
