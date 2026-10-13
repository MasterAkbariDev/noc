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

Certificates expire after 90 days. Re-issue 21 days before expiry at the latest.

1. Check the expiry date:

   ```bash
   openssl x509 -in deploy/pki/out/demo-1.pem -noout -enddate
   openssl x509 -in deploy/pki/out/demo-1.pem -noout -checkend $((21 * 86400)) \
     || echo "renew now: less than 21 days left"
   ```

2. Move the old pair out of the way (the scripts refuse to overwrite it):

   ```bash
   mkdir -p deploy/pki/out/retired
   mv deploy/pki/out/demo-1.pem deploy/pki/out/demo-1-key.pem deploy/pki/out/retired/
   ```

3. Re-issue with the same arguments as before. This generates a new key and a new certificate:

   ```bash
   deploy/pki/issue-server.sh demo-1 10.0.0.5 demo-1.lab.example
   ```

4. Copy the new files to the target or client, then restart the service that reads them (`sudo systemctl restart noc-sentinel`, or `docker compose restart prometheus`). Keep the old files in `retired/` until the new certificate is confirmed working.

Renew certificates at least 21 days before they expire. The check above is the manual form. Automated alerting is a separate task.

## Checks

- `openssl verify -CAfile deploy/pki/out/ca.pem deploy/pki/out/demo-1.pem` prints `OK`.
- `openssl x509 -in deploy/pki/out/demo-1.pem -noout -ext extendedKeyUsage,subjectAltName` shows the EKU and SANs.
- `make pki-test` runs the same checks against a temporary directory. It runs in CI on every push, together with `shellcheck` over `deploy/pki/*.sh` and `tests/pki/*.sh`.
