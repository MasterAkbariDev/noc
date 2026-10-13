# Target installer

`install.sh` puts node_exporter (and, with `--with-sentinel`, noc-sentinel) on an Ubuntu 24.04 target. The targets run live services (VPN, nginx, Docker, bots), so the installer is written to never disturb them.

## What it changes

- node_exporter 1.9.1 from the GitHub release, checked against that release's `sha256sums.txt`, into `/usr/local/bin/node_exporter`. Runs as user `node_exporter`, TLS with client certificates required, collectors trimmed, `MemoryMax=64M`. Config in `/etc/node_exporter/`, unit `node_exporter.service`.
- With `--with-sentinel`: user `noc-sentinel`, a venv in `/opt/noc-sentinel` built from the two wheels, config `/etc/noc-sentinel/config.yaml` (root:noc-sentinel, 0640), TLS files and the HMAC key in `/etc/noc-sentinel/`, unit `noc-sentinel.service` (the unit in `sentinel/noc-sentinel.service`). The venv may get `python3-venv` from apt, and nothing else from apt.
- With `--with-sentinel` and at least one registered unit that allows `start_service` or `restart_service`: the polkit rule `/etc/polkit-1/rules.d/50-noc-sentinel.rules` (root:root, 0644). It lets user `noc-sentinel` start or restart exactly those units. When no registered unit allows it, the file is removed. See "Polkit rule" below.
- ufw rules only when ufw is already active: `allow from <noc-ip>` to the two ports, tagged `noc-node-exporter` and `noc-sentinel`.
- It never runs `ufw enable`, never changes ufw default policies, never edits sshd, never restarts nginx, Docker or any other service, and never runs `apt upgrade`.

Nothing is registered as a managed resource by default. The sentinel config has `resources: []` until you pass `--register-unit`.

## Before you start

1. Issue the certificates with `deploy/pki` (see `deploy/pki/README.md`): `issue-server.sh <name> <ip-or-dns>...` for the target, and `issue-client.sh noc-prometheus` for Prometheus. The installer reads `<cert-name>.pem`, `<cert-name>-key.pem` and `ca.pem` from `--pki-dir`.
2. Pick ports that are free. Port 9443 is used by another service on these hosts, so the defaults are 9100 (node_exporter) and 9444 (sentinel). Choose different ones with `--node-port` and `--sentinel-port` if needed. The installer checks with `ss -ltn` and stops if a port belongs to another process.
3. For the sentinel, have the HMAC key file the NOC worker uses (`--key-file`).
4. Build the wheels on your machine:

   ```bash
   make sentinel-wheels
   ```

   That runs `uv build --package noc-shared --out-dir dist` and `uv build --package noc-sentinel --out-dir dist`. Copy `dist/` to the target with only the two current wheels in it, because the installer needs exactly one `noc_shared-*.whl` and one `noc_sentinel-*.whl`. The wheel dependencies (FastAPI, psutil and the rest) are installed from PyPI, so the target needs outbound HTTPS.

5. Copy the whole `deploy/target/` folder to the target, because the installer reads its unit files and `web-config.yml` from next to itself.

## Dry run first

Always look at the plan before the real run. A dry run changes nothing on the host. On a machine that is not Linux or not root, it prints the same plan and lists what a real run would refuse.

```bash
deploy/target/install.sh --dry-run --noc-ip 203.0.113.10 --pki-dir ./pki \
  --cert-name vps-web-1 --target-name vps-web-1 --with-sentinel \
  --key-file ./noc-worker.key --wheel-dir ./wheels \
  --register-unit svc:demo-shop=demo-shop.service
```

## Real run

```bash
sudo deploy/target/install.sh --noc-ip 203.0.113.10 --pki-dir ./pki \
  --cert-name vps-web-1 --target-name vps-web-1
```

Add `--with-sentinel --key-file ... --wheel-dir ...` for the sentinel. Options:

| Option | Default | Meaning |
|---|---|---|
| `--noc-ip <ip>` | required | NOC address allowed by ufw rules |
| `--pki-dir <dir>` | required | Directory with the PKI output files |
| `--cert-name <name>` | `--target-name` | PKI name of this target's certificate |
| `--target-name <name>` | `hostname -s` | Target name in the sentinel config |
| `--node-port <port>` | 9100 | node_exporter port |
| `--with-sentinel` | off | Also install noc-sentinel |
| `--sentinel-port <port>` | 9444 | Sentinel port |
| `--key-file <file>` | with sentinel | HMAC key for the NOC worker |
| `--key-id <id>` | `noc-worker` | Key id the worker sends in `X-NOC-Key-Id` |
| `--wheel-dir <dir>` | with sentinel | Folder with the two wheels |
| `--environment <lab\|prod>` | `prod` | Sentinel environment |
| `--register-unit <id>=<unit>` | none | Register a unit as a resource, repeatable. The id must match `^[a-z][a-z0-9_-]{0,30}:[A-Za-z0-9@._-]{1,128}$`, for example `svc:demo-shop=demo-shop.service` |
| `--dry-run` | off | Print every action and change nothing |
| `--uninstall` | off | Remove what this installer installed (see below) |

