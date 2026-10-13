import argparse
import ipaddress
import ssl
import sys
from pathlib import Path

import uvicorn

from noc_sentinel.app import create_app
from noc_sentinel.config import load_config
from noc_sentinel.nonce_store import NonceStore
from noc_sentinel.tools.host import PsutilHostReader
from noc_sentinel.tools.journal import SubprocessJournal
from noc_sentinel.tools.systemd import SubprocessSystemctl


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="noc-sentinel")
    parser.add_argument("--config", type=Path, default=Path("/etc/noc-sentinel/config.yaml"))
    parser.add_argument("--insecure-loopback", action="store_true")
    return parser.parse_args(argv)


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def main(argv: list[str] | None = None) -> None:
    arguments = parse_arguments(argv if argv is not None else sys.argv[1:])
    config = load_config(arguments.config)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    nonce_store = NonceStore(config.state_dir / "nonces.sqlite3", config.nonce_ttl_seconds)
    app = create_app(
        config,
        SubprocessSystemctl(),
        nonce_store,
        config.load_secrets(),
        host=PsutilHostReader(),
        journal=SubprocessJournal(),
    )

    if config.tls is None:
        if not (arguments.insecure_loopback and is_loopback(config.listen.host)):
            raise SystemExit("TLS is required unless --insecure-loopback is used on 127.0.0.1")
        uvicorn.run(app, host=config.listen.host, port=config.listen.port)
        return

    uvicorn.run(
        app,
        host=config.listen.host,
        port=config.listen.port,
        ssl_certfile=str(config.tls.cert_file),
        ssl_keyfile=str(config.tls.key_file),
        ssl_ca_certs=str(config.tls.client_ca_file),
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        workers=1,
    )


if __name__ == "__main__":
    main()
