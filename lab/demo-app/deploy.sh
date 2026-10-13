#!/usr/bin/env bash
set -euo pipefail

readonly APP_DIR=/opt/demo-app
readonly ENV_DIR=/etc/demo-app
readonly UNIT_DIR=/etc/systemd/system
readonly UNITS=(demo-shop.service demo-reports.service)
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SOURCE_DIR

if [[ "$(id -u)" -ne 0 ]]; then
    echo "deploy.sh must run as root" >&2
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "python3 3.12 or newer is required" >&2
    exit 1
fi

if ! id demo >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin demo
fi

install -d -m 0755 -o root -g root "$APP_DIR"
install -d -m 0750 -o root -g demo "$ENV_DIR"
if [[ ! -e "$ENV_DIR/env" ]]; then
    install -m 0640 -o root -g demo /dev/null "$ENV_DIR/env"
fi

if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --quiet --no-cache-dir --requirement "$SOURCE_DIR/requirements.txt"

rm -rf "$APP_DIR/demo_app"
cp -R "$SOURCE_DIR/demo_app" "$APP_DIR/demo_app"
find "$APP_DIR/demo_app" -name __pycache__ -type d -prune -exec rm -rf {} +
chown -R root:root "$APP_DIR/demo_app"

for unit in "${UNITS[@]}"; do
    install -m 0644 -o root -g root "$SOURCE_DIR/deploy/$unit" "$UNIT_DIR/$unit"
done
systemctl daemon-reload
systemctl enable "${UNITS[@]}"
systemctl restart "${UNITS[@]}"

sleep 2
for unit in "${UNITS[@]}"; do
    if ! systemctl is-active --quiet "$unit"; then
        echo "$unit did not start; see journalctl -u $unit" >&2
        exit 1
    fi
done
echo "demo-app deployed to $APP_DIR"