Every command the installer runs is printed as `run: ...` (or `[dry-run] ...`). A file that already matches prints `unchanged:` and is not rewritten. A service is restarted only when one of its files changed.

## Manual verification checklist

Run these on the target after the real run. Replace the names with yours.

- [ ] Run the same install command a second time. Every file reports `unchanged:`, and the output has no `Successfully installed` (pip), no `systemctl restart` and no `apt-get` line. The only `run:` lines left are no-ops such as `install -d` and `systemctl enable`.
- [ ] No client certificate is refused. This must fail with a TLS error:

  ```bash
  curl --cacert /etc/node_exporter/tls/ca.pem https://127.0.0.1:9100/metrics
  ```

- [ ] With the Prometheus client certificate, metrics are returned. Copy `noc-prometheus.pem` and `noc-prometheus-key.pem` to a temporary folder for this test and delete them afterwards:

  ```bash
  curl --cacert ca.pem --cert noc-prometheus.pem --key noc-prometheus-key.pem \
    https://127.0.0.1:9100/metrics | head
  ```

- [ ] `systemctl status node_exporter` shows `active (running)`, and `systemctl show -p MemoryMax node_exporter` shows `64M`.
- [ ] With `--with-sentinel`: `systemctl status noc-sentinel` shows `active (running)`. Then `curl --cacert ca.pem --cert noc-prometheus.pem --key ... https://127.0.0.1:9444/healthz` returns a response. Use the worker's client certificate instead of the Prometheus one if the sentinel accepts only the worker.
- [ ] `ss -ltnp` shows node_exporter on `:9100` and, if installed, noc-sentinel on `:9444`. Nothing else changed.
- [ ] `sudo ufw status` (only if ufw is active) lists the two `ALLOW` rules from the NOC IP with comments `noc-node-exporter` and `noc-sentinel`. Nothing else was added.
- [ ] Other services still run: check `systemctl --failed` and your existing services.

## Polkit rule

The sentinel restarts registered units through systemd, which asks polkit for `org.freedesktop.systemd1.manage-units`. The installer writes `/etc/polkit-1/rules.d/50-noc-sentinel.rules` so that this permission is granted only when all three hold:

- the subject is user `noc-sentinel`,
- the verb is `start` or `restart`,
- the unit is one of the registered units whose resource allows `start_service` or `restart_service`.

Every other request gets `polkit.Result.NOT_HANDLED`, so polkit falls through to its default rules, which do not grant it to the service user. The unit list is read from the generated sentinel config with the sentinel venv's Python and `yaml.safe_load`. The config is never evaluated as shell. Every unit name is checked against `^[A-Za-z0-9@._-]{1,128}\.service$` before the file is written, and the installer refuses to write the file if one fails. The file is rewritten only when its content changes, and polkit picks up the change without a restart.

Manual check on the target, after a real run with at least one `--register-unit`. Replace `demo-shop.service` with a registered unit you can restart:

- [ ] The registered unit can be restarted by the sentinel user. This must succeed:

  ```bash
  sudo -u noc-sentinel systemctl restart demo-shop.service
  ```

- [ ] A unit that is not registered is refused. Use a name that does not exist, so nothing can be disturbed if the rule is wrong. It must fail with an authorization error (typically `Access denied`), not with `Unit ... not found`, which would mean the rule let the request through:

  ```bash
  sudo -u noc-sentinel systemctl restart not-registered-check.service
  ```

- [ ] The file is `root:root` with mode `0644`: `stat -c '%U:%G %a' /etc/polkit-1/rules.d/50-noc-sentinel.rules`.

## Firewall

The installer adds rules only when ufw is active. If ufw is inactive or missing, it prints a warning and adds nothing. In that case the ports are reachable from anywhere unless your provider firewall restricts them. Restrict TCP 9100 and 9444 to the NOC IP in the provider's firewall.

## Uninstall

```bash
sudo deploy/target/install.sh --uninstall --noc-ip 203.0.113.10
```

Pass the same `--node-port` and `--sentinel-port` if you changed them from the defaults. Uninstall stops and disables our two units, removes them, removes the polkit rule, removes `/usr/local/bin/node_exporter`, `/etc/node_exporter`, `/etc/noc-sentinel` and `/opt/noc-sentinel`, removes the two users, and deletes the ufw rules for this NOC IP and these ports. It keeps `/var/lib/noc-sentinel` (the action store and nonce database) and the `python3-venv` package. Delete the state folder by hand when you no longer need it. Dry-run works for uninstall too.

## Known gaps

- The installer does not run `apt-get update`. If `python3-venv` is missing and apt has no index, run `sudo apt-get update` first.
- The sha256 file comes from the same GitHub release as the tarball, so it proves the download matches that release and not that the release is genuine. Pin the hash in the script if you need stronger assurance.

## Single-host (staging) install

When the NOC runs on the same machine, bind both services to loopback so no new port is exposed:

```bash
sudo ./install.sh --dry-run --noc-ip 127.0.0.1 --listen-address 127.0.0.1 --pki-dir /root/noc-pki --with-sentinel --key-file /root/noc-keys/noc-worker.key --wheel-dir /root/noc-dist
```

Issue the target's server certificate with `127.0.0.1` in its SANs (`deploy/pki/issue-server.sh <name> 127.0.0.1`).
