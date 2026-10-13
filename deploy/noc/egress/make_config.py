import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_DOMAINS = (
    "domain:generativelanguage.googleapis.com",
    "domain:api.groq.com",
)
PANEL_CONFIG = Path("/usr/local/x-ui/bin/config.json")
PROBE_URL = "https://www.gstatic.com/generate_204"
INBOUND_TAG = "noc-http"
BALANCER_TAG = "llm-egress"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the NOC LLM egress config")
    parser.add_argument("--panel-config", type=Path, default=PANEL_CONFIG)
    parser.add_argument("--prefix", default="sub1-")
    parser.add_argument("--port", type=int, default=10950)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def selected_outbounds(panel: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    outbounds = [
        outbound
        for outbound in panel.get("outbounds", [])
        if str(outbound.get("tag", "")).startswith(prefix)
    ]
    if not outbounds:
        raise SystemExit(f"no outbound tag starts with {prefix!r} in the panel config")
    return outbounds


def egress_config(outbounds: list[dict[str, Any]], prefix: str, port: int) -> dict[str, Any]:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": INBOUND_TAG,
                "listen": "127.0.0.1",
                "port": port,
                "protocol": "http",
                "settings": {},
            }
        ],
        "outbounds": [*outbounds, {"tag": "blocked", "protocol": "blackhole"}],
        "observatory": {
            "subjectSelector": [prefix],
            "probeUrl": PROBE_URL,
            "probeInterval": "1m",
            "enableConcurrency": False,
        },
        "routing": {
            "domainStrategy": "AsIs",
            "balancers": [
                {"tag": BALANCER_TAG, "selector": [prefix], "strategy": {"type": "leastPing"}}
            ],
            "rules": [
                {
                    "type": "field",
                    "inboundTag": [INBOUND_TAG],
                    "domain": list(ALLOWED_DOMAINS),
                    "balancerTag": BALANCER_TAG,
                },
                {"type": "field", "inboundTag": [INBOUND_TAG], "outboundTag": "blocked"},
            ],
        },
    }


def main() -> None:
    arguments = parse_arguments()
    panel = json.loads(arguments.panel_config.read_text())
    outbounds = selected_outbounds(panel, arguments.prefix)
    config = egress_config(outbounds, arguments.prefix, arguments.port)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(config, indent=2))
    arguments.out.chmod(0o640)
    print(f"wrote {arguments.out} with {len(outbounds)} outbound(s)")


if __name__ == "__main__":
    main()
