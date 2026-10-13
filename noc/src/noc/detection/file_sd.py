import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from noc.db.models import Target

NODE_EXPORTER_PORT = 9100


def target_groups(targets: list[Target]) -> dict[str, list[dict[str, object]]]:
    node: list[dict[str, object]] = []
    sentinel: list[dict[str, object]] = []
    for target in sorted(targets, key=lambda t: t.name):
        labels = {"target": target.name, "env": target.environment}
        node.append({"targets": [f"{target.address}:{NODE_EXPORTER_PORT}"], "labels": labels})
        sentinel.append({"targets": [urlsplit(target.sentinel_url).netloc], "labels": labels})
    return {"node.json": node, "sentinel.json": sentinel}


def write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(descriptor, "w") as handle:
        handle.write(content)
    Path(temporary).replace(path)


def render_file_sd(targets: list[Target], directory: Path) -> list[Path]:
    written = []
    for filename, groups in target_groups(targets).items():
        path = directory / filename
        write_atomically(path, json.dumps(groups, indent=2) + "\n")
        written.append(path)
    return written
