import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select

from noc.db.models import Target
from noc.db.session import SessionFactory

NODE_EXPORTER_PORT = 9100
SD_FILE_MODE = 0o644


def target_groups(targets: list[Target]) -> dict[str, list[dict[str, object]]]:
    node: list[dict[str, object]] = []
    sentinel: list[dict[str, object]] = []
    for target in sorted(targets, key=lambda t: t.name):
        labels = {"target": target.name, "env": target.environment}
        node.append({"targets": [f"{target.address}:{NODE_EXPORTER_PORT}"], "labels": labels})
        # A target without a sentinel is only watched through its node_exporter.
        if target.sentinel_url:
            sentinel.append({"targets": [urlsplit(target.sentinel_url).netloc], "labels": labels})
    return {"node.json": node, "sentinel.json": sentinel}


def file_sd_documents(targets: list[Target]) -> dict[str, str]:
    return {
        filename: json.dumps(groups, indent=2) + "\n"
        for filename, groups in target_groups(targets).items()
    }


def stale_documents(desired: dict[str, str], current: dict[str, str | None]) -> dict[str, str]:
    return {name: content for name, content in desired.items() if current.get(name) != content}


def read_document(path: Path) -> str | None:
    try:
        return path.read_text()
    except FileNotFoundError:
        return None


def write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(descriptor, "w") as handle:
        handle.write(content)
    Path(temporary).chmod(SD_FILE_MODE)
    Path(temporary).replace(path)


def render_file_sd(targets: list[Target], directory: Path) -> list[Path]:
    desired = file_sd_documents(targets)
    current = {name: read_document(directory / name) for name in desired}
    changed = stale_documents(desired, current)
    for name, content in changed.items():
        write_atomically(directory / name, content)
    return [directory / name for name in changed]


async def refresh_file_sd(sessions: SessionFactory, directory: Path) -> list[Path]:
    async with sessions() as session:
        targets = list(await session.scalars(select(Target)))
    return render_file_sd(targets, directory)
